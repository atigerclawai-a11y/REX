#!/usr/bin/env python3
"""Top up Shumaeva Anna (W S1) + Gamkrelidze Mikhail (W S2) from their own orders."""
import sqlite3

FIXES = [
    ('Shumaeva Anna', 1, 'Винегрет', 'Борщ красный', 'Жульен', 'Тушеная капуста'),
    ('Gamkrelidze Mikhail', 2, 'Сало', 'Гороховый суп', 'Свиная отбивная', 'Картошка'),
]

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    for name, shift, sal, sup, main_, side in FIXES:
        n = con.execute("SELECT COUNT(*) FROM client_menus WHERE client_name=? AND menu_date='2026-08-05'", (name,)).fetchone()[0]
        if n:
            c = con.execute("""UPDATE client_menus SET salad=?, soup=?, main=?, side=?,
                source_sheet='day_shifted', shift=?
                WHERE client_name=? AND menu_date='2026-08-05'""",
                (sal, sup, main_, side, shift, name))
            print(f'{db.split("/")[-1]} {name}: updated {c.rowcount}')
        else:
            con.execute("""INSERT INTO client_menus (client_name, menu_date, day_code, shift,
                salad, soup, main, side, source_sheet)
                VALUES (?, '2026-08-05', 'W', ?, ?, ?, ?, ?, 'day_shifted')""",
                (name, shift, sal, sup, main_, side))
            print(f'{db.split("/")[-1]} {name}: inserted')
    con.commit()
    con.close()
