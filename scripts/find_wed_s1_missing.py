#!/usr/bin/env python3
"""Find the Wed S1 client missing an order after the Diadia fix."""
import json
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
orders = json.load(open('/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json'))

acon = sqlite3.connect(AUTH)
entry = orders.get('2026-08-05', {})
sched = [r[0] for r in acon.execute("SELECT name FROM clients WHERE active=1 AND day_W_actual=1")]
with_order = []
for name, shifts in entry.items():
    for sh, o in shifts.items():
        if int(sh) == 1:
            with_order.append(name)
missing = [n for n in sched if n not in with_order]
print(f'S1 scheduled {len(sched)}, orders {len(with_order)}, MISSING {len(missing)}')
for m in missing:
    print(f'  ⚠️ {m}')
acon.close()
