#!/usr/bin/env python3
"""Verify the Tuesday blank menus email landed in INBOX."""
import imaplib
import json
import os

creds = json.load(open(os.path.expanduser('~/.rex_gmail_imap.json')))
USER = creds.get('user') or creds.get('email')
PASS = creds.get('password') or creds.get('app_password')

m = imaplib.IMAP4_SSL('imap.gmail.com')
m.login(USER, PASS)
m.select('INBOX')
typ, ids = m.search(None, '(SINCE "4-Aug-2026")')
idl = ids[0].split()
print(f'INBOX today: {len(idl)} emails')
for i in idl[-8:]:
    typ, msg = m.fetch(i, '(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)])')
    raw = msg[0][1].decode('utf-8', 'ignore').replace('\r', '').strip()
    for line in raw.splitlines():
        print(f'  {line[:110]}')
    print('  ---')
m.logout()
