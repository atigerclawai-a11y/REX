#!/usr/bin/env python3
"""APPLY vision-confirmed marks (source A ONLY) to both DBs for Aug 3-7.
Deletes existing rows for these clients then writes clean ocr_scan plates.
extraction.json clients (source B) are LEFT ALONE — their rows are already
toped-up by the fill chain; vision marks are the authoritative upgrade."""
import json
import sqlite3
from datetime import date, timedelta

DBS = ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
       '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']
AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
W31_MON = date(2026, 8, 3)
DAY_CODE = {'M': 0, 'T': 1, 'W': 2, 'TH': 3, 'F': 4}
FIX = {'Вингерет': 'Винегрет', 'Квашеня капуста': 'Квашеная капуста',
       'Салат весенни': 'Салат весенний', 'Дорадо': 'Дорадо запеченая'}

def canon(d):
    return FIX.get(d, d)

# form metadata
form_meta = {}
for f in ['/tmp/w31_forms.json', '/tmp/w31_batch_4.json', '/tmp/w31_batch_5.json']:
    try:
        for x in json.load(open(f)):
            form_meta[str(x['n'])] = x
    except Exception as e:
        print(f'WARN: {f}: {e}')

def form_name(meta):
    return meta.get('name') or meta.get('match')

# vision marks (5 batches)
marks = {}
for f in ['/tmp/w31_marks_1.json', '/tmp/w31_marks_2.json', '/tmp/w31_marks_3.json',
          '/tmp/w31_marks_4.json', '/tmp/w31_marks_5.json']:
    try:
        marks.update(json.load(open(f)))
    except Exception as e:
        print(f'WARN: {f}: {e}')
print(f'vision marks loaded: {len(marks)} forms')

# name → marks
name_marks = {}
unmatched = []
for k, meta in form_meta.items():
    m = marks.get(k)
    nm = form_name(meta)
    if m and nm:
        name_marks[nm] = m
print(f'forms with marks: {len(name_marks)}')

# shift lookup
acon = sqlite3.connect(AUTH)
shift_for = {}
for name in name_marks:
    row = acon.execute("SELECT shift FROM clients WHERE name=?", (name,)).fetchone()
    shift_for[name] = str(row[0]) if row and row[0] else '1'
acon.close()

def apply_to(db):
    con = sqlite3.connect(db)
    cur = con.cursor()
    total_del = 0
    total_written = 0
    for name, source in sorted(name_marks.items()):
        ndel = cur.execute("""DELETE FROM client_menus WHERE client_name=? AND
            menu_date BETWEEN '2026-08-03' AND '2026-08-07'""", (name,)).rowcount
        total_del += ndel
        shift = shift_for.get(name, '1')
        for day, cats in source.items():
            idx = DAY_CODE.get(day)
            if idx is None:
                continue
            d = (W31_MON + timedelta(days=idx)).isoformat()

            def first(v):
                if not v:
                    return None
                if isinstance(v, (list, tuple)):
                    v = v[0] if v else None
                if isinstance(v, (list, tuple)):
                    v = v[0] if v else None
                return canon(str(v)) if v else None

            salad = first(cats.get('salad'))
            soup = first(cats.get('soup'))
            main_ = first(cats.get('main'))
            side = first(cats.get('side'))
            if not any([salad, soup, main_, side]):
                continue
            cur.execute("""INSERT INTO client_menus
                (client_name, menu_date, day_code, shift, salad, soup, main, side, source_sheet)
                VALUES (?,?,?,?,?,?,?,?,'ocr_scan')""",
                (name, d, day, shift, salad, soup, main_, side))
            total_written += 1
    con.commit()
    con.close()
    return total_del, total_written

for db in DBS:
    d, w = apply_to(db)
    print(f'{db.split("/")[-1]}: deleted {d} stale, wrote {w} ocr_scan rows for {len(name_marks)} clients')
