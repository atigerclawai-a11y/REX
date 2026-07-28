#!/usr/bin/env python3
import imaplib, email, json, ssl, socket, re
socket.setdefaulttimeout(10)
ctx = ssl.create_default_context()
try:
    mail = imaplib.IMAP4_SSL('imap.gmail.com', 993, ssl_context=ctx, timeout=10)
    mail.login('atigerclawai@gmail.com', 'uxemapqvhkndgmsv')
    mail.select('INBOX')
    
    # Search for reservation emails from olympusbbg
    status, msgs = mail.search(None, 'FROM "olympusbbg" SUBJECT "Reservation"')
    msg_ids = msgs[0].split() if msgs[0] else []
    
    results = []
    for mid in msg_ids:
        status, data = mail.fetch(mid, '(BODY.PEEK[])')
        if status != 'OK': continue
        for part in data:
            if isinstance(part, tuple):
                raw = part[1]
                msg = email.message_from_bytes(raw)
                from_addr = str(msg['From'] or '')
                subject = str(msg['Subject'] or '')
                date_str = str(msg['Date'] or '')
                
                body = ''
                if msg.is_multipart():
                    for p in msg.walk():
                        if p.get_content_type() == 'text/plain':
                            try:
                                body = p.get_payload(decode=True).decode('utf-8', errors='replace')
                            except:
                                pass
                            break
                else:
                    try:
                        body = msg.get_payload(decode=True).decode('utf-8', errors='replace')
                    except:
                        pass
                
                results.append({
                    'id': mid.decode(),
                    'from': from_addr,
                    'subject': subject,
                    'date': date_str,
                    'body': body[:2000]
                })
    
    mail.logout()
    print(json.dumps({'ok': True, 'count': len(results), 'messages': results}))
except Exception as e:
    print(json.dumps({'error': str(e)[:300]}))
