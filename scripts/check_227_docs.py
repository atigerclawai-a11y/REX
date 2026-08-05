#!/usr/bin/env python3
"""Cross-check: which of the 34 manifest docs were ALREADY vision-processed in
the 227 confirmed forms (batches 1-5)? Those are RECOVERED, not unread."""
import json
import os
import glob

# load the 227 confirmed forms from batch files
confirmed = set()
for b in ['/tmp/w31_batch_1.json', '/tmp/w31_batch_2.json', '/tmp/w31_batch_3.json',
          '/tmp/w31_batch_4.json', '/tmp/w31_batch_5.json']:
    if os.path.exists(b):
        data = json.load(open(b))
        if isinstance(data, list):
            for item in data:
                # each item has a doc identifier somewhere
                doc = item.get('doc') or item.get('doc_id') or item.get('source') or ''
                confirmed.add(str(doc))
        elif isinstance(data, dict):
            for k, v in data.items():
                doc = v.get('doc') if isinstance(v, dict) else ''
                confirmed.add(str(doc) or str(k))

print(f'confirmed set entries: {len(confirmed)}')
for c in sorted(confirmed)[:10]:
    print(f'  {c[:50]}')

# check the marks files too
for b in ['/tmp/w31_marks_1.json', '/tmp/w31_marks_2.json', '/tmp/w31_marks_3.json',
          '/tmp/w31_marks_4.json', '/tmp/w31_marks_5.json']:
    if os.path.exists(b):
        data = json.load(open(b))
        print(f'\n{b}: {type(data).__name__} len {len(data)}')
        items = list(data.items())[:2] if isinstance(data, dict) else data[:2]
        for it in items:
            print(f'  {str(it)[:100]}')
