#!/usr/bin/env python3
"""Verify Thu + Fri kitchen sections pure."""
import fitz
import os

OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'
for f in ['GOJ_TH_S1_Thursday_kitchen.pdf', 'GOJ_TH_S2_Thursday_kitchen.pdf',
          'GOJ_F_S1_Friday_kitchen.pdf', 'GOJ_F_S2_Friday_kitchen.pdf']:
    p = os.path.join(OUT, f)
    if not os.path.exists(p):
        print(f'{f}: MISSING')
        continue
    doc = fitz.open(p)
    txt = doc[0].get_text()
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
    bad = [w for w in ['Борщ', 'Суп', 'Харчо', 'Гороховый', 'Куриный суп'] if w in salad_block]
    doc.close()
    print(f'  {f}: {"❌ " + str(bad) if bad else "✅ clean"}')
