#!/usr/bin/env python3
"""Check footer week on first form of each July 27-31 doc (vision needs the crop;
here we just list which forms belong to which docs so I can spot-check)."""
import json

ROWS = json.load(open('/tmp/matched_table_final.json'))
from collections import Counter
docs = Counter(r['doc'] for r in ROWS)
for d, c in docs.most_common():
    # first page of first form in this doc
    r = next(x for x in ROWS if x['doc'] == d)
    print(f'{d}: {c} forms — first: #{r["n"]} {r["match"]} p{r["page"]}')
