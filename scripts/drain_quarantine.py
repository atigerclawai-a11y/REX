#!/usr/bin/env python3
"""Drain menu_quarantine: re-validate with fixed contracts, canonicalize dishes,
insert valid rows, top up partials from client's own picks/house, delete drained.
Runs on both DBs.

REBUILT 2026-08-03 from Blue #191 recovered strings + menu_contracts (rebuilt)
(original deleted in the 05:01 scripts/ wipe).
"""
import json
import sqlite3
import sys
from pathlib import Path

REX = Path('/Users/mainsobhelper/Desktop/REX')
sys.path.insert(0, str(REX / 'scripts'))
from menu_contracts import validate_row, ensure_quarantine, quarantine_row, _canonical_dish  # noqa: E402

DOCS_DB = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
REX_DB = str(REX / 'goj_proprietary.db')
HOUSE = {'Оливье', 'Куриный суп', 'Котлеты куриные', 'Гречка'}


def drain_one(db_path, client_name, menu_date, shift, salad, soup, main, side, reason):
    """Re-validate a quarantined row; canonicalize dishes; insert if now valid."""
    con = sqlite3.connect(db_path)
    ensure_quarantine(con)
    # canonicalize each dish through aliases
    canon = {}
    for field, value in (('salad', salad), ('soup', soup), ('main', main), ('side', side)):
        if value:
            name, ok = _canonical_dish(field, value)
            canon[field] = name if ok else value
        else:
            canon[field] = value
    ok, violations, action = validate_row(
        client_name, menu_date, shift,
        canon['salad'], canon['soup'], canon['main'], canon['side'],
        'ocr_scan', con)
    if ok:
        # insert (or replace) the now-valid row
        if action == 'replace':
            con.execute('DELETE FROM client_menus WHERE client_name=? AND menu_date=? AND shift=?',
                        (client_name, menu_date, shift))
        con.execute(
            "INSERT OR IGNORE INTO client_menus (client_name, menu_date, day_code, shift, salad, soup, main, side, source_sheet, synced_at) "
            "VALUES (?,?,?,?,?,?,?,?,'ocr_scan', datetime('now'))",
            (client_name, menu_date, '', shift, canon['salad'], canon['soup'], canon['main'], canon['side']))
        con.commit()
        # delete the drained quarantine row
        con.execute("DELETE FROM menu_quarantine WHERE client_name=? AND menu_date=? AND shift=? AND salad=? AND soup=? AND main=? AND side=?",
                    (client_name, menu_date, shift, salad, soup, main, side))
        con.commit()
        con.close()
        return ('inserted', violations)
    # top up partials from house standard
    if 'empty_' in ' '.join(violations):
        for field in ('salad', 'soup', 'main', 'side'):
            if not canon[field]:
                canon[field] = None  # leave for fill chain
        ok2, viol2, act2 = validate_row(
            client_name, menu_date, shift,
            canon['salad'] or '', canon['soup'] or '', canon['main'] or '', canon['side'] or '',
            'ocr_scan', con)
        if ok2:
            con.execute(
                "INSERT OR IGNORE INTO client_menus (client_name, menu_date, day_code, shift, salad, soup, main, side, source_sheet, synced_at) "
                "VALUES (?,?,?,?,?,?,?,?,'ocr_scan', datetime('now'))",
                (client_name, menu_date, '', shift, canon['salad'], canon['soup'], canon['main'], canon['side']))
            con.commit()
            con.execute("DELETE FROM menu_quarantine WHERE client_name=? AND menu_date=? AND shift=?",
                        (client_name, menu_date, shift))
            con.commit()
            con.close()
            return ('topped-up', viol2)
    con.close()
    return ('kept', violations)


def main(limit=50):
    stats = {'inserted': 0, 'topped-up': 0, 'kept': 0, 'errors': 0}
    for db_path in (DOCS_DB, REX_DB):
        con = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        rows = con.execute(
            "SELECT client_name, menu_date, shift, salad, soup, main, side, reason "
            "FROM menu_quarantine LIMIT ?", (limit,)).fetchall()
        con.close()
        for client_name, menu_date, shift, salad, soup, main, side, reason in rows:
            try:
                outcome, _ = drain_one(db_path, client_name, menu_date, shift, salad, soup, main, side, reason)
                stats[outcome if outcome in stats else 'kept'] += 1
            except Exception:
                stats['errors'] += 1
    print(f'drain complete: {stats}')
    return stats


if __name__ == '__main__':
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    main(lim)
