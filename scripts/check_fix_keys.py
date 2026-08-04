#!/usr/bin/env python3
"""Check what manifest rows the WRONG fix keys (110/167/200) actually map to,
and confirm the correct keys (141/198/231)."""
import json

MANIFEST = json.load(open('/tmp/unreadable_full_manifest.json'))
results = json.load(open('/tmp/unreadable_guesses.json'))

print('rows that WRONG keys map to:')
for bad in ['110', '167', '200']:
    for m in MANIFEST:
        if str(m['n']) == bad:
            print(f"  key {bad} → manifest n={m['n']} {m['doc']} p{m['page']}  (results[{bad}]={results.get(bad)!r})")

print('\ncorrect keys check:')
for good in ['141', '198', '231']:
    for m in MANIFEST:
        if str(m['n']) == good:
            print(f"  key {good} → {m['doc']} p{m['page']}  (results[{good}]={results.get(good)!r})")
