#!/usr/bin/env python3
"""Survey: what's in signin_intake/ + how many sign-in PDFs arrived recently.
Also check email_intake_processed for sign-in routing stats."""
import os
from datetime import datetime

SIGNIN = '/Users/mainsobhelper/Desktop/REX/signin_intake'
if os.path.isdir(SIGNIN):
    files = sorted(os.listdir(SIGNIN))
    print(f'signin_intake: {len(files)} files')
    recent = [f for f in files if f.endswith('.pdf')][-15:]
    for f in recent:
        p = os.path.join(SIGNIN, f)
        mt = datetime.fromtimestamp(os.stat(p).st_mtime).strftime('%m-%d %H:%M')
        print(f'  {f} ({mt})')
else:
    print('signin_intake MISSING')

# check the processed log for sign-in counts
proc = os.path.expanduser('~/.hermes/profiles/work/state/email_intake_processed.txt')
if os.path.exists(proc):
    lines = open(proc).read().splitlines()
    print(f'\nprocessed log: {len(lines)} lines')
    # last 8 entries
    for l in lines[-8:]:
        print(f'  {l[:110]}')
