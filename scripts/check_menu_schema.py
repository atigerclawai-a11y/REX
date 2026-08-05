#!/usr/bin/env python3
"""Check client_menus schema — where is the source doc recorded?"""
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
print('client_menus columns:')
for r in p.execute("PRAGMA table_info(client_menus)"):
    print(f'  {r[1]} ({r[2]})')

# look at a few ocr_scan rows to see if a doc field exists
print('\nsample ocr_scan rows (all columns):')
cols = [r[1] for r in p.execute("PRAGMA table_info(client_menus)")]
for row in p.execute("SELECT * FROM client_menus WHERE source_sheet='ocr_scan' LIMIT 3"):
    print('  ' + ' | '.join(f'{c}={v}' for c, v in zip(cols, row) if v))
p.close()
