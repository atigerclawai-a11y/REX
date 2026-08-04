#!/usr/bin/env python3
"""Check: (a) what the emailed orders JSON has for these clients vs DB now,
(b) promoter cron last runs, (c) recovery extraction output."""
import json
import sqlite3
import os

# (a) orders JSON vs DB
orders = json.load(open('/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json'))
p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
print('=== emailed JSON vs DB for garbage clients (Wed) ===')
for name in ['Mikhaylova Sofiya', 'Kormova Lyubov', 'Minogina Ninel', 'Umanskaya Yelena']:
    j = orders.get('2026-08-05', {}).get(name, {})
    db = p.execute("""SELECT salad, soup, main, side, source_sheet FROM client_menus
        WHERE client_name=? AND menu_date='2026-08-05'""", (name,)).fetchall()
    print(f'\n{name}:')
    print(f'  JSON: {j}')
    for r in db:
        print(f'  DB:   {r[0]}|{r[1]}|{r[2]}|{r[3]} [{r[4]}]')
p.close()

# (b) orders JSON mtime
st = os.stat('/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json')
from datetime import datetime
print(f'\norders JSON mtime: {datetime.fromtimestamp(st.st_mtime).strftime("%m-%d %H:%M:%S")}')

# (c) promoter cron output dir
cron_out = '/Users/mainsobhelper/.hermes/profiles/work/cron/output/4132e4a0f3a6'
if os.path.isdir(cron_out):
    files = sorted(os.listdir(cron_out))
    print(f'\npromoter cron outputs (last 5): {files[-5:]}')
    if files:
        latest = os.path.join(cron_out, files[-1])
        txt = open(latest, errors='ignore').read()
        print(f'  {files[-1]}: {txt[:300]}')
