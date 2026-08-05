#!/usr/bin/env python3
"""Check both JSON files' per-day entry counts."""
import json
import os

for p in ['/Users/mainsobhelper/goj_corpus/goj files/data/GOJ_Menu_Orders.json',
          '/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json']:
    if os.path.exists(p):
        data = json.load(open(p))
        print(f'\n{os.path.basename(os.path.dirname(os.path.dirname(p)))}/{os.path.basename(os.path.dirname(p))}:')
        for d in ['2026-08-04', '2026-08-05', '2026-08-06', '2026-08-07']:
            n = len(data.get(d, {}))
            print(f'  {d}: {n} entries')
