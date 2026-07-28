#!/usr/bin/env python3
"""Check Gmail inbox via IMAP for reservation emails."""
import imaplib, email, json, sys, re, ssl
from email.header import decode_header
from datetime import datetime

EMAIL = "olympusbbg@gmail.com"
PASSWORD = "Hermes12345$"
IMAP_SERVER = "imap.gmail.com"

ctx = ssl.create_default_context()

try:
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, 993, ssl_context=ctx, timeout=15)
    mail.login(EMAIL, PASSWORD)
    mail.select("INBOX")
    
    # Search for recent emails (last 3 days)
    status, messages = mail.search(None, '(SINCE "18-Jun-2026")')
    if status != "OK":
        print(json.dumps({"ok": True, "messages": [], "note": "search failed"}))
        mail.logout()
        sys.exit(0)
    
    msg_ids = messages[0].split()
    if not msg_ids:
        print(json.dumps({"ok": True, "messages": [], "note": "no recent messages"}))
        mail.logout()
        sys.exit(0)
    
    # Get the 10 most recent
    msg_ids = msg_ids[-10:]
    
    inbox = []
    for mid in reversed(msg_ids):
        status, data = mail.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (From Subject Date)] BODY.PEEK[TEXT])")
        if status != "OK":
            continue
        
        # Parse headers
        raw = data[0][1] if isinstance(data[0], tuple) else b""
        msg = email.message_from_bytes(raw) if raw else None
        
        from_addr = str(msg["From"] or "(unknown)")
        subject = str(decode_header(msg["Subject"] or "(no subject)")[0][0])
        if isinstance(subject, bytes):
            subject = subject.decode("utf-8", errors="replace")
        date_str = str(msg["Date"] or "")
        
        # Get snippet from body (second part of fetch)
        body_data = b""
        if len(data) > 1 and isinstance(data[1], tuple):
            body_data = data[1][1]
        
        snippet = ""
        if body_data:
            try:
                body_text = body_data.decode("utf-8", errors="replace")
                snippet = body_text[:300].replace("\r", " ").replace("\n", " ").strip()
            except:
                snippet = str(body_data[:200])
        
        inbox.append({
            "id": mid.decode(),
            "from": from_addr,
            "subject": subject,
            "date": date_str,
            "snippet": snippet,
            "account": EMAIL,
        })
    
    mail.logout()
    print(json.dumps({"ok": True, "messages": inbox, "count": len(inbox)}))
    
except imaplib.IMAP4.error as e:
    err = str(e)
    # Try with app password hint
    print(json.dumps({"error": f"IMAP login failed: {err}", "hint": "May need app password if 2FA is enabled"}))
except Exception as e:
    print(json.dumps({"error": f"IMAP error: {e}"}))
