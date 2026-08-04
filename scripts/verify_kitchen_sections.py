#!/usr/bin/env python3
"""Dump SALADS and SOUPS sections of each kitchen sheet — verify no cross-contamination."""
import fitz
import os

OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'
for f in ['GOJ_T_S1_Tuesday_kitchen.pdf', 'GOJ_T_S2_Tuesday_kitchen.pdf',
          'GOJ_W_S1_Wednesday_kitchen.pdf', 'GOJ_W_S2_Wednesday_kitchen.pdf']:
    p = os.path.join(OUT, f)
    doc = fitz.open(p)
    t = doc[0].get_text()
    lines = [l for l in t.splitlines() if l.strip()]
    print(f'\n{"="*55}\n{f} — page 1\n{"="*55}')
    # print from SALADS to end of page-1 SOUPS
    try:
        s = lines.index('SALADS')
        e = s
        for i in range(s, len(lines)):
            if lines[i] == 'SOUPS' or lines[i].startswith('Page '):
                e = i
                break
        else:
            e = len(lines)
        print(' '.join(lines[s:min(e + 4, len(lines))]))
    except ValueError:
        print('  (no SALADS section on page 1)')
    doc.close()
