#!/usr/bin/env python3
"""CC_ig_email_watcher.py — Poll IMAP for IG archive emails + auto-save to ~/Downloads/.

Runs in foreground (use --daemon for cron).
"""
import imaplib
import email
import json
import os
import re
import sys
import time
from email.header import decode_header
from pathlib import Path

CREDS_FILE = Path.home() / ".rex_gmail_imap.json"
WATCH_DIR = Path.home() / "Downloads"
DONE_MARKER = WATCH_DIR / ".ig_archive_processed"


def decode_header_value(v):
    if v is None:
        return ""
    parts = decode_header(v)
    out = []
    for txt, enc in parts:
        if isinstance(txt, bytes):
            out.append(txt.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(txt)
    return "".join(out)


def looks_like_ig_archive(msg) -> bool:
    """Match: From mail.instagram.com OR subject contains 'Instagram' + 'download'/'ready'"""
    frm = decode_header_value(msg.get("From", "")).lower()
    subj = decode_header_value(msg.get("Subject", "")).lower()
    if "instagram" in frm or "instagram" in subj:
        if "download" in subj or "ready" in subj or "data" in subj:
            return True
    return False


def save_attachments(msg, target_dir: Path) -> list[Path]:
    saved = []
    for part in msg.walk():
        fn = part.get_filename()
        if not fn:
            continue
        fn = decode_header_value(fn)
        if not (".zip" in fn.lower() or fn.lower().endswith(".tar.gz")):
            continue
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", fn)
        out = target_dir / f"instagram_{int(time.time())}_{safe_name}"
        payload = part.get_payload(decode=True)
        if payload:
            out.write_bytes(payload)
            saved.append(out)
    return saved


def main():
    creds = json.load(open(CREDS_FILE))
    m = imaplib.IMAP4_SSL(creds["imap_host"], creds["imap_port"])
    m.login(creds["email"], creds["app_password"])
    m.select("INBOX")

    print(f"[{time.strftime('%H:%M:%S')}] Scanning INBOX for IG archive emails...")
    # Targeted search — don't fetch whole inbox
    status, data = m.search(None, '(FROM "mail.instagram.com")')
    ids = data[0].split() if data[0] else []
    if not ids:
        # Try broader IG-related search
        status, data = m.search(None, '(SUBJECT "instagram")')
        ids = data[0].split() if data[0] else []
    print(f"   Found {len(ids)} candidate messages")

    found = []
    for mid in reversed(ids[-10:]):  # last 10 candidates
        # Fetch only envelope first (faster than RFC822)
        status, env_data = m.fetch(mid, "(BODY.PEEK[HEADER])")
        hdr_blob = b""
        for part in env_data:
            if isinstance(part, tuple):
                hdr_blob += part[1]
        msg = email.message_from_bytes(hdr_blob)
        if not looks_like_ig_archive(msg):
            continue
        # Now fetch full body for attachments
        status, msg_data = m.fetch(mid, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        saved = save_attachments(msg, WATCH_DIR)
        for s in saved:
            print(f"   ✓ Saved: {s.name} ({s.stat().st_size / 1024:.1f} KB)")
            found.append(s)

    m.logout()

    if found:
        print(f"\n✅ {len(found)} archive(s) saved to {WATCH_DIR}")
        print("   CC_ig_archive_parser.py will auto-process them.")
    else:
        print("\n   No IG archive email found yet. Re-run later.")
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main())