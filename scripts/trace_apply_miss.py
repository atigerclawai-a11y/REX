#!/usr/bin/env python3
"""Trace: does marks_5 have Shefer Bella (#1)? What did the apply script do?"""
import json

batch5 = json.load(open('/tmp/w31_batch_5.json'))
print('batch5 first 3:')
for b in batch5[:3]:
    print(f'  n={b["n"]} name={b["name"]} doc={b["doc"]} page={b["page"]}')

marks5 = json.load(open('/tmp/w31_marks_5.json'))
print(f'\nmarks_5 keys: {sorted(marks5.keys())[:10]}')
for k in ['1', '2', '3']:
    print(f'  #{k}: {json.dumps(marks5.get(k, {}), ensure_ascii=False)[:200]}')

# what did apply use as the name for n=1?
form_meta = {}
for f in ['/tmp/w31_forms.json', '/tmp/w31_batch_4.json', '/tmp/w31_batch_5.json']:
    try:
        for x in json.load(open(f)):
            form_meta[str(x['n'])] = x
    except Exception:
        pass
meta = form_meta.get('1', {})
print(f'\nform_meta[1]: {meta}')
print(f'  name field: {meta.get("name")!r}')
print(f'  match field: {meta.get("match")!r}')
