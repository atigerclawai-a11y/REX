#!/usr/bin/env python3
"""THURSDAY DEEP CHECK: auth says 118/47=165. Live Carecenta Day5 said 149.
Find WHO the extra 16 are (in auth TH but NOT in Carecenta TH)."""
import difflib
import json
import sqlite3

cc = json.load(open('/tmp/carecenta_clients_week.json'))
a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')

# Carecenta Thursday attendees (Day5)
cc_thu = set()
for name, days in cc:
    if '5' in {str(d) for d in days}:
        cc_thu.add(name.lower())
print(f'Carecenta Thursday: {len(cc_thu)} clients')

# auth Thursday attendees
au_thu = set()
for shift in (1, 2):
    for r in a.execute("SELECT name FROM clients WHERE active=1 AND day_TH_actual=?", (shift,)):
        au_thu.add(r[0].lower())
print(f'Auth Thursday: {len(au_thu)} clients')

# auth-but-not-Carecenta (the extra)
extra = au_thu - cc_thu
print(f'\nIN AUTH NOT CARECENTA ({len(extra)}):')
for n in sorted(extra):
    # find auth display name
    r = a.execute("SELECT name, day_TH_actual FROM clients WHERE LOWER(name)=?", (n,)).fetchone()
    print(f'  {r[0]} S{r[1]}')

# Carecenta-but-not-auth (the missing)
missing = cc_thu - au_thu
print(f'\nIN CARECENTA NOT AUTH ({len(missing)}):')
for n in sorted(missing):
    print(f'  {n}')
a.close()
