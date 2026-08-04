#!/usr/bin/env python3
"""Build + email the #N → best guess table from focr results, fuzzy-matched to roster."""
import json
import os
import smtplib
import sqlite3
from difflib import SequenceMatcher
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

GUESSES = '/tmp/unreadable_guesses.json'
MANIFEST = json.load(open('/tmp/unreadable_full_manifest.json'))
AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'

# roster names
con = sqlite3.connect(AUTH)
roster = [r[0] for r in con.execute("SELECT name FROM clients WHERE active=1")]
con.close()

def norm(s):
    return ' '.join(s.strip().lower().split())

def best_match(raw):
    """Fuzzy-match a raw focr name to the roster; return (name, score)."""
    if not raw:
        return (None, 0)
    n = norm(raw)
    # exact
    for r in roster:
        if norm(r) == n:
            return (r, 100)
    # surname-first match: "LAST FIRST" vs roster "First Last"
    parts = n.split()
    best, best_s = None, 0
    for r in roster:
        rn = norm(r)
        # token overlap
        rtoks = set(rn.split())
        ntoks = set(parts)
        inter = len(rtoks & ntoks)
        if inter == 0:
            continue
        # score: matched tokens / max tokens
        s = int(100 * inter / max(len(rtoks), len(ntoks)))
        # partial similarity bonus
        s += int(SequenceMatcher(None, n, rn).ratio() * 40)
        if s > best_s:
            best, best_s = r, s
    return (best, best_s)

results = json.load(open(GUESSES))
# merge vision fixes — they win over focr nulls (read with Claude vision)
VF = '/tmp/vision_fixes.json'
if os.path.exists(VF):
    for k, v in json.load(open(VF)).items():
        results[k] = v
rows = []
for m in MANIFEST:
    n = m['n']
    raw = results.get(str(n)) or results.get(n)
    name, score = best_match(raw)
    rows.append((n, m['doc'], m['page'], raw, name, score))

named = sum(1 for r in rows if r[4])
print(f'total {len(rows)}, matched {named}, unmatched {len(rows) - named}')

# build table
lines = ['# | raw focr read | best guess | score', '--- | --- | --- | ---']
for n, doc, page, raw, name, score in rows:
    lines.append(f"{n} | {raw or '—'} | {name or '**UNKNOWN**'} | {score}%")
table = '\n'.join(lines)

creds = json.load(open(os.path.expanduser('~/.rex_gmail_imap.json')))
SENDER = creds.get('user') or creds.get('email')
PASS = creds.get('password') or creds.get('app_password')
TO = 'atigerclawai@gmail.com'

msg = MIMEMultipart()
msg['From'] = SENDER
msg['To'] = TO
msg['Subject'] = f'GOJ unreadable forms — best guesses ({named}/{len(rows)} matched) — reply with corrections'
msg.attach(MIMEText(
    f'Kato —\n\nBest-guess table for the 232 unreadable forms (matches the #N in the PDFs).\n'
    f'{named}/{len(rows)} fuzzy-matched to the roster. "UNKNOWN" needs your call.\n'
    f'Reply "#N = Correct Name" or "all correct" — I apply immediately.\n\n{table}\n', 'plain'))

with smtplib.SMTP('smtp.gmail.com', 587) as s:
    s.starttls()
    s.login(SENDER, PASS)
    s.send_message(msg)
print(f'EMAILED guess table to {TO}')
