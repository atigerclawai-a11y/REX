#!/usr/bin/env python3
"""Verify extraction.json selections for doc006808/809/811 are complete plates
(all 4 cells) — these get written as this week's real orders."""
import json
from pathlib import Path

BASE = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')
CAT = {'САЛАТЫ': 'salad', 'СУПЫ': 'soup', 'ГЛАВНОЕ': 'main', 'ГАРНИР': 'side'}

complete = 0
partial = 0
for d in ['doc00680820260727160512', 'doc00680920260727160541', 'doc00681120260727160643']:
    ej = BASE / d / 'extraction.json'
    if not ej.exists():
        continue
    data = json.load(open(ej))
    for name, entry in data.items():
        if not isinstance(entry, dict) or 'selections' not in entry:
            continue
        for day, cats in entry['selections'].items():
            cells = {}
            for cat, dishes in cats.items():
                dish = dishes[0] if dishes else None
                if isinstance(dish, (list, tuple)):
                    dish = dish[0]
                c = CAT.get(cat)
                if c and dish:
                    cells[c] = dish
            status = 'COMPLETE' if all(k in cells for k in ('salad', 'soup', 'main', 'side')) else 'partial'
            if status == 'COMPLETE':
                complete += 1
            else:
                partial += 1
                print(f'  PARTIAL {name} {day}: {cells}')
print(f'\nselection days: complete={complete}, partial={partial}')
