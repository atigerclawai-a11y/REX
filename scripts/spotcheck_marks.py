#!/usr/bin/env python3
"""Spot-check: extract marks for ONE confirmed form to verify focr reads checkmarks."""
import json
import sys
from pathlib import Path

sys.path.insert(0, '/Users/mainsobhelper/Desktop/REX/scripts')
from focr_reader import read_form_pages  # noqa

BASE = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')
ROWS = json.load(open('/tmp/matched_table_final.json'))
r = ROWS[0]  # first confirmed form
print(f'form: #{r["n"]} {r["match"]} {r["doc"]} p{r["page"]}')

ddir = BASE / r['doc']
p1 = ddir / f"p{r['page']}-{r['page']:02d}.png"
p2 = ddir / f"p{r['page']+1}-{r['page']+1:02d}.png"
print(f'p1: {p1} exists={p1.exists()}')
print(f'p2: {p2} exists={p2.exists()}')

res = read_form_pages(str(p1), str(p2))
print(f'read_name: {res.get("name")!r}')
marks = res.get('marks', {})
print(f'marks: {json.dumps(marks, ensure_ascii=False)[:800]}')
