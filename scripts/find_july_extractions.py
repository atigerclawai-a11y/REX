#!/usr/bin/env python3
"""Find unreadable-name forms in July 27-31 batches (doc006808+ era)."""
import json
import os
import re
from pathlib import Path

# where do extraction JSONs live?
candidates = [
    Path('/Users/mainsobhelper/Desktop/REX/blank_parse'),
    Path('/Users/mainsobhelper/Documents/goj files/blank_parse'),
    Path('/Users/mainsobhelper/Desktop/REX/extractions'),
    Path('/Users/mainsobhelper/Documents/goj files/extractions'),
]
for c in candidates:
    print(f'{c}: exists={c.exists()}')

# search for extraction jsons referencing the July 27 batches
for c in candidates:
    if not c.exists():
        continue
    hits = sorted(c.glob('*006808*')) + sorted(c.glob('*006809*')) + sorted(c.glob('*006811*')) + sorted(c.glob('*006812*')) + sorted(c.glob('*006879*')) + sorted(c.glob('*006881*')) + sorted(c.glob('*006921*')) + sorted(c.glob('*007011*')) + sorted(c.glob('*007013*'))
    if hits:
        print(f'\n=== {c} ===')
        for h in hits:
            print(f'  {h.name} ({h.stat().st_size})')
