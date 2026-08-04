#!/usr/bin/env python3
"""Check: (a) any extraction.json produced by recovery for manifest docs?
(b) how many of the 67 no-form clients actually attend Tue/Wed this week?"""
import json
import sqlite3
from pathlib import Path

REX = Path('/Users/mainsobhelper/Desktop/REX')
mf = REX / '.page_guard_recover.json'
docs = []
if mf.exists():
    data = json.load(open(mf))
    docs = data if isinstance(data, list) else data.get('docs', [])

# (a) extraction files newer than the recovery start (~19:30 Jul 3)
from datetime import datetime
new_ext = []
BASE = REX / 'blank_parse'
for ddir in BASE.iterdir():
    if not ddir.is_dir():
        continue
    for ej in ddir.glob('extraction*.json'):
        mt = datetime.fromtimestamp(ej.stat().st_mtime)
        if mt.hour >= 20 or (mt.day == 4 and mt.hour < 6):
            try:
                n = len(json.load(open(ej)))
            except Exception:
                n = -1
            new_ext.append((ddir.name[:20], ej.name, mt.strftime('%m-%d %H:%M'), n))
print(f'extraction files written tonight (recovery era): {len(new_ext)}')
for e in sorted(new_ext, key=lambda x: x[2])[-15:]:
    print(f'  {e[0]} {e[1]} {e[2]} ({e[3]} forms)')

# (b) no-form clients attending Tue/Wed
p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
noform = [r[0] for r in p.execute("""SELECT DISTINCT client_name FROM client_menus
    WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07'
    AND client_name NOT IN (
        SELECT DISTINCT client_name FROM client_menus
        WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07' AND source_sheet='ocr_scan')""")]
p.close()

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
attends = []
for n in noform:
    r = a.execute("""SELECT day_T_actual, day_W_actual FROM clients WHERE name=?""", (n,)).fetchone()
    if r and (r[0] in (1, 2) or r[1] in (1, 2)):
        attends.append((n, r[0], r[1]))
a.close()
print(f'\nno-form clients: {len(noform)} | attending Tue/Wed this week: {len(attends)}')
for n, t, w in sorted(attends):
    print(f'  {n} (Tue={t} Wed={w})')
