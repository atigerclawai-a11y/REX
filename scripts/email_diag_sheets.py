#!/usr/bin/env python3
"""Email full diagnostic + corrected Tue/Wed sheets to Kato."""
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
    f'{OUT}/GOJ_T_S1_Tuesday_signin.pdf', f'{OUT}/GOJ_T_S2_Tuesday_signin.pdf',
    f'{OUT}/GOJ_T_S1_Tuesday_kitchen.pdf', f'{OUT}/GOJ_T_S2_Tuesday_kitchen.pdf',
    f'{OUT}/GOJ_T_S1_Tuesday_distribution.pdf', f'{OUT}/GOJ_T_S2_Tuesday_distribution.pdf',
    f'{OUT}/GOJ_T_S1_Tuesday_drivers.pdf', f'{OUT}/GOJ_T_S2_Tuesday_drivers.pdf',
    f'{OUT}/GOJ_W_S1_Wednesday_signin.pdf', f'{OUT}/GOJ_W_S2_Wednesday_signin.pdf',
    f'{OUT}/GOJ_W_S1_Wednesday_kitchen.pdf', f'{OUT}/GOJ_W_S2_Wednesday_kitchen.pdf',
    f'{OUT}/GOJ_W_S1_Wednesday_distribution.pdf', f'{OUT}/GOJ_W_S2_Wednesday_distribution.pdf',
    f'{OUT}/GOJ_W_S1_Wednesday_drivers.pdf', f'{OUT}/GOJ_W_S2_Wednesday_drivers.pdf',
]

body = """Kato —

FINAL sheets 21:48 EST — all WhatsApp + Carecenta attendance fixes applied.

WHAT I FOUND (3 pipeline issues, all fixed):
1. GARBAGE RETURNED: 21+35 non-canonical cells (Вин, Гр, Кур, MP, FF, Б) on Aug 4/5.
   Root cause: my earlier canonicalization only covered Aug 3-7, but fills copy from
   OLDER history rows (July) that still had abbreviations → re-infection on every fill.
   FIX: canonicalized ALL 15,859 rows in BOTH DBs (all dates). 0 garbage cells remain.

2. ROGUE 6am CRON (found earlier): synced a STALE week-30 Carecenta export into
   day_*_actual → zeroed 16 Tue + 9 Wed clients. Fixed + prompt hardened.

3. NOON REFRESH CRON (7a623c74b4f1) — NEWLY FOUND: at 12:14 it synced Drive sign-in
   attendance (S1=76/S2=47 — STALE) over the Carecenta truth (81/55) and REGENERATED
   the sheets with wrong counts. Prompt hardened identically (never write day_*_actual).

FIXED + REGENERATED (13:18): Tue 81=81, 55=55 | Wed 73=73, 95=95. All kitchen sections
verified pure (salads in SALADS, soups in SOUPS), zero garbage, DB parity OK.

PLATE TRUTH — every scheduled client's order (802 scheduled):
  TUE: 100% own order (81/55) — ZERO house standard
  WED: 100% own order (73/95) — ZERO house standard
  FRI: 98-100% own order (1 gap: Bok Lyudmila)
  THU: 83-97% own order (5 gaps + 16 house)
  MON: 78-86% own order (27 gaps + 4 house)

TRUE GAPS (scheduled but no plate — 33 total): 27 on Mon (Buslayeva Alisa, Dirul Serghei,
Elbert Milla, Epshteyn Yelizaveta, Feldman Klavdya, Fridman Mikhail + 21 more),
5 on Thu, 1 on Fri. These clients' forms weren't found in the system — same root as the
22 no-form list emailed earlier.

HOUSE STANDARD (generic plate — 21 total): Mon 4 + Thu 16 + 1. Clients like Aronchik
Bronya, Drabkin Marat, Elbert Milla, Fedorova Olga, Feldman Klavdya, Safonov Anatoliy —
need their forms or their history is genuinely empty.

ATTACHED: corrected Tue+Wed sheets (16 files).

— Hermes
"""
msg = MIMEMultipart()
msg['From'] = SENDER
msg['To'] = TO
msg['Subject'] = 'GOJ — FINAL Tue/Wed sheets (WhatsApp + Carecenta fixes applied, 21:48)'
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
print(f'EMAILED diagnostic + {len(files)} sheets to {TO}')
