from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from tools.common import NewsletterError, load_dotenv, require_env, validate_email
from tools.dry_run_fixture import fixture_research
from tools.gmail_draft import create_draft, send_draft
from tools.local_infographic import generate_infographic
from tools.render_email import build_message, render_html, render_text
from tools.research import NewsletterResearch, research_newsletter


ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger("newsletter")


@dataclass
class RunContext:
    """Own the output folder, manifest and safe progress logging for one run."""

    run_id: str
    output_dir: Path
    manifest: dict[str, Any]
    started: float

    @classmethod
    def create(cls, *, topic: str, recipient: str, dry_run: bool) -> "RunContext":
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        output_dir = ROOT / ".tmp" / run_id
        output_dir.mkdir(parents=True, exist_ok=False)
        manifest = {
            "run_id": run_id,
            "created_at": datetime.now(UTC).isoformat(),
            "topic": topic,
            "recipient": recipient,
            "dry_run": dry_run,
            "status": "running",
            "steps": [],
        }
        return cls(run_id, output_dir, manifest, time.monotonic())

    def step(self, name: str, **details: Any) -> None:
        self.manifest["steps"].append(
            {"name": name, "at": datetime.now(UTC).isoformat(), **details}
        )
        suffix = " " + " ".join(f"{key}={value}" for key, value in details.items()) if details else ""
        LOGGER.info("run=%s step=%s%s", self.run_id, name, suffix)

    def complete(self, *, draft_id: str | None, message_id: str | None) -> None:
        self.manifest.update(
            status="complete",
            draft_id=draft_id,
            message_id=message_id,
            duration_seconds=round(time.monotonic() - self.started, 3),
        )

    def fail(self, exc: Exception) -> None:
        safe_message = str(exc)[:500]
        self.manifest.update(
            status="failed",
            error_type=type(exc).__name__,
            error=safe_message,
            duration_seconds=round(time.monotonic() - self.started, 3),
        )
        LOGGER.error(
            "run=%s failed type=%s message=%s",
            self.run_id,
            type(exc).__name__,
            safe_message[:200],
        )

    def write_manifest(self) -> None:
        _write_json(self.output_dir / "run-manifest.json", self.manifest)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Opret et kildebaseret HTML-nyhedsbrev som Gmail-kladde")
    parser.add_argument("--topic", required=True, help="Nyhedsbrevets emne")
    parser.add_argument("--angle", default="", help="Valgfri redaktionel vinkel")
    parser.add_argument("--audience", default="bred professionel målgruppe", help="Målgruppe")
    parser.add_argument("--tone", default="neutral og professionel", help="Tone")
    parser.add_argument("--recipient", help="Én testmodtager; ellers NEWSLETTER_RECIPIENT")
    parser.add_argument("--dry-run", action="store_true", help="Brug fixtures uden netværk, credits eller Gmail-ændringer")
    parser.add_argument("--send", action="store_true", help="Send den oprettede Gmail-kladde; kræver udtrykkelig godkendelse")
    return parser.parse_args(argv)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_recipient(args: argparse.Namespace) -> str:
    configured = args.recipient or os.getenv("NEWSLETTER_RECIPIENT", "")
    if args.dry_run and not configured.strip():
        configured = "dry-run@example.com"
    return validate_email(configured)


def _create_research(args: argparse.Namespace, context: RunContext) -> NewsletterResearch:
    if args.dry_run:
        research = fixture_research(args.topic)
        context.step("research_fixture")
        return research

    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    research = research_newsletter(
        api_key=require_env("GEMINI_API_KEY"),
        model=model,
        topic=args.topic,
        angle=args.angle,
        audience=args.audience,
        tone=args.tone,
    )
    context.step("research_complete", model=model)
    return research


def _render_artifacts(
    *, context: RunContext, research: NewsletterResearch, recipient: str
) -> EmailMessage:
    _write_json(context.output_dir / "research.json", research.to_dict())

    image_path = context.output_dir / "infographic.png"
    generate_infographic(research, image_path)
    context.step("image_local")

    html_body = render_html(research)
    text_body = render_text(research)
    (context.output_dir / "newsletter.html").write_text(html_body, encoding="utf-8")
    (context.output_dir / "newsletter.txt").write_text(text_body, encoding="utf-8")

    message = build_message(
        recipient=recipient,
        research=research,
        html_body=html_body,
        text_body=text_body,
        image_path=image_path,
    )
    (context.output_dir / "newsletter.eml").write_bytes(message.as_bytes())
    context.step("render_complete")
    return message


def _deliver_message(
    *, message: EmailMessage, dry_run: bool, should_send: bool, context: RunContext
) -> tuple[str | None, str | None]:
    if dry_run:
        context.step("gmail_skipped")
        return None, None

    credentials_path = ROOT / "credentials.json"
    token_path = ROOT / "token.json"
    draft_id = create_draft(message, credentials_path, token_path)
    context.step("gmail_draft_created", draft_id=draft_id)

    if not should_send:
        return draft_id, None

    message_id = send_draft(draft_id, credentials_path, token_path)
    context.step("gmail_draft_sent", message_id=message_id)
    return draft_id, message_id


def run(args: argparse.Namespace) -> dict:
    should_send = bool(getattr(args, "send", False))
    if args.dry_run and should_send:
        raise NewsletterError("--send kan ikke bruges sammen med --dry-run")

    load_dotenv(ROOT / ".env")
    recipient = _resolve_recipient(args)
    context = RunContext.create(topic=args.topic, recipient=recipient, dry_run=args.dry_run)

    try:
        research = _create_research(args, context)
        message = _render_artifacts(context=context, research=research, recipient=recipient)
        draft_id, message_id = _deliver_message(
            message=message,
            dry_run=args.dry_run,
            should_send=should_send,
            context=context,
        )
        context.complete(draft_id=draft_id, message_id=message_id)
        return {
            "run_id": context.run_id,
            "output_dir": str(context.output_dir),
            "draft_id": draft_id,
            "message_id": message_id,
            "dry_run": args.dry_run,
        }
    except Exception as exc:
        context.fail(exc)
        raise
    finally:
        context.write_manifest()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        result = run(parse_args(argv))
    except NewsletterError as exc:
        print(f"Fejl: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Afbrudt.", file=sys.stderr)
        return 130
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
