#!/usr/bin/env python3
"""Check vision worker progress."""
import os
from pathlib import Path

BASE = Path('/Users/mainsobhelper/.hermes/profiles/work/cache/delegation')
for deleg in ['deleg_5811a93d', 'deleg_e252661e']:
    print(f'=== {deleg} ===')
    d = BASE / 'live' / deleg
    for t in sorted(d.glob('task-*.log')):
        txt = t.read_text(errors='ignore')
        n = txt.count('vision_analyze ok')
        print(f'  {t.name}: {n} vision calls done')

print('\nmarks files:')
for f in sorted(Path('/tmp').glob('w31_marks_*.json')):
    print(f'  {f.name} ({f.stat().st_size} bytes)')
