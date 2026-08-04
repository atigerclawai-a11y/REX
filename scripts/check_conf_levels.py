#!/usr/bin/env python3
"""Find unreadable/low-confidence forms in July 27-31 batches."""
import json
from pathlib import Path

BASE = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')
TARGETS = ['doc006808', 'doc006809', 'doc006811', 'doc006812', 'doc006879',
           'doc006880', 'doc006881', 'doc006889', 'doc006891', 'doc006921',
           'doc007011', 'doc007012', 'doc007013', 'doc007014']

for t in TARGETS:
    d = next((x for x in BASE.iterdir() if x.is_dir() and x.name.startswith(t)), None)
    if d is None:
        continue
    ej = d / 'extraction.json'
    if not ej.exists():
        print(f'{t}: NO extraction.json')
        continue
    data = json.load(open(ej))
    names = list(data.keys()) if isinstance(data, dict) else []
    # name_conf distribution
    low = []
    for n in names:
        info = data[n]
        conf = info.get('name_conf', 1.0) if isinstance(info, dict) else 1.0
        if conf < 1.0:
            low.append((n, conf))
    # page coverage: which form-page indexes have no extraction?
    pages = set()
    for n in names:
        info = data[n]
        if isinstance(info, dict):
            for p in info.get('pages', []):
                pages.add(int(p))
    n_png = len([f for f in d.glob('p*-*.png') if not f.name.startswith('pg')])
    exp_forms = n_png // 2
    covered_forms = len({(p - 1) // 2 for p in pages})
    print(f'{t}: {len(names)} named forms, {n_png}pp → {exp_forms} expected, {covered_forms} covered, low-conf={len(low)}')
    for n, c in low[:8]:
        print(f'    LOW CONF {c:.2f}: {n}')
