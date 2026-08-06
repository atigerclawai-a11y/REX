#!/usr/bin/env python3
"""Find Wed Aug 5 missing plates (72/73, 95/96)."""
import json
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
orders = json.load(open('/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json'))
a = sqlite3.connect(AUTH)
for shift in (1, 2):
    sched = [r[0] for r in a.execute("SELECT name FROM clients WHERE active=1 AND day_W_actual=?", (shift,))]
    have = set()
    for name, shifts in orders.get('2026-08-05', {}).items():
        for sh, o in shifts.items():
            if int(sh) == shift:
                have.add(name)
    missing = [n for n in sched if n not in have]
    print(f'WED S{shift}: scheduled {len(sched)}, missing {len(missing)}: {missing}')
a.close()
