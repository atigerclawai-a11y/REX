#!/usr/bin/env python3
"""Dump the kitchen sheet text to see salads/soups ordering."""
import fitz
import os

OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'
for f in ['GOJ_T_S1_Tuesday_kitchen.pdf', 'GOJ_T_S2_Tuesday_kitchen.pdf']:
    p = os.path.join(OUT, f)
    doc = fitz.open(p)
    print(f'\n{"="*60}\n{f} — page 1\n{"="*60}')
    t = doc[0].get_text()
    print(t[:1800])
    doc.close()
