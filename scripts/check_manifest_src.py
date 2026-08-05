#!/usr/bin/env python3
"""Check lock file + page_guard.py for manifest reconstruction."""
import os

lock = '/Users/mainsobhelper/Desktop/REX/.page_guard_recover.lock'
if os.path.exists(lock):
    print(f'LOCK: {open(lock).read()[:300]}')
else:
    print('no lock')

pg = '/Users/mainsobhelper/Desktop/REX/scripts/page_guard.py'
if os.path.exists(pg):
    s = open(pg).read()
    print(f'\npage_guard.py: {len(s)} chars')
    # find manifest-related code
    import re
    for m in re.finditer(r'.*manifest.*', s, re.I):
        print(f'  {m.group(0).strip()[:120]}')
