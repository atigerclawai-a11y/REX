#!/usr/bin/env python3
"""Verify Thu kitchen sections clean + list all Wed/Thu files for email."""
import fitz
import os
from datetime import datetime

OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'
print('=== THU KITCHEN SECTIONS ===')
for f in ['GOJ_TH_S1_Thursday_kitchen.pdf', 'GOJ_TH_S2_Thursday_kitchen.pdf']:
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

print('\n=== FILES TO EMAIL ===')
for f in sorted(os.listdir(OUT)):
    if ('Aug05' in f and ('signin' in f or 'kitchen' in f or 'distribution' in f)) or \
       ('Thursday' in f and ('signin' in f or 'kitchen' in f or 'distribution' in f)):
        p = os.path.join(OUT, f)
        mt = datetime.fromtimestamp(os.stat(p).st_mtime).strftime('%m-%d %H:%M')
        print(f'  {f} ({mt})')
