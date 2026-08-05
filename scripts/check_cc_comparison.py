#!/usr/bin/env python3
"""COMPARE: live Carecenta attendance vs auth_tracker day_*_actual for this week.
Carecenta truth: Clients.aspx weekly table (LiveScrape), auth = what sheets use."""
import json
import os
import pickle
import sqlite3

# check for a recent carecenta scrape
for f in ['/tmp/carecenta_weekly.json', '/tmp/live_roster.json',
          '/tmp/tue_definitive.json', '/tmp/wed_definitive.json']:
    if os.path.exists(f):
        st = os.stat(f).st_mtime
        from datetime import datetime
        print(f'{f}: {datetime.fromtimestamp(st).strftime("%m-%d %H:%M")}')

# what we have on disk
if os.path.exists('/tmp/tue_definitive.json'):
    tue = json.load(open('/tmp/tue_definitive.json'))
    print(f'\ntue_definitive: {json.dumps(tue, ensure_ascii=False)[:300]}')
