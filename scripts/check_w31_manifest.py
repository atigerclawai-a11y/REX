#!/usr/bin/env python3
"""Check: which manifest docs are week-31 era (July 29-31), do they have PNGs,
and are any of the 22 attending no-form clients among their confirmed forms?"""
import json
import sqlite3
from pathlib import Path

REX = Path('/Users/mainsobhelper/Desktop/REX')
mf = json.load(open(REX / '.page_guard_recover.json'))
docs = mf if isinstance(mf, list) else mf.get('docs', [])

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
surnames = {n.split()[0].lower() for n in attending if n.split()}

print(f'attending no-form: {len(attending)}')
for d in docs:
    docname = d[0] if isinstance(d, (list, tuple)) else (d if isinstance(d, str) else d.get('doc', ''))
    # week-31 era = filename ts 20260729+
    if '20260729' in docname or '20260730' in docname or '20260731' in docname:
        ddir = REX / 'blank_parse' / docname
        pngs = list(ddir.glob('p*.png')) if ddir.exists() else []
        print(f'  {docname[:24]}: {len(pngs)} pngs')

# list the 22 attending no-form clients for the record
print(f'\nThe 22 attending no-form clients:')
for n in sorted(attending):
    print(f'  {n}')
