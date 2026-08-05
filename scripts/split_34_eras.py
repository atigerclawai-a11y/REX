#!/usr/bin/env python3
"""Split the 34 docs: which are THIS week's source scans (Jul 27-31) vs OLDER
(Jul 16-24 = previous week's forms). And which were vision-recovered."""
import json
import re

docs34 = json.load(open('/tmp/manifest_34.json'))
this_week, older = [], []
for docname, pages, path in docs34:
    m = re.search(r'^\d{6}(\d{8})\d{6}$', str(docname).split('.')[0])
    d8 = m.group(1) if m else '?'
    if d8 >= '20260727':
        this_week.append((docname, pages, d8))
    else:
        older.append((docname, pages, d8))

print(f'THIS WEEK (Jul 27-31 = forms for Aug 3-7): {len(this_week)}')
for d, pg, dt in this_week:
    print(f'  {d} ({pg}pp, {dt})')
print(f'\nOLDER (Jul 16-24 = PREVIOUS week forms): {len(older)}')
for d, pg, dt in older:
    print(f'  {d} ({pg}pp, {dt})')
