#!/usr/bin/env python3
"""Prepare vision-extraction batch files for the 157 week-31 forms.
Each entry: doc, page1, page2, expected client name."""
import json
from pathlib import Path

ROWS = json.load(open('/tmp/matched_table_final.json'))
BASE = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')

W31_DOCS = {'doc00687820260729073749', 'doc00687920260729073826', 'doc00688020260729073901',
            'doc00688120260729073944', 'doc00701120260731112514', 'doc00701220260731112550',
            'doc00701320260731112625', 'doc00701420260731112656'}

forms = []
for r in ROWS:
    if r['doc'] not in W31_DOCS:
        continue
    ddir = BASE / r['doc']
    p1 = ddir / f"p{r['page']}-{r['page']:02d}.png"
    p2 = ddir / f"p{r['page']+1}-{r['page']+1:02d}.png"
    if not p1.exists():
        p1 = ddir / f"p{r['page']}-{r['page']}.png"
    if not p2.exists():
        p2 = ddir / f"p{r['page']+1}-{r['page']+1}.png"
    forms.append({'n': r['n'], 'name': r['match'], 'doc': r['doc'], 'page': r['page'],
                  'p1': str(p1), 'p2': str(p2), 'p1_ok': p1.exists(), 'p2_ok': p2.exists()})

print(f'week-31 forms: {len(forms)}')
missing = [f for f in forms if not f['p1_ok'] or not f['p2_ok']]
print(f'missing pages: {len(missing)}')
for f in missing:
    print(f"  #{f['n']} {f['name']} {f['doc']} p{f['page']} p1_ok={f['p1_ok']} p2_ok={f['p2_ok']}")

json.dump(forms, open('/tmp/w31_forms.json', 'w'), indent=1)

# split into 3 batches for parallel vision extraction
import math
B = 3
size = math.ceil(len(forms) / B)
for i in range(B):
    batch = forms[i * size:(i + 1) * size]
    json.dump(batch, open(f'/tmp/w31_batch_{i + 1}.json', 'w'), indent=1)
    print(f'batch {i + 1}: {len(batch)} forms')
