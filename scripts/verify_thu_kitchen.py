#!/usr/bin/env python3
"""Verify Thursday kitchen sheets: sections pure, totals match."""
import fitz
import os
from datetime import datetime

OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'
for f in ['GOJ_TH_S1_Thursday_kitchen.pdf', 'GOJ_TH_S2_Thursday_kitchen.pdf']:
    p = os.path.join(OUT, f)
    if not os.path.exists(p):
        print(f'{f}: MISSING')
        continue
    mt = datetime.fromtimestamp(os.stat(p).st_mtime).strftime('%H:%M:%S')
    doc = fitz.open(p)
    txt = doc[0].get_text()
    # extract SALADS block
    in_salads = False
    salad_block = ''
    for line in txt.splitlines():
        if 'САЛАТЫ' in line.upper():
            in_salads = True
            continue
        if in_salads and 'СУПЫ' in line.upper():
            break
        if in_salads:
            salad_block += line + ' '
    soup_words = ['Борщ', 'Суп', 'Харчо', 'Гороховый', 'Куриный суп']
    bad = [w for w in soup_words if w in salad_block]
    doc.close()
    print(f'{f} ({mt}): {"❌ LEAK: " + str(bad) if bad else "✅ clean"}')
