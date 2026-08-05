#!/usr/bin/env python3
"""Fix 5 Thu rows with empty/partial plates (both DBs) — fill from each client's
own most recent complete order."""
import sqlite3

FIXES = [
    # name, shift, salad, soup, main, side
    ('Chepizhko Raya', 1, 'Квашеная капуста', 'Гороховый суп', 'Голубцы', 'Гречка'),
    ('Dranikov Berta', 1, 'Селедка', 'Борщ зеленый', 'Салмон', 'Паста'),
    ('Drochik Oleg', 1, 'Салат Днестр', 'Овощной суп', 'Цыпленок табака', 'Гречка'),
    ('Makaron Khaya', 2, 'Квашеная капуста', 'Борщ красный', 'Вареники с картошкой', 'Тушеная капуста'),
    ('Verbitskaya Svetlana', 2, 'Салат Днестр', 'Грибной суп', 'Поперечка', 'Гречка'),
]

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    for name, sh, sal, sup, main_, side in FIXES:
        n = con.execute("SELECT COUNT(*) FROM client_menus WHERE client_name=? AND menu_date='2026-08-06'", (name,)).fetchone()[0]
        if n:
            c = con.execute("""UPDATE client_menus SET salad=?, soup=?, main=?, side=?,
                source_sheet='day_shifted', shift=?
                WHERE client_name=? AND menu_date='2026-08-06'""",
                (sal, sup, main_, side, sh, name))
            print(f'{db.split("/")[-1]} {name}: updated {c.rowcount}')
        else:
            con.execute("""INSERT INTO client_menus (client_name, menu_date, day_code, shift,
                salad, soup, main, side, source_sheet)
                VALUES (?, '2026-08-06', 'TH', ?, ?, ?, ?, ?, 'day_shifted')""",
                (name, sh, sal, sup, main_, side))
            print(f'{db.split("/")[-1]} {name}: inserted')
    con.commit()
    con.close()
