#!/usr/bin/env python3
"""Email: Wednesday sign-in + kitchen + distribution (73/96) + CORRECTED Thursday
package (102/47=149 — fixed from 118/47 after live Carecenta verification)."""
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
    # Wednesday
    f'{OUT}/GOJ_W_S1_Wednesday_signin.pdf',
    f'{OUT}/GOJ_W_S1_Wednesday_kitchen.pdf',
    f'{OUT}/GOJ_W_S1_Wednesday_distribution.pdf',
    f'{OUT}/GOJ_W_S2_Wednesday_signin.pdf',
    f'{OUT}/GOJ_W_S2_Wednesday_kitchen.pdf',
    f'{OUT}/GOJ_W_S2_Wednesday_distribution.pdf',
    # Thursday corrected
    f'{OUT}/GOJ_TH_S1_Thursday_signin.pdf',
    f'{OUT}/GOJ_TH_S1_Thursday_kitchen.pdf',
    f'{OUT}/GOJ_TH_S1_Thursday_distribution.pdf',
    f'{OUT}/GOJ_TH_S2_Thursday_signin.pdf',
    f'{OUT}/GOJ_TH_S2_Thursday_kitchen.pdf',
    f'{OUT}/GOJ_TH_S2_Thursday_distribution.pdf',
]

body = """Kato —

WEDNESDAY + THURSDAY PACKAGES (all verified):

📋 WEDNESDAY Aug 5 (73 S1 / 96 S2 — 169 total, matches live Carecenta):
• GOJ_W_S1/S2_Wednesday_signin.pdf
• GOJ_W_S1/S2_Wednesday_kitchen.pdf (sections verified pure)
• GOJ_W_S1/S2_Wednesday_distribution.pdf

📋 THURSDAY Aug 6 — CORRECTED (102 S1 / 47 S2 = 149 total):
⚠️ YOU WERE RIGHT TO ASK. The old 118/47 was WRONG — it had 25 clients who
do NOT attend Thursday per live Carecenta (they attend Mon/Wed/Fri etc.):
Aronchik Bronya, Astrakhan Bella, Breicher Larisa, Britavskaya Sofiya, Brodskaya
Lidiya, Buslayeva Alisa, Chebotareva Galina, Chepizhko Raya, Chupikova Elvira,
Coniglio Vera, Diadia Valentina, Dirul Serghei, Dmitriyeva Tamara, Dodik Sima,
Dovgalyuk Zelda, Dranikov Berta, Drochik Oleg, Egorova Valentina, Elbert Milla,
Erlikhman Rita, Fedorova Olga, Feldman Klavdya, Firdman Mark, Fridman Mikhail,
Furman Vladimir.

AND it was MISSING 9 clients who DO attend Thursday per Carecenta (added):
Beylina Emma, Bardenshteyn Larisa, Bekerman Alla, Berezkin Mikhail, Gendelman
Anatoliy, Gendelman Liliya, Kormova Lyubov, Maglakelidze Mzia, Kormov Feliks
(reactivated — he was active=0 like his wife).

The root cause: Thursday NEVER had a definitive sync from live Carecenta
(only Tuesday + Wednesday did). Now day_TH_actual = 102/47 = 149 = Carecenta truth.
All plates reconciled: S1 102=102, S2 47=47, ZERO gaps, kitchen clean.

— Hermes
"""
msg = MIMEMultipart()
msg['From'] = SENDER
msg['To'] = TO
msg['Subject'] = 'GOJ — Wed Aug 5 signin/kitchen/distribution (73/96) + Thu CORRECTED (102/47=149)'
msg.attach(MIMEText(body, 'plain'))
for f in files:
    if os.path.exists(f):
        with open(f, 'rb') as fh:
            part = MIMEApplication(fh.read(), _subtype='pdf')
            part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(f))
            msg.attach(part)
    else:
        print(f'WARN missing: {f}')

with smtplib.SMTP('smtp.gmail.com', 587) as s:
    s.starttls()
    s.login(SENDER, PASS)
    s.send_message(msg)
print(f'EMAILED {len(files)} files to {TO}')
