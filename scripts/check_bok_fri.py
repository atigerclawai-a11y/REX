#!/usr/bin/env python3
"""Check Bok Lyudmila Fri: why no plate? She's attending (придёт сама per WhatsApp 19:36)."""
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
a = sqlite3.connect(AUTH)
p = sqlite3.connect(PROP)

print('auth:')
for r in a.execute("SELECT name, active, day_F_actual FROM clients WHERE name LIKE '%Bok%'"):
    print(f'  {r}')

print('\nrows this week:')
for r in p.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
    FROM client_menus WHERE client_name LIKE '%Bok%'
    AND menu_date BETWEEN '2026-08-03' AND '2026-08-07' ORDER BY menu_date"""):
    print(f'  {r[0]} {r[1]} S{r[2]}: {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}]')

print('\nhistory:')
for r in p.execute("""SELECT menu_date, day_code, salad, soup, main, side, source_sheet
    FROM client_menus WHERE client_name LIKE '%Bok%' AND menu_date < '2026-08-03'
    ORDER BY menu_date DESC LIMIT 5"""):
    print(f'  {r[0]} {r[1]}: {r[2]}|{r[3]}|{r[4]}|{r[5]} [{r[6]}]')
a.close()
p.close()
