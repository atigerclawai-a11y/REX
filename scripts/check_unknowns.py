#!/usr/bin/env python3
"""Cross-check UNKNOWN rows: which doc are they from, and are their picks already in the DB?"""
import json
import sqlite3

rows = json.load(open('/tmp/matched_table.json'))
unknown = [r for r in rows if not r['match']]
print(f'UNKNOWN: {len(unknown)}')

# group by doc
from collections import Counter
docs = Counter(r['doc'] for r in unknown)
for d, c in docs.most_common():
    print(f'  {d}: {c} forms')

# check doc006880 — was it vision-recovered?
p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
# how many ocr_scan rows exist for week 31 that came from doc006880-era docs?
for r in unknown:
    if '006880' in r['doc']:
        print(f"\n#{r['n']} {r['doc']} p{r['page']} — raw: {r['raw']!r}")
p.close()
