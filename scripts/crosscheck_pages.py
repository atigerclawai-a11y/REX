#!/usr/bin/env python3
"""Cross-check: are the 'unreadable' pages really missing, or extracted under other pages?"""
import json
from pathlib import Path

BASE = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')

for doc in ['doc00680820260727160512', 'doc00680920260727160541', 'doc00681120260727160643']:
    d = BASE / doc
    ej = d / 'extraction.json'
    data = json.load(open(ej))
    print(f'=== {doc}: {len(data)} extracted names ===')
    # list all extracted with their pages
    for n, info in data.items():
        pages = info.get('pages', []) if isinstance(info, dict) else []
        print(f'  {n}: pages={pages}')
