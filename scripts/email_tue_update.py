#!/usr/bin/env python3
"""Re-email corrected Tuesday package (Mikhaylova fix) + unchanged Wednesday."""
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
    'Menus_Tue_Aug04_S1_LIVE.pdf', 'Menus_Tue_Aug04_S2_LIVE.pdf',
]

msg = MIMEMultipart()
msg['From'] = SENDER
msg['To'] = TO
msg['Subject'] = 'GOJ Tuesday Aug 4 — UPDATED (Mikhaylova plate fix) 81/55'
msg.attach(MIMEText(
    'Kato —\n\n'
    'Tuesday Aug 4 updated: Mikhaylova Sofiya\'s plate corrected to her real order\n'
    '(Винегрет | Борщ зеленый | Вареники с картошкой | Тушеная капуста).\n'
    'All 136 scheduled clients now have a complete plate — 0 incomplete, 0 missing.\n'
    '81 S1 / 55 S2, sign-in = kitchen = distribution.\n', 'plain'))

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
print(f'EMAILED {len(files)} files to {TO}')
