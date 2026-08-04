#!/usr/bin/env python3
"""Find scheduled clients with NO menu order on Aug 4/5."""
import json
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
orders = json.load(open('/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json'))

acon = sqlite3.connect(AUTH)
for date, day_col in [('2026-08-04', 'day_T_actual'), ('2026-08-05', 'day_W_actual')]:
    print(f'\n=== {date} ===')
    entry = orders.get(date, {})
    for shift in (1, 2):
        sched = [r[0] for r in acon.execute(
            f"SELECT name FROM clients WHERE active=1 AND {day_col}=?", (shift,))]
        with_order = []
        for name, shifts in entry.items():
            for sh, o in shifts.items():
                if int(sh) == shift:
                    with_order.append(name)
        missing = [n for n in sched if n not in with_order]
        print(f'  S{shift}: scheduled {len(sched)}, orders {len(with_order)}, MISSING {len(missing)}')
        for m in missing:
            print(f'    ⚠️ {m}')
acon.close()
