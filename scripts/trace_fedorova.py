#!/usr/bin/env python3
"""Trace Fedorova Olga: which batch, what marks, what's in DB, what's her attendance."""
import json
import sqlite3

# 1. find her in all batch files
print('=== batch membership ===')
for bf in ['/tmp/w31_batch_1.json', '/tmp/w31_batch_2.json', '/tmp/w31_batch_3.json',
           '/tmp/w31_batch_4.json', '/tmp/w31_batch_5.json']:
    try:
        for x in json.load(open(bf)):
            nm = x.get('name') or x.get('match') or ''
            if 'Fedorova' in nm or 'Федорова' in nm:
                print(f'  {bf}: n={x["n"]} name={nm} doc={x.get("doc")} page={x.get("page")}')
    except Exception as e:
        print(f'  {bf}: ERR {e}')

# 2. her vision marks
print('\n=== vision marks ===')
for mf in ['/tmp/w31_marks_1.json', '/tmp/w31_marks_2.json', '/tmp/w31_marks_3.json',
           '/tmp/w31_marks_4.json', '/tmp/w31_marks_5.json']:
    try:
        marks = json.load(open(mf))
        for k, v in marks.items():
            pass  # keys are form numbers, need to map
    except Exception:
        pass

# 3. DB rows this week
print('\n=== DB rows (Documents) ===')
p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
for r in p.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
    FROM client_menus WHERE client_name='Fedorova Olga'
    AND menu_date BETWEEN '2026-08-03' AND '2026-08-07' ORDER BY menu_date"""):
    print(f'  {r[0]} {r[1]} S{r[2]}: {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}]')
print('\n=== DB rows (REX) ===')
p2 = sqlite3.connect('/Users/mainsobhelper/Desktop/REX/goj_proprietary.db')
for r in p2.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
    FROM client_menus WHERE client_name='Fedorova Olga'
    AND menu_date BETWEEN '2026-08-03' AND '2026-08-07' ORDER BY menu_date"""):
    print(f'  {r[0]} {r[1]} S{r[2]}: {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}]')

# 4. attendance
print('\n=== attendance ===')
a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
r = a.execute("""SELECT name, active, day_M_actual, day_T_actual, day_W_actual, day_TH_actual, day_F_actual
    FROM clients WHERE name='Fedorova Olga'""").fetchone()
print(f'  {r}')
a.close()
p.close()
p2.close()
