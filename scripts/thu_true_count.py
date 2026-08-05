#!/usr/bin/env python3
"""Of the 63 auth clients missing from the scrape — how many attend Thursday?
And what's the TRUE Thursday count if the scrape were complete?"""
import json
import sqlite3

cc = json.load(open('/tmp/carecenta_clients_week.json'))
cc_all = {name.lower() for name, days in cc}

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
au_thu = []
missing_thu = []
for r in a.execute("SELECT name, day_TH_actual FROM clients WHERE active=1 AND day_TH_actual IN (1,2)"):
    n_low = r[0].lower()
    if n_low not in cc_all:
        missing_thu.append((r[0], r[1]))
    au_thu.append((r[0], r[1]))

print(f'Auth Thursday total: {len(au_thu)}')
print(f'  of which MISSING from Carecenta scrape: {len(missing_thu)}')
for name, shift in sorted(missing_thu):
    print(f'  S{shift} {name}')

# how many Carecenta Thursday clients are NOT in auth?
cc_thu = {name.lower() for name, days in cc if '5' in {str(d) for d in days}}
au_all_low = {r[0].lower() for r in a.execute("SELECT name FROM clients WHERE active=1")}
cc_only = [n for n in cc_thu if n not in au_all_low]
print(f'\nCarecenta Thu clients not in auth: {len(cc_only)}')
for n in sorted(cc_only):
    print(f'  {n}')
a.close()
