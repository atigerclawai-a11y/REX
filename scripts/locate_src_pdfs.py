#!/usr/bin/env python3
"""Locate source PDFs for the unreadable docs + which blank_parse dirs have rendered pages."""
from pathlib import Path

REX = Path('/Users/mainsobhelper/Desktop/REX')
BASE = REX / 'blank_parse'
STABLE = REX / 'menu_intake_stable'
SCANS = Path('/Users/mainsobhelper/Documents/goj files/scans/ocr_processed')
OCR_DONE = Path('/tmp/ocr_done_all')

docs = ['doc00680820260727160512', 'doc00680920260727160541', 'doc00681120260727160643',
        'doc00681220260727160712', 'doc00687920260729073826', 'doc00688020260729073901',
        'doc00688120260729073944', 'doc00688920260729104631', 'doc00689120260729104710',
        'doc00692120260730070429', 'doc00701120260731112514', 'doc00701220260731112550',
        'doc00701320260731112625', 'doc00701420260731112656']

for doc in docs:
    # rendered pages?
    d = BASE / doc
    npng = len([f for f in d.glob('p*-*.png') if not f.name.startswith('pg')]) if d.exists() else 0
    # source pdf?
    src = None
    for base in (STABLE, SCANS, OCR_DONE, REX):
        hits = list(base.glob(f'*{doc}*.pdf'))
        if hits:
            src = hits[0]
            break
    print(f'{doc}: pages_rendered={npng} src_pdf={"YES " + str(src).split("/")[-1] if src else "NO"}')
