#!/usr/bin/env python3
"""Verify final package email landed in INBOX."""
import imaplib
import json
import os

creds = json.load(open(os.path.expanduser('~/.rex_gmail_imap.json')))
USER = creds.get('user') or creds.get('email')
PASS = creds.get('password') or creds.get('app_password')

m = imaplib.IMAP4_SSL('imap.gmail.com')
m.login(USER, PASS)
m.select('INBOX')
typ, ids = m.search(None, '(SINCE "3-Aug-2026")')
idl = ids[0].split()
print(f'INBOX since Aug 3: {len(idl)} emails')
for i in idl[-6:]:
    typ, msg = m.fetch(i, '(BODY.PEEK[HEADER.FIELDS (SUBJECT)])')
    subj = msg[0][1].decode('utf-8', 'ignore').replace('\r', '').replace('\n', ' ')
    print(f'  {subj[:110]}')
m.logout()
