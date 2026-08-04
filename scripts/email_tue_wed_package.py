#!/usr/bin/env python3
"""Email Tuesday + Wednesday complete package via IMAP SMTP (Gmail App Password)."""
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
    # Tuesday Aug 4 — 81/55
    'GOJ_T_S1_Tuesday_signin.pdf', 'GOJ_T_S1_Tuesday_kitchen.pdf',
    'GOJ_T_S1_Tuesday_distribution.pdf', 'GOJ_T_S1_Tuesday_drivers.pdf',
    'GOJ_T_S2_Tuesday_signin.pdf', 'GOJ_T_S2_Tuesday_kitchen.pdf',
    'GOJ_T_S2_Tuesday_distribution.pdf', 'GOJ_T_S2_Tuesday_drivers.pdf',
    # Wednesday Aug 5 — 73/95
    'GOJ_W_S1_Wednesday_signin.pdf', 'GOJ_W_S1_Wednesday_kitchen.pdf',
    'GOJ_W_S1_Wednesday_distribution.pdf', 'GOJ_W_S1_Wednesday_drivers.pdf',
    'GOJ_W_S2_Wednesday_signin.pdf', 'GOJ_W_S2_Wednesday_kitchen.pdf',
    'GOJ_W_S2_Wednesday_distribution.pdf', 'GOJ_W_S2_Wednesday_drivers.pdf',
    # Blank menus (shift-split, QR + IDs)
    'Menus_Tue_Aug04_S1_LIVE.pdf', 'Menus_Tue_Aug04_S2_LIVE.pdf',
    'Menus_Wed_Aug05_S1_LIVE.pdf', 'Menus_Wed_Aug05_S2_LIVE.pdf',
]

msg = MIMEMultipart()
msg['From'] = SENDER
msg['To'] = TO
msg['Subject'] = 'GOJ Tuesday Aug 4 (81/55) + Wednesday Aug 5 (73/95) sheets + blank menus — LIVE Carecenta'
body = (
    'Kato —\n\n'
    'Tuesday Aug 4 (from live Carecenta, dashboard-verified 81/55):\n'
    '  S1 signin/kitchen/distribution/drivers + S2 = 8 files\n'
    'Wednesday Aug 5 (live schedule times: 73 AM / 95 PM):\n'
    '  S1 signin/kitchen/distribution/drivers + S2 = 8 files\n'
    'Blank menus (shift-split, QR goj:cid|w|n, 4-digit IDs): Tue + Wed = 4 files\n\n'
    'All sign-in = kitchen = distribution exactly. Every scheduled client has a plate.\n'
    'Flags: Kormova Lyubov (Carecenta Wed PM but inactive in auth — excluded);\n'
    'Krutikov Aleksandr (Carecenta Wed AM, not in auth at all).\n'
)
msg.attach(MIMEText(body, 'plain'))

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
print(f'EMAILED {len(files)} files ({sum(os.path.getsize(os.path.join(OUT,f)) for f in files if os.path.exists(os.path.join(OUT,f)))//1048576} MB total) to {TO}')
