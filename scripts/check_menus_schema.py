#!/usr/bin/env python3
"""Check client_menus schema in both DBs + how existing ocr_scan rows look."""
import sqlite3

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    print(f'=== {db.split("/")[-1]} ===')
    print('columns:', [r[1] for r in con.execute("PRAGMA table_info(client_menus)")])
    row = con.execute("SELECT * FROM client_menus WHERE source_sheet='ocr_scan' LIMIT 1").fetchone()
    cols = [r[1] for r in con.execute("PRAGMA table_info(client_menus)")]
    if row:
        print('sample ocr_scan row:', dict(zip(cols, row)))
    # distinct day_code values
    try:
        print('day_codes:', [r[0] for r in con.execute("SELECT DISTINCT day_code FROM client_menus")][:8])
    except Exception as e:
        print('day_code col error:', e)
    con.close()
