#!/usr/bin/env python3
"""Extract marks_5 JSON from the subagent summary transcript and write it."""
import json
import re
from pathlib import Path

SUMMARY = '/Users/mainsobhelper/.hermes/profiles/work/cache/delegation/subagent-summary-1-20260804_052410_707391.txt'
OUT = '/tmp/w31_marks_5.json'

txt = Path(SUMMARY).read_text(errors='ignore')
# find the JSON block between ```json and ```
m = re.search(r'```json\n(.*?)\n```', txt, re.S)
if not m:
    print('no json block found')
    raise SystemExit(1)
data = json.loads(m.group(1))
print(f'parsed {len(data)} forms from transcript')
# validate structure
for k, v in data.items():
    if not isinstance(v, dict):
        print(f'  form {k}: NOT a dict: {v!r}')
# check keys match batch 5 names
batch = json.load(open('/tmp/w31_batch_5.json'))
for b in batch:
    n = str(b['n'])
    if n not in data:
        print(f'  MISSING form {n} ({b["name"]})')
json.dump(data, open(OUT, 'w'), indent=1, ensure_ascii=False)
print(f'written {OUT}: {len(data)} forms')
