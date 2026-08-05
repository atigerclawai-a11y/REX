#!/usr/bin/env python3
"""Fedorova Thursday history + full mismatch list from reapply (batch 5 used stale shift)."""
import json
import sqlite3

# her TH history
p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
print('=== Fedorova Olga THURSDAY history ===')
for r in p.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
    FROM client_menus WHERE client_name='Fedorova Olga' AND day_code='TH'
    ORDER BY menu_date DESC LIMIT 6"""):
    print(f'  {r[0]} {r[1]} S{r[2]}: {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}]')

print('\n=== Fedorova full history (recent) ===')
for r in p.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
    FROM client_menus WHERE client_name='Fedorova Olga' ORDER BY menu_date DESC LIMIT 10"""):
    print(f'  {r[0]} {r[1]} S{r[2]}: {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}]')

# full mismatch count: batch5 clients where DB shift != auth actual shift
a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
b5 = json.load(open('/tmp/w31_batch_5.json'))
print('\n=== ALL batch-5 shift mismatches (DB shift vs auth actual) ===')
mis = []
for x in b5:
    nm = x.get('name') or x.get('match')
    if not nm:
        continue
    att = a.execute("SELECT day_M_actual, day_T_actual, day_W_actual, day_TH_actual, day_F_actual FROM clients WHERE name=?", (nm,)).fetchone()
    if not att:
        continue
    for i, day in enumerate(['M', 'T', 'W', 'TH', 'F']):
        sh_att = att[i]
        if not sh_att:
            continue
        rows = p.execute("""SELECT shift FROM client_menus
            WHERE client_name=? AND day_code=? AND menu_date BETWEEN '2026-08-03' AND '2026-08-07'""",
            (nm, day)).fetchall()
        for (dbsh,) in rows:
            if dbsh != sh_att:
                mis.append((nm, day, sh_att, dbsh))
print(f'total mismatches: {len(mis)}')
for m in mis:
    print(f'  {m}')
a.close()
p.close()
