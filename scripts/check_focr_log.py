#!/usr/bin/env python3
"""Check recovery log — which docs finished, which failed, what's pending."""
import os
from pathlib import Path

REX = Path('/Users/mainsobhelper/Desktop/REX')
# find recovery log files
for p in REX.glob('*recover*.log'):
    print(f'LOG: {p.name} ({p.stat().st_size})')
for p in REX.glob('*.log'):
    if 'focr' in p.name.lower() or 'recover' in p.name.lower() or 'promot' in p.name.lower():
        print(f'LOG: {p.name} ({p.stat().st_size})')

# tail the most likely one
for name in ['focr_recover.log', 'promote_recovery.log', 'recovery.log']:
    p = REX / name
    if p.exists():
        lines = p.read_text().splitlines()
        print(f'\n=== {name} (last 25 of {len(lines)}) ===')
        for l in lines[-25:]:
            print(f'  {l}')
