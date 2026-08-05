#!/usr/bin/env python3
"""Find Wed S2 client missing a plate (96 scheduled, 95 orders)."""
import json
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
orders = json.load(open('/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json'))
a = sqlite3.connect(AUTH)
sched = [r[0] for r in a.execute("SELECT name FROM clients WHERE active=1 AND day_W_actual=2")]
have = set()
for name, shifts in orders.get('2026-08-05', {}).items():
    for sh, o in shifts.items():
        if int(sh) == 2:
            have.add(name)
missing = [n for n in sched if n not in have]
print(f'Wed S2: scheduled {len(sched)}, have {len(have)}, missing {missing}')
a.close()
