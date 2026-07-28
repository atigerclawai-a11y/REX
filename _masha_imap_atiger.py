#!/usr/bin/env python3
"""Check Gmail via IMAP for atigerclawai — look for olympusbbg forwarded emails."""
import imaplib, email, json, ssl

EMAIL = "atigerclawai@gmail.com"
PASSWORD = "uxemapqvhkndgmsv"
IMAP_SERVER = "imap.gmail.com"

ctx = ssl.create_default_context()

try:
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, 993, ssl_context=ctx, timeout=15)
    mail.login(EMAIL, PASSWORD)
    mail.select("INBOX")
    
    status, messages = mail.search(None, "ALL")
    msg_ids = messages[0].split()[-20:]
    
    inbox = []
    for mid in reversed(msg_ids):
        try:
            status, data = mail.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (From Subject Date)] BODY.PEEK[TEXT])")
            if status != "OK": continue
            raw = data[0][1] if data[0] else b""
            msg = email.message_from_bytes(raw) if isinstance(raw, bytes) else None
            if not msg: continue
            from_addr = str(msg["From"] or "(unknown)")
            subject = str(msg["Subject"] or "(no subject)")
            date_str = str(msg["Date"] or "")
            body_data = b""
            if len(data) > 1 and data[1] and isinstance(data[1], tuple):
                body_data = data[1][1] if data[1][1] else b""
            snippet = ""
            if body_data:
                try: snippet = body_data.decode("utf-8", errors="replace")[:500]
                except: pass
            inbox.append({"from": from_addr, "subject": subject, "date": date_str, "snippet": snippet})
        except Exception as e:
            inbox.append({"error": str(e)[:100]})
    
    mail.logout()
    print(json.dumps({"ok": True, "count": len(inbox), "messages": inbox}))
except imaplib.IMAP4.error as e:
    print(json.dumps({"error": f"IMAP failed: {e}"}))
except Exception as e:
    print(json.dumps({"error": str(e)}))
