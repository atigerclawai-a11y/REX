#!/usr/bin/env python3
"""Fedorova Olga's vision marks (batch 5 n=6) + shift check."""
import json

b5 = json.load(open('/tmp/w31_batch_5.json'))
m5 = json.load(open('/tmp/w31_marks_5.json'))

for x in b5:
    if x.get('name') == 'Fedorova Olga':
        print(f'batch5 n={x["n"]} doc={x["doc"]} page={x["page"]}')
        marks = m5.get(str(x['n']), {})
        print(f'MARKS: {json.dumps(marks, ensure_ascii=False, indent=1)}')
        break

# also check the first-batch 30 review (doc006808 page 25 = which form #?)
# the first 30 review had #6 = Fedorova Olga per the earlier list
print('\n(first-30 review had #6 Fedorova Olga — doc006808 p25)')

# check other clients in batch 5 who attend S1 — did they get wrong shift too?
print('\n=== batch-5 clients: attendance vs DB shift mismatch check ===')
import sqlite3
a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
mismatch = []
for x in b5:
    nm = x.get('name') or x.get('match')
    if not nm:
        continue
    att = a.execute("SELECT day_M_actual, day_T_actual, day_W_actual, day_TH_actual, day_F_actual FROM clients WHERE name=?", (nm,)).fetchone()
    if not att:
        continue
    days = ['M', 'T', 'W', 'TH', 'F']
    for i, day in enumerate(days):
        sh_att = att[i]
        if not sh_att:
            continue
        # DB row shift for that day
        dbrow = p.execute("""SELECT shift, source_sheet FROM client_menus
            WHERE client_name=? AND day_code=? AND menu_date BETWEEN '2026-08-03' AND '2026-08-07'""",
            (nm, day)).fetchone()
        if dbrow and dbrow[0] != sh_att:
            mismatch.append((nm, day, sh_att, dbrow[0], dbrow[1]))
print(f'mismatches: {len(mismatch)}')
for m in mismatch:
    print(f'  {m}')
a.close()
p.close()
