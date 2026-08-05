#!/usr/bin/env python3
"""Check why Thu JSON has 115 S1 orders vs 118 scheduled (3 gap)."""
import json
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
orders = json.load(open('/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json'))
a = sqlite3.connect(AUTH)
for shift in (1, 2):
    sched = [r[0] for r in a.execute("SELECT name FROM clients WHERE active=1 AND day_TH_actual=?", (shift,))]
    have = set()
    for name, shifts in orders.get('2026-08-06', {}).items():
        for sh, o in shifts.items():
            if int(sh) == shift:
                have.add(name)
    missing = [n for n in sched if n not in have]
    print(f'THU S{shift}: scheduled {len(sched)}, in JSON {len(have)}, missing {missing}')
a.close()
