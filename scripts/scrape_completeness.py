#!/usr/bin/env python3
"""Is the Carecenta scrape complete? Check if the 'extra' clients appear ANYWHERE
in the scrape (any day), or are missing entirely (scrape incomplete)."""
import json
import sqlite3

cc = json.load(open('/tmp/carecenta_clients_week.json'))
cc_all = {name.lower(): days for name, days in cc}
print(f'Carecenta scrape total: {len(cc_all)}')

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
au_all = {r[0].lower(): r[0] for r in a.execute("SELECT name FROM clients WHERE active=1")}
print(f'Auth active total: {len(au_all)}')

# auth clients NOT in the Carecenta scrape at all (scrape gap?)
not_in_scrape = [n for n in au_all if n not in cc_all]
print(f'\nAuth active NOT in Carecenta scrape ({len(not_in_scrape)}):')
for n in sorted(not_in_scrape)[:30]:
    r = a.execute("SELECT name, day_M_actual, day_T_actual, day_W_actual, day_TH_actual, day_F_actual FROM clients WHERE LOWER(name)=?", (n,)).fetchone()
    print(f'  {r[0]}: M={r[1]} T={r[2]} W={r[3]} TH={r[4]} F={r[5]}')
a.close()
