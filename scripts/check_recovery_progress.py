#!/usr/bin/env python3
"""Check recovery progress + count total unreadable forms across all docs."""
import json
import os
from pathlib import Path

REX = Path('/Users/mainsobhelper/Desktop/REX')
BASE = REX / 'blank_parse'

# is recovery still running?
lock = REX / '.page_guard_recover.lock'
if lock.exists():
    pid = lock.read_text().strip()
    alive = os.path.exists(f'/proc/{pid}') if os.path.exists('/proc') else True
    import subprocess
    r = subprocess.run(['ps', '-p', pid, '-o', 'pid=,command='], capture_output=True, text=True)
    print(f'lock pid={pid}: {"ALIVE" if r.returncode == 0 else "dead"} {r.stdout.strip()[:80]}')

# full manifest
m = REX / '.page_guard_recover.json'
docs = json.load(open(m))
if isinstance(docs, dict):
    docs = docs.get('docs', docs)
print(f'\nmanifest: {len(docs)} docs')

# extraction.json now present?
present = sum(1 for d in BASE.iterdir() if d.is_dir() and (d / 'extraction.json').exists())
print(f'blank_parse dirs with extraction.json: {present}')

# total expected forms vs extracted
total_exp = total_ext = 0
for d in sorted(BASE.iterdir()):
    if not d.is_dir():
        continue
    npng = len([f for f in d.glob('p*-*.png') if not f.name.startswith('pg')])
    ej = d / 'extraction.json'
    if ej.exists():
        data = json.load(open(ej))
        n = len(data) if isinstance(data, dict) else 0
    else:
        n = 0
    if npng:
        total_exp += npng // 2
        total_ext += n
print(f'TOTAL: {total_exp} expected forms, {total_ext} extracted → {total_exp - total_ext} unreadable/missing')
