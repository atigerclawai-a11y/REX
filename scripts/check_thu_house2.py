#!/usr/bin/env python3
"""Check which 2 clients are house_standard on Thu."""
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
for r in p.execute("""SELECT client_name, shift FROM client_menus
    WHERE menu_date='2026-08-06' AND source_sheet='house_standard'"""):
    print(f'  {r[0]} S{r[1]}')
    # do they have history?
    h = p.execute("""SELECT COUNT(*) FROM client_menus WHERE client_name=?
        AND main != '' AND main NOT LIKE '%заказ не размещен%'
        AND source_sheet NOT IN ('house_standard','no_order_flag')""", (r[0],)).fetchone()[0]
    print(f'    history rows with real order: {h}')
p.close()
