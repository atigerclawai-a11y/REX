#!/usr/bin/env python3
"""Cleanup: delete wrong-provenance partial rows on Aug 3-7 for week-30 doc clients
(their picks belong to Jul 27-31). Only rows that are PARTIAL (missing main or side)
or where the client has NO confirmed week-31 form. Run AFTER apply_w31_marks."""
import json
import sqlite3
from pathlib import Path

DBS = ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
       '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']
BASE = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')

W30_DOCS = ['doc00680820260727160512', 'doc00680920260727160541', 'doc00681020260727160603',
            'doc00681120260727160643', 'doc00681220260727160712']

# week-30 doc clients (their extraction.json names)
w30_clients = set()
for d in W30_DOCS:
    ddir = BASE / d
    if ddir.exists():
        for f in ddir.glob('extraction*.json'):
            try:
                w30_clients.update(json.load(open(f)).keys())
            except Exception:
                pass

# clients with confirmed week-31 forms (will have real rows after apply)
W31_FORMS = json.load(open('/tmp/w31_forms.json'))
w31_names = {f['name'] for f in W31_FORMS}

# cleanup candidates: week-30 clients on Aug 3-7, NOT having a week-31 form
# (their week-30 picks don't belong here at all)
for db in DBS:
    con = sqlite3.connect(db)
    rows = con.execute("""SELECT id, client_name, menu_date, day_code, salad, soup, main, side, source_sheet
        FROM client_menus WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07'
        AND source_sheet='ocr_scan'""").fetchall()
    to_del = []
    for r in rows:
        cid, name, d, dc, salad, soup, main_, side, src = r
        if name in w30_clients and name not in w31_names:
            # partial or full — week-30 client has no business on week-31 dates
            to_del.append(cid)
    if to_del:
        cur = con.execute(f"DELETE FROM client_menus WHERE id IN ({','.join('?'*len(to_del))})", to_del)
        print(f'{db.split("/")[-1]}: deleted {cur.rowcount} wrong-provenance rows '
              f'({len(w30_clients)} w30 clients, {len(w31_names)} have real w31 forms)')
    else:
        print(f'{db.split("/")[-1]}: 0 pollution rows to delete')
    con.commit()
    con.close()
