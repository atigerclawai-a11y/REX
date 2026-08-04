#!/usr/bin/env python3
"""Broader check: Sent folder + INBOX search by date for the piece emails."""
import imaplib
import json
import os

creds = json.load(open(os.path.expanduser('~/.rex_gmail_imap.json')))
USER = creds.get('user') or creds.get('email')
PASS = creds.get('password') or creds.get('app_password')

m = imaplib.IMAP4_SSL('imap.gmail.com')
m.login(USER, PASS)

# check Sent
for box in ['"[Gmail]/Sent Mail"', 'Sent']:
    try:
        typ, data = m.select(box)
        if typ == 'OK':
            print(f'--- {box}: {data[0].decode()} msgs ---')
            typ, ids = m.search(None, '(SINCE "3-Aug-2026")')
            idl = ids[0].split()
            print(f'  since Aug 3: {len(idl)} emails')
            for i in idl[-8:]:
                typ, msg = m.fetch(i, '(BODY.PEEK[HEADER.FIELDS (SUBJECT)])')
                subj = msg[0][1].decode('utf-8', 'ignore').replace('\r', '').replace('\n', ' ')
                print(f'  {subj[:110]}')
            break
    except Exception as e:
        print(f'  {box}: {e}')

# INBOX search by date
m.select('INBOX')
typ, ids = m.search(None, '(SINCE "3-Aug-2026")')
idl = ids[0].split()
print(f'\nINBOX since Aug 3: {len(idl)} emails')
for i in idl[-10:]:
    typ, msg = m.fetch(i, '(BODY.PEEK[HEADER.FIELDS (SUBJECT)])')
    subj = msg[0][1].decode('utf-8', 'ignore').replace('\r', '').replace('\n', ' ')
    print(f'  {subj[:110]}')
m.logout()
