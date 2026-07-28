#!/usr/bin/env python3
"""
REX Email PDF Watcher
======================
Runs every 10 minutes via launchd.

Scans Gmail for new emails containing PDF attachments.
For each new PDF email found:
  1. Sends Rexxie a Telegram message asking Kato if he wants to extract
  2. Logs unanswered prompts so the 9 PM report can include them

Kato replies "yes" or "no" to Rexxie — the bot handles the actual extraction.

State file: ~/Desktop/REX/logs/pdf_watcher_state.json
  { "seen_ids": [...], "pending_prompts": [{gmail_id, subject, sender, pdf_names, prompted_at}] }

Paperless config: ~/Desktop/REX/rex_paperless_config.json
  { "url": "http://localhost:8000", "token": "your-paperless-api-token" }
"""

import sys
import json
import logging
import time
import urllib.request
import urllib.error
import base64
from datetime import datetime, timedelta
from pathlib import Path

REX_DIR    = Path(__file__).parent
LOG_PATH   = REX_DIR / "logs" / "pdf_watcher.log"
STATE_PATH = REX_DIR / "logs" / "pdf_watcher_state.json"
TG_CONFIG  = REX_DIR / "rex_rexxie_telegram_config.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_PATH), mode="a"),
    ],
)
log = logging.getLogger("rex-pdf-watcher")

REX_API = "http://localhost:8000"

# Maximum look-back if no previous run timestamp found (days)
MAX_LOOKBACK_DAYS = 7


# ── State management ───────────────────────────────────────────────────────────

def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return {"seen_ids": [], "pending_prompts": [], "last_run": None}


def _save_state(state: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


# ── Telegram ────────────────────────────────────────────────────────────────────

def _load_tg() -> tuple:
    if TG_CONFIG.exists():
        try:
            d = json.loads(TG_CONFIG.read_text())
            return d.get("bot_token", ""), d.get("owner_chat_id", 0)
        except Exception:
            pass
    return "", 0


def _send_telegram(token: str, chat_id: int, text: str, parse_mode: str = "HTML") -> bool:
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()).get("ok", False)
    except Exception as e:
        log.error(f"Telegram send failed: {e}")
        return False


# ── Gmail PDF detection ────────────────────────────────────────────────────────

def _gmail_service():
    """Return authenticated Gmail service using REX credentials."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        log.error("google-auth not installed. Run: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client --break-system-packages")
        return None

    TOKEN_PATH = Path.home() / ".rex_google_token.json"
    CREDS_PATH = REX_DIR / "google_credentials.json"

    if not TOKEN_PATH.exists():
        log.warning("Gmail token not found — skipping PDF scan")
        return None

    try:
        creds = Credentials.from_authorized_user_file(
            str(TOKEN_PATH),
            ["https://www.googleapis.com/auth/gmail.readonly"],
        )
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        if not creds or not creds.valid:
            log.warning("Gmail credentials invalid — skipping PDF scan")
            return None
        return build("gmail", "v1", credentials=creds)
    except Exception as e:
        log.error(f"Gmail service error: {e}")
        return None


def _get_header(headers: list, name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _scan_for_pdf_emails(svc, seen_ids: list, state: dict = None) -> list:
    """
    Search Gmail for emails with PDF attachments received in the last 24h.
    Returns list of new emails: [{gmail_id, subject, sender, pdf_names}]
    """
    # Search for emails with PDF attachments.
    # Use last_run timestamp so a watcher that was offline catches up (up to MAX_LOOKBACK_DAYS).
    last_run_str = state.get("last_run") if isinstance(state, dict) else None
    if last_run_str:
        try:
            last_run_dt = datetime.fromisoformat(last_run_str)
            lookback = datetime.utcnow() - last_run_dt
            # Add 1-day buffer, cap at MAX_LOOKBACK_DAYS
            hours_back = min(lookback.total_seconds() / 3600 + 24, MAX_LOOKBACK_DAYS * 24)
        except Exception:
            hours_back = 24
    else:
        hours_back = MAX_LOOKBACK_DAYS * 24  # first run — scan full lookback window
    since = (datetime.utcnow() - timedelta(hours=hours_back)).strftime("%Y/%m/%d")
    log.info(f"  Lookback window: {hours_back:.0f}h (since {since})")
    query = f"has:attachment filename:pdf after:{since}"

    try:
        results = svc.users().messages().list(
            userId="me",
            q=query,
            maxResults=20,
        ).execute()
    except Exception as e:
        log.error(f"Gmail search failed: {e}")
        return []

    messages = results.get("messages", [])
    new_emails = []

    for msg_ref in messages:
        msg_id = msg_ref["id"]
        if msg_id in seen_ids:
            continue

        try:
            msg = svc.users().messages().get(
                userId="me", id=msg_id, format="metadata",
                metadataHeaders=["Subject", "From", "Date"],
            ).execute()

            headers = msg.get("payload", {}).get("headers", [])
            subject = _get_header(headers, "Subject") or "(no subject)"
            sender  = _get_header(headers, "From") or "Unknown sender"

            # Get attachment list
            full_msg = svc.users().messages().get(
                userId="me", id=msg_id, format="full",
            ).execute()

            pdf_names = []
            def _walk_parts(parts):
                for part in parts:
                    filename = part.get("filename", "")
                    mime = part.get("mimeType", "")
                    if filename and (mime == "application/pdf" or filename.lower().endswith(".pdf")):
                        pdf_names.append(filename)
                    sub = part.get("parts", [])
                    if sub:
                        _walk_parts(sub)

            payload = full_msg.get("payload", {})
            _walk_parts(payload.get("parts", []) or [payload])

            if pdf_names:
                new_emails.append({
                    "gmail_id":  msg_id,
                    "subject":   subject,
                    "sender":    sender,
                    "pdf_names": pdf_names,
                    "prompted_at": datetime.utcnow().isoformat(),
                })

        except Exception as e:
            log.error(f"Error reading message {msg_id}: {e}")

    return new_emails


# ── Main run ─────────────────────────────────────────────────────────────────

def _download_attachment(svc, gmail_id: str, pdf_name: str) -> bytes | None:
    """
    Download a specific PDF attachment from a Gmail message.
    Returns raw PDF bytes, or None on failure.
    """
    try:
        full_msg = svc.users().messages().get(userId="me", id=gmail_id, format="full").execute()

        def _find_part(parts, target_name):
            for part in parts:
                if part.get("filename", "").lower() == target_name.lower():
                    return part
                sub = part.get("parts", [])
                if sub:
                    found = _find_part(sub, target_name)
                    if found:
                        return found
            return None

        payload = full_msg.get("payload", {})
        part = _find_part(payload.get("parts", []) or [payload], pdf_name)
        if not part:
            log.warning(f"Attachment '{pdf_name}' not found in message {gmail_id}")
            return None

        body = part.get("body", {})
        att_id = body.get("attachmentId")
        if att_id:
            att = svc.users().messages().attachments().get(
                userId="me", messageId=gmail_id, id=att_id
            ).execute()
            data = att.get("data", "")
        else:
            data = body.get("data", "")

        if not data:
            return None
        # Gmail uses URL-safe base64
        import base64 as _b64
        return _b64.urlsafe_b64decode(data + "==")

    except Exception as e:
        log.error(f"Download failed for '{pdf_name}' in {gmail_id}: {e}")
        return None


def _process_attachment(pdf_bytes: bytes, filename: str, sender: str, subject: str) -> dict:
    """
    Save the PDF to the signins/ folder and run it through goj_signin_intake.
    Returns the process_file() result dict.
    """
    import sys as _sys
    import tempfile
    signins_dir = REX_DIR / "signins"
    signins_dir.mkdir(parents=True, exist_ok=True)

    # Save to a uniquely named temp file
    from datetime import datetime as _dt
    stamp = _dt.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in filename)
    dest = signins_dir / f"email_{stamp}_{safe_name}"
    dest.write_bytes(pdf_bytes)
    log.info(f"  → Saved to {dest.name}")

    # Run through the intake classifier
    try:
        _sys.path.insert(0, str(REX_DIR))
        from goj_signin_intake import process_file
        result = process_file(dest)
        log.info(f"  → Intake result: {result.get('status')} / {result.get('type','?')}")
        return result
    except Exception as e:
        log.error(f"  → goj_signin_intake error: {e}")
        return {"status": "error", "reason": str(e), "file": str(dest)}


def run():
    log.info("PDF watcher: checking Gmail for PDF attachments…")
    state = _load_state()

    svc = _gmail_service()
    if not svc:
        log.warning("Gmail not available — skipping this run")
        return

    new_emails = _scan_for_pdf_emails(svc, state["seen_ids"], state)

    if not new_emails:
        log.info("No new PDF emails found")
        state["last_run"] = datetime.utcnow().isoformat()
        _save_state(state)
        return

    token, chat_id = _load_tg()
    log.info(f"Found {len(new_emails)} new email(s) with PDFs — auto-processing…")

    processed_count = 0
    ambiguous_count = 0
    error_count     = 0

    for email in new_emails:
        state["seen_ids"].append(email["gmail_id"])
        if len(state["seen_ids"]) > 500:
            state["seen_ids"] = state["seen_ids"][-500:]

        for pdf_name in email.get("pdf_names", []):
            log.info(f"  Processing attachment: {pdf_name}  (from {email['sender']})")

            pdf_bytes = _download_attachment(svc, email["gmail_id"], pdf_name)
            if not pdf_bytes:
                log.warning(f"  ⚠ Could not download {pdf_name} — skipping")
                error_count += 1
                continue

            result = _process_attachment(pdf_bytes, pdf_name, email["sender"], email["subject"])

            if result["status"] == "ok":
                processed_count += 1
                # Notify via Telegram that it was auto-routed
                msg = (
                    f"✅ <b>Email PDF auto-processed</b>\n\n"
                    f"📧 <b>From:</b> {email['sender']}\n"
                    f"📋 <b>Subject:</b> {email['subject']}\n"
                    f"📄 <b>File:</b> {pdf_name}\n"
                    f"📁 <b>Routed as:</b> {result.get('type','?')} → {result.get('output','')}"
                )
                if token and chat_id:
                    _send_telegram(token, chat_id, msg)

            elif result["status"] == "ambiguous":
                ambiguous_count += 1
                # _notify_rexxie_unknown_doc() is called inside process_file() — Rexxie already knows

            else:
                error_count += 1
                if token and chat_id:
                    _send_telegram(token, chat_id,
                        f"⚠️ <b>Email PDF could not be processed</b>\n\n"
                        f"📄 <b>File:</b> {pdf_name}\n"
                        f"❌ <b>Reason:</b> {result.get('reason', 'unknown error')}"
                    )

    state["last_run"] = datetime.utcnow().isoformat()
    _save_state(state)
    log.info(f"PDF watcher: done. {processed_count} routed, {ambiguous_count} sent to Rexxie, {error_count} errors")


if __name__ == "__main__":
    run()
