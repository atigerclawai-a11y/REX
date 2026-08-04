#!/usr/bin/env python3
"""Extract kitchen sheet contents — check row/line 46 in each."""
import fitz
import os

OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'
files = [
    'GOJ_T_S1_Tuesday_kitchen.pdf',
    'GOJ_T_S2_Tuesday_kitchen.pdf',
    'GOJ_W_S1_Wednesday_kitchen.pdf',
    'GOJ_W_S2_Wednesday_kitchen.pdf',
]

for f in files:
    p = os.path.join(OUT, f)
    if not os.path.exists(p):
        print(f'MISSING {f}')
        continue
    doc = fitz.open(p)
    print(f'\n{"="*70}\n{f} — {doc.page_count} pages\n{"="*70}')
    # extract all text lines across pages
    lines = []
    for pg in doc:
        t = pg.get_text()
        for l in t.splitlines():
            l = l.strip()
            if l:
                lines.append(l)
    doc.close()
    print(f'total lines: {len(lines)}')
    # show around line 46 (index 45)
    for i in range(max(0, 40), min(len(lines), 52)):
        print(f'  [{i+1}] {lines[i]}')
