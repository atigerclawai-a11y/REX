#!/usr/bin/env python3
"""Identify EXACT unreadable form pages per July 27-31 doc (pages not covered by extraction)."""
import json
from pathlib import Path

BASE = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')
docs = ['doc00680820260727160512', 'doc00680920260727160541', 'doc00681120260727160643',
        'doc00681220260727160712', 'doc00687920260729073826', 'doc00688020260729073901',
        'doc00688120260729073944', 'doc00688920260729104631', 'doc00689120260729104710',
        'doc00692120260730070429', 'doc00701120260731112514', 'doc00701220260731112550',
        'doc00701320260731112625', 'doc00701420260731112656']

all_unreadable = []
for doc in docs:
    d = BASE / doc
    npng = len([f for f in d.glob('p*-*.png') if not f.name.startswith('pg')])
    ej = d / 'extraction.json'
    covered_pages = set()
    if ej.exists():
        data = json.load(open(ej))
        if isinstance(data, dict):
            for n, info in data.items():
                if isinstance(info, dict):
                    for p in info.get('pages', []):
                        covered_pages.add(int(p))
    # forms = page pairs (1,2),(3,4),...
    unreadable_forms = []
    for i in range(0, npng, 2):
        p1 = i + 1
        p2 = i + 2
        if p1 not in covered_pages:
            unreadable_forms.append((p1, p2))
    if unreadable_forms:
        all_unreadable.append((doc, npng, unreadable_forms))

for doc, npng, forms in all_unreadable:
    print(f'{doc}: {npng}pp, {len(forms)} unreadable forms — pages {[f[0] for f in forms]}')
print(f'\nTOTAL unreadable forms across processed July 27-31 docs: {sum(len(f) for _,_,f in all_unreadable)}')
