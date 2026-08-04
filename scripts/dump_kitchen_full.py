#!/usr/bin/env python3
"""Full dump of both kitchen sheets to find ALL jumbles."""
import fitz
import os

OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'
for f in ['GOJ_T_S1_Tuesday_kitchen.pdf', 'GOJ_T_S2_Tuesday_kitchen.pdf']:
    p = os.path.join(OUT, f)
    doc = fitz.open(p)
    print(f'\n{"="*60}\n{f} ({doc.page_count} pages)\n{"="*60}')
    for pi in range(doc.page_count):
        t = doc[pi].get_text()
        lines = [l for l in t.splitlines() if l.strip()]
        print(f'--- page {pi+1} ({len(lines)} lines) ---')
        for i, l in enumerate(lines[:60]):
            print(f'  {l}')
        if len(lines) > 60:
            print(f'  ... ({len(lines)-60} more lines)')
    doc.close()
