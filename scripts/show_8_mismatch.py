#!/usr/bin/env python3
"""Show all 8 mismatch clients: their DB rows for the mismatched day + whether
they have real marks for that day."""
import json
import sqlite3

MIS = [('Ivanova Liudmila', 'M', 2, '1'), ('Ivanova Liudmila', 'F', 2, '1'),
       ('Fedorova Olga', 'M', 1, '2'), ('Elbert Milla', 'M', 1, '2'),
       ('Chupikova Elvira', 'M', 1, '2'), ('Shapiro Roza', 'M', 2, '1'),
       ('Shapiro Roza', 'F', 2, '1'), ('Bialkovska Maria', 'W', 2, '1')]

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
DATE = {'M': '2026-08-03', 'T': '2026-08-04', 'W': '2026-08-05', 'TH': '2026-08-06', 'F': '2026-08-07'}
for name, day, att_sh, db_sh in MIS:
    d = DATE[day]
    rows = p.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
        FROM client_menus WHERE client_name=? AND menu_date=? AND day_code=?""",
        (name, d, day)).fetchall()
    print(f'{name} {day}: attend S{att_sh}, DB has S{db_sh}')
    for r in rows:
        print(f'    {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}]')
p.close()
