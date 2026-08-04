#!/usr/bin/env python3
"""Find where '46' appears in kitchen sheets + check salad totals vs client counts."""
import fitz
import os
import re

OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'
files = ['GOJ_T_S1_Tuesday_kitchen.pdf', 'GOJ_T_S2_Tuesday_kitchen.pdf',
         'GOJ_W_S1_Wednesday_kitchen.pdf', 'GOJ_W_S2_Wednesday_kitchen.pdf']

for f in files:
    path = os.path.join(OUT, f)
    doc = fitz.open(path)
    lines = []
    for pg in doc:
        for l in pg.get_text().splitlines():
            l = l.strip()
            if l:
                lines.append(l)
    doc.close()
    print(f'\n{"="*60}\n{f}\n{"="*60}')
    for i, l in enumerate(lines):
        if l == '46':
            print(f'  line {i+1}: "46" — context:')
            for j in range(max(0, i-3), min(len(lines), i+4)):
                print(f'    [{j+1}] {lines[j]}')
    # salad section total = line before 'SOUPS' marker... find all SECTION TOTAL
    print('  SECTION TOTALS:')
    for i, l in enumerate(lines):
        if l == 'SECTION TOTAL':
            print(f'    line {i+1}: total = {lines[i+1] if i+1 < len(lines) else "?"}')
