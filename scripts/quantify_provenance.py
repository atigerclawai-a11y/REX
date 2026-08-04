#!/usr/bin/env python3
"""Quantify: ocr_scan rows on Aug 3-7 that came from WEEK-30 docs (wrong provenance).
July 27 docs = week 30: doc006808, 006809, 006810, 006811, 006812.
Week-31 docs = July 29+: doc006878-881, doc007011-014."""
import sqlite3

W30_DOCS = ['doc006808', 'doc006809', 'doc006810', 'doc006811', 'doc006812']
W31_DOCS = ['doc006878', 'doc006879', 'doc006880', 'doc006881',
            'doc007011', 'doc007012', 'doc007013', 'doc007014']

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')

# rows for Aug 3-7 by source
print('=== Aug 3-7 rows by source_sheet ===')
for r in p.execute("""SELECT source_sheet, COUNT(*) FROM client_menus
    WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07' GROUP BY 1 ORDER BY 2 DESC"""):
    print(f'  {r[0]}: {r[1]}')

# The provenance problem: extraction.json for week-30 docs got applied to Aug 3-7.
# Check clients of week-30 docs who have Aug 3-7 ocr_scan rows.
print('\n=== week-30 doc clients with Aug 3-7 ocr_scan rows (suspect provenance) ===')
import json
from pathlib import Path
BASE = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')
suspect = {}
for d in W30_DOCS:
    ej = BASE / d
    if not ej.exists():
        continue
    ejf = list(ej.glob('extraction*.json'))
    names = []
    for f in ejf:
        try:
            names += list(json.load(open(f)).keys())
        except Exception:
            pass
    for name in names:
        n = p.execute("""SELECT COUNT(*) FROM client_menus WHERE client_name=?
            AND menu_date BETWEEN '2026-08-03' AND '2026-08-07' AND source_sheet='ocr_scan'""",
            (name,)).fetchone()[0]
        if n:
            suspect[name] = n
print(f'  {len(suspect)} suspect clients:')
for k, v in sorted(suspect.items())[:30]:
    print(f'    {k}: {v} rows')
p.close()
