#!/usr/bin/env python3
"""Debug: re-run apply logic in dry-run for Shefer Bella to see what it writes."""
import json
import sqlite3
from datetime import date, timedelta

DBS = ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db']
AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
W31_MON = date(2026, 8, 3)
DAY_CODE = {'M': 0, 'T': 1, 'W': 2, 'TH': 3, 'F': 4}
FIX = {'Вингерет': 'Винегрет'}

marks = {}
for f in ['/tmp/w31_marks_1.json', '/tmp/w31_marks_2.json', '/tmp/w31_marks_3.json',
          '/tmp/w31_marks_4.json', '/tmp/w31_marks_5.json']:
    try:
        marks.update(json.load(open(f)))
    except Exception:
        pass

form_meta = {}
for f in ['/tmp/w31_forms.json', '/tmp/w31_batch_4.json', '/tmp/w31_batch_5.json']:
    try:
        for x in json.load(open(f)):
            form_meta[str(x['n'])] = x
    except Exception:
        pass

def form_name(meta):
    return meta.get('name') or meta.get('match')

# simulate for Shefer Bella (n=1)
meta = form_meta.get('1')
print(f'meta: {meta}')
print(f'form_name: {form_name(meta)}')
m = marks.get('1')
print(f'marks M: {m.get("M")}')

# check what's in DB now under that name for Aug 3-7
p = sqlite3.connect(DBS[0])
rows = p.execute("""SELECT menu_date, day_code, salad, soup, main, side, source_sheet
    FROM client_menus WHERE client_name=? AND menu_date BETWEEN '2026-08-03' AND '2026-08-07'
    ORDER BY menu_date""", ('Shefer Bella',)).fetchall()
for r in rows:
    print(f'  DB: {r[0]} {r[1]}: {r[2]}|{r[3]}|{r[4]}|{r[5]} [{r[6]}]')
p.close()
