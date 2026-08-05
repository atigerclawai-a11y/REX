#!/usr/bin/env python3
"""Fix 5 Thu S1 gaps (both DBs):
- Breytman Polina: shift 2→1 (keep her day_shifted plate)
- Epshteyn Yelizaveta: shift 2→1 (keep her ocr_scan plate)
- Coniglio Vera: insert from her own order (Салат из баклажан|Борщ красный|Баса с помидорами|Гречка)
- Dmitriyeva Tamara: insert from her own order (Оливье|Куриный суп|Курица в терияки|Тушеная капуста)
- Firdman Mark: insert from his own order (Винегрет|Борщ зеленый|Баса с помидорами|Гречка)"""
import sqlite3

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    # shift fixes
    for name in ['Breytman Polina', 'Epshteyn Yelizaveta']:
        c = con.execute("""UPDATE client_menus SET shift=1
            WHERE client_name=? AND menu_date='2026-08-06'""", (name,))
        print(f'{db.split("/")[-1]} {name}: {c.rowcount} row shift→1')
    # inserts
    INSERTS = [
        ('Coniglio Vera', 'Салат из баклажан', 'Борщ красный', 'Баса с помидорами', 'Гречка'),
        ('Dmitriyeva Tamara', 'Оливье', 'Куриный суп', 'Курица в терияки', 'Тушеная капуста'),
        ('Firdman Mark', 'Винегрет', 'Борщ зеленый', 'Баса с помидорами', 'Гречка'),
    ]
    for name, sal, sup, main_, side in INSERTS:
        n = con.execute("SELECT COUNT(*) FROM client_menus WHERE client_name=? AND menu_date='2026-08-06'", (name,)).fetchone()[0]
        if n:
            con.execute("""UPDATE client_menus SET salad=?, soup=?, main=?, side=?,
                source_sheet='day_shifted', shift=1
                WHERE client_name=? AND menu_date='2026-08-06'""", (sal, sup, main_, side, name))
            print(f'{db.split("/")[-1]} {name}: updated existing row')
        else:
            con.execute("""INSERT INTO client_menus (client_name, menu_date, day_code, shift,
                salad, soup, main, side, source_sheet)
                VALUES (?, '2026-08-06', 'TH', '1', ?, ?, ?, ?, 'day_shifted')""",
                (name, sal, sup, main_, side))
            print(f'{db.split("/")[-1]} {name}: inserted row')
    con.commit()
    con.close()
