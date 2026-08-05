#!/usr/bin/env python3
"""Fix Sepashvili Julieta: move from Friday to Tuesday (Oleg 08-04 12:11).
Auth: day_T_actual=2, day_F_actual=0. Plate: needs a Tuesday plate from her
own history (her Friday fallback was Свекла|Гороховый суп|Салмон|Стручковая фасоль)."""
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
# 1. update auth attendance
a = sqlite3.connect(AUTH)
c = a.execute("UPDATE clients SET day_T_actual=2, day_F_actual=0 WHERE name='Sepashvili Julieta'")
print(f'auth: {c.rowcount} row — Tue=2, Fri=0')
a.commit()

# check her history for a Tuesday order
p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
print('\nhistory:')
for r in p.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
    FROM client_menus WHERE client_name='Sepashvili Julieta' ORDER BY menu_date DESC LIMIT 8"""):
    print(f'  {r[0]} {r[1]} S{r[2]}: {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}]')
p.close()
