#!/usr/bin/env python3
"""Find Wednesday clients with empty salad or soup in orders/DB."""
import json
import sqlite3

# 1. orders JSON
d = json.load(open('/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json'))
entry = d.get('2026-08-05', {})
print('=== Wed Aug 5 orders JSON: clients with empty salad or soup ===')
for name, shifts in entry.items():
    for sh, o in shifts.items():
        if not o.get('salad') or not o.get('soup'):
            print(f'  {name} S{sh}: salad={o.get("salad")!r} soup={o.get("soup")!r} main={o.get("main")!r} side={o.get("side")!r}')

# 2. DB check
p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
rows = p.execute("""SELECT client_name, shift, salad, soup, main, side, source_sheet
    FROM client_menus WHERE menu_date='2026-08-05'""").fetchall()
p.close()
print('\n=== DB: Wed Aug 5 rows with empty salad or soup ===')
for name, shift, salad, soup, main_, side, src in rows:
    if not salad or not soup:
        print(f'  {name} S{shift} [{src}]: salad={salad!r} soup={soup!r} main={main_!r} side={side!r}')
