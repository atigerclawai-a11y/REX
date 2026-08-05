#!/usr/bin/env python3
"""Type-safe shift mismatch check: int(att) vs int(db)."""
import json
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
b5 = json.load(open('/tmp/w31_batch_5.json'))

real = []
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
            if int(dbsh) != int(sh_att):
                real.append((nm, day, sh_att, dbsh))

print(f'REAL mismatches (int-compare): {len(real)}')
for m in real:
    print(f'  {m}')
a.close()
p.close()
