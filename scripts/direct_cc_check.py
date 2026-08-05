#!/usr/bin/env python3
"""Direct check: do Carecenta names exist for the 'extra' auth clients?"""
import json
import sqlite3

cc = json.load(open('/tmp/carecenta_clients_week.json'))
cc_all = sorted({name.lower() for name, days in cc})
cc_thu = {name.lower() for name, days in cc if '5' in {str(d) for d in days}}

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
targets = ['Brodskaya Lidiya', 'Buslayeva Alisa', 'Chebotareva Galina', 'Chupikova Elvira',
           'Coniglio Vera', 'Dirul Serghei', 'Dodik Sima', 'Dovgalyuk Zelda', 'Elbert Milla',
           'Fedorova Olga', 'Fridman Mikhail', 'Furman Vladimir', 'Bakanurskiy Svetlana',
           'Gukovskaja Natasha', 'Shtaygman Yelena']

for t in targets:
    low = t.lower()
    # exact in Carecenta?
    in_cc = low in cc_thu
    # any surname match in Carecenta Thursday?
    sur = low.split()[0]
    sur_matches = [c for c in cc_thu if c.split()[0] == sur]
    print(f'{t}: inCC_THU={in_cc}, surname matches in CC_THU: {sur_matches or "NONE"}')

print(f'\nCarecenta total clients: {len(cc_all)}, Thursday: {len(cc_thu)}')
a.close()
