#!/usr/bin/env python3
"""Check sheet timestamps + what the 20:00 cron's skill says about actuals."""
import os
from datetime import datetime

OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'
print('=== sheet timestamps ===')
for f in ['GOJ_T_S1_Tuesday_signin.pdf', 'GOJ_T_S2_Tuesday_signin.pdf',
          'GOJ_W_S1_Wednesday_signin.pdf', 'GOJ_W_S2_Wednesday_signin.pdf',
          'GOJ_M_S1_Monday_signin.pdf', 'GOJ_M_S2_Monday_signin.pdf']:
    p = os.path.join(OUT, f)
    mt = datetime.fromtimestamp(os.stat(p).st_mtime).strftime('%H:%M:%S') if os.path.exists(p) else 'MISSING'
    print(f'  {f}: {mt}')

# check the daily-handoff skill for the rogue SQL
SKILL = '/Users/mainsobhelper/.hermes/profiles/work/skills/goj/goj-daily-handoff/SKILL.md'
if os.path.exists(SKILL):
    txt = open(SKILL, errors='ignore').read()
    import re
    for m in re.finditer(r'UPDATE clients SET day_\w+_actual[^\n]*', txt):
        print(f'\nskill SQL: {m.group(0)}')
    # also check for carecenta roster sync references
    for line in txt.splitlines():
        if 'day_W_actual' in line or '64' in line and '96' in line:
            print(f'  line: {line[:120]}')
