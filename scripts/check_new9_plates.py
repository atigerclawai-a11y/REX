#!/usr/bin/env python3
"""Check: do the 9 newly-added Thursday clients have Thu plates?
Also check their source shift for plate rows."""
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
NEW = ['Beylina Emma', 'Bardenshteyn Larisa', 'Bekerman Alla', 'Berezkin Mikhail',
       'Gendelman Anatoliy', 'Gendelman Liliya', 'Kormova Lyubov', 'Maglakelidze Mzia',
       'Kormov Feliks']
for name in NEW:
    rows = p.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
        FROM client_menus WHERE client_name=? AND menu_date='2026-08-06'""", (name,)).fetchall()
    if rows:
        for r in rows:
            print(f'{name}: {r[3]}|{r[4]}|{r[5]}|{r[6]} S{r[2]} [{r[7]}]')
    else:
        print(f'{name}: ❌ NO THU PLATE')
p.close()
