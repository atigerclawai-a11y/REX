#!/usr/bin/env python3
'''PRE-GENERATION GATE — run before any menu-sheet generation for <date>.

Usage:  python3 pre_generation_gate.py 2026-07-29
Exit 0: safe to generate.  Exit 1: REFUSES to generate — every failure printed.

Refuses if:
  1. any attendee for <date> (auth_tracker day_X_actual IN (1,2), active=1)
     lacks a COMPLETE menu row (row exists, shift in 1/2, 4 dishes non-empty)
     in the canonical proprietary DB;
  2. any client_menus row for <date> (either DB) has a bad shift or a
     non-catalog / wrong-category dish (locked catalog week30_dishes.json);
  3. any un-applied extraction_surya.json exists in blank_parse
     (stale-sheet guard — OCR arrived but was never promoted/applied).

Stdlib only. Read-only against both DBs — fixes nothing, reports only.
REBUILT 2026-08-03 from Blue #191 decompile (original deleted 05:01 scripts/ wipe).
'''
import glob
import os
import sqlite3
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from menu_contracts import AUTH_DB, WEEKDAY_COL, VALID_SHIFTS, FIELD2CAT, _load_catalog, _canonical_dish, canon

DBS = [
    '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
    '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db',
]
CANONICAL = DBS[0]
BLANK_PARSE = '/Users/mainsobhelper/Desktop/REX/blank_parse'


def main():
    if len(sys.argv) != 2:
        sys.exit('usage: pre_generation_gate.py <YYYY-MM-DD>')
    mdate = sys.argv[1]
    wd = date.fromisoformat(mdate).weekday()
    if wd not in WEEKDAY_COL:
        sys.exit(f'GATE FAIL: {mdate} is not a service day (weekday={wd})')
    col = WEEKDAY_COL[wd]
    failures = []

    # 1. every attendee has a COMPLETE menu row
    a = sqlite3.connect(f'file:{AUTH_DB}?mode=ro', uri=True)
    attendees = a.execute(f'SELECT name FROM clients WHERE active=1 AND {col} IN (1,2) ORDER BY name').fetchall()
    a.close()
    c = sqlite3.connect(f'file:{CANONICAL}?mode=ro', uri=True)
    rows = c.execute('SELECT client_name, shift, salad, soup, main, side FROM client_menus WHERE menu_date=?', (mdate,)).fetchall()
    c.close()
    by_name = {}
    for r in rows:
        by_name.setdefault(canon(r[0]), []).append(r)

    missing, incomplete = [], []
    for (name,) in attendees:
        got = by_name.get(canon(name), [])
        if not got:
            missing.append(name)
            continue
        complete = any(
            r[1] in VALID_SHIFTS and all(str(v).strip() for v in r[2:6])
            for r in got
        )
        if not complete:
            incomplete.append(name)
    if missing:
        failures.append(
            f'{len(missing)} attendee(s) with NO menu row for {mdate}: '
            + ', '.join(missing[:10]) + (' ...' if len(missing) > 10 else ''))
    if incomplete:
        failures.append(
            f'{len(incomplete)} attendee(s) with INCOMPLETE menu row for {mdate}: '
            + ', '.join(incomplete[:10]) + (' ...' if len(incomplete) > 10 else ''))

    # 2. catalog/shift integrity across BOTH DBs (canonicalize aliases first —
    #    kitchen shorthand like Вин/Ол/Б is legitimate, only true garbage flags)
    cat = _load_catalog()
    for dbp in DBS:
        con = sqlite3.connect(f'file:{dbp}?mode=ro', uri=True)
        for r in con.execute('SELECT client_name, shift, salad, soup, main, side FROM client_menus WHERE menu_date=?', (mdate,)):
            shift = str(r[1])
            if shift not in VALID_SHIFTS:
                failures.append(f'{os.path.basename(dbp)}: bad_shift {r[0]} {shift!r}')
            for field, value in zip(('salad', 'soup', 'main', 'side'), r[2:6]):
                if value and str(value).strip():
                    v = str(value).strip()
                    name, ok = _canonical_dish(field, v)
                    if not ok:
                        failures.append(f'{os.path.basename(dbp)}: non-catalog {field}={v!r} ({r[0]})')
        con.close()

    # 3. stale un-applied extractions
    stale = glob.glob(os.path.join(BLANK_PARSE, '*', 'extraction_surya.json'))
    if stale:
        failures.append(f'{len(stale)} un-applied extraction_surya.json in blank_parse (stale-sheet guard)')

    if failures:
        print(f'GATE FAIL for {mdate}:')
        for f in failures:
            print(f'  - {f}')
        sys.exit(1)
    print(f'GATE OK for {mdate} — safe to generate.')
    sys.exit(0)


if __name__ == '__main__':
    main()
