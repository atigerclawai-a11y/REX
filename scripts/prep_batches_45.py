#!/usr/bin/env python3
"""Build batch 4 (40 July-27 forms from the 197) + batch 5 (30 first-batch forms
from doc006808/809/811) for vision extraction."""
import json
import re
from pathlib import Path

BASE = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')

# Batch 4: July-27 forms from the matched table (006810 + 006812)
ROWS = json.load(open('/tmp/matched_table_final.json'))
jul27 = [r for r in ROWS if r['doc'] in ('doc00681020260727160603', 'doc00681220260727160712')]
print(f'batch 4 (July-27 from 197): {len(jul27)}')

# Batch 5: the 30 first-batch confirmed forms (UNREAD_*.png filenames → doc+page)
# names from the first review: 1-30 mapping in the original table
FIRST_NAMES = ['Ivanova Liudmila', 'Bogat Svetlana', 'Gritshevsky Yosef', 'Radomyselskiy Semen',
               'Shifrina Margarita', 'Fedorova Olga', 'Borshchevskaya Galina', 'Shvarts Edvard',
               'Khalfina Aida', 'Rudoy Emma', 'Elbert Milla', 'Makaron Khaya', 'Levin Leonid',
               'Chupikova Elvira', 'Shapiro Roza', 'Nirshberg Aron', 'Yemelyanova Alla',
               'Mindich Aleksandr', 'Rukhlevich Svetlana', 'Slavinskiy Grigoriy',
               'Palatnik Yelizaveta', 'Leybengrub Larisa', 'Rodava Iryna', 'Rodov Vladimir',
               'Adyan Ludmila', 'Grinshpun Izrail', 'Prilutskaya Tatyana', 'Kovaleva Viktoriya',
               'Bialkovska Maria', 'Posadova Liubov']

unread = {}
for p in Path('/Users/mainsobhelper/Desktop/REX/garbled_review').glob('UNREAD_*.png'):
    m = re.match(r'UNREAD_\d+_(doc\d+)_p(\d+)\.png', p.name)
    if m:
        idx = int(p.name.split('_')[1])
        unread[idx] = (m.group(1), int(m.group(2)))

first30 = []
for i, name in enumerate(FIRST_NAMES, 1):
    doc, page = unread.get(i, (None, None))
    if doc is None:
        print(f'  MISSING mapping for #{i} {name}')
        continue
    ddir = BASE / doc
    p1 = ddir / f"p{page}-{page:02d}.png"
    p2 = ddir / f"p{page+1}-{page+1:02d}.png"
    if not p1.exists():
        p1 = ddir / f"p{page}-{page}.png"
    if not p2.exists():
        p2 = ddir / f"p{page+1}-{page+1}.png"
    first30.append({'n': i, 'name': name, 'doc': doc, 'page': page,
                    'p1': str(p1), 'p2': str(p2), 'p1_ok': p1.exists(), 'p2_ok': p2.exists()})
print(f'batch 5 (first 30): {len(first30)}')

missing = [f for f in first30 if not f['p1_ok'] or not f['p2_ok']]
print(f'  missing pages: {len(missing)}')
for f in missing:
    print(f"    #{f['n']} {f['name']} {f['doc']} p{f['page']}")

json.dump(jul27, open('/tmp/w31_batch_4.json', 'w'), indent=1)
json.dump(first30, open('/tmp/w31_batch_5.json', 'w'), indent=1)
print('saved batch 4 + 5')
