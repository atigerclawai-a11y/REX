#!/usr/bin/env python3
"""Compare all 3 orders files + check which one the generator's BASE_DIR resolves to."""
import json
import os
from pathlib import Path

for p in ['/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json',
          '/Users/mainsobhelper/Documents/goj files/dashboard/data/GOJ_Menu_Orders.json',
          '/Users/mainsobhelper/Documents/goj files/dashboard/GOJ_Menu_Orders.json']:
    mt = os.path.getmtime(p) if os.path.exists(p) else 0
    n = 0
    if os.path.exists(p):
        try:
            n = len(json.load(open(p)))
        except Exception:
            pass
    print(f'{os.path.basename(os.path.dirname(p))}/{os.path.basename(p)}: mtime={mt:.0f} days={len([p])} dates={n}')

# what does the generator resolve?
BASE_DIR = Path('/Users/mainsobhelper/Documents/goj files/dashboard/generate_tomorrow.py').resolve().parent.parent
print(f'\ngenerator BASE_DIR: {BASE_DIR}')
print(f'DATA_DIR: {BASE_DIR / "data"}')
print(f'orders at DATA_DIR exists: {(BASE_DIR / "data" / "GOJ_Menu_Orders.json").exists()}')
