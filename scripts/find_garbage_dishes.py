#!/usr/bin/env python3
"""Find ALL non-canonical/garbage dish names in client_menus for Aug 3-7."""
import sqlite3

CANONICAL = {'Винегрет', 'Оливье', 'Сало', 'Селедка', 'Квашеная капуста', 'Салат Днестр',
             'Свекла', 'Салат из баклажан', 'Салат весенний', 'Борщ зеленый', 'Борщ красный',
             'Куриный суп', 'Гороховый суп', 'Грибной суп', 'Овощной суп', 'Харчо',
             'Баса с помидорами', 'Блины с мясом', 'Блины с творогом', 'Вареники с картошкой',
             'Голубцы', 'Гуляш', 'Дорадо запеченая', 'Жульен', 'Котлеты куриные',
             'Курица в терияки', 'Куриные крылышки', 'Пельмени', 'Поперечка', 'Салмон',
             'Свиная отбивная', 'Цыпленок табака', 'Чалахач', 'Чебуреки', 'Шницель куриный',
             'Тушеная капуста', 'Картошка', 'Картошка фри', 'Паста', 'Гречка', 'Пюре',
             'Стручковая фасоль'}

DBS = ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
       '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']

for db in DBS:
    con = sqlite3.connect(db)
    rows = con.execute("""SELECT client_name, menu_date, day_code, salad, soup, main, side
        FROM client_menus WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07'""").fetchall()
    bad = []
    for name, d, dc, salad, soup, main_, side in rows:
        for cell, label in [(salad, 'salad'), (soup, 'soup'), (main_, 'main'), (side, 'side')]:
            if cell and cell.strip() not in CANONICAL:
                bad.append((name, d, dc, label, cell))
    print(f'\n=== {db.split("/")[-1]}: {len(bad)} non-canonical cells ===')
    seen = {}
    for name, d, dc, label, cell in bad:
        seen.setdefault(cell, []).append((name, d, dc, label))
    for cell, hits in sorted(seen.items()):
        print(f'  {cell!r}: {len(hits)}×  e.g. {hits[0][0]} {hits[0][1]} {hits[0][2]} ({hits[0][3]})')
    con.close()
