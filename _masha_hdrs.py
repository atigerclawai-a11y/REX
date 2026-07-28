#!/usr/bin/env python3
import imaplib, email, json, ssl, socket
socket.setdefaulttimeout(10)
ctx = ssl.create_default_context()
try:
    mail = imaplib.IMAP4_SSL('imap.gmail.com', 993, ssl_context=ctx, timeout=10)
    mail.login('atigerclawai@gmail.com', 'uxemapqvhkndgmsv')
    mail.select('INBOX')
    
    # Get last 20 message IDs
    status, msgs = mail.search(None, 'ALL')
    all_ids = msgs[0].split()[-20:] if msgs[0] else []
    
    recent = []
    for mid in reversed(all_ids[-10:]):
        status, data = mail.fetch(mid, '(BODY.PEEK[HEADER.FIELDS (From Subject Date)])')
        if status != 'OK': continue
        for part in data:
            if isinstance(part, tuple):
                raw = part[1]
                msg = email.message_from_bytes(raw)
                recent.append({
                    'from': str(msg['From'] or ''),
                    'subject': str(msg['Subject'] or ''),
                    'date': str(msg['Date'] or '')
                })
                break
    
    mail.logout()
    print(json.dumps({'ok': True, 'count': len(recent), 'messages': recent}))
except Exception as e:
    print(json.dumps({'error': str(e)[:300]}))
