#!/usr/bin/env python3
"""Run focr on all 30 unreadable name-region crops + fuzzy-match to roster."""
import json
import os
import re
import subprocess
import sqlite3
from pathlib import Path

REX = Path('/Users/mainsobhelper/Desktop/REX')
GARBLED = REX / 'garbled_review'

# roster for fuzzy match
con = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
roster = [r[0] for r in con.execute("SELECT name FROM clients WHERE active=1")]
con.close()


def norm(n):
    return re.sub(r'[^a-z\'\- ]', '', n.lower()).strip()


results = []
pngs = sorted(GARBLED.glob('UNREAD_*.png'))
print(f'{len(pngs)} name crops to read via focr')
for i, png in enumerate(pngs, 1):
    r = subprocess.run(['focr', 'ocr', '--json', str(png)], capture_output=True, text=True, timeout=120)
    txt = ''
    try:
        data = json.loads(r.stdout)
        txt = data.get('markdown', '') or data.get('text', '') or ''
    except Exception:
        txt = r.stdout or ''
    txt = txt.strip().replace('\n', ' ')
    results.append({'idx': i, 'file': png.name, 'focr': txt})
    print(f'  [{i:02d}] {png.name}: focr="{txt[:60]}"')

json.dump(results, open('/tmp/unread_focr.json', 'w'), ensure_ascii=False, indent=1)
print('\nsaved /tmp/unread_focr.json')
