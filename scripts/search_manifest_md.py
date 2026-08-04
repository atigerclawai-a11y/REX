#!/usr/bin/env python3
"""Search manifest docs' MinerU md + page images for the 22 attending no-form surnames."""
import json
import sqlite3
import re
from pathlib import Path

REX = Path('/Users/mainsobhelper/Desktop/REX')
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

# manifest docs
mf = json.load(open(REX / '.page_guard_recover.json')) if (REX / '.page_guard_recover.json').exists() else []
docs = mf if isinstance(mf, list) else mf.get('docs', [])

# search MinerU md for surnames
print('searching MinerU md in manifest docs...')
for d in docs:
    if isinstance(d, (list, tuple)) and len(d) >= 1:
        docname = d[0]
    elif isinstance(d, str):
        docname = d
    elif isinstance(d, dict):
        docname = d.get('doc', '')
    else:
        continue
    md = REX / 'menu_ocr_full' / docname / 'ocr' / f'{docname}.md'
    if not md.exists():
        md = REX / 'menu_ocr_full' / docname / docname / 'auto' / f'{docname}.md'
    if not md.exists():
        continue
    txt = md.read_text(errors='ignore').lower()
    for s in surnames:
        if s in txt:
            print(f'  {s}: found in {docname[:20]} md')
