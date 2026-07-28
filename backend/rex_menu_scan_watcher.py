"""
rex_menu_scan_watcher.py — Auto Gmail → Menu OCR Pipeline
==========================================================

Runs as a background task inside the REX lifespan.

Every 5 minutes it:
  1. Connects to Gmail via IMAP (App Password — no OAuth, no token expiry)
  2. Searches for scan emails from Allen or the office scanner
  3. Downloads any new PDF attachments to the menus directory
  4. Saves PDFs to Paperless-ngx as an archive buffer
  5. Triggers the 4-engine OCR consensus pipeline on each new PDF
  6. Reports results to Kato via Rexxie on Telegram

Auth: Gmail App Password stored in ~/.rex_gmail_imap.json
  No OAuth tokens. No expiry. Works reliably under launchd.

Setup: bash ~/Desktop/REX/CC_setup_gmail_imap.command

Watched senders (any of these triggers a download):
  - allen@gardenofjoybrooklyn.com
  - olympusbbg@gmail.com
  - goj3152.scans@gmail.com

State file: ~/Desktop/REX/logs/menu_scan_watcher_state.json
  Tracks seen IMAP UIDs so re-starts don't reprocess old emails.
"""

import asyncio
import email as email_lib
import imaplib
import json
import logging
import os
import subprocess
from datetime import datetime, timedelta
from email.header import decode_header as _decode_header
from pathlib import Path
from typing import Optional

logger = logging.getLogger("rex.menu_scan_watcher")

# ── Paths ──────────────────────────────────────────────────────────────────────
REX_DIR         = Path(__file__).resolve().parent.parent
STATE_PATH      = REX_DIR / "logs" / "menu_scan_watcher_state.json"
MENUS_DIR       = Path.home() / "Documents" / "goj files" / "dashboard" / "documents" / "menus"
DB_PATH         = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
ENV_PATH        = Path.home() / "Documents" / "goj files" / ".env"
TG_CFG_PATH     = REX_DIR / "rex_rexxie_telegram_config.json"
IMAP_CFG_PATH   = Path.home() / ".rex_gmail_imap.json"

# ── IMAP settings ──────────────────────────────────────────────────────────────
IMAP_HOST  = "imap.gmail.com"
IMAP_PORT  = 993
IMAP_EMAIL = "atigerclawai@gmail.com"

# ── Scan senders ──────────────────────────────────────────────────────────────
SCAN_SENDERS = {
    "allen@gardenofjoybrooklyn.com",
    "olympusbbg@gmail.com",
    "goj3152.scans@gmail.com",
}

# ── Poll interval ─────────────────────────────────────────────────────────────
POLL_SECONDS = 300  # 5 minutes
SEARCH_DAYS  = 60   # look back this many days for scans


# ── App Password helpers ───────────────────────────────────────────────────────

def _get_app_password() -> Optional[str]:
    """Read Gmail App Password from config file or env var."""
    # env var takes precedence (useful for testing)
    pw = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    if pw:
        return pw
    if IMAP_CFG_PATH.exists():
        try:
            cfg = json.loads(IMAP_CFG_PATH.read_text())
            return cfg.get("app_password", "").strip() or None
        except Exception:
            pass
    return None


def is_configured() -> bool:
    """True if IMAP credentials are available."""
    return bool(_get_app_password())


# ── IMAP connection ────────────────────────────────────────────────────────────

def _imap_connect() -> imaplib.IMAP4_SSL:
    password = _get_app_password()
    if not password:
        raise RuntimeError(
            "Gmail App Password not configured. "
            "Run: bash ~/Desktop/REX/CC_setup_gmail_imap.command"
        )
    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    mail.login(IMAP_EMAIL, password)
    return mail


# ── State helpers ──────────────────────────────────────────────────────────────

def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return {"seen_ids": [], "last_check": None, "processed_count": 0}


def _save_state(state: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


# ── Telegram helper ────────────────────────────────────────────────────────────

def _send_telegram(text: str) -> bool:
    if not TG_CFG_PATH.exists():
        return False
    try:
        d = json.loads(TG_CFG_PATH.read_text())
        token   = d.get("bot_token", "")
        chat_id = d.get("owner_chat_id", 0)
    except Exception:
        return False
    if not token or not chat_id:
        return False
    import urllib.request as _req
    url     = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    req     = _req.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with _req.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()).get("ok", False)
    except Exception as e:
        logger.warning(f"Telegram send failed: {e}")
        return False


# ── Paperless helper ───────────────────────────────────────────────────────────

def _get_paperless_config() -> dict:
    # No hardcoded token. Load from ENV_PATH (PAPERLESS_TOKEN); _ingest_paperless
    # no-ops cleanly when the token is absent. Rotate the previously-committed
    # token and store the new one in the env file / Keychain.
    cfg = {"url": "http://localhost:8010", "token": ""}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()
                if k == "PAPERLESS_URL":
                    cfg["url"] = v
                elif k == "PAPERLESS_TOKEN":
                    cfg["token"] = v
    return cfg


def _ingest_paperless(filepath: Path, title: str):
    """Upload PDF to Paperless-ngx."""
    import urllib.request as _req
    import uuid
    cfg      = _get_paperless_config()
    pl_url   = cfg["url"].rstrip("/")
    pl_token = cfg["token"]
    if not pl_token:
        return
    boundary = uuid.uuid4().hex
    data     = filepath.read_bytes()
    fname    = filepath.name
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="document"; filename="{fname}"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}\r\n".encode() + (
        f'Content-Disposition: form-data; name="title"\r\n\r\n{title}\r\n'
        f"--{boundary}--\r\n"
    ).encode()
    req = _req.Request(
        f"{pl_url}/api/documents/post_document/",
        data=body,
        headers={
            "Authorization": f"Token {pl_token}",
            "Content-Type":  f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with _req.urlopen(req, timeout=30) as resp:
            logger.info(f"Paperless ingest OK: {fname} ({resp.status})")
    except Exception as e:
        logger.warning(f"Paperless ingest failed for {fname}: {e}")


# ── IMAP PDF downloader ────────────────────────────────────────────────────────

def _decode_header_value(value: str) -> str:
    """Decode RFC2047-encoded email header value."""
    parts = _decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def _download_pdfs_from_imap_message(msg, uid_str: str) -> list[Path]:
    """Extract and save all PDF attachments from an email.message.Message object."""
    MENUS_DIR.mkdir(parents=True, exist_ok=True)
    saved = []

    subject_raw = msg.get("Subject", "(no subject)")
    subject = _decode_header_value(subject_raw)

    for part in msg.walk():
        content_type = part.get_content_type()
        filename_raw = part.get_filename()

        if not filename_raw:
            continue

        filename = _decode_header_value(filename_raw)
        is_pdf = (
            content_type == "application/pdf"
            or filename.lower().endswith(".pdf")
            or content_type == "application/octet-stream" and filename.lower().endswith(".pdf")
        )
        if not is_pdf:
            continue

        payload = part.get_payload(decode=True)
        if not payload:
            continue

        # Validate actual PDF magic bytes — a .pdf extension / forged MIME type
        # is not trust. Reject anything that is not a real PDF before it reaches
        # disk, Paperless, or the OCR pipeline.
        if not payload.startswith(b"%PDF-"):
            logger.warning(f"Rejected non-PDF attachment (bad magic): {filename!r}")
            continue

        # Use UID + filename to avoid collisions
        safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
        if not uid_str.isdigit():        # UID must be a server integer
            logger.warning(f"Rejected non-numeric IMAP UID: {uid_str!r}")
            continue
        dest_name = f"{uid_str}_{safe_name}"
        dest_path = MENUS_DIR / dest_name

        # Path-traversal containment: the resolved destination must stay inside
        # MENUS_DIR regardless of any crafted filename/UID.
        if not dest_path.resolve().is_relative_to(MENUS_DIR.resolve()):
            logger.error(f"Path traversal blocked: {dest_path}")
            continue

        if not dest_path.exists():
            dest_path.write_bytes(payload)
            logger.info(f"Saved: {dest_path}")
            saved.append(dest_path)

            title = f"Menu Scan — {subject[:80]} — {datetime.now().strftime('%Y-%m-%d')}"
            _ingest_paperless(dest_path, title)

    return saved


# ── OCR trigger ────────────────────────────────────────────────────────────────

def _trigger_ocr_on_files(pdf_paths: list[Path]) -> dict:
    """Enqueue PDFs for OCR via CC_ocr_queue then launch worker non-blocking."""
    import sys
    sys.path.insert(0, str(REX_DIR))
    from CC_ocr_queue import enqueue_scan

    queued = []
    for pdf_path in pdf_paths:
        job_id = enqueue_scan(str(pdf_path), mode="local")
        if job_id:
            queued.append(pdf_path.name)

    python_bin = REX_DIR / ".venv" / "bin" / "python3"
    if not python_bin.exists():
        python_bin = Path(sys.executable)
    subprocess.Popen(
        [str(python_bin), str(REX_DIR / "CC_ocr_worker.py")],
        close_fds=True,
    )
    return {"ok": True, "queued": queued}


# ── Main poll loop ─────────────────────────────────────────────────────────────

def _poll_once():
    """
    One pass: connect to Gmail via IMAP, find new scan PDFs, trigger OCR.
    Called from the async watcher every POLL_SECONDS.
    """
    if not is_configured():
        logger.debug("Gmail IMAP not configured — skipping scan watcher poll")
        return

    state = _load_state()
    seen  = set(state.get("seen_ids", []))

    # Connect to IMAP
    try:
        mail = _imap_connect()
    except Exception as e:
        logger.warning(f"Gmail IMAP connect failed: {e}")
        _send_telegram(f"⚠️ <b>Scan watcher: IMAP connect failed</b>\n{e}\nCheck App Password config.")
        return

    try:
        mail.select("INBOX")

        # Build date filter — search last SEARCH_DAYS days
        since_date = (datetime.now() - timedelta(days=SEARCH_DAYS)).strftime("%d-%b-%Y")

        # Search each sender separately (IMAP OR is limited)
        all_uids: set[bytes] = set()
        for sender in SCAN_SENDERS:
            try:
                _, data = mail.uid("search", None, f'(FROM "{sender}" SINCE "{since_date}")')
                if data and data[0]:
                    for uid in data[0].split():
                        all_uids.add(uid)
            except Exception as e:
                logger.warning(f"IMAP search failed for {sender}: {e}")

        new_pdfs  = []
        processed = 0

        for uid_bytes in all_uids:
            uid_str = uid_bytes.decode()
            if uid_str in seen:
                continue

            try:
                _, msg_data = mail.uid("fetch", uid_bytes, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    seen.add(uid_str)
                    continue

                raw_email = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw_email)

                # Re-verify the sender at processing time. The IMAP FROM search
                # is server-dependent and not a guarantee; confirm the actual
                # From: address is on the allowlist before trusting attachments.
                from email.utils import parseaddr as _parseaddr
                from_addr = _parseaddr(msg.get("From", ""))[1].lower()
                if from_addr not in {s.lower() for s in SCAN_SENDERS}:
                    logger.warning(f"Dropped UID {uid_str}: sender {from_addr!r} not allowlisted")
                    seen.add(uid_str)
                    continue

                saved = _download_pdfs_from_imap_message(msg, uid_str)
                if saved:
                    processed += 1
                    subject = _decode_header_value(msg.get("Subject", "(no subject)"))
                    logger.info(f"Downloaded {len(saved)} PDFs from UID {uid_str} ({subject})")

                    # ── Route sign-in sheets to CC_signin_ocr ─────────────────
                    # Whole-word match only. Substring matching on "sign" routes
                    # "design"/"assignment"/"resignation" PDFs into the
                    # attendance pipeline — a corruption vector for client data.
                    import re as _re
                    if _re.search(r"\b(sign[ -]?in|signin|attendance)\b",
                                  subject.lower()):
                        import sys as _sys
                        _sys.path.insert(0, str(REX_DIR))
                        from CC_signin_ocr import process_signin_sheet as _process_signin
                        try:
                            from CC_signin_ocr_report import (
                                build_summary as _build_sum,
                                send_telegram as _send_tg,
                            )
                        except Exception:
                            _build_sum = _send_tg = None
                        from datetime import datetime as _dt
                        for pdf in saved:
                            try:
                                _stats = _process_signin(pdf)
                                logger.info(f"Sign-in OCR complete: {pdf.name}")
                                # Step 10: Telegram OCR summary to Kato. Failure
                                # here must never break the OCR result above.
                                if _build_sum and _send_tg:
                                    try:
                                        _send_tg(_build_sum(
                                            pdf, _stats,
                                            _dt.now().strftime("%Y-%m-%d")))
                                    except Exception as _se:
                                        logger.warning(f"OCR summary send failed: {_se}")
                            except Exception as _e:
                                logger.error(f"Sign-in OCR failed for {pdf.name}: {_e}")
                    else:
                        new_pdfs.extend(saved)   # existing menu OCR flow
                    # ──────────────────────────────────────────────────────────

            except Exception as e:
                logger.warning(f"Failed to process UID {uid_str}: {e}")

            seen.add(uid_str)

    finally:
        try:
            mail.logout()
        except Exception:
            pass

    # Persist state
    state["seen_ids"]        = list(seen)[-500:]  # cap at 500
    state["last_check"]      = datetime.now().isoformat()
    state["processed_count"] = state.get("processed_count", 0) + processed
    _save_state(state)

    if not new_pdfs:
        return

    # Notify Kato
    pdf_list = "\n".join(f"  • {p.name}" for p in new_pdfs)
    _send_telegram(
        f"📬 <b>New menu scan(s) received!</b>\n"
        f"Found {len(new_pdfs)} new PDF(s) from Allen/scanner:\n{pdf_list}\n\n"
        f"⏳ Queued for OCR processing — worker running in background."
    )

    # Enqueue OCR
    ocr_results = _trigger_ocr_on_files(new_pdfs)
    queued = ocr_results.get("queued", [])
    _send_telegram(
        f"✅ <b>OCR queued</b>\n"
        f"Enqueued {len(queued)} of {len(new_pdfs)} PDF(s) for hybrid OCR.\n"
        f"Worker running in background — results via Telegram when done.\n"
        f"Check dashboard → client profiles → 📋 Menu Orders for results."
    )


# ── Async background task ──────────────────────────────────────────────────────

async def run_menu_scan_watcher():
    """
    Async background task — runs forever, polling Gmail via IMAP every POLL_SECONDS.
    Start from the FastAPI lifespan alongside other background tasks.
    """
    logger.info(f"🔍 Menu scan watcher started (IMAP) — polling every {POLL_SECONDS}s")
    loop = asyncio.get_event_loop()

    while True:
        try:
            await loop.run_in_executor(None, _poll_once)
        except Exception as e:
            logger.error(f"Menu scan watcher error: {e}", exc_info=True)

        await asyncio.sleep(POLL_SECONDS)
