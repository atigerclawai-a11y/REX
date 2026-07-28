#!/usr/bin/env python3
"""Fetch reservation emails via IMAP."""
import json, imaplib, email, sys
from email.header import decode_header

with open('/Users/mainsobhelper/.rex_gmail_imap.json') as f:
    creds = json.load(f)

mail = imaplib.IMAP4_SSL('imap.gmail.com')
mail.login(creds['email'], creds['app_password'])
mail.select('INBOX')

# Get last 30 messages
result, data = mail.search(None, 'ALL')
all_ids = data[0].split()
recent = all_ids[-30:]

print(f'Scanning last 30 of {len(all_ids)} total messages for reservation emails...')
matches = []
for mid in reversed(recent):
    res, hdr_data = mail.fetch(mid, '(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])')
    raw = hdr_data[0][1].decode(errors='replace')
    subj_match = [l[9:] for l in raw.split('\r\n') if l.lower().startswith('subject:')]
    subject = subj_match[0].strip() if subj_match else ''
    if 'reservation' in subject.lower():
        matches.append(mid)
        from_match = [l[6:] for l in raw.split('\r\n') if l.lower().startswith('from:')]
        sender = from_match[0].strip() if from_match else ''
        date_match = [l[6:] for l in raw.split('\r\n') if l.lower().startswith('date:')]
        date = date_match[0].strip() if date_match else ''
        print(f'MATCH: {mid.decode()} | {subject} | {sender} | {date}')

print(f'\nFound {len(matches)} matching emails. Fetching full bodies...')

for mid in matches:
    res, msg_data = mail.fetch(mid, '(RFC822)')
    raw = msg_data[0][1]
    msg = email.message_from_bytes(raw)
    
    body = ''
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct in ('text/plain', 'text/html'):
                payload = part.get_payload(decode=True)
                try:
                    body = payload.decode()
                except:
                    body = payload.decode('latin-1')
                if ct == 'text/plain':
                    break
    else:
        payload = msg.get_payload(decode=True)
        try:
            body = payload.decode()
        except:
            body = payload.decode('latin-1')
    
    print(f'\n===== EMAIL {mid.decode()} =====')
    print(body[:3000])
    print('===== END =====')

mail.logout()
