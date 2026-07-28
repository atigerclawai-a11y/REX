"""
GOJ Menu Flag Reporter
======================
Reads unresolved flags from goj_menu_flags_queue.json and sends
them to Kato via Rexxie's Telegram bot — including the actual scanned
PDF so Kato can see the form and identify the client.

Kato replies to Rexxie like:
  "menu fix: flag_id=42 name=John Smith"
  "menu fix: flag_id=42 skip"
  "menu fix: flag_id=42 confirm"

Then run goj_menu_confirm_handler.py to process his replies.

Run:
    cd ~/Desktop/REX && source .venv/bin/activate
    python goj_menu_flag_reporter.py
"""

import json
import logging
import sys
import urllib.request
import urllib.parse
import urllib.error
import tempfile
import os
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("flag_reporter")

# ─── Paths ────────────────────────────────────────────────────────────────────
REX_DIR        = Path.home() / "Desktop" / "REX"
FLAGS_FILE     = REX_DIR / "goj_menu_flags_queue.json"
REXXIE_CONFIG  = REX_DIR / "rex_rexxie_telegram_config.json"

# ─── Paperless config ─────────────────────────────────────────────────────────
LAST_FLAG_FILE  = REX_DIR / ".goj_menu_last_flag"
PAPERLESS_URL   = "http://100.99.86.60:8000"
PAPERLESS_TOKEN = "583e819be1146b96b935007c6ad7f584a3a1b1b7"

# How many flags to send per run (send one at a time with PDF attached)
BATCH_SIZE = 10


# ─── Telegram helpers ─────────────────────────────────────────────────────────

def send_telegram_text(token: str, chat_id: int, text: str) -> bool:
    """Send a plain-text Telegram message."""
    url  = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({
        "chat_id":    chat_id,
        "text":       text,
        "parse_mode": "Markdown",
    }).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read())
            return result.get("ok", False)
    except Exception as e:
        log.error(f"Telegram text send failed: {e}")
        return False


def send_telegram_document(token: str, chat_id: int,
                           pdf_bytes: bytes, filename: str, caption: str) -> bool:
    """Send a PDF file as a Telegram document with caption."""
    url = f"https://api.telegram.org/bot{token}/sendDocument"

    # Build multipart/form-data manually
    boundary = "----TelegramBoundary"
    body_parts = []

    def add_field(name, value):
        body_parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        )

    add_field("chat_id", str(chat_id))
    add_field("caption", caption[:1024])
    add_field("parse_mode", "Markdown")

    # File part
    body_parts.append(
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    )

    body_bytes = "".join(body_parts).encode() + pdf_bytes + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        url,
        data=body_bytes,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
            if not result.get("ok"):
                log.warning(f"Telegram doc send not OK: {result}")
            return result.get("ok", False)
    except Exception as e:
        log.error(f"Telegram document send failed: {e}")
        return False


# ─── Paperless PDF download ───────────────────────────────────────────────────

def download_pdf_from_paperless(doc_id: int) -> bytes | None:
    """Download the original PDF for a Paperless document."""
    url = f"{PAPERLESS_URL}/api/documents/{doc_id}/download/"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Token {PAPERLESS_TOKEN}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read()
    except Exception as e:
        log.warning(f"Could not download PDF for doc {doc_id}: {e}")
        return None


# ─── Rexxie config ────────────────────────────────────────────────────────────

def load_rexxie_config() -> dict:
    if not REXXIE_CONFIG.exists():
        log.error(f"Rexxie config not found at {REXXIE_CONFIG}")
        return {}
    try:
        return json.loads(REXXIE_CONFIG.read_text())
    except Exception as e:
        log.error(f"Could not read Rexxie config: {e}")
        return {}


# ─── Format caption for each flag ────────────────────────────────────────────

def format_flag_caption(flag: dict, number: int) -> str:
    doc_id     = flag.get("doc_id", "?")
    flag_id    = flag.get("flag_id", str(doc_id))
    candidate  = flag.get("candidate_name", "") or ""
    matched    = flag.get("matched_name", "") or ""
    confidence = flag.get("confidence", 0)
    status     = flag.get("status", "low")
    created    = flag.get("created", "")
    selections = flag.get("selections", {})

    lines = [
        f"🚩 *Menu Review #{number}* — Doc {doc_id}",
        f"📅 Week of {created}",
        "",
    ]

    if status == "medium" and matched:
        lines.append(f"OCR read: `{candidate}`")
        lines.append(f"Best guess: *{matched}* ({confidence:.0%})")
        lines.append("")
        lines.append(f"✅ If correct: `menu fix: flag_id={flag_id} confirm`")
        lines.append(f"✏️ If wrong: `menu fix: flag_id={flag_id} name=Correct Name`")
    else:
        if candidate:
            lines.append(f"OCR read: `{candidate}` — couldn't match a client")
        else:
            lines.append("OCR couldn't read the name on this form.")
        lines.append("")
        lines.append(f"✏️ Reply: `menu fix: flag_id={flag_id} name=Client Name`")
        lines.append(f"⏭️ Skip: `menu fix: flag_id={flag_id} skip`")

    # Food selections found
    if selections:
        sel_parts = []
        for day, cats in selections.items():
            items = []
            for cat_items in cats.values():
                items.extend(cat_items)
            if items:
                sel_parts.append(f"{day}: {', '.join(items[:3])}")
        if sel_parts:
            lines.append("")
            lines.append(f"🍽️ {' | '.join(sel_parts[:3])}")

    return "\n".join(lines)


def format_summary_header(total: int) -> str:
    return (
        f"📋 *GOJ Menu Review — {total} forms need your attention*\n"
        f"_{datetime.now().strftime('%B %d, %Y %H:%M')}_\n\n"
        "Look at each scanned form I'm sending, identify the client, "
        "and reply with the commands below each one."
    )


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    log.info("=== GOJ Menu Flag Reporter ===")

    # --resend flag: mark all unresolved flags as unsent so they go again
    resend_mode = "--resend" in sys.argv
    if resend_mode:
        log.info("--resend mode: re-queuing all unresolved flags")

    cfg = load_rexxie_config()
    if not cfg:
        return

    token   = cfg.get("token") or cfg.get("bot_token") or cfg.get("rexxie_token")
    chat_id = cfg.get("owner_chat_id")

    if not token or not chat_id:
        log.error("Rexxie bot token or owner_chat_id not found in config.")
        return

    log.info(f"Sending to Kato (chat_id={chat_id})")

    if not FLAGS_FILE.exists():
        log.info("No flags queue found. Run goj_menu_ocr_processor.py first.")
        return

    flags = json.loads(FLAGS_FILE.read_text())

    # In resend mode, reset sent_to_kato for all unresolved flags
    if resend_mode:
        reset_count = 0
        for f in flags:
            if not f.get("resolved"):
                f["sent_to_kato"] = False
                f.pop("sent_at", None)
                reset_count += 1
        FLAGS_FILE.write_text(json.dumps(flags, indent=2, ensure_ascii=False))
        log.info(f"  Reset {reset_count} flags — resending now")

    pending = [f for f in flags if not f.get("sent_to_kato") and not f.get("resolved")]

    if not pending:
        log.info("No pending flags to send. Use --resend to re-send already-sent flags.")
        return

    log.info(f"Found {len(pending)} unsent flags")

    # Send summary header
    send_telegram_text(token, chat_id, format_summary_header(len(pending)))

    sent_count = 0
    for i, flag in enumerate(pending[:BATCH_SIZE], 1):
        doc_id  = flag.get("doc_id")
        flag_id = flag.get("flag_id", str(doc_id))

        caption = format_flag_caption(flag, i)

        # Try to send the actual PDF
        pdf_sent = False
        if doc_id:
            log.info(f"  Downloading PDF for doc {doc_id}...")
            pdf_bytes = download_pdf_from_paperless(doc_id)
            if pdf_bytes:
                filename = f"menu_doc_{doc_id}.pdf"
                ok = send_telegram_document(token, chat_id, pdf_bytes, filename, caption)
                if ok:
                    log.info(f"  ✅ Sent PDF + caption for flag {flag_id}")
                    pdf_sent = True
                else:
                    log.warning(f"  PDF send failed for doc {doc_id}, falling back to text")

        # Fall back to text-only if PDF failed
        if not pdf_sent:
            ok = send_telegram_text(token, chat_id, caption)
            if ok:
                log.info(f"  ✅ Sent text flag {flag_id} (no PDF)")

        if pdf_sent or ok:
            for fl in flags:
                if str(fl.get("flag_id")) == str(flag_id):
                    fl["sent_to_kato"] = True
                    fl["sent_at"]      = datetime.now().isoformat()
            # Track last sent flag so Rexxie knows which one you're replying to
            LAST_FLAG_FILE.write_text(str(flag_id))
            sent_count += 1

    # Save updated flags
    FLAGS_FILE.write_text(json.dumps(flags, indent=2, ensure_ascii=False))

    remaining = len(pending) - sent_count
    log.info(f"\nSent {sent_count} flags to Kato via Telegram (with PDFs).")
    if remaining > 0:
        log.info(f"  {remaining} remaining — run again to send next batch.")
    log.info("Run 'python goj_menu_confirm_handler.py' after you reply to Rexxie.")


if __name__ == "__main__":
    main()
