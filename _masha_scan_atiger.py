#!/usr/bin/env python3
import imaplib, email, json, ssl, socket
socket.setdefaulttimeout(10)
ctx = ssl.create_default_context()
try:
    mail = imaplib.IMAP4_SSL('imap.gmail.com', 993, ssl_context=ctx, timeout=10)
    mail.login('atigerclawai@gmail.com', 'uxemapqvhkndgmsv')
    mail.select('INBOX')
    # Search broadly: owner.com, reservation, booking, olympusbbg
    results = {}
    for query in ['FROM "owner.com"', 'SUBJECT "reservation"', 'SUBJECT "booking"', 'SUBJECT "owner.com"', 'TO "olympusbbg"', 'FROM "olympusbbg"']:
        status, messages = mail.search(None, query)
        ids = messages[0].split()[-10:] if messages[0] else []
        if ids:
            results[query] = len(ids)
    # Also get last 5 messages regardless
    status, msgs = mail.search(None, 'ALL')
    all_ids = msgs[0].split()[-5:] if msgs[0] else []
    recent = []
    for mid in reversed(all_ids):
        status, data = mail.fetch(mid, '(BODY.PEEK[HEADER.FIELDS (From Subject Date)] BODY.PEEK[TEXT])')
        if status != 'OK': continue
        raw = data[0][1] if data[0] else b''
        msg = email.message_from_bytes(raw) if isinstance(raw, bytes) else None
        if not msg: continue
        body = b''
        if len(data) > 1 and data[1] and isinstance(data[1], tuple): body = data[1][1] or b''
        snippet = body.decode('utf-8', errors='replace')[:200] if body else ''
        recent.append({'from': str(msg['From'] or ''), 'subject': str(msg['Subject'] or ''), 'date': str(msg['Date'] or ''), 'snippet': snippet})
    mail.logout()
    print(json.dumps({'ok': True, 'search_counts': results, 'recent_5': recent}))
except Exception as e:
    print(json.dumps({'error': str(e)[:300]}))
