#!/usr/bin/env python3
"""Top up the 8 gap clients with their own real orders (both DBs).
Target: Thu S2 Kormov Feliks; Fri S1 Bok/Diadia/Karpina/Lysenko/Shumaeva/Matanseva;
Fri S2 Lvova Tamara."""
import sqlite3

FIXES = [
    # name, date, shift, salad, soup, main, side
    ('Kormov Feliks', '2026-08-06', 2, 'Винегрет', 'Гороховый суп', 'Поперечка', 'Гречка'),
    ('Bok Lyudmila', '2026-08-07', 1, 'Сало', 'Куриный суп', 'Блины с творогом', 'Гречка'),
    ('Diadia Valentina', '2026-08-07', 1, 'Салат из баклажан', 'Куриный суп', 'Баса с помидорами', 'Пюре'),
    ('Karpina Taisiia', '2026-08-07', 1, 'Сало', 'Борщ красный', 'Чалахач', 'Пюре'),
    ('Lysenko Tetiana', '2026-08-07', 1, 'Винегрет', 'Куриный суп', 'Блины с мясом', 'Гречка'),
    ('Shumaeva Anna', '2026-08-07', 1, 'Винегрет', 'Борщ красный', 'Жульен', 'Тушеная капуста'),
    ('Matanseva Ofelia', '2026-08-07', 1, 'Борщ зеленый', 'Овощной суп', 'Оливье', 'Тушеная капуста'),
    ('Lvova Tamara', '2026-08-07', 2, 'Квашеная капуста', 'Борщ зеленый', 'Голубцы', 'Тушеная капуста'),
]

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    for name, date, shift, sal, sup, main_, side in FIXES:
        n = con.execute("SELECT COUNT(*) FROM client_menus WHERE client_name=? AND menu_date=? AND shift=?", (name, date, shift)).fetchone()[0]
        if n:
            c = con.execute("""UPDATE client_menus SET salad=?, soup=?, main=?, side=?,
                source_sheet='day_shifted' WHERE client_name=? AND menu_date=? AND shift=?""",
                (sal, sup, main_, side, name, date, shift))
            print(f'{db.split("/")[-1]} {name}: updated {c.rowcount}')
        else:
            day_code = 'TH' if date == '2026-08-06' else 'F'
            con.execute("""INSERT INTO client_menus (client_name, menu_date, day_code, shift,
                salad, soup, main, side, source_sheet)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'day_shifted')""",
                (name, date, day_code, shift, sal, sup, main_, side))
            print(f'{db.split("/")[-1]} {name}: inserted')
    con.commit()
    con.close()
