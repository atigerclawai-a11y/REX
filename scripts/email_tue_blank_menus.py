#!/usr/bin/env python3
"""Email Tuesday blank menus (S1 81 / S2 55) to Kato."""
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
    f'{OUT}/Menus_Tue_Aug04_S1_LIVE.pdf',
    f'{OUT}/Menus_Tue_Aug04_S2_LIVE.pdf',
]

msg = MIMEMultipart()
msg['From'] = SENDER
msg['To'] = TO
msg['Subject'] = 'GOJ — BLANK MENUS Tuesday Aug 4 (S1 81 / S2 55) — print-ready'
body = """Kato —

Tuesday blank menus, split by shift, print-ready:

• Menus_Tue_Aug04_S1_LIVE.pdf — 81 clients (162pp)
• Menus_Tue_Aug04_S2_LIVE.pdf — 55 clients (110pp)

Format: client name top-left, Week #32 (week of 2026-08-03),
4-digit ID in footer ([ID 0428]), QR bottom-right clear band.
Roster = auth day_T_actual 81/55 (matches the sign-in/kitchen sheets).

— Hermes
"""
msg.attach(MIMEText(body, 'plain'))
for f in files:
    with open(f, 'rb') as fh:
        part = MIMEApplication(fh.read(), _subtype='pdf')
        part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(f))
        msg.attach(part)

with smtplib.SMTP('smtp.gmail.com', 587) as s:
    s.starttls()
    s.login(SENDER, PASS)
    s.send_message(msg)
print(f'EMAILED {len(files)} blank-menu PDFs to {TO}')
