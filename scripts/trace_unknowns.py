#!/usr/bin/env python3
"""Trace: original manifest n for the 3 unknown rows + what results holds for them."""
import json

MANIFEST = json.load(open('/tmp/unreadable_full_manifest.json'))
results = json.load(open('/tmp/unreadable_guesses.json'))
vf = json.load(open('/tmp/vision_fixes.json'))

targets = [('doc00688120260729073944', 37), ('doc00701320260731112625', 15),
           ('doc00701420260731112656', 33)]
for d, pg in targets:
    orig = [m for m in MANIFEST if m['doc'] == d and m['page'] == pg]
    print(f'{d} p{pg}:')
    for m in orig:
        print(f"  manifest n={m['n']} crop={m['crop'].split('/')[-1]}")
        print(f"  results[{m['n']}]={results.get(str(m['n']))!r}")
        print(f"  vision_fixes[{m['n']}]={vf.get(str(m['n']))!r}")

# also check: was there a duplicate page entry for 881?
print('\nall doc006881 entries in manifest:')
for m in MANIFEST:
    if m['doc'] == 'doc00688120260729073944':
        print(f"  n={m['n']} p{m['page']}")
