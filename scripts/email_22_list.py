#!/usr/bin/env python3
"""Email the 22 attending no-form clients list to Kato for physical-form check."""
import json
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

creds = json.load(open(os.path.expanduser('~/.rex_gmail_imap.json')))
SENDER = creds.get('user') or creds.get('email')
PASS = creds.get('password') or creds.get('app_password')
TO = 'atigerclawai@gmail.com'

names22 = ['Bolotin Marina (Wed S2)', 'Dovgalyuk Zelda (Tue S2)', 'Gamkrelidze Mikhail (Wed S2)',
           'Krayz Raisa (Tue S1)', 'Lazovskiy Lina (Wed S2)', 'Lazovskiy Valeriy (Wed S2)',
           'Matanseva Ofelia (Tue S2)', 'Mikhaylova Sofiya (Tue S1, Wed S1)',
           'Minogina Ninel (Wed S2)', 'Nikolaeva Galina (Wed S1)', 'Safonov Anatoliy (Tue S1)',
           'Sekh Stefaniia (Tue S1)', 'Shadkhan Bella (Tue S1)', 'Shkolnik Betya (Tue S1)',
           'Shteyman Faina (Tue S2, Wed S2)', 'Shumaeva Anna (Wed S1)', 'Shvayko Nelli (Wed S1)',
           'Umanskaya Yelena (Wed S2)', 'Volov Boris (Tue S2)', 'Yermakov Marat (Wed S1)',
           'Zabizhin Grigoriy (Tue S1)', 'Zhelabovska Nadia (Wed S2)']

body = """Kato —

22 scheduled clients this week have NO form in the system. I searched every source
(matched table, unreadable manifest, focr reads, extraction files, intake dirs) —
their forms were never scanned in, or not returned.

They currently get their OWN most recent order (fallback) — not house standard.

If you have their physical forms, I'll rescan + vision-read them and get real picks.

Tue Aug 4 + Wed Aug 5 attending, no form found:
""" + '\n'.join(f'  • {n}' for n in names22) + """

— Hermes
"""

msg = MIMEMultipart()
msg['From'] = SENDER
msg['To'] = TO
msg['Subject'] = 'GOJ — 22 clients with NO form this week (Tue/Wed) — do you have their forms?'
msg.attach(MIMEText(body, 'plain'))

with smtplib.SMTP('smtp.gmail.com', 587) as s:
    s.starttls()
    s.login(SENDER, PASS)
    s.send_message(msg)
print(f'emailed 22-client list to {TO}')
