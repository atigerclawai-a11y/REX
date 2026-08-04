#!/usr/bin/env python3
"""Delete garbage fallback dups for Epshteyn/Buslayeva on Thu (keep real ocr_scan)."""
import sqlite3

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    for name in ['Epshteyn Yelizaveta', 'Buslayeva Alisa']:
        rows = con.execute("""SELECT rowid, source_sheet, salad, soup, main, side FROM client_menus
            WHERE client_name=? AND menu_date='2026-08-06' ORDER BY source_sheet""", (name,)).fetchall()
        print(f'{db.split("/")[-1]} {name}:')
        for r in rows:
            print(f'  rowid={r[0]} [{r[1]}]: {r[2]}|{r[3]}|{r[4]}|{r[5]}')
        # delete fallback dup if an ocr_scan exists for same date
        has_ocr = con.execute("""SELECT COUNT(*) FROM client_menus
            WHERE client_name=? AND menu_date='2026-08-06' AND source_sheet='ocr_scan'""", (name,)).fetchone()[0]
        if has_ocr:
            c = con.execute("""DELETE FROM client_menus WHERE client_name=? AND menu_date='2026-08-06'
                AND source_sheet='last_order_fallback'""", (name,))
            print(f'  → deleted {c.rowcount} fallback dup (kept ocr_scan)')
        else:
            # no real row — fix the fallback in place
            c = con.execute("""UPDATE client_menus SET salad='Оливье', soup='Борщ зеленый',
                main='Оливье', side='Тушеная капуста', source_sheet='day_shifted'
                WHERE client_name=? AND menu_date='2026-08-06' AND source_sheet='last_order_fallback'""",
                (name,))
            print(f'  → fixed {c.rowcount} fallback in place (no ocr_scan existed)')
    con.commit()
    con.close()
