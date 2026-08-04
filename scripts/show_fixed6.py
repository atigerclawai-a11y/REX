#!/usr/bin/env python3
"""Show the 6 clients' NEW Tue/Wed plates (should be their real recent orders)."""
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
for name in ['Sekh Stefaniia', 'Shteyman Faina', 'Britavskaya Sofiya', 'Shadkhan Bella',
             'Safonov Anatoliy']:
    for r in p.execute("""SELECT menu_date, shift, day_code, salad, soup, main, side, source_sheet
        FROM client_menus WHERE client_name=? AND menu_date IN ('2026-08-04','2026-08-05')
        ORDER BY menu_date""", (name,)):
        print(f'{name} {r[0]} S{r[1]}: {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}]')
p.close()
