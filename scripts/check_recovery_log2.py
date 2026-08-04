#!/usr/bin/env python3
"""Check page_guard.log for recovery progress + find any focr/recovery output dirs."""
import os
from pathlib import Path

REX = Path('/Users/mainsobhelper/Desktop/REX')
lg = REX / 'page_guard.log'
lines = lg.read_text().splitlines() if lg.exists() else []
print(f'page_guard.log: {len(lines)} lines')

# look for recovery progress markers
for l in lines[-60:]:
    if 'recover' in l.lower() or 'extract' in l.lower() or 'focr' in l.lower() or 'read' in l.lower() or '✓' in l or 'done' in l.lower():
        print(f'  {l}')

# recovery output dirs
print('\nrecovery-related dirs:')
for d in sorted(REX.iterdir()):
    if d.is_dir() and any(k in d.name.lower() for k in ['recover', 'focr', 'quarant']):
        n = len(list(d.iterdir()))
        print(f'  {d.name}/ ({n} items)')
