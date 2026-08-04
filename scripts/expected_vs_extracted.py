#!/usr/bin/env python3
"""Compare expected forms (pages/2) vs extracted forms per doc — find unreadable/missing."""
import json
import os
from pathlib import Path

BASE = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')

print(f"{'doc':<22} {'pp':>3} {'exp':>4} {'ext':>4}  notes")
for d in sorted(BASE.iterdir()):
    if not d.is_dir():
        continue
    ej = d / 'extraction.json'
    if not ej.exists():
        print(f'{d.name:<22} {"?":>3} {"?":>4} {"0":>4}  NO extraction.json')
        continue
    try:
        data = json.load(open(ej))
    except Exception:
        print(f'{d.name:<22} {"?":>3} {"?":>4} {"?":>4}  UNREADABLE json')
        continue
    # count forms
    forms = []
    if isinstance(data, dict) and 'days' in data:
        for day, fl in data['days'].items():
            if isinstance(fl, list):
                for f in fl:
                    f['_day'] = day
                    forms.append(f)
    elif isinstance(data, list):
        forms = data
    elif isinstance(data, dict):
        for k in ('forms', 'extractions'):
            if isinstance(data.get(k), list):
                forms = data[k]
    # page count from png files
    pngs = [f for f in d.glob('p*-*.png') if not f.name.startswith('pg')]
    pp = len(pngs)
    exp = pp // 2
    names = [str(f.get('name', '')).strip() for f in forms if isinstance(f, dict)]
    empty = [n for n in names if not n or len(n) < 3]
    print(f'{d.name:<22} {pp:>3} {exp:>4} {len(forms):>4}  empty_names={len(empty)}')
    for n in empty[:5]:
        print(f'    EMPTY NAME: {n}')
