#!/usr/bin/env python3
"""Reconcile: why did quantify find 0 suspect clients when sanity showed Sorits Lev
has Aug 3-7 ocr_scan rows? Check what extraction files exist and their names."""
import json
from pathlib import Path

BASE = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')
for d in ['doc00680820260727160512', 'doc00680920260727160541', 'doc00681020260727160603',
          'doc00681120260727160643', 'doc00681220260727160712']:
    ddir = BASE / d
    if not ddir.exists():
        print(f'{d}: NO DIR')
        continue
    files = list(ddir.glob('extraction*.json'))
    print(f'{d}: {[f.name for f in files]}')
    for f in files:
        try:
            data = json.load(open(f))
            names = list(data.keys()) if isinstance(data, dict) else 'LIST'
            print(f'   {f.name}: {len(names) if isinstance(names, list) else names} entries')
            if isinstance(names, list):
                print(f'     first 5: {names[:5]}')
        except Exception as e:
            print(f'   {f.name}: ERROR {e}')
