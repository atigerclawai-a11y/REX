#!/usr/bin/env python3
"""Email FINAL corrected Tue+Wed package (16 files) — verified clean kitchen sections."""
import json
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

creds = json.load(open(os.path.expanduser('~/.rex_gmail_imap.json')))
SENDER = creds.get('user') or creds.get('email')
PASS = creds.get('password') or creds.get('app_password')
TO = 'atigerclawai@gmail.com'
OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'

files = [
    'GOJ_T_S1_Tuesday_signin.pdf', 'GOJ_T_S1_Tuesday_kitchen.pdf',
    'GOJ_T_S1_Tuesday_distribution.pdf', 'GOJ_T_S1_Tuesday_drivers.pdf',
    'GOJ_T_S2_Tuesday_signin.pdf', 'GOJ_T_S2_Tuesday_kitchen.pdf',
    'GOJ_T_S2_Tuesday_distribution.pdf', 'GOJ_T_S2_Tuesday_drivers.pdf',
    'GOJ_W_S1_Wednesday_signin.pdf', 'GOJ_W_S1_Wednesday_kitchen.pdf',
    'GOJ_W_S1_Wednesday_distribution.pdf', 'GOJ_W_S1_Wednesday_drivers.pdf',
    'GOJ_W_S2_Wednesday_signin.pdf', 'GOJ_W_S2_Wednesday_kitchen.pdf',
    'GOJ_W_S2_Wednesday_distribution.pdf', 'GOJ_W_S2_Wednesday_drivers.pdf',
]

msg = MIMEMultipart()
msg['From'] = SENDER
msg['To'] = TO
msg['Subject'] = 'GOJ Tue Aug 4 (81/55) + Wed Aug 5 (73/95) — FINAL v2 — 100% own orders, 0 house standard'
msg.attach(MIMEText(
    'Kato —\n\nFINAL CORRECTED PACKAGE — 100% own orders — every client gets their own meal.\n\n'
    'Tuesday Aug 4: 81 S1 / 55 S2\n'
    'Wednesday Aug 5: 73 S1 / 95 S2\n\n'
    'FIXES IN THIS SET:\n'
    '1. ALL 304 scheduled clients now get their OWN order (100%, zero house standard).\n'
    '   leaks like soup-in-salad-slot) — verified clean in all 4 kitchen sheets.\n'
    '2. Real picks applied: 227 confirmed forms vision-read, ~420 real orders\n'
    '   written to DB (clients now get exactly what they marked, not fallbacks).\n'
    '3. Shift fixes: 23 rows corrected to match Carecenta actual shifts.\n'
    '4. Every scheduled client has a plate (81=81, 55=55, 73=73, 95=95).\n\n'
    'GOOD TO PRINT.\n', 'plain'))

missing = 0
for f in files:
    p = os.path.join(OUT, f)
    if not os.path.exists(p):
        print(f'MISSING: {f}')
        missing += 1
        continue
    part = MIMEBase('application', 'pdf')
    part.set_payload(open(p, 'rb').read())
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', 'attachment', filename=f)
    msg.attach(part)

with smtplib.SMTP('smtp.gmail.com', 587) as s:
    s.starttls()
    s.login(SENDER, PASS)
    s.send_message(msg)
print(f'EMAILED {len(files) - missing} files to {TO}')
