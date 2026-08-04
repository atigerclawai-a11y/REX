#!/usr/bin/env python3
"""Definitive scope: split confirmed forms by doc week (30 vs 31), and check for
any surya extraction files on the July 29-31 docs."""
import json
import sqlite3
from pathlib import Path

ROWS = json.load(open('/tmp/matched_table_final.json'))
BASE = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')

W30_DOCS = {'doc00680820260727160512', 'doc00680920260727160541', 'doc00681020260727160603',
            'doc00681120260727160643', 'doc00681220260727160712'}
W31_DOCS = {'doc00687820260729073749', 'doc00687920260729073826', 'doc00688020260729073901',
            'doc00688120260729073944', 'doc00701120260731112514', 'doc00701220260731112550',
            'doc00701320260731112625', 'doc00701420260731112656'}

w30 = [r for r in ROWS if r['doc'] in W30_DOCS]
w31 = [r for r in ROWS if r['doc'] in W31_DOCS]
print(f'week-30 forms (Jul 27 docs → picks for Jul 27-31, PAST): {len(w30)}')
print(f'week-31 forms (Jul 29-31 docs → picks for Aug 3-7, THIS WEEK): {len(w31)}')

# check for surya/tesseract extraction files on w31 docs
print('\n=== extraction files on week-31 docs ===')
for d in sorted(W31_DOCS):
    ddir = BASE / d
    if ddir.exists():
        files = [f.name for f in ddir.iterdir() if 'extraction' in f.name]
        print(f'  {d}: {files if files else "NONE"}')

# how many of the w31 clients are Tue/Wed scheduled?
AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
con = sqlite3.connect(AUTH)
tue = wed = 0
for r in w31:
    row = con.execute("SELECT day_T_actual, day_W_actual FROM clients WHERE name=?", (r['match'],)).fetchone()
    if row:
        if row[0] in (1, 2):
            tue += 1
        if row[1] in (1, 2):
            wed += 1
con.close()
print(f'\nw31 forms for Tue-scheduled clients: {tue} | Wed-scheduled: {wed}')
