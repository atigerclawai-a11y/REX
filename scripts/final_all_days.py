#!/usr/bin/env python3
"""Final verification: emails landed + all day counts match Carecenta."""
import imaplib
import json
import os
import sqlite3

creds = json.load(open(os.path.expanduser('~/.rex_gmail_imap.json')))
USER = creds.get('user') or creds.get('email')
PASS = creds.get('password') or creds.get('app_password')

M = imaplib.IMAP4_SSL('imap.gmail.com')
M.login(USER, PASS)
M.select('INBOX')
typ, data = M.search(None, 'SUBJECT', '"CORRECTED (88/61"')
print(f'Thu/Fri corrected email: {"FOUND" if data[0] else "not found"}')
M.logout()

print('\n=== ALL DAYS vs CARECENTA TRUTH ===')
a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
for col, label, truth in [('day_T_actual', 'TUE Aug4', '81/55=136'),
                          ('day_W_actual', 'WED Aug5', '73/96=169'),
                          ('day_TH_actual', 'THU Aug6', '88/61=149'),
                          ('day_F_actual', 'FRI Aug7', '96/103=199')]:
    s1 = a.execute(f"SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=1").fetchone()[0]
    s2 = a.execute(f"SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=2").fetchone()[0]
    match = '✅' if f'{s1}/{s2}' == truth.split('=')[0] else '⚠️'
    print(f'  {match} {label}: {s1}/{s2} (truth {truth})')
a.close()
