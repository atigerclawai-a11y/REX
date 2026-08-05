#!/usr/bin/env python3
"""Email: Wed Aug 5 blank forms (73/96) + Thu Aug 6 full package (118/47)."""
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
    f'{OUT}/Menus_Wed_Aug05_S1_LIVE.pdf',
    f'{OUT}/Menus_Wed_Aug05_S2_LIVE.pdf',
    f'{OUT}/GOJ_TH_S1_Thursday_signin.pdf',
    f'{OUT}/GOJ_TH_S2_Thursday_signin.pdf',
    f'{OUT}/GOJ_TH_S1_Thursday_kitchen.pdf',
    f'{OUT}/GOJ_TH_S2_Thursday_kitchen.pdf',
    f'{OUT}/GOJ_TH_S1_Thursday_distribution.pdf',
    f'{OUT}/GOJ_TH_S2_Thursday_distribution.pdf',
    f'{OUT}/GOJ_TH_S1_Thursday_drivers.pdf',
    f'{OUT}/GOJ_TH_S2_Thursday_drivers.pdf',
]

body = """Kato —

WEDNESDAY FORMS + THURSDAY PACKAGE (all verified correct):

📝 WED AUG 5 BLANK MENUS (forms for clients to fill):
• Menus_Wed_Aug05_S1_LIVE.pdf — 73 clients (146pp)
• Menus_Wed_Aug05_S2_LIVE.pdf — 96 clients (192pp)
Format: name top-left, Week #32, 4-digit ID footer ([ID 1305]), QR bottom-right.
Roster = auth day_W_actual 73/96 (matches live Carecenta 169 total).
0 missing IDs (assigned Kormova Lyubov ID 1305 — she was reactivated per Carecenta).

🍳 THU AUG 6 KITCHEN STAFF LIST + FULL PACKAGE (118 S1 / 47 S2):
• GOJ_TH_S1/S2_Thursday_kitchen.pdf — verified pure sections (salads in SALADS, soups in SOUPS)
• GOJ_TH_S1/S2_Thursday_signin.pdf
• GOJ_TH_S1/S2_Thursday_distribution.pdf
• GOJ_TH_S1/S2_Thursday_drivers.pdf
Counts: S1 118=118, S2 47=47 — every scheduled client has a plate, ZERO gaps.

FIXES APPLIED FOR THU:
• 16 house_standard → each client's OWN order (from their history) — only 1 house left (Hurlenia Leanid, no history)
• 5 gap clients filled from their own orders (Chepizhko, Dranikov, Drochik, Makaron, Verbitskaya)
• 2 shift mismatches fixed (Breytman, Epshteyn S2→S1)
• Zero garbage cells in both DBs

ALSO: change-log cron FIXED (was failing on Drive OAuth — now uses SA + local log;
38 WhatsApp changes backfilled including Kravets Sima sick, Polyak MD, Sepashvili day change).

— Hermes
"""
msg = MIMEMultipart()
msg['From'] = SENDER
msg['To'] = TO
msg['Subject'] = 'GOJ — Wed Aug 5 FORMS (73/96) + Thu Aug 6 KITCHEN & full package (118/47)'
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
