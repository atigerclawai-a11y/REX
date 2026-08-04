#!/usr/bin/env python3
"""RE-APPLY with batch-scoped keys (fixes n-collision that dropped batch-4 forms).
Each (batch, n) is unique: B1(157 forms), B4(40), B5(30). Writes ocr_scan rows
for any confirmed client that has NO ocr_scan rows yet this week (delete-then-write
only their days, preserving existing real rows)."""
import json
import sqlite3
from datetime import date, timedelta

DBS = ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
       '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']
AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
W31_MON = date(2026, 8, 3)
DAY_CODE = {'M': 0, 'T': 1, 'W': 2, 'TH': 3, 'F': 4}
FIX = {'Вингерет': 'Винегрет', 'Квашеня капуста': 'Квашеная капуста'}

def canon(d):
    return FIX.get(d, d)

# batch → (forms_file, marks_file)
BATCHES = [
    ('B1', '/tmp/w31_batch_1.json', '/tmp/w31_marks_1.json'),
    ('B2', '/tmp/w31_batch_2.json', '/tmp/w31_marks_2.json'),
    ('B3', '/tmp/w31_batch_3.json', '/tmp/w31_marks_3.json'),
    ('B4', '/tmp/w31_batch_4.json', '/tmp/w31_marks_4.json'),
    ('B5', '/tmp/w31_batch_5.json', '/tmp/w31_marks_5.json'),
]

# merge with batch-scoped keys: (batch, n) → (name, marks)
confirmed = {}  # name → marks (first occurrence wins; later batch same name = same marks anyway)
for batch, forms_f, marks_f in BATCHES:
    try:
        marks = json.load(open(marks_f))
    except Exception as e:
        print(f'WARN {marks_f}: {e}')
        continue
    forms = json.load(open(forms_f)) if forms_f else []
    for x in forms:
        n = str(x['n'])
        name = x.get('name') or x.get('match')
        m = marks.get(n)
        if m and name and name not in confirmed:
            confirmed[name] = m
print(f'confirmed with marks: {len(confirmed)} clients')

# shift lookup
acon = sqlite3.connect(AUTH)
shift_for = {}
for name in confirmed:
    row = acon.execute("SELECT shift FROM clients WHERE name=?", (name,)).fetchone()
    shift_for[name] = str(row[0]) if row and row[0] else '1'
acon.close()

def apply_to(db):
    con = sqlite3.connect(db)
    cur = con.cursor()
    written = 0
    skipped = 0
    for name, source in sorted(confirmed.items()):
        # does this client already have ocr_scan rows this week? (batch-5 already applied)
        has_ocr = cur.execute("""SELECT COUNT(*) FROM client_menus
            WHERE client_name=? AND menu_date BETWEEN '2026-08-03' AND '2026-08-07'
            AND source_sheet='ocr_scan'""", (name,)).fetchone()[0]
        if has_ocr:
            skipped += 1
            continue
        # delete only fallback rows for this client (their real marks replace them)
        cur.execute("""DELETE FROM client_menus WHERE client_name=?
            AND menu_date BETWEEN '2026-08-03' AND '2026-08-07'
            AND source_sheet IN ('last_order_fallback','house_standard')""", (name,))
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
            salad, soup, main_, side = first(cats.get('salad')), first(cats.get('soup')), first(cats.get('main')), first(cats.get('side'))
            if not any([salad, soup, main_, side]):
                continue
            cur.execute("""INSERT OR IGNORE INTO client_menus
                (client_name, menu_date, day_code, shift, salad, soup, main, side, source_sheet)
                VALUES (?,?,?,?,?,?,?,?,'ocr_scan')""",
                (name, d, day, shift, salad, soup, main_, side))
            written += 1
    con.commit()
    con.close()
    return written, skipped

for db in DBS:
    w, s = apply_to(db)
    print(f'{db.split("/")[-1]}: wrote {w} ocr_scan rows, skipped {s} already-applied')
