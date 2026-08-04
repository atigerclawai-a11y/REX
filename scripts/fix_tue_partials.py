#!/usr/bin/env python3
"""Fix partial Tuesday rows — delete stale partials in BOTH DBs + orders JSON,
so CC_menu_fill tops up from own history."""
import json
import sqlite3

DATE = '2026-08-04'
DBS = ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
       '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']
# Partial/garbage rows found: missing dishes or non-canonical abbreviations
names = ['Sorits Lev', 'Brikker Ella', 'Krivolapov Leonid', 'Marder Yakov',
         'Kravets Sima', 'Mikhaylova Sofiya', 'Leykina Margatita', 'Livanova Marioula']

for db in DBS:
    c = sqlite3.connect(db)
    n = 0
    for name in names:
        cur = c.execute("DELETE FROM client_menus WHERE menu_date=? AND client_name=?", (DATE, name))
        n += cur.rowcount
    c.commit()
    c.close()
    print(f'{db}: deleted {n} partial rows for {DATE}')

P = '/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json'
d = json.load(open(P))
if '2026-08-04' in d:
    for name in names:
        d['2026-08-04'].pop(name, None)
    json.dump(d, open(P, 'w'), ensure_ascii=False, indent=1)
    print('orders JSON: removed partial entries for the 8 clients')
