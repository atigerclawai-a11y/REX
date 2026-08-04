#!/usr/bin/env python3
"""Verify the 5 review emails landed in Gmail INBOX (IMAP subject search)."""
import imaplib
import json
import os

creds = json.load(open(os.path.expanduser('~/.rex_gmail_imap.json')))
USER = creds.get('user') or creds.get('email')
PASS = creds.get('password') or creds.get('app_password')

m = imaplib.IMAP4_SSL('imap.gmail.com')
m.login(USER, PASS)
m.select('INBOX')

subjects = ['GOJ unreadable_Jul27', 'GOJ unreadable_Jul29', 'GOJ unreadable_Jul30',
            'GOJ unreadable_Jul31', 'GOJ ALL unreadable forms Jul 27-31']
for subj in subjects:
    typ, data = m.search(None, f'(SUBJECT "{subj}")')
    ids = data[0].split()
    print(f'{subj}: {len(ids)} email(s) in INBOX')
    for i in ids[-1:]:
        typ, msg = m.fetch(i, '(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)])')
        print(f'  {msg[0][1].decode()[:120]}')
m.logout()
