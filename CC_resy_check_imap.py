#!/usr/bin/env python3
"""CC_resy_check_imap.py — One-shot check for NEW Owner.com reservation emails.
Narrow filters only (FROM/SUBJECT + SINCE) to avoid hanging the huge inbox."""
import imaplib, json, sys
from pathlib import Path
from email.header import decode_header

creds = json.load(open(Path.home() / ".rex_gmail_imap.json"))
EMAIL = creds["email"]
PW = creds["app_password"]

M = imaplib.IMAP4_SSL("imap.gmail.com", 993)
M.login(EMAIL, PW)
M.select("INBOX")

# Highest UID in inbox (to compare against last processed 1347)
typ, data = M.search(None, "ALL")
all_ids = data[0].split()
print(f"INBOX total messages: {len(all_ids)}")

# Last known processed UID per reservations JSON was atigerclawai:1347
# Check messages with UID > 1347
typ, data = M.uid("search", None, "UID", "1348:*")
uids = data[0].split()
print(f"Messages with UID > 1347: {len(uids)}")
if uids:
    # Show last 15 UIDs and their subjects
    for uid in uids[-15:]:
        typ, msg_data = M.uid("fetch", uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
        if msg_data and msg_data[0]:
            raw = msg_data[0][1].decode("utf-8", "replace")
            subj = ""
            for line in raw.splitlines():
                if line.lower().startswith("subject:"):
                    subj = line[8:].strip()
            print(f"  UID {uid.decode()}: {subj[:100]}")
else:
    # Fallback: search for reservation form submissions since late July
    print("No UIDs > 1347. Checking FROM/SUBJECT filter since 27-Jul-2026...")
    typ, data = M.search(None, '(SINCE "27-Jul-2026" FROM "allen")')
    print(f"  FROM allen since 27-Jul: {len(data[0].split()) if data[0] else 0}")
    typ, data = M.search(None, '(SINCE "27-Jul-2026" SUBJECT "Form Submission")')
    print(f"  SUBJECT Form Submission since 27-Jul: {len(data[0].split()) if data[0] else 0}")

M.logout()
