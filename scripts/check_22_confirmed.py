#!/usr/bin/env python3
"""Check: which of the 22 attending no-form clients are in the confirmed batches?"""
import json
import sqlite3

confirmed = set()
for bf in ['/tmp/w31_batch_1.json', '/tmp/w31_batch_2.json', '/tmp/w31_batch_3.json',
           '/tmp/w31_batch_4.json', '/tmp/w31_batch_5.json']:
    try:
        for x in json.load(open(bf)):
            confirmed.add(x.get('name') or x.get('match'))
    except Exception:
        pass

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
noform = set(r[0] for r in p.execute("""SELECT DISTINCT client_name FROM client_menus
    WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07'
    AND client_name NOT IN (
        SELECT DISTINCT client_name FROM client_menus
        WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07' AND source_sheet='ocr_scan')"""))
p.close()
a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
attending = set()
for n in noform:
    r = a.execute("SELECT day_T_actual, day_W_actual FROM clients WHERE name=?", (n,)).fetchone()
    if r and (r[0] in (1, 2) or r[1] in (1, 2)):
        attending.add(n)
a.close()

in_conf = sorted(attending & confirmed)
not_conf = sorted(attending - confirmed)
print(f'of {len(attending)} attending no-form clients:')
print(f'  IN confirmed batches: {len(in_conf)} → {in_conf}')
print(f'  NOT confirmed (no form found in review): {len(not_conf)} → {not_conf}')
