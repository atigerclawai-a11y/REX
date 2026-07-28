#!/usr/bin/env python3
import imaplib, email, json, ssl, socket
socket.setdefaulttimeout(10)
ctx = ssl.create_default_context()
try:
    mail = imaplib.IMAP4_SSL('imap.gmail.com', 993, ssl_context=ctx, timeout=10)
    mail.login('atigerclawai@gmail.com', 'uxemapqvhkndgmsv')
    mail.select('INBOX')
    status, messages = mail.search(None, '(OR FROM "owner.com" TO "owner.com")')
    msg_ids = messages[0].split()[-5:] if messages[0] else []
    inbox = []
    for mid in reversed(msg_ids):
        status, data = mail.fetch(mid, '(BODY.PEEK[HEADER.FIELDS (From Subject Date)])')
        if status != 'OK': continue
        raw = data[0][1] if data[0] else b''
        msg = email.message_from_bytes(raw) if isinstance(raw, bytes) else None
        if not msg: continue
        inbox.append({'from': str(msg['From'] or ''), 'subject': str(msg['Subject'] or ''), 'date': str(msg['Date'] or '')})
    mail.logout()
    print(json.dumps({'ok': True, 'count': len(inbox), 'messages': inbox}))
except Exception as e:
    print(json.dumps({'error': str(e)[:300]}))
