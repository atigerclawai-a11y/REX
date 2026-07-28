#!/usr/bin/env python3
"""Fetch a specific reservation email body via IMAP."""
import imaplib, email, json, ssl, sys
from email.header import decode_header

EMAIL = "olympusbbg@gmail.com"
PASSWORD = "Hermes12345$"
IMAP_SERVER = "imap.gmail.com"
SEARCH_SUBJECT = sys.argv[1] if len(sys.argv) > 1 else "New Reservations Form Submission"

ctx = ssl.create_default_context()
mail = imaplib.IMAP4_SSL(IMAP_SERVER, 993, ssl_context=ctx, timeout=15)
mail.login(EMAIL, PASSWORD)
mail.select("INBOX")

status, messages = mail.search(None, f'(SUBJECT "{SEARCH_SUBJECT}")')
if status == "OK" and messages[0]:
    msg_ids = messages[0].split()
    mid = msg_ids[-1]
    status, data = mail.fetch(mid, "(RFC822)")
    if status == "OK":
        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        body += payload.decode("utf-8", errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode("utf-8", errors="replace")
        
        print(json.dumps({"ok": True, "subject": str(msg["Subject"]), "from": str(msg["From"]), "date": str(msg["Date"]), "body": body[:5000]}))
    else:
        print(json.dumps({"ok": False, "error": "fetch failed"}))
else:
    print(json.dumps({"ok": False, "error": "not found"}))

mail.logout()
