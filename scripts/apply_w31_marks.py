#!/usr/bin/env python3
"""Apply vision-extracted week-31 marks to BOTH goj_proprietary DBs.
For each confirmed form with marks: write ocr_scan rows for Aug 3-7 (M/T/W/TH/F)
mapped via WEEK31 dates, delete-then-insert per (client, date) to avoid stale rows."""
import json
import sqlite3
import sys
from datetime import date, timedelta

DBS = ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
       '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']

W31_MON = date(2026, 8, 3)
DAY_CODE = {'M': 0, 'T': 1, 'W': 2, 'TH': 3, 'F': 4}

# marks files from vision workers
marks = {}
for f in ['/tmp/w31_marks_1.json', '/tmp/w31_marks_2.json', '/tmp/w31_marks_3.json']:
    try:
        marks.update(json.load(open(f)))
    except Exception as e:
        print(f'WARN: {f} not readable: {e}')

# form metadata (n → name, doc, page)
FORMS = {str(f['n']): f for f in json.load(open('/tmp/w31_forms.json'))}

print(f'loaded marks for {len(marks)} forms')

# canonical dish fixups (focr/vision typos)
FIX = {'Вингерет': 'Винегрет', 'Квашеня капуста': 'Квашеная капуста',
       'Салат весенни': 'Салат весенний', 'Дорадо': 'Дорадо запеченая'}

def canon(d):
    return FIX.get(d, d)

# shift per client from auth_tracker
AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
acon = sqlite3.connect(AUTH)
shift_for = {}
for name in [f['name'] for f in FORMS.values()]:
    row = acon.execute("SELECT shift FROM clients WHERE name=?", (name,)).fetchone()
    shift_for[name] = row[0] if row and row[0] else '1'
acon.close()

def apply_to_db(db, marks, forms):
    con = sqlite3.connect(db)
    cur = con.cursor()
    written = 0
    deleted = 0
    for n_str, m in marks.items():
        f = forms.get(n_str)
        if not f:
            continue
        name = f['name']
        shift = shift_for.get(name, '1')
        # delete existing rows for this client in week 31 (delete-before-refill)
        ndel = cur.execute("""DELETE FROM client_menus WHERE client_name=? AND
            menu_date BETWEEN '2026-08-03' AND '2026-08-07'""", (name,)).rowcount
        deleted += ndel
        for day, cats in m.items():
            idx = DAY_CODE.get(day)
            if idx is None:
                continue
            d = (W31_MON + timedelta(days=idx)).isoformat()
            salad = canon(cats.get('salad', [''])[0]) if cats.get('salad') else None
            soup = canon(cats.get('soup', [''])[0]) if cats.get('soup') else None
            main = canon(cats.get('main', [''])[0]) if cats.get('main') else None
            side = canon(cats.get('side', [''])[0]) if cats.get('side') else None
            if not any([salad, soup, main, side]):
                continue
            cur.execute("""INSERT INTO client_menus
                (client_name, menu_date, day_code, shift, salad, soup, main, side, source_sheet)
                VALUES (?,?,?,?,?,?,?,?,'ocr_scan')""",
                (name, d, day, shift, salad, soup, main, side))
            written += 1
    con.commit()
    con.close()
    return written, deleted

for db in DBS:
    w, d = apply_to_db(db, marks, FORMS)
    print(f'{db.split("/")[-1]}: written {w} ocr_scan rows, deleted {d} stale rows')
