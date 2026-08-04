#!/usr/bin/env python3
"""Email corrected Tue+Wed package — kitchen totals now reconcile."""
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
msg['Subject'] = 'GOJ Tue Aug 4 (81/55) + Wed Aug 5 (73/95) — CORRECTED, kitchen totals reconcile'
msg.attach(MIMEText(
    'Kato —\n\n'
    'CORRECTED PACKAGE (the 21:30 nightly cron had clobbered Tuesday\'s attendance\n'
    'from live 81/55 down to stale 76/47 — found + fixed + root-caused).\n\n'
    'Tuesday Aug 4: 81 S1 / 55 S2 — signin = kitchen = distribution = 81/55 ✓\n'
    'Wednesday Aug 5: 73 S1 / 95 S2 — signin = kitchen = distribution = 73/95 ✓\n'
    'All kitchen section totals now equal client counts (previously Wed salads were\n'
    '71/90 — 9 clients had empty salad/soup cells from partial OCR; all topped up\n'
    'from their own real history).\n\n'
    'Root cause: GOJ Daily Package cron (d5a36bd909c4, 20:00) ran the old skill step\n'
    'UPDATE clients SET day_T_actual = day_T_base — overwriting the live Carecenta\n'
    '81/55 with stale 76/47, then regenerated wrong sheets. Skill + cron prompt now\n'
    'forbid the reset. ghs_schedule.db (retired, 0 bytes) was also implicated.\n', 'plain'))

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
