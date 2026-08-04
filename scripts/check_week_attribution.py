#!/usr/bin/env python3
"""Per-doc week attribution via already-extracted clients' DB dates."""
import json
import sqlite3
from pathlib import Path

BASE = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')
p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')

# docs with extraction.json — check their clients' menu_date ranges
for d in ['doc00680820260727160512', 'doc00680920260727160541', 'doc00681120260727160643',
          'doc00687820260729073749', 'doc00701120260731112514', 'doc00701220260731112550']:
    ej = BASE / d / 'extraction.json'
    if not ej.exists():
        continue
    names = list(json.load(open(ej)).keys())[:5]
    print(f'\n=== {d} (extracted clients) ===')
    for name in names:
        dates = [r[0] for r in p.execute(
            "SELECT DISTINCT menu_date FROM client_menus WHERE client_name=? AND source_sheet='ocr_scan' "
            "ORDER BY menu_date", (name,))]
        w31 = [x for x in dates if x >= '2026-08-03']
        w30 = [x for x in dates if '2026-07-27' <= x <= '2026-08-02']
        print(f'  {name}: w31={w31[:6]} w30={w30[:6]}')
p.close()
