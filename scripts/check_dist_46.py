#!/usr/bin/env python3
"""Check distribution sheets — find client #46 in each."""
import fitz
import os
import re

OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'
files = [
    'GOJ_T_S1_Tuesday_distribution.pdf',
    'GOJ_T_S2_Tuesday_distribution.pdf',
    'GOJ_W_S1_Wednesday_distribution.pdf',
    'GOJ_W_S2_Wednesday_distribution.pdf',
]

for f in files:
    p = os.path.join(OUT, f)
    doc = fitz.open(p)
    print(f'\n{"="*70}\n{f} — {doc.page_count} pages\n{"="*70}')
    # find numbered rows: "46 <name> ..." — distribution rows start with index
    lines = []
    for pg in doc:
        t = pg.get_text()
        for l in t.splitlines():
            l = l.strip()
            if l:
                lines.append(l)
    doc.close()
    # print context around any "46" at line start
    for i, l in enumerate(lines):
        if re.match(r'^46\s', l) or l == '46':
            print(f'  FOUND #46 at line {i+1}: {l}')
            # print neighbors
            for j in range(max(0, i-2), min(len(lines), i+4)):
                print(f'    [{j+1}] {lines[j]}')
            print()
