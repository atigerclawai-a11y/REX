#!/usr/bin/env python3
"""Complete unreadable review: ALL July 27-31 era unreadable forms minus the 30
confirmed. Crop name region, number, save manifest."""
import json
import re
from pathlib import Path
from PIL import Image

BASE = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')
CROPS = Path('/tmp/name_crops_all')
CROPS.mkdir(parents=True, exist_ok=True)

DOCS = ['doc00680820260727160512', 'doc00680920260727160541', 'doc00681020260727160603',
        'doc00681120260727160643', 'doc00681220260727160712', 'doc00687820260729073749',
        'doc00687920260729073826', 'doc00688020260729073901', 'doc00688120260729073944',
        'doc00692120260730070429', 'doc00701120260731112514', 'doc00701220260731112550',
        'doc00701320260731112625', 'doc00701420260731112656']

# 30 confirmed pages (from the review PDF file names)
CONFIRMED = set()
for p in Path('/Users/mainsobhelper/Desktop/REX/garbled_review').glob('UNREAD_*.png'):
    m = re.match(r'UNREAD_\d+_(doc\d+)_p(\d+)\.png', p.name)
    if m:
        CONFIRMED.add((m.group(1), int(m.group(2))))
print(f'confirmed pages: {len(CONFIRMED)}')

forms = []
for d in DOCS:
    ddir = BASE / d
    if not ddir.exists():
        continue
    ej = ddir / 'extraction.json'
    extracted_pages = set()
    if ej.exists():
        try:
            for v in json.load(open(ej)).values():
                if isinstance(v, dict) and 'pages' in v:
                    for pg in v['pages']:
                        extracted_pages.add(int(pg))
        except Exception:
            pass
    pngs = sorted(ddir.glob('p*-*.png'), key=lambda p: int(p.name.split('-')[0][1:]) if p.name.split('-')[0][1:].isdigit() else 0)
    pages = {}
    for p in pngs:
        try:
            pages[int(p.name.split('-')[0][1:])] = p
        except Exception:
            pass
    odd_pages = sorted(p for p in pages if p % 2 == 1)
    for pg in odd_pages:
        if (d, pg) in CONFIRMED:
            continue
        if pg in extracted_pages:
            continue  # already extracted (has real picks in DB)
        forms.append((d, pg, pages[pg]))

print(f'unreadable forms to send: {len(forms)}')
# crop name region (top 28% — Имя: field) from each form's first page
manifest = []
for i, (d, pg, png) in enumerate(forms, 1):
    out = CROPS / f'F{i:03d}_{d}_p{pg}.png'
    if not out.exists():
        img = Image.open(png)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.28)))
        crop.save(out)
    manifest.append({'n': i, 'doc': d, 'page': pg, 'crop': str(out)})
json.dump(manifest, open('/tmp/unreadable_full_manifest.json', 'w'), indent=1)
print(f'crops saved: {len(manifest)} → {CROPS}')
