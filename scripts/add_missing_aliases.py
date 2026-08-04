#!/usr/bin/env python3
"""Add missing aliases to dish_aliases.json (Котл. кур, Квашеня капуста)."""
import json
from pathlib import Path

p = Path('/Users/mainsobhelper/Desktop/REX/scripts/dish_aliases.json')
a = json.load(open(p))
a.setdefault('main', {})['Котл. кур'] = 'Котлеты куриные'
a.setdefault('salad', {})['Квашеня капуста'] = 'Квашеная капуста'
a['salad']['Квашеняя капуста'] = 'Квашеная капуста'
json.dump(a, open(p, 'w'), ensure_ascii=False, indent=1)
print('aliases updated:', a['main']['Котл. кур'], '/', a['salad']['Квашеня капуста'])
