#!/usr/bin/env python3
"""Verify marks coverage: all 5 batches × all forms have marks files."""
import json

# batch files
batches = {'/tmp/w31_forms.json': 'B1(157)', '/tmp/w31_batch_4.json': 'B4(40)', '/tmp/w31_batch_5.json': 'B5(30)'}
marks_files = ['/tmp/w31_marks_1.json', '/tmp/w31_marks_2.json', '/tmp/w31_marks_3.json',
               '/tmp/w31_marks_4.json', '/tmp/w31_marks_5.json']

all_marks = {}
for f in marks_files:
    try:
        d = json.load(open(f))
        all_marks.update(d)
        print(f'{f}: {len(d)} forms')
    except Exception as e:
        print(f'{f}: ERROR {e}')

total_forms = 0
for bf, label in batches.items():
    batch = json.load(open(bf))
    total_forms += len(batch)
    missing = [x['name'] for x in batch if str(x['n']) not in all_marks]
    print(f'{label}: {len(batch)} forms, missing marks: {len(missing)} {missing[:5]}')

print(f'\nTOTAL forms: {total_forms}, marks entries: {len(all_marks)}')
# how many marks are empty {} (no marks at all)?
empty = [k for k, v in all_marks.items() if not v]
print(f'empty marks (no picks): {len(empty)} {empty}')
