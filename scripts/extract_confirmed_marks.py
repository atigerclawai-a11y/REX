#!/usr/bin/env python3
"""Extract marks for all confirmed forms via focr_reader.read_form_pages.
Incremental save per form. Resumable. Maps to week-31 dates (Aug 3-7)."""
import json
import sys
import subprocess
from pathlib import Path

sys.path.insert(0, '/Users/mainsobhelper/Desktop/REX/scripts')
from focr_reader import read_form_pages  # noqa

BASE = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')
ROWS = json.load(open('/tmp/matched_table_final.json'))
OUT = '/tmp/confirmed_marks.json'

WEEK31 = {'M': '2026-08-03', 'T': '2026-08-04', 'W': '2026-08-05',
          'TH': '2026-08-06', 'F': '2026-08-07'}

results = {}
if Path(OUT).exists():
    try:
        results = json.load(open(OUT))
        print(f'resuming: {len(results)} forms already extracted', flush=True)
    except Exception:
        results = {}

done = 0
for r in ROWS:
    n = r['n']
    if str(n) in results or n in results:
        done += 1
        continue
    ddir = BASE / r['doc']
    p1 = ddir / f"p{r['page']}-{r['page']:02d}.png"
    p2 = ddir / f"p{r['page']+1}-{r['page']+1:02d}.png"
    if not p1.exists() or not p2.exists():
        # try alternate naming pN-N.png
        p1 = ddir / f"p{r['page']}-{r['page']}.png"
        p2 = ddir / f"p{r['page']+1}-{r['page']+1}.png"
    if not p1.exists() or not p2.exists():
        print(f'#{n} MISSING pages: {p1} / {p2}', flush=True)
        results[n] = {'error': 'missing_pages'}
        json.dump(results, open(OUT, 'w'))
        done += 1
        continue
    try:
        res = read_form_pages(str(p1), str(p2))
        # cross-check name
        results[n] = {'doc': r['doc'], 'page': r['page'],
                      'expected': r['match'], 'read_name': res.get('name'),
                      'marks': res.get('marks', {})}
    except Exception as e:
        results[n] = {'doc': r['doc'], 'page': r['page'],
                      'expected': r['match'], 'error': str(e)}
    json.dump(results, open(OUT, 'w'))
    done += 1
    if done % 10 == 0:
        print(f'{done}/{len(ROWS)}', flush=True)

ok = sum(1 for v in results.values() if v.get('marks') and not v.get('error'))
print(f'DONE: {ok}/{len(ROWS)} with marks → {OUT}', flush=True)
