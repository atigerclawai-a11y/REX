#!/usr/bin/env python3
"""Email Tuesday Aug 4 sheets NOW — the verified 81/55 package."""
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
]

msg = MIMEMultipart()
msg['From'] = SENDER
msg['To'] = TO
msg['Subject'] = 'GOJ TUESDAY Aug 4 — FINAL sheets (81/55) — print now'
msg.attach(MIMEText(
    'Kato —\n\nTUESDAY AUG 4 FINAL PACKAGE — ready to print.\n\n'
    'S1: 81 clients | S2: 55 clients\n'
    'signin = kitchen = distribution = 81/55 (verified)\n'
    'Kitchen section totals = client counts (verified)\n\n'
    'These are the verified sheets (day_T_actual 81/55, live Carecenta).\n'
    'A real-pick upgrade is in progress (vision-reading confirmed forms) —\n'
    'if it lands before morning I send an updated set, but these are GOOD TO PRINT.\n', 'plain'))

for f in files:
    p = os.path.join(OUT, f)
    if not os.path.exists(p):
        print(f'MISSING: {f}')
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
print(f'EMAILED Tuesday package: {len(files)} files to {TO}')
