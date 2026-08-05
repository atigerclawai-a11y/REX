#!/usr/bin/env python3
"""Is 149 (scrape) vs 165 (auth) a spelling issue or a real gap?
Check: auth Thursday clients not in scrape — are they in scrape under OTHER days?
And does the scrape pagination cover ALL clients?"""
import difflib
import json
import sqlite3

cc = json.load(open('/tmp/carecenta_clients_week.json'))
cc_all = {name.lower(): days for name, days in cc}

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')

# The 14 auth-Thu clients 'missing' from scrape — check if they're in scrape under variant spelling
print('=== 14 auth-Thu clients: variant spelling in scrape? ===')
check = ['Diadia Valentina', 'Dorodnova Kateryna', 'Dovgalyuk Zelda', 'Drochik Oleg',
         'Goryachkovsky Alexandr', 'Gurevich Victor', 'Katerskaya Nina',
         'Kheyfits-Shapiro Aleksandra', 'Melnyk Mariia', 'Meltser Eugene', 'Meltser Larisa',
         'Patsiuchenko Oleg', 'Perepelytsa Lubov', 'Sekh Stefaniia']
for name in check:
    low = name.lower()
    if low in cc_all:
        print(f'  {name}: IN SCRAPE (days={cc_all[low]})')
        continue
    sur = low.split()[0]
    variants = [n for n in cc_all if n.split()[0] == sur or difflib.SequenceMatcher(None, low, n).ratio() > 0.8]
    print(f'  {name}: variants={variants or "NONE"}')

# How many auth-active clients have zero attendance all week? (wouldn't be in scrape)
print('\n=== auth-active clients with NO attendance this week ===')
zero = 0
for r in a.execute("""SELECT name, day_M_actual, day_T_actual, day_W_actual, day_TH_actual, day_F_actual
    FROM clients WHERE active=1"""):
    if not (r[1] or r[2] or r[3] or r[4] or r[5]):
        zero += 1
print(f'  {zero} clients with zero attendance (not in scrape by design)')
a.close()
