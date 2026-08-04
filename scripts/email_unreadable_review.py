#!/usr/bin/env python3
"""Email the unreadable-forms review PDF to Kato."""
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
PDF = '/Users/mainsobhelper/Desktop/REX/garbled_review/GOJ_unreadable_forms_review_JUL27-28.pdf'

msg = MIMEMultipart()
msg['From'] = SENDER
msg['To'] = TO
msg['Subject'] = 'GOJ unreadable forms (30) — July 27 batch — my best guess per form'
body = (
    'Kato —\n\n'
    'Every form from your July 27-28 scan that the pipeline did NOT extract (30 forms).\n'
    'Each PDF page shows the form name region + MY BEST GUESS at the client (from focr OCR).\n\n'
    'IMPORTANT: these were readable all along — the sweep bug after the scripts wipe is why\n'
    'they never got extracted. Confirm/correct the names and I will apply them immediately.\n\n'
    'Quick list of my guesses:\n'
    '  1 Ivanova Liudmila   2 Bogat Svetlana   3 Gritshevsky Yosef\n'
    '  4 Radomyselskiy Semen 5 Shifrina Margarita 6 Fedorova Olga\n'
    '  7 Borshchevskaya Galina 8 Shvarts Edvard  9 Khalfina Aida\n'
    '  10 Rudoy Emma   11 Elbert Milla   12 Makaron Khaya\n'
    '  13 Levin Leonid  14 Chupikova Elvira  15 Shapiro Roza\n'
    '  16 Nirshberg Aron  17 Yemelyanova Alla  18 Mindich Aleksandr\n'
    '  19 Rukhlevich Svetlana  20 Slavinskiy Grigoriy  21 Palatnik Yelizaveta\n'
    '  22 Leybengrub Larisa  23 Rodava Iryna  24 Rodov Vladimir\n'
    '  25 Adyan Ludmila  26 Grinshpun Izrail  27 Prilutskaya Tatyana\n'
    '  28 Kovaleva Viktoriya  29 Bialkovska Maria  30 Posadova Liubov\n'
)
msg.attach(MIMEText(body, 'plain'))

part = MIMEBase('application', 'pdf')
part.set_payload(open(PDF, 'rb').read())
encoders.encode_base64(part)
part.add_header('Content-Disposition', 'attachment', filename='GOJ_unreadable_forms_review_JUL27-28.pdf')
msg.attach(part)

with smtplib.SMTP('smtp.gmail.com', 587) as s:
    s.starttls()
    s.login(SENDER, PASS)
    s.send_message(msg)
print(f'EMAILED {PDF} to {TO}')
