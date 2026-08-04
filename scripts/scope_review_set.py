#!/usr/bin/env python3
"""Scope the review set: recovery manifest docs + DB ocr_scan rows per doc era."""
import json
import sqlite3
from pathlib import Path

REX = Path('/Users/mainsobhelper/Desktop/REX')
# recovery manifest
mf = REX / '.page_guard_recover.json'
if mf.exists():
    data = json.load(open(mf))
    docs = data if isinstance(data, list) else data.get('docs', data.get('manifest', []))
    print(f'recovery manifest: {len(docs)} docs')
    for d in docs[:40]:
        if isinstance(d, dict):
            print(f"  {d.get('doc', d.get('id', '?'))}  {d.get('pages', d.get('pp', '?'))}pp")
        else:
            print(f'  {d}')
else:
    print('no recovery manifest')

# DB: what do we already have for Aug 3-7 by source?
p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
print('\nDB ocr_scan rows for Aug 3-7 (already applied):')
for d in ['2026-08-03', '2026-08-04', '2026-08-05', '2026-08-06', '2026-08-07']:
    n = p.execute("SELECT COUNT(*) FROM client_menus WHERE menu_date=? AND source_sheet='ocr_scan'", (d,)).fetchone()[0]
    print(f'  {d}: {n}')
p.close()
