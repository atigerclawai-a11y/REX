#!/usr/bin/env python3
"""Check Bialkovska Maria + Bolotin Marina Wed state."""
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
for name in ['Bialkovska Maria', 'Bolotin Marina']:
    print(f'=== {name} ===')
    for r in p.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
        FROM client_menus WHERE client_name=? AND menu_date BETWEEN '2026-08-03' AND '2026-08-07'
        ORDER BY menu_date""", (name,)):
        print(f'  {r[0]} {r[1]} S{r[2]}: {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}]')
p.close()

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
for name in ['Bialkovska Maria', 'Bolotin Marina']:
    r = a.execute("SELECT name, day_W_actual FROM clients WHERE name=?", (name,)).fetchone()
    print(f'auth {name}: Wed={r[1] if r else "NOT FOUND"}')
a.close()
