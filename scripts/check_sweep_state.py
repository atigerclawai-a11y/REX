#!/usr/bin/env python3
"""Check sweep state classification for the 14 docs (menu vs signin vs quarantined)."""
import json
from pathlib import Path

REX = Path('/Users/mainsobhelper/Desktop/REX')
# sweep state file
for cand in [REX / 'sweep_state.json', REX / 'menu_sweep_state.json',
             REX / '.sweep_state.json', REX / 'state' / 'sweep_state.json']:
    if cand.exists():
        data = json.load(open(cand))
        print(f'state file: {cand}')
        # find the doc entries
        docs = data.get('docs', data) if isinstance(data, dict) else data
        if isinstance(docs, dict):
            for k, v in docs.items():
                if '006808' in k or '006809' in k or '006810' in k or '006811' in k or '006812' in k or \
                   '006878' in k or '006879' in k or '006880' in k or '006881' in k or '006921' in k or \
                   '007011' in k or '007012' in k or '007013' in k or '007014' in k:
                    print(f'  {k}: {v}')
        break
else:
    print('no sweep state found, trying dirs')
