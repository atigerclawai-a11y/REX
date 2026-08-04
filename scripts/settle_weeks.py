#!/usr/bin/env python3
"""Settle week attribution: check form footer weeks + doc md footers + how the
existing promoter mapped these docs."""
import json
import re
import sqlite3
from pathlib import Path

REX = Path('/Users/mainsobhelper/Desktop/REX')

# 1. Check mineru md footers for the July 27-31 docs
print('=== MinerU md week footers ===')
for d in ['doc00680820260727160512', 'doc00680920260727160541', 'doc00681020260727160603',
          'doc00681120260727160643', 'doc00681220260727160712', 'doc00687820260729073749',
          'doc00687920260729073826', 'doc00688020260729073901', 'doc00688120260729073944',
          'doc00701120260731112514', 'doc00701220260731112550', 'doc00701320260731112625',
          'doc00701420260731112656']:
    md = REX / 'menu_ocr_full' / d / 'ocr' / f'{d}.md'
    foot = '?'
    if md.exists():
        txt = md.read_text(errors='ignore')
        m = re.findall(r'Week\s*#?:?\s*(\d+)', txt)
        if m:
            foot = ','.join(m[:3])
    else:
        # try auto dir
        md2 = REX / 'menu_ocr_full' / d / f'{d}' / 'auto' / f'{d}.md'
        if md2.exists():
            txt = md2.read_text(errors='ignore')
            m = re.findall(r'Week\s*#?:?\s*(\d+)', txt)
            foot = ','.join(m[:3]) if m else 'no-match'
    print(f'  {d[:20]}: {foot}')

# 2. How does the promoter map weeks? check week_for()
prom = REX / 'scripts' / 'promote_focr_recovery.py'
if prom.exists():
    txt = prom.read_text()
    m = re.search(r'def week_for.*?(?=\ndef |\Z)', txt, re.S)
    if m:
        print('\n=== week_for() logic ===')
        print(m.group(0)[:800])
    m2 = re.search(r'WEEK_DATES\s*=\s*\{[^}]+\}', txt)
    if m2:
        print('\nWEEK_DATES:', m2.group(0))
