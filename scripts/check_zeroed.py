#!/usr/bin/env python3
"""Full extent: how many active clients got zeroed for Tue by the 05:15 sync?"""
import sqlite3

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
zeroed_t = a.execute("""SELECT COUNT(*) FROM clients WHERE active=1 AND day_T_base IN (1,2) AND day_T_actual=0""").fetchone()[0]
zeroed_w = a.execute("""SELECT COUNT(*) FROM clients WHERE active=1 AND day_W_base IN (1,2) AND day_W_actual=0""").fetchone()[0]
print(f'clients base≠actual (zeroed): Tue={zeroed_t}, Wed={zeroed_w}')

# also: what's the change detector / sync last output?
import os
for lg in ['/Users/mainsobhelper/Desktop/REX/CC_carecenta_auth_sync.log',
           '/Users/mainsobhelper/Documents/goj files/logs/carecenta_auth_sync.log',
           '/Users/mainsobhelper/Desktop/REX/carecenta_auth_sync.log']:
    if os.path.exists(lg):
        lines = open(lg, errors='ignore').read().splitlines()
        print(f'\n{lg} last 12:')
        for l in lines[-12:]:
            print(f'  {l}')
a.close()
