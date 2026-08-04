#!/usr/bin/env python3
"""Check rendered PNGs exist for unreadable pages + find OCR markdown for name guesses."""
from pathlib import Path

REX = Path('/Users/mainsobhelper/Desktop/REX')
BASE = REX / 'blank_parse'

# the 30 unreadable forms in processed docs
targets = {
    'doc00680820260727160512': [7, 15, 17, 19, 23, 25, 35, 41, 43],
    'doc00680920260727160541': [1, 3, 9, 11, 13, 17, 21, 23, 25, 27, 33],
    'doc00681120260727160643': [1, 3, 5, 7, 9, 13, 15, 19, 21, 27],
}

for doc, pages in targets.items():
    d = BASE / doc
    missing = []
    for p in pages:
        f = d / f'p{p:02d}-{p:02d}.png'
        if not f.exists():
            # try p{p}-{p:02d} naming
            alt = list(d.glob(f'p{p}-*.png'))
            if not alt:
                missing.append(p)
    print(f'{doc}: pages {pages}, missing png: {missing if missing else "none"}')

# OCR markdown for name guesses
print('\nmenu_ocr_full dirs:')
ocr_full = REX / 'menu_ocr_full'
if ocr_full.exists():
    for doc in targets:
        hits = list(ocr_full.glob(f'{doc}/ocr/*.md')) + list(ocr_full.glob(f'*{doc}*/ocr/*.md'))
        print(f'  {doc}: {"FOUND " + str(hits[0]) if hits else "no md"}')
