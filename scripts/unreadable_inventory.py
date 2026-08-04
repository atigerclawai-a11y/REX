#!/usr/bin/env python3
"""Precise unreadable inventory: exist vs missing extraction, recovery process state."""
import json
import os
import subprocess
from pathlib import Path

BASE = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')
# check recovery process
r = subprocess.run(['pgrep', '-fl', 'focr'], capture_output=True, text=True)
print('focr processes:', r.stdout.strip() or 'NONE')

# all doc dirs with their extraction state
print(f"\n{'dir':<26}{'pages':>6}{'extr_json':>10}{'names':>7}{'unread':>8}")
tot = 0
for d in sorted(BASE.iterdir()):
    if not d.is_dir() or not d.name.startswith('doc'):
        continue
    pngs = list(d.glob('p*-*.png'))
    pages = set()
    for p in pngs:
        try:
            pages.add(int(p.name.split('-')[0][1:]))
        except Exception:
            pass
    np = len(pages)
    ej = d / 'extraction.json'
    has_ej = ej.exists()
    nnames = 0
    if has_ej:
        try:
            nnames = len(json.load(open(ej)))
        except Exception:
            nnames = -1
    nforms = (np + 1) // 2
    unread = max(nforms - nnames, 0) if np else (0 if not has_ej else nforms)
    if np or has_ej:
        tot += unread
        print(f"{d.name:<26}{np:>6}{str(has_ej):>10}{nnames:>7}{unread:>8}")
print(f"\nTOTAL unreadable: {tot}")
