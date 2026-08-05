#!/usr/bin/env python3
"""Verify the contact-sheet email landed in inbox."""
import json
import os
import imaplib
import email
from email.header import decode_header

creds = json.load(open(os.path.expanduser('~/.rex_gmail_imap.json')))
USER = creds.get('user') or creds.get('email')
PASS = creds.get('password') or creds.get('app_password')

M = imaplib.IMAP4_SSL('imap.gmail.com')
M.login(USER, PASS)
M.select('INBOX')
typ, data = M.search(None, 'SUBJECT', '"34 UNREADABLE"')
ids = data[0].split()
print(f'matching emails: {len(ids)}')
if ids:
    typ, msg_data = M.fetch(ids[-1], '(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])')
    raw = msg_data[0][1].decode(errors='ignore')
    print(raw[:300])
M.logout()
