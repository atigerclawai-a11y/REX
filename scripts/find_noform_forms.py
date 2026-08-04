#!/usr/bin/env python3
"""Check if the 22 Tue/Wed no-form clients have forms in the raw scan data
(blank_parse pngs, garbled reads, or the review queue)."""
import json
import sqlite3
import re
from pathlib import Path

# 22 attending no-form clients
p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
noform = set(r[0] for r in p.execute("""SELECT DISTINCT client_name FROM client_menus
    WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07'
    AND client_name NOT IN (
        SELECT DISTINCT client_name FROM client_menus
        WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07' AND source_sheet='ocr_scan')"""))
p.close()

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
attending = set()
for n in noform:
    r = a.execute("SELECT day_T_actual, day_W_actual FROM clients WHERE name=?", (n,)).fetchone()
    if r and (r[0] in (1, 2) or r[1] in (1, 2)):
        attending.add(n)
a.close()

# surnames of attending no-form clients
surnames = set()
for n in attending:
    parts = n.split()
    if parts:
        surnames.add(parts[0].lower())
print(f'attending no-form clients: {len(attending)}')

# search all blank_parse extraction + focr results for surname matches
BASE = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')
hits = {}
for ddir in BASE.iterdir():
    if not ddir.is_dir():
        continue
    for ej in ddir.glob('extraction*.json'):
        try:
            data = json.load(open(ej))
            for name in data.keys():
                n0 = name.split()[0].lower() if name.split() else ''
                if n0 in surnames:
                    hits.setdefault(name, []).append(ddir.name[:16])
        except Exception:
            pass

print(f'surname hits in extraction files: {len(hits)}')
for name, docs in sorted(hits.items()):
    print(f'  {name}: {docs}')

# check review queue table
p2 = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
try:
    q = p2.execute("SELECT * FROM menu_review_queue").fetchall()
    print(f'\nmenu_review_queue: {len(q)} rows')
    for r in q:
        print(f'  {r}')
except Exception as e:
    print(f'review queue: {e}')
p2.close()
