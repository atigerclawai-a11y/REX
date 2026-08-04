#!/usr/bin/env python3
"""Full dump of garbled_names_review.pdf + quarantine doc list."""
import fitz
import os
from pathlib import Path

pdf = fitz.open('/Users/mainsobhelper/Desktop/REX/garbled_review/GOJ_garbled_names_review.pdf')
print(f'GOJ_garbled_names_review.pdf: {pdf.page_count} pages')
for i in range(pdf.page_count):
    t = pdf[i].get_text().replace('\n', ' | ')[:180]
    print(f'  p{i+1}: {t}')
pdf.close()

print('\n=== menu_ocr_quarantine/ ===')
q = Path('/Users/mainsobhelper/Desktop/REX/menu_ocr_quarantine')
for f in sorted(q.iterdir()):
    print(f'  {f.name} ({f.stat().st_size} bytes)')

print('\n=== garbled_review/ ===')
g = Path('/Users/mainsobhelper/Desktop/REX/garbled_review')
for f in sorted(g.iterdir()):
    print(f'  {f.name} ({f.stat().st_size} bytes)')
