#!/usr/bin/env python3
"""Check why doc006889/006891 .md have no date — are they empty/failed OCR?"""
import os

for doc in ['doc00688920260729104631', 'doc00689120260729104710']:
    base = f'/Users/mainsobhelper/Desktop/REX/signin_ocr_full/{doc}'
    md = f'{base}/ocr/{doc}.md'
    sz = os.path.getsize(md) if os.path.exists(md) else 0
    print(f'{doc}: md size {sz}')
    if sz > 0:
        txt = open(md, errors='ignore').read()
        print(f'  head: {txt[:150]!r}')
    # check auto dir for the actual md
    auto = f'{base}/{doc}/auto/{doc}.md'
    if os.path.exists(auto):
        asz = os.path.getsize(auto)
        print(f'  auto md size: {asz}')
        if asz > 0:
            print(f'  auto head: {open(auto, errors="ignore").read()[:150]!r}')
