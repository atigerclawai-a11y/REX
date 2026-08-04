#!/usr/bin/env python3
"""Background: focr best-guess for all 232 unreadable crops → guesses JSON."""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, '/Users/mainsobhelper/Desktop/REX/scripts')
from focr_reader import read_form_pages  # noqa

MANIFEST = json.load(open('/tmp/unreadable_full_manifest.json'))
GUESSES = '/tmp/unreadable_guesses.json'
FOCR = '/Users/mainsobhelper/.local/bin/focr'

results = {}
if Path(GUESSES).exists():
    try:
        results = json.load(open(GUESSES))
        print(f'resuming: {len(results)} already saved', flush=True)
    except Exception:
        results = {}
done = 0
for m in MANIFEST:
    n = m['n']
    if n in results:
        done += 1
        continue  # already read
    crop = m['crop']
    # focr on the name crop alone — read just the name
    try:
        proc = subprocess.run([FOCR, 'ocr', '--json', crop],
                              capture_output=True, text=True, timeout=300)
        if proc.returncode == 0:
            data = json.loads(proc.stdout)
            html = data.get('markdown', '')
            import re
            mm = re.search(r'Имя:\s*([^<]+?)\s*<', html)
            name = mm.group(1).strip() if mm else None
            results[m['n']] = name
        else:
            results[m['n']] = None
    except Exception as e:
        results[m['n']] = None
    done += 1
    # incremental save — a kill must not lose progress
    json.dump(results, open(GUESSES, 'w'), indent=1)
    if done % 20 == 0:
        print(f'{done}/{len(MANIFEST)}', flush=True)

json.dump(results, open(GUESSES, 'w'), indent=1)
print(f'DONE: {sum(1 for v in results.values() if v)}/{len(results)} names read → {GUESSES}')
