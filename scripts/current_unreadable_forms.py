#!/usr/bin/env python3
"""CURRENT unreadable forms per doc: pages not covered by extraction.json,
minus what the DB already has as ocr_scan (recovery may have applied picks)."""
import json
import sqlite3
from pathlib import Path

BASE = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'

TARGETS = ['doc00681220260727160712', 'doc00687920260729073826', 'doc00688020260729073901',
           'doc00688120260729073944', 'doc00688920260729104631', 'doc00689120260729104710',
           'doc00692120260730070429', 'doc00692220260730070458', 'doc00692320260730070515',
           'doc00700820260731112335', 'doc00700920260731112356', 'doc00701020260731112428',
           'doc00701120260731112514', 'doc00701220260731112550', 'doc00701320260731112608',
           'doc00701420260731112656']

print(f"{'doc':<22}{'pages':>6}{'extr':>6}{'unread':>8}")
total_unread = 0
for d in TARGETS:
    ddir = BASE / d
    if not ddir.exists():
        continue
    # count pages via p*-*.png files
    pngs = sorted(ddir.glob('p*-*.png'))
    # unique page numbers (p7-07 → page 7)
    pages = set()
    for p in pngs:
        try:
            num = int(p.name.split('-')[0][1:])
            pages.add(num)
        except Exception:
            pass
    npages = len(pages)
    # forms = page pairs → odd page starts a form
    nforms = (npages + 1) // 2
    # extracted names from extraction.json
    ej = ddir / 'extraction.json'
    extracted = 0
    if ej.exists():
        try:
            extracted = len(json.load(open(ej)))
        except Exception:
            extracted = -1
    unread = nforms - extracted if extracted >= 0 else nforms
    total_unread += max(unread, 0)
    print(f"{d:<22}{npages:>6}{extracted:>6}{max(unread,0):>8}")

print(f"\nTOTAL unreadable forms (current): {total_unread}")
