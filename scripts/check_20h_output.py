#!/usr/bin/env python3
"""Check the 20:00 cron's run output for tonight (did it clobber actuals?)."""
import os
from datetime import datetime

cron_out = '/Users/mainsobhelper/.hermes/profiles/work/cron/output/d5a36bd909c4'
files = sorted(os.listdir(cron_out))
print(f'files: {files[-3:]}')
for f in files[-2:]:
    p = os.path.join(cron_out, f)
    print(f'\n=== {f} ({datetime.fromtimestamp(os.stat(p).st_mtime).strftime("%H:%M:%S")}) ===')
    txt = open(p, errors='ignore').read()
    # show the response section only
    if '## Response' in txt:
        resp = txt.split('## Response', 1)[1]
        print(resp[:1500])
    else:
        print(txt[:800])
