#!/usr/bin/env python3
"""Cross-check: are the 96 no-ocr clients in the confirmed 220?"""
import json
import sqlite3

# confirmed names
confirmed = set()
for bf in ['/tmp/w31_batch_1.json', '/tmp/w31_batch_2.json', '/tmp/w31_batch_3.json',
           '/tmp/w31_batch_4.json', '/tmp/w31_batch_5.json']:
    try:
        for x in json.load(open(bf)):
            confirmed.add(x.get('name') or x.get('match'))
    except Exception:
        pass
print(f'confirmed: {len(confirmed)}')

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
noform = [r[0] for r in p.execute("""SELECT DISTINCT client_name FROM client_menus
    WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07'
    AND client_name NOT IN (
        SELECT DISTINCT client_name FROM client_menus
        WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07' AND source_sheet='ocr_scan')
    ORDER BY client_name""")]
p.close()

in_conf = [n for n in noform if n in confirmed]
not_conf = [n for n in noform if n not in confirmed]
print(f'no-ocr clients: {len(noform)} | in confirmed: {len(in_conf)} | NOT confirmed: {len(not_conf)}')
print(f'\nIN CONFIRMED but no ocr rows ({len(in_conf)}):')
for n in in_conf:
    print(f'  {n}')
print(f'\nNOT confirmed (no form found) ({len(not_conf)}):')
for n in not_conf:
    print(f'  {n}')
