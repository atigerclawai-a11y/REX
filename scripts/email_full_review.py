#!/usr/bin/env python3
"""Email the complete 232-form unreadable review PDF to Kato."""
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
PDF = '/Users/mainsobhelper/Desktop/REX/garbled_review/GOJ_unreadable_forms_ALL_JUL27-31.pdf'

msg = MIMEMultipart()
msg['From'] = SENDER
msg['To'] = TO
msg['Subject'] = 'GOJ ALL unreadable forms Jul 27-31 — 232 forms, numbered (best guesses following)'
msg.attach(MIMEText(
    'Kato —\n\n'
    'Every unreadable form from the July 27-31 scans, 232 total, numbered #1-#232.\n'
    'Each page shows the client-name region of one form (top of the form).\n'
    'Reply with corrections in the format "#N = Correct Name" (or "all correct").\n'
    'My best guesses for each # are being OCR-read right now — a follow-up email\n'
    'with the full guess list is on the way.\n\n'
    'Once confirmed, I apply their real picks → 100% real-order coverage.\n', 'plain'))

part = MIMEBase('application', 'pdf')
part.set_payload(open(PDF, 'rb').read())
encoders.encode_base64(part)
part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(PDF))
msg.attach(part)

with smtplib.SMTP('smtp.gmail.com', 587) as s:
    s.starttls()
    s.login(SENDER, PASS)
    s.send_message(msg)
print(f'EMAILED {PDF} ({os.path.getsize(PDF)/1e6:.1f} MB) to {TO}')
