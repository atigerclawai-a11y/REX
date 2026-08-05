#!/usr/bin/env python3
"""Trace: who removed 10 clients from W1? Check cron outputs around 20:15-21:45."""
import os
from datetime import datetime

cron_out = '/Users/mainsobhelper/.hermes/profiles/work/cron/output'
# candidates that touch actuals: 6am refresh, noon, 17:10 docs, 20:00 package, 05:15 sync
for cid, name in [('839aed29d920', '6am-refresh'), ('7a623c74b4f1', 'noon-refresh'),
                  ('2fd58acac200', '17:10-daily-docs'), ('d5a36bd909c4', '20:00-package'),
                  ('678426d4d2c8', '05:15-auth-sync')]:
    d = os.path.join(cron_out, cid)
    if not os.path.isdir(d):
        continue
    files = sorted(os.listdir(d))
    today = [f for f in files if f.startswith('2026-08-04')]
    print(f'{name}: {len(today)} runs today')
    for f in today[-3:]:
        p = os.path.join(d, f)
        mt = datetime.fromtimestamp(os.stat(p).st_mtime).strftime('%H:%M')
        print(f'  {f[:16]} ({mt})')
