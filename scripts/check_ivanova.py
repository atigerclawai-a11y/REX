#!/usr/bin/env python3
"""Check Ivanova Liudmila + Bogat Svetlana rows this week (confirmed #1, #2)."""
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
for name in ['Ivanova Liudmila', 'Bogat Svetlana']:
    print(f'\n=== {name} ===')
    for r in p.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
        FROM client_menus WHERE client_name=? AND menu_date BETWEEN '2026-08-03' AND '2026-08-07'
        ORDER BY menu_date""", (name,)):
        print(f'  {r[0]} {r[1]} S{r[2]}: {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}]')
p.close()

# is she in auth as Ivanova Liudmila?
a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
for name in ['Ivanova Liudmila', 'Bogat Svetlana']:
    r = a.execute("SELECT name, active, day_M_actual, day_T_actual, day_W_actual, day_TH_actual, day_F_actual FROM clients WHERE name=?", (name,)).fetchone()
    print(f'\nauth {name}: {r}')
a.close()
