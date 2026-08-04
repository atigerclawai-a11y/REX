#!/usr/bin/env python3
"""Check if recovery already extracted marks for our confirmed forms."""
import json
import sqlite3
from pathlib import Path

BASE = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')
rows = json.load(open('/tmp/matched_table_final.json'))

# which docs have extraction_focr.json / extraction_surya.json?
docs = sorted(set(r['doc'] for r in rows))
for d in docs:
    ddir = BASE / d
    if not ddir.exists():
        continue
    extras = [f.name for f in ddir.iterdir() if 'extraction' in f.name]
    print(f'{d}: {extras}')

# check: does DB already have ocr_scan rows for confirmed clients on week-31 dates?
p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
print('\n=== confirmed clients: existing w31 ocr_scan rows? ===')
have = missing = 0
for r in rows[:10]:
    name = r['match']
    n = p.execute("SELECT COUNT(*) FROM client_menus WHERE client_name=? AND menu_date BETWEEN '2026-08-03' AND '2026-08-07' AND source_sheet='ocr_scan'", (name,)).fetchone()[0]
    print(f'  {name}: {n} w31 ocr rows')
p.close()
