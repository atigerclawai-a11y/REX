#!/usr/bin/env python3
"""Fix partial OCR rows for the 5 clients missing mains — delete stale partials,
re-run fill chain (tops up from own history). DELETE scoped to these clients+date."""
import sqlite3

DATE = '2026-08-05'
DBS = ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
       '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']
names = ['Borshch Diana', 'Krivitskaya Zoya', 'Krivolapov Leonid', 'Leyderman Feliks', 'Povroznik Mikhail']

for db in DBS:
    c = sqlite3.connect(db)
    n = 0
    for name in names:
        cur = c.execute("DELETE FROM client_menus WHERE menu_date=? AND client_name=?", (DATE, name))
        n += cur.rowcount
    c.commit()
    c.close()
    print(f'{db}: deleted {n} partial rows for {DATE}')

# Also remove the 2026-08-05 entry from the runtime orders JSON so the fill
# chain + rebuild writes fresh data (clean slate for these clients).
import json
P = '/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json'
d = json.load(open(P))
if '2026-08-05' in d:
    for name in names:
        d['2026-08-05'].pop(name, None)
    json.dump(d, open(P, 'w'), ensure_ascii=False, indent=1)
    print('orders JSON: removed partial entries for the 5 clients')
