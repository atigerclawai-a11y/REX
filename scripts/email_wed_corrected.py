#!/usr/bin/env python3
"""Email: corrected Wednesday Aug 5 package (73/96) — regenerated from Carecenta
truth + OCR data after killing the Drive leaks."""
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
files = [f'{OUT}/GOJ_W_S1_Wednesday_{k}.pdf' for k in ['signin', 'kitchen', 'distribution', 'drivers']] + \
        [f'{OUT}/GOJ_W_S2_Wednesday_{k}.pdf' for k in ['signin', 'kitchen', 'distribution', 'drivers']]

body = """Kato —

WEDNESDAY AUG 5 — CORRECTED PACKAGE (73 S1 / 96 S2 = 169, matches LIVE Carecenta).

You were right: the Drive files should never have been used after OCR. I found
and killed the leak — the 17:10 GOJ Daily Documents cron loaded a skill that
still said "Drive is the source of truth" and synced Drive sign-in/menu tabs
into the DB. That's what caused today's sign-in + food-log mistakes.

FIXED:
• All 4 generation crons (6am, noon, 17:10, 20:00) + the 3PM launchd scheduler
  now carry the HARD LAW: Drive = OUTPUT ONLY. Attendance = LIVE Carecenta,
  menus = OCR pipeline. --skip-preflight is mandatory everywhere.
• goj-kitchen-distribution + goj-operations skills rewritten with the
  superseding banner (same as goj-drive-first).
• Wed attendance restored 64/97 → 73/96 (Carecenta truth).
• Regenerated ALL 8 Wednesday PDFs from correct data — full reconciliation
  (73=73, 96=96), kitchen sections verified pure.

ATTACHED: sign-in + kitchen + distribution + drivers × S1/S2 (8 files).

— Hermes
"""
msg = MIMEMultipart()
msg['From'] = SENDER
msg['To'] = TO
msg['Subject'] = 'GOJ — Wed Aug 5 CORRECTED (73/96, Carecenta truth) — Drive leak killed'
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
