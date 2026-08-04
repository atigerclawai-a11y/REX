#!/usr/bin/env python3
"""Check: scheduled Wednesday clients (day_W_actual) WITHOUT a menu order in goj_proprietary.db."""
import json
import sqlite3

DATE = '2026-08-05'
AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'

a = sqlite3.connect(AUTH)
sched = a.execute("SELECT name, day_W_actual FROM clients WHERE active=1 AND day_W_actual IN (1,2)").fetchall()
a.close()

p = sqlite3.connect(PROP)
rows = p.execute("""SELECT client_name, shift FROM client_menus
    WHERE menu_date=? AND main NOT LIKE '%заказ не размещен%' AND main != ''""", (DATE,)).fetchall()
p.close()
have = {(n, str(s)) for n, s in rows}

missing = [(n, s) for n, s in sched if (n, str(s)) not in have]
print(f'scheduled: {len(sched)}  (S1={sum(1 for _,s in sched if s==1)} S2={sum(1 for _,s in sched if s==2)})')
print(f'scheduled WITHOUT menu order ({len(missing)}):')
for n, s in missing:
    print(f'  S{s}: {n}')
