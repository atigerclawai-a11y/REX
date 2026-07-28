#!/usr/bin/env python3
"""Check Gmail inbox via IMAP for reservation emails — try atigerclawai@gmail.com"""
import imaplib, email, json, sys, ssl
from email.header import decode_header

EMAIL = "atigerclawai@gmail.com"
PASSWORD = "Hermes12345$"
IMAP_SERVER = "imap.gmail.com"

ctx = ssl.create_default_context()

try:
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, 993, ssl_context=ctx, timeout=15)
    mail.login(EMAIL, PASSWORD)
    mail.select("INBOX")
    
    # Get last 20 messages
    status, messages = mail.search(None, "ALL")
    if status != "OK":
        print(json.dumps({"ok": True, "messages": [], "note": "search failed"}))
        mail.logout()
        sys.exit(0)
    
    msg_ids = messages[0].split()
    if not msg_ids:
        print(json.dumps({"ok": True, "messages": []}))
        mail.logout()
        sys.exit(0)
    
    # Get the 10 most recent
    msg_ids = msg_ids[-10:]
    
    inbox = []
    for mid in reversed(msg_ids):
        try:
            status, data = mail.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (From Subject Date)] BODY.PEEK[TEXT])")
            if status != "OK":
                continue
            
            raw = data[0][1] if data[0] else b""
            msg = email.message_from_bytes(raw) if isinstance(raw, bytes) else None
            if not msg:
                continue
            
            from_addr = str(msg["From"] or "(unknown)")
            subject = str(msg["Subject"] or "(no subject)")
            date_str = str(msg["Date"] or "")
            
            body_data = b""
            if len(data) > 1 and data[1] and isinstance(data[1], tuple):
                body_data = data[1][1] if data[1][1] else b""
            
            snippet = ""
            if body_data:
                try:
                    body_text = body_data.decode("utf-8", errors="replace")
                    snippet = body_text[:300].replace("\r", " ").replace("\n", " ").strip()
                except:
                    snippet = ""
            
            inbox.append({
                "id": mid.decode(),
                "from": from_addr,
                "subject": subject,
                "date": date_str,
                "snippet": snippet,
            })
        except Exception as e:
            inbox.append({"id": mid.decode() if mid else "?", "error": str(e)[:100]})
    
    mail.logout()
    print(json.dumps({"ok": True, "messages": inbox, "count": len(inbox), "account": EMAIL}))
    
except imaplib.IMAP4.error as e:
    print(json.dumps({"error": f"IMAP login failed: {e}"}))
except Exception as e:
    print(json.dumps({"error": f"IMAP error: {e}"}))
