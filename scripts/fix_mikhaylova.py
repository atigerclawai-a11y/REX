#!/usr/bin/env python3
"""Fix Mikhaylova Sofiya Aug 4 row — replace partial garbage with her complete
real order (Винегрет | Борщ зеленый | Вареники с картошкой | Тушеная капуста)."""
import sqlite3

DATE = '2026-08-04'
DBS = ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
       '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']
name = 'Mikhaylova Sofiya'
dishes = ('Винегрет', 'Борщ зеленый', 'Вареники с картошкой', 'Тушеная капуста')

for db in DBS:
    c = sqlite3.connect(db)
    # delete the partial row first (fill is INSERT OR IGNORE — idempotent on existing)
    c.execute("DELETE FROM client_menus WHERE menu_date=? AND client_name=? AND shift='1'", (DATE, name))
    c.execute("""INSERT INTO client_menus
        (client_name, menu_date, day_code, shift, salad, soup, main, side, source_sheet, synced_at)
        VALUES (?,?, 'T', '1', ?,?,?,?, 'last_order_fallback', datetime('now'))""",
        (name, DATE, *dishes))
    c.commit()
    # verify
    row = c.execute("SELECT salad, soup, main, side FROM client_menus WHERE menu_date=? AND client_name=?", (DATE, name)).fetchone()
    print(f'{db.split("/")[-1]}: {row}')
    c.close()

# clean the orders JSON entry too
import json
P = '/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json'
d = json.load(open(P))
if DATE in d and name in d[DATE]:
    d[DATE][name] = {'1': {'salad': dishes[0], 'soup': dishes[1], 'main': dishes[2], 'side': dishes[3]}}
    json.dump(d, open(P, 'w'), ensure_ascii=False, indent=1)
    print('orders JSON: fixed entry')
