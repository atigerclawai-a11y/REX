#!/usr/bin/env python3.11
"""
CC_ocr_telegram_fallback.py — Send unreadable OCR/parser files to Telegram for review
======================================================================================

When any OCR or Drive-parser path can't read a file, this helper:
  1. Renders page 1 as a PNG (via pdftoppm if PDF, or downloads as-is for images)
  2. Sends the image to Kato via Telegram with a caption explaining WHY it failed
     and showing whatever partial data was extracted
  3. Records the file in ~/Desktop/REX/.ocr_review_queue.json so we don't spam
     Kato with the same PDF on every poll cycle

Public API:
  from CC_ocr_telegram_fallback import flag_for_review
  flag_for_review(
      source="carecenta_auth",
      file_path=Path("/tmp/foo.pdf"),     # or Drive file_id
      drive_file_id=None,
      reason="filename pattern unrecognized",
      partial={"filename": "MELNYK NEW .PDF"},
      bot="rex_of_gold",                  # which bot persona to send from
  )

Bot routing (which Telegram bot persona sends the message):
  - "rex_of_gold" → @RexOfGold_bot (GOJ ops + auth review) — default
  - "goj_attendance" → @GojAttendance_bot (sign-in / attendance review)
  - "goj_receipts" → @GOJReceipts_bot (billing/receipt review)

Env vars (loaded from ~/.hermes-cloud/.env):
  TELEGRAM_BOT_TOKEN    — generic fallback bot
  REX_OF_GOLD_BOT_TOKEN — preferred for ops review
  GOJ_ATTENDANCE_TOKEN  — preferred for attendance review
  TELEGRAM_HOME_CHANNEL — Kato's chat id (default destination)

CLI:
  python3 CC_ocr_telegram_fallback.py --test                  # send a test ping
  python3 CC_ocr_telegram_fallback.py --pdf /path/to/foo.pdf  # send one PDF
  python3 CC_ocr_telegram_fallback.py --drive-id <id>         # download from Drive + send
  python3 CC_ocr_telegram_fallback.py --status                # show review queue
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Load env from hermes-cloud .env at import time
try:
    from dotenv import load_dotenv as _load
    _load(os.path.expanduser("~/.hermes-cloud/.env"), override=False)
except Exception:
    pass

HOME = Path.home()
REX  = HOME / "Desktop" / "REX"
QUEUE_FILE = REX / ".ocr_review_queue.json"
LOG_DIR = REX / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "ocr_review.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("ocr_review")


# ── Bot selection ────────────────────────────────────────────────────────────

BOT_ENV_KEYS = {
    "rex_of_gold":    ("REX_OF_GOLD_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"),
    "goj_attendance": ("GOJ_ATTENDANCE_TOKEN",  "TELEGRAM_BOT_TOKEN"),
    "goj_receipts":   ("GOJ_RECEIPTS_BOT_TOKEN","TELEGRAM_BOT_TOKEN"),
    "default":        ("TELEGRAM_BOT_TOKEN",),
}


def _bot_token(bot: str) -> Optional[str]:
    for key in BOT_ENV_KEYS.get(bot, BOT_ENV_KEYS["default"]):
        v = os.getenv(key)
        if v:
            return v.strip()
    return None


def _chat_id() -> str:
    return os.getenv("TELEGRAM_HOME_CHANNEL") or os.getenv("KATO_CHAT_ID") or "5587703834"


# ── Queue persistence ────────────────────────────────────────────────────────

def _load_queue() -> Dict[str, Any]:
    if QUEUE_FILE.exists():
        try:
            return json.loads(QUEUE_FILE.read_text())
        except Exception:
            pass
    return {"entries": {}}


def _save_queue(q: Dict[str, Any]) -> None:
    QUEUE_FILE.write_text(json.dumps(q, indent=2))


# ── PDF → PNG render ─────────────────────────────────────────────────────────

def _render_pdf_page(pdf_path: Path, out_dir: Path, page_num: int = 1, dpi: int = 150) -> Optional[Path]:
    """Render a specific page of a PDF to PNG via pdftoppm (Homebrew poppler).
    Returns the path to the rendered PNG, or None on failure.
    page_num is 1-indexed (page 1 = first page)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = pdf_path.stem.replace(" ", "_")[:60]
    out_prefix = out_dir / f"{stem}_p{page_num}"
    try:
        subprocess.run(
            ["pdftoppm", "-png", "-r", str(dpi), "-f", str(page_num), "-l", str(page_num),
             str(pdf_path), str(out_prefix)],
            check=True, capture_output=True, timeout=60,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.error(f"pdftoppm failed for {pdf_path.name} page {page_num}: {e}")
        return None
    # pdftoppm appends "-{page_num}.png" for single-page output
    rendered = out_prefix.with_name(f"{stem}_p{page_num}-{page_num}.png")
    if rendered.exists():
        return rendered
    # Fall back to checking for any png starting with our prefix
    for p in out_dir.glob(f"{stem}_p{page_num}*.png"):
        return p
    return None


# Backward-compat alias
_render_pdf_first_page = _render_pdf_page  # defaults to page 1


# ── Drive download ───────────────────────────────────────────────────────────

def _download_drive(file_id: str, dest: Path) -> Optional[Path]:
    """Download a Drive file to a local path. Returns the path, or None on fail."""
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload
    except ImportError:
        log.error("google api packages not available — skipping Drive download")
        return None

    creds = Credentials.from_authorized_user_file(
        os.path.expanduser("~/.rex_google_token.json"),
    )
    drive = build("drive", "v3", credentials=creds)
    try:
        request = drive.files().get_media(fileId=file_id)
        with open(dest, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        return dest
    except Exception as e:
        log.error(f"Drive download failed for {file_id}: {e}")
        return None


# ── Telegram send ────────────────────────────────────────────────────────────

def _send_photo(bot_token: str, chat_id: str, image_path: Path, caption: str) -> Dict[str, Any]:
    """POST sendPhoto with multipart upload."""
    import http.client, mimetypes, uuid
    boundary = f"-----CC{uuid.uuid4().hex}"
    image_bytes = image_path.read_bytes()
    body_parts = []
    def _add(name: str, value: str):
        body_parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n")
    _add("chat_id", chat_id)
    _add("caption", caption[:1024])  # Telegram caption limit
    # plain text — filenames with dots/underscores break Markdown parser
    body_parts.append(
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"photo\"; filename=\"{image_path.name}\"\r\n"
        f"Content-Type: image/png\r\n\r\n"
    )
    body_bytes = "".join(body_parts).encode("utf-8") + image_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
    conn = http.client.HTTPSConnection("api.telegram.org", timeout=30)
    conn.request(
        "POST", f"/bot{bot_token}/sendPhoto",
        body=body_bytes,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8", errors="replace")
    conn.close()
    try:
        return {"status": resp.status, **json.loads(raw)}
    except Exception:
        return {"status": resp.status, "raw": raw[:400]}


def _send_document(bot_token: str, chat_id: str, file_path: Path, caption: str) -> Dict[str, Any]:
    """Fallback: send the original PDF if render failed."""
    import http.client, uuid
    boundary = f"-----CC{uuid.uuid4().hex}"
    file_bytes = file_path.read_bytes()
    body_parts = []
    def _add(name: str, value: str):
        body_parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n")
    _add("chat_id", chat_id)
    _add("caption", caption[:1024])
    # plain text — filenames with dots/underscores break Markdown parser
    body_parts.append(
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"document\"; filename=\"{file_path.name}\"\r\n"
        f"Content-Type: application/pdf\r\n\r\n"
    )
    body_bytes = "".join(body_parts).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
    conn = http.client.HTTPSConnection("api.telegram.org", timeout=60)
    conn.request(
        "POST", f"/bot{bot_token}/sendDocument",
        body=body_bytes,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8", errors="replace")
    conn.close()
    try:
        return {"status": resp.status, **json.loads(raw)}
    except Exception:
        return {"status": resp.status, "raw": raw[:400]}


# ── Public API ───────────────────────────────────────────────────────────────

def flag_for_review(
    source: str,
    file_path: Optional[Path] = None,
    drive_file_id: Optional[str] = None,
    reason: str = "OCR/parser could not read this file",
    partial: Optional[Dict[str, Any]] = None,
    bot: str = "rex_of_gold",
    force: bool = False,
    page_num: int = 1,
) -> Dict[str, Any]:
    """Send a file to Kato via Telegram for manual review.

    Idempotent: by default, a given (source, file_id-or-name) is sent ONCE
    until it's marked resolved in the queue file. Pass force=True to resend.

    Returns a dict with keys: ok, queue_key, telegram_response (if sent).
    """
    # Build a stable queue key
    key = f"{source}:{drive_file_id or (file_path.name if file_path else 'unknown')}"
    queue = _load_queue()
    entry = queue["entries"].get(key)
    if entry and not force and entry.get("status") in ("queued", "delivered"):
        log.info(f"  ⏭  {key} already in review queue ({entry.get('status')}) — skipping")
        return {"ok": True, "queue_key": key, "status": "already_queued"}

    # Acquire local PDF
    tmp_dir = Path(tempfile.mkdtemp(prefix="ocr_review_"))
    local_pdf: Optional[Path] = None
    if file_path and file_path.exists():
        local_pdf = file_path
    elif drive_file_id:
        local_pdf = _download_drive(drive_file_id, tmp_dir / "source.pdf")
    if not local_pdf or not local_pdf.exists():
        log.error(f"  ❌ could not obtain source file for {key}")
        return {"ok": False, "queue_key": key, "error": "no source file"}

    # Render
    png = _render_pdf_page(local_pdf, tmp_dir, page_num=page_num) if local_pdf.suffix.lower() == ".pdf" else local_pdf

    # Compose caption — plain text (no markdown chars to escape)
    caption_lines = [
        f"⚠️ OCR review needed — {source}",
        f"📄 {local_pdf.name}  (page {page_num})",
        f"Reason: {reason}",
    ]
    if partial:
        caption_lines.append("Partial:")
        for k, v in partial.items():
            caption_lines.append(f"  · {k}: {v}")
    if drive_file_id:
        caption_lines.append(f"Drive: https://drive.google.com/file/d/{drive_file_id}/view")
    caption = "\n".join(caption_lines)

    # Send
    token = _bot_token(bot)
    chat  = _chat_id()
    if not token:
        log.error(f"  ❌ no Telegram bot token for '{bot}'")
        return {"ok": False, "queue_key": key, "error": "no token"}

    if png and png.exists() and png.suffix == ".png":
        result = _send_photo(token, chat, png, caption)
        method = "photo"
    else:
        # Last resort: send the PDF as a document
        result = _send_document(token, chat, local_pdf, caption)
        method = "document"
    sent_ok = result.get("ok", False) and result.get("status", 0) == 200

    queue["entries"][key] = {
        "source":           source,
        "file_path":        str(file_path) if file_path else None,
        "drive_file_id":    drive_file_id,
        "reason":           reason,
        "partial":          partial or {},
        "bot":              bot,
        "sent_at":          datetime.now(timezone.utc).isoformat(),
        "method":           method,
        "status":           "delivered" if sent_ok else "send_failed",
        "telegram_response": {"ok": result.get("ok"), "status": result.get("status")},
    }
    _save_queue(queue)
    if sent_ok:
        log.info(f"  📤 sent to Telegram as {method} — {key}")
    else:
        log.error(f"  ❌ Telegram send failed — {key} — {result}")
    return {"ok": sent_ok, "queue_key": key, "method": method,
            "telegram_response": result}


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--test", action="store_true",
                   help="send a text-only test ping to confirm bot+chat work")
    p.add_argument("--pdf", help="local PDF path to send for review")
    p.add_argument("--drive-id", help="Drive file ID to download + send")
    p.add_argument("--source", default="cli_test",
                   help="source label (e.g. carecenta_auth, sign_in)")
    p.add_argument("--reason", default="manual review requested via CLI")
    p.add_argument("--bot", default="rex_of_gold",
                   choices=list(BOT_ENV_KEYS.keys()))
    p.add_argument("--force", action="store_true",
                   help="re-send even if already in queue")
    p.add_argument("--status", action="store_true",
                   help="print the review queue + exit")
    args = p.parse_args()

    if args.status:
        print(json.dumps(_load_queue(), indent=2))
        return 0

    if args.test:
        # Text-only ping
        token = _bot_token(args.bot)
        chat  = _chat_id()
        if not token:
            print(f"❌ no token for bot '{args.bot}'")
            return 1
        body = urllib.parse.urlencode({
            "chat_id": chat,
            "text":   f"✅ OCR-fail Telegram fallback test\n"
                      f"Bot: {args.bot}\n"
                      f"Chat: {chat}\n"
                      f"Time: {datetime.now(timezone.utc).isoformat()}",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=body,
            method="POST",
        )
        try:
            r = urllib.request.urlopen(req, timeout=15)
            print(f"✅ test send: HTTP {r.status}")
            print(r.read(400).decode())
        except urllib.error.HTTPError as e:
            print(f"❌ test send: HTTP {e.code}")
            print(e.read(400).decode())
        return 0

    if args.pdf:
        path = Path(args.pdf).expanduser()
        if not path.exists():
            print(f"❌ {path} not found")
            return 1
        result = flag_for_review(
            source=args.source, file_path=path, reason=args.reason,
            bot=args.bot, force=args.force,
        )
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    if args.drive_id:
        result = flag_for_review(
            source=args.source, drive_file_id=args.drive_id, reason=args.reason,
            bot=args.bot, force=args.force,
        )
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
