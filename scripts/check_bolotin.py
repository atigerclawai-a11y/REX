#!/usr/bin/env python3
"""Check Bolotin Marina: DB rows this week + history."""
import sqlite3

con = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
print('Bolotin Marina rows this week:')
for r in con.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
    FROM client_menus WHERE client_name='Bolotin Marina'
    AND menu_date BETWEEN '2026-08-03' AND '2026-08-07' ORDER BY menu_date"""):
    print(f'  {r[0]} {r[1]} S{r[2]}: {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}]')
print('\nHistory:')
for r in con.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
    FROM client_menus WHERE client_name='Bolotin Marina'
    AND menu_date < '2026-08-03' ORDER BY menu_date DESC LIMIT 6"""):
    print(f'  {r[0]} {r[1]} S{r[2]}: {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}]')
con.close()

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
r = a.execute("SELECT name, active, day_T_actual, day_W_actual, shift FROM clients WHERE name='Bolotin Marina'").fetchone()
print(f'\nauth: {r}')
a.close()
