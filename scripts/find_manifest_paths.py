#!/usr/bin/env python3
"""Find the real file path for each of the 34 manifest docs."""
import json
import os

mf = '/Users/mainsobhelper/Desktop/REX/.page_guard_recover.json'
data = json.load(open(mf))
docs = data.get('docs', [])
print(f'{len(docs)} docs in manifest')

# candidate search roots
roots = [
    '/Users/mainsobhelper/Desktop/REX/menu_intake_stable',
    '/Users/mainsobhelper/Desktop/REX/menu_ocr_quarantine',
    '/Users/mainsobhelper/Desktop/REX/blank_parse',
    '/tmp/ocr_done_all',
    '/tmp/ocr_done',
    '/Users/mainsobhelper/Desktop/REX/scans',
    '/Users/mainsobhelper/Desktop/REX/ocr_done',
    '/Users/mainsobhelper/Desktop/REX/data',
    '/Users/mainsobhelper/Desktop/REX',
]

found = {}
for docname, pages in docs:
    # normalize: strip .pdf
    base = str(docname)
    if not base.endswith('.pdf'):
        base = base + '.pdf'
    hits = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _, files in os.walk(root):
            for f in files:
                if f == base or f == str(docname):
                    hits.append(os.path.join(dirpath, f))
    found[base] = (hits, pages)

missing = []
for docname, (hits, pages) in found.items():
    if hits:
        print(f'{docname}: {pages}pp → {hits[0]}')
    else:
        print(f'{docname}: {pages}pp → ❌ NOT FOUND')
        missing.append(docname)

json.dump({k: (v[0][0] if v[0] else None, v[1]) for k, v in found.items()},
          open('/tmp/manifest_paths.json', 'w'))
print(f'\n{len(missing)} missing')
