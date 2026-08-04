#!/usr/bin/env python3
"""Email the FINAL matched table (197 forms, 100% matched) to Kato."""
import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

rows = json.load(open('/tmp/matched_table_final.json'))

# table with original numbering restored for PDF cross-reference? No — new numbering
# matches the PDFs #1-#232... but we EXCLUDED 35 forms, so PDF numbers ≠ table numbers!
# The PDFs still carry the ORIGINAL 232 numbering. Map back: build doc+page → old #.
MANIFEST = json.load(open('/tmp/unreadable_full_manifest.json'))
# original manifest numbering (before excludes) is what's printed in the PDFs
# The PDFs were built from the ORIGINAL manifest (232 forms) — numbering F001-F232.
# So each row's PDF number = its manifest n.
old_n_by_docpage = {(m['doc'], m['page']): m['n'] for m in MANIFEST}

lines = ['# | name | source']
for r in rows:
    old = old_n_by_docpage.get((r['doc'], r['page']))
    lines.append(f"{old} | {r['match']} | {r['doc'][:15]} p{r['page']}")
table = '\n'.join(lines)

creds = json.load(open(os.path.expanduser('~/.rex_gmail_imap.json')))
SENDER = creds.get('user') or creds.get('email')
PASS = creds.get('password') or creds.get('app_password')
TO = 'atigerclawai@gmail.com'

msg = MIMEMultipart()
msg['From'] = SENDER
msg['To'] = TO
msg['Subject'] = f'GOJ unreadable forms — ALL {len(rows)} matched (197/197) — reply with wrong numbers only'
msg.attach(MIMEText(
    f'Kato —\n\nALL {len(rows)} unreadable forms now have a roster match (100%).\n'
    f'Numbers refer to the PDFs I sent (#1-#232). Reply with ONLY the numbers that are wrong,\n'
    f'like "12, 45, 200" — or "all correct".\n\n{table}\n', 'plain'))

with smtplib.SMTP('smtp.gmail.com', 587) as s:
    s.starttls()
    s.login(SENDER, PASS)
    s.send_message(msg)
print(f'EMAILED matched table ({len(rows)} rows) to {TO}')
