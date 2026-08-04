#!/usr/bin/env python3
"""Sanity check: how did the DB/pipeline treat doc006808's extracted forms?
(July 27 doc — if pipeline mapped to w30, that confirms week attribution.)"""
import json
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')

# extracted clients from doc006808 (July 27 scan)
for name in ['Sorits Lev', 'Gutkina Lyudmila', 'Finkelman Galina']:
    rows = p.execute("""SELECT menu_date, day_code, salad, soup, main, side, source_sheet
        FROM client_menus WHERE client_name=? AND menu_date BETWEEN '2026-07-27' AND '2026-08-07'
        ORDER BY menu_date""", (name,)).fetchall()
    print(f'\n{name}:')
    for r in rows[:12]:
        print(f"  {r[0]} {r[1]}: {r[2]} | {r[3]} | {r[4]} | {r[5]} [{r[6]}]")
p.close()
