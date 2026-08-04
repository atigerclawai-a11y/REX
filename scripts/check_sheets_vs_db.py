#!/usr/bin/env python3
"""Check: do the CURRENT on-disk sheets have the re-applied ocr_scan picks?
Compare orders JSON (drives sheets) vs DB for a collision client."""
import json
import sqlite3

# orders JSON was rebuilt at 05:52 (before re-apply at ~06:0x?)
import os
from datetime import datetime
oj = '/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json'
st = os.stat(oj)
print(f'orders JSON mtime: {datetime.fromtimestamp(st.st_mtime).strftime("%H:%M:%S")}')

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
# Uchitel Vilyam's DB rows now
for r in p.execute("""SELECT menu_date, day_code, salad, soup, main, side, source_sheet
    FROM client_menus WHERE client_name='Uchitel Vilyam'
    AND menu_date IN ('2026-08-04','2026-08-05') ORDER BY menu_date"""):
    print(f'DB: {r[0]} {r[1]}: {r[2]}|{r[3]}|{r[4]}|{r[5]} [{r[6]}]')

# what's in the orders JSON?
orders = json.load(open(oj))
for dt in ['2026-08-04', '2026-08-05']:
    for name, shifts in orders.get(dt, {}).items():
        if 'Uchitel' in name:
            print(f'JSON {dt}: {name} → {shifts}')
p.close()
