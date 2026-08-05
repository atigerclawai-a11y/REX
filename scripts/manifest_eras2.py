#!/usr/bin/env python3
"""Manifest docs by era: [docname, pages] pairs."""
import json
import re

mf = '/Users/mainsobhelper/Desktop/REX/.page_guard_recover.json'
data = json.load(open(mf))
docs = data.get('docs', [])
print(f'{len(docs)} docs')
w31, w30, older = [], [], []
for docname, pages in docs:
    m = re.search(r'doc\d+(\d{8})\d*', str(docname))
    date = m.group(1) if m else '????'
    if date >= '20260729':
        w31.append((docname, pages))
    elif date >= '20260727':
        w30.append((docname, pages))
    else:
        older.append((docname, pages))

print(f'\nW31 (Jul29+, THIS week): {len(w31)}')
for d, p in w31:
    print(f'  {d[:30]}: {p}pp')
print(f'\nW30 (Jul27-28): {len(w30)}')
for d, p in w30:
    print(f'  {d[:30]}: {p}pp')
print(f'\nOLDER (pre-Jul27): {len(older)}')
for d, p in older[:10]:
    print(f'  {d[:30]}: {p}pp')
