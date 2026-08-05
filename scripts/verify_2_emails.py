#!/usr/bin/env python3
"""Verify both emails landed."""
import imaplib
import json
import os

creds = json.load(open(os.path.expanduser('~/.rex_gmail_imap.json')))
USER = creds.get('user') or creds.get('email')
PASS = creds.get('password') or creds.get('app_password')

M = imaplib.IMAP4_SSL('imap.gmail.com')
M.login(USER, PASS)
M.select('INBOX')
for subj in ['CORRECTED (102/47', 'UNREADABLE docs']:
    typ, data = M.search(None, 'SUBJECT', f'"{subj}"')
    print(f'{subj}: {"FOUND" if data[0] else "not found"}')
M.logout()
