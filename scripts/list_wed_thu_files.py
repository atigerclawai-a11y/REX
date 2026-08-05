#!/usr/bin/env python3
"""List all generated files for Wed forms + Thu package."""
import os
from datetime import datetime

OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'
print('=== WED FORMS (blank menus) ===')
for f in ['Menus_Wed_Aug05_S1_LIVE.pdf', 'Menus_Wed_Aug05_S2_LIVE.pdf']:
    p = os.path.join(OUT, f)
    sz = os.path.getsize(p) if os.path.exists(p) else 0
    print(f'  {f}: {sz//1024} KB')

print('\n=== THU PACKAGE ===')
for f in sorted(os.listdir(OUT)):
    if 'Thu' in f or 'TH_' in f or 'Aug06' in f:
        p = os.path.join(OUT, f)
        mt = datetime.fromtimestamp(os.stat(p).st_mtime).strftime('%m-%d %H:%M')
        sz = os.path.getsize(p) // 1024
        print(f'  {f} ({sz} KB, {mt})')
