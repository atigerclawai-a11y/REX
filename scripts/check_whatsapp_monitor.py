#!/usr/bin/env python3
"""Check WhatsApp monitor output for changed-day updates."""
import os
from datetime import datetime

cron_out = '/Users/mainsobhelper/.hermes/profiles/work/cron/output'
# whatsapp detector + change log crons
for cid, name in [('bdf54191c11e', 'whatsapp-detector'), ('ca534f4adbb5', 'goj-change-log'),
                  ('3ed5914afa6d', 'whatsapp-daily-summary'), ('ff362f84e43e', 'wuzapi-watchdog')]:
    d = os.path.join(cron_out, cid)
    if not os.path.isdir(d):
        print(f'{name}: no dir')
        continue
    files = sorted(os.listdir(d))
    today = [f for f in files if f.startswith('2026-08-04')]
    print(f'\n=== {name} ({cid[:8]}) — {len(today)} runs today ===')
    if today:
        latest = os.path.join(d, today[-1])
        txt = open(latest, errors='ignore').read()
        # print the response part
        if '## Response' in txt:
            resp = txt.split('## Response', 1)[1]
            print(resp[:1200])
        else:
            print(txt[:800])
