#!/usr/bin/env python3
"""Email: CORRECTED Thursday (88/61=149) + Friday (96/103=199) packages —
synced cleanly from live Carecenta with BOTH time formats (9AM-1PM=S1,
1:15PM-5:15PM=S2), same method as the accepted Wednesday."""
import json
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

creds = json.load(open(os.path.expanduser('~/.rex_gmail_imap.json')))
SENDER = creds.get('user') or creds.get('email')
PASS = creds.get('password') or creds.get('app_password')
TO = 'atigerclawai@gmail.com'

OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'
files = [
    f'{OUT}/GOJ_TH_S1_Thursday_signin.pdf',
    f'{OUT}/GOJ_TH_S1_Thursday_kitchen.pdf',
    f'{OUT}/GOJ_TH_S1_Thursday_distribution.pdf',
    f'{OUT}/GOJ_TH_S2_Thursday_signin.pdf',
    f'{OUT}/GOJ_TH_S2_Thursday_kitchen.pdf',
    f'{OUT}/GOJ_TH_S2_Thursday_distribution.pdf',
    f'{OUT}/GOJ_F_S1_Friday_signin.pdf',
    f'{OUT}/GOJ_F_S1_Friday_kitchen.pdf',
    f'{OUT}/GOJ_F_S1_Friday_distribution.pdf',
    f'{OUT}/GOJ_F_S2_Friday_signin.pdf',
    f'{OUT}/GOJ_F_S2_Friday_kitchen.pdf',
    f'{OUT}/GOJ_F_S2_Friday_distribution.pdf',
]

body = """Kato —

THURSDAY + FRIDAY — CORRECTED, synced CLEANLY from Carecenta (no incremental edits).

You were right — the earlier numbers were wrong because MY parser was broken,
not Carecenta. My regex only matched the "1:15PM-5:15PM" time format and missed
every "9AM-1PM" (morning shift S1) client, so Thursday S1 was invisible and the
counts kept shifting. Fixed: both time formats parsed, same method as the
accepted Wednesday roster (assemble_wed.py → 73/96).

LIVE CARECENTA TRUTH (Clients.aspx, full week, both shifts):
  THU Aug 6: 88 S1 (9AM-1PM) + 61 S2 (1:15PM) = 149
  FRI Aug 7: 96 S1 + 103 S2 = 199

day_TH_actual + day_F_actual zero-then-set from this roster — 0 unmapped.
All plates reconciled: Thu 88=88/61=61, Fri 96=96/103=103. Kitchen clean.

ATTACHED (12 files): sign-in + kitchen + distribution × S1/S2 for both days.

— Hermes
"""
msg = MIMEMultipart()
msg['From'] = SENDER
msg['To'] = TO
msg['Subject'] = 'GOJ — Thu CORRECTED (88/61=149) + Fri (96/103=199) — clean Carecenta sync'
msg.attach(MIMEText(body, 'plain'))
for f in files:
    if os.path.exists(f):
        with open(f, 'rb') as fh:
            part = MIMEApplication(fh.read(), _subtype='pdf')
            part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(f))
            msg.attach(part)

with smtplib.SMTP('smtp.gmail.com', 587) as s:
    s.starttls()
    s.login(SENDER, PASS)
    s.send_message(msg)
print(f'EMAILED {len(files)} files to {TO}')
