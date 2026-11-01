from __future__ import annotations

import json
import os
import re
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class NewsletterError(RuntimeError):
    """A safe, user-facing workflow failure."""


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise NewsletterError(f"Manglende konfiguration: {name}")
    return value


def validate_email(value: str) -> str:
    value = value.strip()
    if "," in value or ";" in value or "\n" in value or "\r" in value:
        raise NewsletterError("MVP'en tillader kun én modtager")
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", value):
        raise NewsletterError("Ugyldig modtageradresse")
    return value


@dataclass
class HttpResponse:
    status: int
    body: bytes
    headers: dict[str, str]

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


def http_request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 60,
) -> HttpResponse:
    body = None if json_body is None else json.dumps(json_body).encode("utf-8")
    request = urllib.request.Request(url, data=body, method=method)
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    if json_body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        try:
            import certifi
            ssl_context = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            ssl_context = ssl.create_default_context()
        with urllib.request.urlopen(request, timeout=timeout, context=ssl_context) as response:
            return HttpResponse(response.status, response.read(), dict(response.headers.items()))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise NewsletterError(f"HTTP {exc.code} fra ekstern tjeneste: {detail}") from exc
    except urllib.error.URLError as exc:
        raise NewsletterError(f"Netværksfejl mod ekstern tjeneste: {exc.reason}") from exc
