#!/usr/bin/env python3
"""Find category leaks: soup names in salad cells, salad names in soup cells, etc."""
import sqlite3

SOUPS = {'Борщ зеленый', 'Борщ красный', 'Куриный суп', 'Гороховый суп', 'Грибной суп',
         'Овощной суп', 'Харчо'}
SALADS = {'Винегрет', 'Оливье', 'Сало', 'Селедка', 'Квашеная капуста', 'Салат Днестр',
          'Свекла', 'Салат из баклажан', 'Салат весенний'}

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    p = sqlite3.connect(db)
    print(f'\n=== {db.split("/")[-1]} ===')
    rows = p.execute("""SELECT client_name, menu_date, day_code, salad, soup, main, side, source_sheet
        FROM client_menus WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07'""").fetchall()
    leaks = []
    for name, d, dc, salad, soup, main_, side, src in rows:
        if salad in SOUPS:
            leaks.append((name, d, dc, 'salad←soup', salad, src))
        if soup in SALADS:
            leaks.append((name, d, dc, 'soup←salad', soup, src))
        if main_ in SALADS or main_ in SOUPS:
            leaks.append((name, d, dc, 'main←other', main_, src))
        if side in SALADS or side in SOUPS:
            leaks.append((name, d, dc, 'side←other', side, src))
    for l in leaks:
        print(f'  {l[0]} {l[1]} {l[2]}: {l[3]} {l[4]!r} [{l[5]}]')
    if not leaks:
        print('  no category leaks')
    p.close()
