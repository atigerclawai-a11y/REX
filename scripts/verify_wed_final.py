#!/usr/bin/env python3
"""Verify Wed files + kitchen sections pure."""
import fitz
import os
from datetime import datetime

OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'
print('=== WED FILES ON DISK ===')
for f in sorted(os.listdir(OUT)):
    if 'Wednesday' in f and any(k in f for k in ['signin', 'kitchen', 'distribution', 'drivers']):
        p = os.path.join(OUT, f)
        mt = datetime.fromtimestamp(os.stat(p).st_mtime).strftime('%m-%d %H:%M:%S')
        sz = os.path.getsize(p) // 1024
        print(f'  {f} ({sz} KB, {mt})')

print('\n=== KITCHEN SECTIONS ===')
for f in ['GOJ_W_S1_Wednesday_kitchen.pdf', 'GOJ_W_S2_Wednesday_kitchen.pdf']:
    p = os.path.join(OUT, f)
    if not os.path.exists(p):
        print(f'  {f}: MISSING')
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
