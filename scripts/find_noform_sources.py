#!/usr/bin/env python3
"""Check the 67 no-form clients: do their names appear in ANY extraction file,
any review queue, or are they just absent from the scans?"""
import json
import sqlite3
from pathlib import Path

# 67 no-form clients
p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
noform = [r[0] for r in p.execute("""SELECT DISTINCT client_name FROM client_menus
    WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07'
    AND client_name NOT IN (
        SELECT DISTINCT client_name FROM client_menus
        WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07' AND source_sheet='ocr_scan')
    ORDER BY client_name""")]
p.close()

# search all extraction files (blank_parse) for these names
BASE = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')
found_in_extraction = {}
for ddir in BASE.iterdir():
    if not ddir.is_dir():
        continue
    for ej in ddir.glob('extraction*.json'):
        try:
            data = json.load(open(ej))
            for name in data.keys():
                if name in noform:
                    found_in_extraction.setdefault(name, []).append(ddir.name[:15])
        except Exception:
            pass

print(f'no-form clients: {len(noform)}')
print(f'found in some extraction.json: {len(found_in_extraction)}')
for name, docs in sorted(found_in_extraction.items()):
    print(f'  {name}: {docs}')

missing = [n for n in noform if n not in found_in_extraction]
print(f'\nNOT in any extraction ({len(missing)}):')
for n in missing:
    print(f'  {n}')
