#!/usr/bin/env python3
"""Quantify wrong-provenance pollution: partial ocr_scan rows on Aug 3-7 from
week-30 doc clients (their picks belong to Jul 27-31, not this week)."""
import json
import sqlite3
from pathlib import Path

BASE = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')
p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')

W30_DOCS = ['doc00680820260727160512', 'doc00680920260727160541', 'doc00681020260727160603',
            'doc00681120260727160643', 'doc00681220260727160712']

# all clients in week-30 doc extraction.json files
w30_clients = set()
for d in W30_DOCS:
    for f in (BASE / d).glob('extraction*.json') if (BASE / d).exists() else []:
        try:
            w30_clients.update(json.load(open(f)).keys())
        except Exception:
            pass

print(f'week-30 doc clients: {len(w30_clients)}')

# their Aug 3-7 rows
rows = p.execute("""SELECT client_name, menu_date, day_code, salad, soup, main, side, source_sheet
    FROM client_menus WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07'
    AND source_sheet='ocr_scan' ORDER BY client_name, menu_date""").fetchall()
poll = [r for r in rows if r[0] in w30_clients]
print(f'Aug 3-7 ocr_scan rows for week-30 clients: {len(poll)}')
for r in poll:
    print(f"  {r[0]} {r[1]} {r[2]}: {r[3] or ''} | {r[4] or ''} | {r[5] or ''} | {r[6] or ''}")
p.close()
