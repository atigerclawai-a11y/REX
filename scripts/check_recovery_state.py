#!/usr/bin/env python3
"""Full recovery manifest + page_guard log tail + which docs are still pending."""
import json
import os
from pathlib import Path

REX = Path('/Users/mainsobhelper/Desktop/REX')

m = REX / '.page_guard_recover.json'
if m.exists():
    d = json.load(open(m))
    docs = d.get('docs', d) if isinstance(d, dict) else d
    print(f'recovery manifest: {len(docs)} docs')
    for x in docs:
        print(f'  {x}')

# lock file — still running?
lock = REX / '.page_guard_recover.lock'
if lock.exists():
    print(f'\nlock exists: {lock.read_text().strip()[:80]} (PID)')

# page_guard log tail
lg = REX / 'page_guard.log'
if lg.exists():
    lines = lg.read_text().splitlines()
    print(f'\npage_guard.log tail ({len(lines)} lines):')
    for l in lines[-12:]:
        print(f'  {l}')

# focr recovery log
for name in ['focr_recover.log', 'recovery.log', 'sweep.log']:
    p = REX / name
    if p.exists():
        lines = p.read_text().splitlines()
        print(f'\n{name} tail:')
        for l in lines[-8:]:
            print(f'  {l}')
