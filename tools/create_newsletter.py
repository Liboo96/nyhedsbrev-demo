from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from tools.common import NewsletterError, load_dotenv, require_env, validate_email
from tools.dry_run_fixture import fixture_research
from tools.gmail_draft import create_draft, send_draft
from tools.local_infographic import generate_infographic
from tools.render_email import build_message, render_html, render_text
from tools.research import research_newsletter


ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger("newsletter")


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


def run(args: argparse.Namespace) -> dict:
    should_send = bool(getattr(args, "send", False))
    if args.dry_run and should_send:
        raise NewsletterError("--send kan ikke bruges sammen med --dry-run")
    load_dotenv(ROOT / ".env")
    configured_recipient = args.recipient or os.getenv("NEWSLETTER_RECIPIENT", "")
    if args.dry_run and not configured_recipient.strip():
        configured_recipient = "dry-run@example.com"
    recipient = validate_email(configured_recipient)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    output_dir = ROOT / ".tmp" / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    manifest: dict = {"run_id": run_id, "created_at": datetime.now(UTC).isoformat(), "topic": args.topic, "recipient": recipient, "dry_run": args.dry_run, "status": "running", "steps": []}

    def step(name: str, **details) -> None:
        manifest["steps"].append({"name": name, "at": datetime.now(UTC).isoformat(), **details})
        LOGGER.info("run=%s step=%s%s", run_id, name, " " + " ".join(f"{k}={v}" for k, v in details.items()) if details else "")

    try:
        if args.dry_run:
            research = fixture_research(args.topic)
            step("research_fixture")
        else:
            model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
            research = research_newsletter(api_key=require_env("GEMINI_API_KEY"), model=model, topic=args.topic, angle=args.angle, audience=args.audience, tone=args.tone)
            step("research_complete", model=model)
        (output_dir / "research.json").write_text(json.dumps(research.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

        image_path = output_dir / "infographic.png"
        generate_infographic(research, image_path)
        step("image_local")

        html_body, text_body = render_html(research), render_text(research)
        (output_dir / "newsletter.html").write_text(html_body, encoding="utf-8")
        (output_dir / "newsletter.txt").write_text(text_body, encoding="utf-8")
        message = build_message(recipient=recipient, research=research, html_body=html_body, text_body=text_body, image_path=image_path)
        (output_dir / "newsletter.eml").write_bytes(message.as_bytes())
        step("render_complete")

        message_id = None
        if args.dry_run:
            draft_id = None
            step("gmail_skipped")
        else:
            draft_id = create_draft(message, ROOT / "credentials.json", ROOT / "token.json")
            step("gmail_draft_created", draft_id=draft_id)
            if should_send:
                message_id = send_draft(draft_id, ROOT / "credentials.json", ROOT / "token.json")
                step("gmail_draft_sent", message_id=message_id)
        manifest.update(status="complete", draft_id=draft_id, message_id=message_id, duration_seconds=round(time.monotonic() - started, 3))
        return {"run_id": run_id, "output_dir": str(output_dir), "draft_id": draft_id, "message_id": message_id, "dry_run": args.dry_run}
    except Exception as exc:
        manifest.update(status="failed", error_type=type(exc).__name__, error=str(exc)[:500], duration_seconds=round(time.monotonic() - started, 3))
        LOGGER.error("run=%s failed type=%s message=%s", run_id, type(exc).__name__, str(exc)[:200])
        raise
    finally:
        (output_dir / "run-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


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
