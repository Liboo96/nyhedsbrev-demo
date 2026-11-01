from __future__ import annotations

import base64
from email.message import EmailMessage
from pathlib import Path

from tools.common import NewsletterError


GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.compose"


def get_credentials(credentials_path: Path, token_path: Path):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise NewsletterError("Google-afhængigheder mangler. Kør: python -m pip install -r requirements.txt") from exc
    credentials = None
    if token_path.exists():
        credentials = Credentials.from_authorized_user_file(str(token_path), [GMAIL_SCOPE])
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if not credentials or not credentials.valid:
        if not credentials_path.exists():
            raise NewsletterError(f"Google OAuth-filen mangler: {credentials_path}")
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), [GMAIL_SCOPE])
        credentials = flow.run_local_server(port=0)
    token_path.write_text(credentials.to_json(), encoding="utf-8")
    return credentials


def get_gmail_service(credentials_path: Path, token_path: Path):
    credentials = get_credentials(credentials_path, token_path)
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise NewsletterError("Google-afhængigheder mangler. Kør: python -m pip install -r requirements.txt") from exc
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def create_draft(message: EmailMessage, credentials_path: Path, token_path: Path) -> str:
    try:
        from googleapiclient.errors import HttpError
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        result = get_gmail_service(credentials_path, token_path).users().drafts().create(
            userId="me", body={"message": {"raw": raw}}
        ).execute()
    except HttpError as exc:
        status = getattr(exc.resp, "status", "ukendt")
        raise NewsletterError(f"Gmail kunne ikke oprette kladden (HTTP {status})") from exc
    draft_id = result.get("id")
    if not draft_id:
        raise NewsletterError("Gmail returnerede ingen kladde-id")
    return str(draft_id)


def send_draft(draft_id: str, credentials_path: Path, token_path: Path) -> str:
    """Send the stored Gmail draft without reconstructing its MIME message."""
    if not draft_id.strip():
        raise NewsletterError("Gmail-kladde-id mangler")
    try:
        from googleapiclient.errors import HttpError
        result = get_gmail_service(credentials_path, token_path).users().drafts().send(
            userId="me", body={"id": draft_id}
        ).execute()
    except HttpError as exc:
        status = getattr(exc.resp, "status", "ukendt")
        raise NewsletterError(f"Gmail kunne ikke sende kladden (HTTP {status})") from exc
    message_id = result.get("id")
    if not message_id:
        raise NewsletterError("Gmail returnerede ingen mail-id efter afsendelse")
    return str(message_id)
