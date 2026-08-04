#!/usr/bin/env python3
"""Check Diadia's shift: DB row vs auth scheduled shift."""
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
print('DB rows Aug 5:')
for r in p.execute("""SELECT rowid, client_name, menu_date, day_code, shift, salad, soup, main, side, source_sheet
    FROM client_menus WHERE client_name='Diadia Valentina' AND menu_date='2026-08-05'"""):
    print(f'  rowid={r[0]} {r[2]} {r[3]} shift={r[4]}: {r[5]}|{r[6]}|{r[7]}|{r[8]} [{r[9]}]')
p.close()

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
print('\nauth:')
for r in a.execute("SELECT name, shift, day_W_actual, day_T_actual FROM clients WHERE name='Diadia Valentina'"):
    print(f'  {r}')
a.close()
