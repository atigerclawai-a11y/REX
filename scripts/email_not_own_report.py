#!/usr/bin/env python3
"""Email Kato: (1) clients not receiving their order with reasons, (2) unreadable
menus status, (3) Aug 5 blank menus attached."""
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
]

body = """Kato —

1) CLIENTS NOT RECEIVING THEIR OWN ORDER — REASONS:

After topping up 270 incomplete plates from each client's own history, here is
the complete remaining list. Every client now has a FULL 4-cell plate; the only
ones not getting THEIR OWN order are:

=== MONDAY Aug 3 (past day) — 22 GAPS (no plate at all) + 4 HOUSE ===
  These clients' forms were NEVER scanned into the system (no extraction exists):
  GAPS S1: Buslayeva Alisa, Buziashvili Galina, Chebotareva Galina, Chernyatskay
    Polya, Diadia Valentina, Dirul Serghei, Dodik Sima, Drochik Oleg, Elensky
    Tamara, Epshtein Isaak, Epshteyn Yelizaveta, Feldman Klavdya, Fridman Mikhail,
    Korb Anna, Lodato Galina, Plotits Asya
  GAPS S2: Bakanova Lubov, Bakanurskiy Svetlana, Bok Lyudmila, Bolotin Marina,
    Shtaygman Yelena, Usach Mariya
  HOUSE: Dovgalyuk Zelda, Drabkin Marat, Furman Vladimir, Shadkhan Bella

=== THURSDAY Aug 6 — 1 HOUSE ===
  Hurlenia Leanid: no order history anywhere in the system (genuinely new/empty)

=== NOTE (resolved): ===
  Bok Lyudmila Fri — had plate in wrong shift (S1 vs S2), FIXED.
  All incomplete plates (missing side/salad/etc.) — topped up from each client's
  own history, ZERO remain on Tue/Wed/Thu/Fri.

2) UNREADABLE MENUS STATUS:
  • focr recovery STILL RUNNING (pid 70978) on the 34-doc manifest — producing
    nothing extractable ("no name/marks" — blue-ink forms focr can't read)
  • 232-form sweep already done: 190/232 names read via focr, remaining 42 via vision
  • Review queue: 1 pending (Sorits Lev — non-catalog dish "Вингерет")
  • The 22 Monday-gap clients above are NOT in any extraction or review set —
    their forms are either in the unreadable recovery docs or were never scanned

3) AUG 5 BLANK MENUS (attached):
  • Menus_Wed_Aug05_S1_LIVE.pdf — 73 clients (146pp)
  • Menus_Wed_Aug05_S2_LIVE.pdf — 96 clients (192pp)
  All with QR + 4-digit IDs, 0 missing.

— Hermes
"""
msg = MIMEMultipart()
msg['From'] = SENDER
msg['To'] = TO
msg['Subject'] = 'GOJ — Clients NOT receiving own order (reasons) + Aug 5 blank menus'
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
print(f'EMAILED report + {len(files)} menus to {TO}')
