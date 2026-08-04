#!/usr/bin/env python3
"""Find complete real orders for the 9 incomplete Wednesday clients."""
import sqlite3

PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
names = ['Gorodetskaya Ninel', 'Lebedenko Valentyna', 'Gutkina Lyudmila',
         'Starodubets Valentina', 'Glukhova Shavelina', 'Bass Khana',
         'Dranikov Berta', 'Ruvinskaya Natalia', 'Maglakelidze Mzia']

p = sqlite3.connect(PROP)
p.row_factory = sqlite3.Row
for name in names:
    print(f'\n=== {name} — history (complete rows only) ===')
    rows = p.execute("""SELECT menu_date, shift, salad, soup, main, side, source_sheet
        FROM client_menus WHERE client_name=?
        AND salad!='' AND soup!='' AND main!='' AND side!=''
        ORDER BY menu_date DESC LIMIT 4""", (name,)).fetchall()
    for r in rows:
        print(f"  {r['menu_date']} S{r['shift']} [{r['source_sheet']}]: {r['salad']} | {r['soup']} | {r['main']} | {r['side']}")
    if not rows:
        print('  (no complete history rows)')
        # partial history
        rows2 = p.execute("""SELECT menu_date, shift, salad, soup, main, side, source_sheet
            FROM client_menus WHERE client_name=? ORDER BY menu_date DESC LIMIT 3""", (name,)).fetchall()
        for r in rows2:
            print(f"  PART {r['menu_date']} S{r['shift']} [{r['source_sheet']}]: {r['salad']} | {r['soup']} | {r['main']} | {r['side']}")
p.close()
