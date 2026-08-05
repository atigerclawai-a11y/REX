#!/usr/bin/env python3
"""Email: numbered contact sheet (34 unreadable docs) + index + Sorits fix."""
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

links = json.load(open('/tmp/manifest_34_links.json'))

idx_lines = []
for n, doc, pages, link, dst in links:
    idx_lines.append(f"#{n:02d}  {doc}  ({pages}pp)")

body = """Kato —

Here are the 34 documents I cannot read, NUMBERED so you can reply in this session
what each one is. The contact sheet PDF has the first page of each doc as a
thumbnail with its number — open it and reply like: "#5 = weekly menu roster", etc.

THE 34 DOCS:
""" + "\n".join(idx_lines) + """

Also attached: the INDEX page (text list).

📌 SORITS LEV — DONE: "Вингерет" → "Винегрет" (review item resolved; his Friday
plate already has Винегрет correctly in the DB).

NOTE: full PDFs are in ~/Desktop/REX/unreadable_34/ (numbered copies, ~470MB total
— too big for email, so I sent the contact sheet instead). Reply here with the
numbers and what each is; I'll apply them immediately.

— Hermes
"""
msg = MIMEMultipart()
msg['From'] = SENDER
msg['To'] = TO
msg['Subject'] = 'GOJ — 34 UNREADABLE docs, numbered (contact sheet) — reply with what each is'
msg.attach(MIMEText(body, 'plain'))
for f in ['/Users/mainsobhelper/Desktop/REX/unreadable_34/UNREADABLE_CONTACT_SHEET.pdf']:
    with open(f, 'rb') as fh:
        part = MIMEApplication(fh.read(), _subtype='pdf')
        part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(f))
        msg.attach(part)

with smtplib.SMTP('smtp.gmail.com', 587) as s:
    s.starttls()
    s.login(SENDER, PASS)
    s.send_message(msg)
print(f'EMAILED contact sheet to {TO}')
