#!/usr/bin/env python3
"""Delete Diadia Valentina's duplicate garbage fallback row on Aug 5 (both DBs)."""
import sqlite3

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    # show duplicates first
    rows = con.execute("""SELECT rowid, client_name, menu_date, day_code, salad, soup, main, side, source_sheet
        FROM client_menus WHERE client_name='Diadia Valentina' AND menu_date='2026-08-05'
        ORDER BY source_sheet""").fetchall()
    for r in rows:
        print(f'{db.split("/")[-1]} rowid={r[0]}: {r[4]}|{r[5]}|{r[6]}|{r[7]} [{r[8]}]')
    # delete the fallback/garbage duplicate (keep ocr_scan)
    cur = con.execute("""DELETE FROM client_menus WHERE client_name='Diadia Valentina'
        AND menu_date='2026-08-05' AND source_sheet='last_order_fallback'""")
    print(f'  deleted {cur.rowcount} fallback duplicate')
    con.commit()
    con.close()
