#!/usr/bin/env python3
"""Fix 3 Thursday garbage rows (both DBs):
- Dirul Serghei: replace garbage fallback with real order from history
- Fridman Mikhail: replace garbage fallback with his real this-week pattern
- Breytman Polina: delete garbage day_shifted dup, top up partial ocr_scan"""
import sqlite3

FIXES = [
    # (client, date, keep_source, salad, soup, main, side)
    ('Dirul Serghei', '2026-08-06', 'last_order_fallback',
     'Борщ зеленый', 'Борщ зеленый', 'Оливье', 'Тушеная капуста'),
    ('Fridman Mikhail', '2026-08-06', 'last_order_fallback',
     'Салат Днестр', 'Куриный суп', 'Шницель куриный', 'Гречка'),
    # Breytman: delete garbage day_shifted dup, then top up partial ocr_scan
    ('Breytman Polina', '2026-08-06', '__DELETE_DUP__', None, None, None, None),
]

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    for name, date, src, salad, soup, main_, side in FIXES:
        if src == '__DELETE_DUP__':
            c = con.execute("""DELETE FROM client_menus WHERE client_name=? AND menu_date=?
                AND source_sheet='day_shifted'""", (name, date))
            print(f'{db.split("/")[-1]} {name}: deleted {c.rowcount} garbage day_shifted dup')
            # now top up the partial ocr_scan row from her real Thu history
            c = con.execute("""UPDATE client_menus SET salad='Оливье', soup='Борщ красный',
                main='Чалахач', side='Гречка', source_sheet='day_shifted'
                WHERE client_name=? AND menu_date=? AND source_sheet='ocr_scan'""", (name, date))
            print(f'{db.split("/")[-1]} {name}: topped up {c.rowcount} partial ocr row')
        else:
            c = con.execute("""UPDATE client_menus SET salad=?, soup=?, main=?, side=?,
                source_sheet='day_shifted'
                WHERE client_name=? AND menu_date=? AND source_sheet=?""",
                (salad, soup, main_, side, name, date, src))
            print(f'{db.split("/")[-1]} {name}: fixed {c.rowcount} row → {salad}|{soup}|{main_}|{side}')
    con.commit()
    con.close()
