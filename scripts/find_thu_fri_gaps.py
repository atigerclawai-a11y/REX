#!/usr/bin/env python3
"""Find missing plates for Thu/Fri after the clean sync."""
import json
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
orders = json.load(open('/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json'))
a = sqlite3.connect(AUTH)
for date, col in [('2026-08-06', 'day_TH_actual'), ('2026-08-07', 'day_F_actual')]:
    for shift in (1, 2):
        sched = [r[0] for r in a.execute(f"SELECT name FROM clients WHERE active=1 AND {col}=?", (shift,))]
        have = set()
        for name, shifts in orders.get(date, {}).items():
            for sh, o in shifts.items():
                if int(sh) == shift:
                    have.add(name)
        missing = [n for n in sched if n not in have]
        print(f'{date} S{shift}: scheduled {len(sched)}, missing {len(missing)}: {missing}')
a.close()
