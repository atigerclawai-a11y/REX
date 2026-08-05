#!/usr/bin/env python3
"""Verify: Dovgalyuk Zelda + Drochik Oleg in auth TH=1 — check their Carecenta
schedule via the tue_definitive/wed_definitive sync records (the synced truth)."""
import json
import os
import sqlite3

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
for name in ['Dovgalyuk Zelda', 'Drochik Oleg']:
    r = a.execute("""SELECT name, active, day_M_actual, day_T_actual, day_W_actual,
        day_TH_actual, day_F_actual FROM clients WHERE name=?""", (name,)).fetchone()
    print(f'{name}: {r}')

# check definitive sync records
print('\n=== definitive sync files ===')
for f in ['tue_definitive.json', 'wed_definitive.json']:
    for root in ['/Users/mainsobhelper/Desktop/REX/data', '/Users/mainsobhelper/Desktop/REX',
                 '/Users/mainsobhelper/Documents/goj files/data']:
        p = os.path.join(root, f)
        if os.path.exists(p):
            mt = os.path.getmtime(p)
            print(f'  {p} (mtime {mt})')
            break
a.close()
