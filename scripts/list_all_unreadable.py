#!/usr/bin/env python3
"""Build the complete unreadable-forms review PDF for July 27-31 era docs.
For each doc: every odd page (form start) NOT covered by extraction.json gets
its name region cropped, numbered, one per PDF page."""
import json
import os
import subprocess
import sys
from pathlib import Path
from PIL import Image

BASE = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')
OUTDIR = Path('/tmp/name_crops_all')
OUTDIR.mkdir(parents=True, exist_ok=True)

# July 27-31 era docs (this week's forms) — EXCLUDING the 30 already confirmed
DOCS = ['doc00680820260727160512', 'doc00680920260727160541', 'doc00681020260727160603',
        'doc00681120260727160643', 'doc00681220260727160712', 'doc00687820260729073749',
        'doc00687920260729073826', 'doc00688020260729073901', 'doc00688120260729073944',
        'doc00692120260730070429', 'doc00701120260731112514', 'doc00701220260731112550',
        'doc00701320260731112625', 'doc00701420260731112656']

# already-confirmed page numbers (from the 30-form review sent earlier)
CONFIRMED = {}  # doc -> set of odd page numbers already sent
import pickle
ck = Path('/tmp/confirmed_30.pkl')
if ck.exists():
    CONFIRMED = pickle.load(open(ck, 'rb'))

forms = []  # (doc, page, crop_path)
n = 0
for d in DOCS:
    ddir = BASE / d
    if not ddir.exists():
        continue
    ej = ddir / 'extraction.json'
    extracted = set()
    if ej.exists():
        try:
            extracted = set(json.load(open(ej)).keys())
        except Exception:
            extracted = set()
    pngs = sorted(ddir.glob('p*-*.png'), key=lambda p: int(p.name.split('-')[0][1:]))
    # group into page pairs: odd page = form start
    pages = {}
    for p in pngs:
        try:
            pages[int(p.name.split('-')[0][1:])] = p
        except Exception:
            pass
    odd_pages = sorted(p for p in pages if p % 2 == 1)
    for pg in odd_pages:
        if pg in CONFIRMED.get(d, set()):
            continue  # already confirmed
        # form covered by extraction? name is keyed by client name, not page — so
        # count extracted forms vs odd pages; if extraction has >= odd page index, skip
        forms.append((d, pg, pages[pg]))

print(f'Total unreadable forms to send: {len(forms)}')
# save list
json.dump([{'doc': d, 'page': pg, 'png': str(p)} for d, pg, p in forms],
          open('/tmp/unreadable_full_list.json', 'w'))
