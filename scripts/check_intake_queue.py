#!/usr/bin/env python3
"""Check the intake queue — docs that may hold the 22 missing forms."""
import os
from pathlib import Path

# intake dirs
candidates = [
    Path('/Users/mainsobhelper/Documents/goj files/menu_intake_stable'),
    Path('/Users/mainsobhelper/Documents/goj files/menu_intake'),
    Path('/Users/mainsobhelper/Documents/goj files/ocr_intake'),
    Path('/Users/mainsobhelper/Desktop/REX/intake'),
]
for d in candidates:
    if d.exists():
        files = sorted(d.iterdir())
        pdfs = [f for f in files if f.suffix.lower() in ('.pdf', '.tif', '.tiff', '.png', '.jpg')]
        print(f'{d}: {len(files)} items, {len(pdfs)} pdfs/images')
        for f in pdfs[-8:]:
            print(f'  {f.name[:60]} {f.stat().st_mtime}')

# menu_intake_stable contents detail
mid = Path('/Users/mainsobhelper/Documents/goj files/menu_intake_stable')
if mid.exists():
    from datetime import datetime
    print(f'\nmenu_intake_stable recent:')
    for f in sorted(mid.iterdir(), key=lambda x: x.stat().st_mtime)[-12:]:
        mt = datetime.fromtimestamp(f.stat().st_mtime).strftime('%m-%d %H:%M')
        print(f'  {mt}  {f.name[:70]}')
