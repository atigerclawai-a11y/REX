#!/usr/bin/env python3
"""Diagnose: do the 5 missing-menu clients have any rows at all for Aug 5? What did fill write?"""
import sqlite3

DATE = '2026-08-05'
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
names = ['Borshch Diana', 'Krivitskaya Zoya', 'Krivolapov Leonid', 'Leyderman Feliks', 'Povroznik Mikhail']

p = sqlite3.connect(PROP)
p.row_factory = sqlite3.Row
print('=== all Aug 5 rows for these clients ===')
for n in names:
    rows = p.execute("SELECT client_name, shift, salad, soup, main, side, source_sheet FROM client_menus WHERE menu_date=? AND client_name=?", (DATE, n)).fetchall()
    print(f'{n}: {len(rows)} rows')
    for r in rows:
        print(f'   S{r["shift"]} [{r["source_sheet"]}]: {r["salad"]} | {r["soup"]} | {r["main"]} | {r["side"]}')
    # history
    hist = p.execute("SELECT menu_date, shift, main, source_sheet FROM client_menus WHERE client_name=? AND main != '' AND main NOT LIKE '%заказ не размещен%' ORDER BY menu_date DESC LIMIT 3", (n,)).fetchall()
    print(f'   history: {[(r["menu_date"], r["shift"], r["main"][:20], r["source_sheet"]) for r in hist]}')
p.close()
