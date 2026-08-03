#!/usr/bin/env python3
"""Active learning — corrections to knowledge (Kato 2026-07-28, cron 30-min).

Every correction is permanent knowledge:
  1. new name_alias rows   → applied (aliases=N)
  2. menu_corrections rows → dish_confusions.json (wrong→right per category)
  3. per-client few-shot exemplars → active_learning/exemplars_<client>.json
Prints 'aliases=N confusions=N exemplar-clients=N' (no_agent cron output).

REBUILT 2026-08-03 from goj-menu-pipeline skill spec + verified cron output format
(original deleted in the 05:01 scripts/ wipe — no pyc survived).
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

REX = Path.home() / 'Desktop/REX'
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
SCRIPTS = REX / 'scripts'
CONFUSIONS = SCRIPTS / 'dish_confusions.json'
EXEMPLAR_DIR = SCRIPTS / 'active_learning'
MARKER = REX / '.active_learning_applied.json'

# corrections already folded into knowledge (idempotence marker)
FIELDS = ('id', 'client_name', 'category', 'wrong', 'right', 'source', 'created_at')


def main():
    con = sqlite3.connect(PROP)
    con.row_factory = sqlite3.Row

    # 1. aliases — fold approved name_alias rows into the roster-matching layer.
    # The canonical knowledge store IS name_alias itself (surya/promoter read it).
    # We track newly-applied ones via the marker so counts reflect deltas.
    applied = set()
    try:
        marker = json.loads(MARKER.read_text())
        applied = set(marker.get('aliases', []))
    except Exception:
        applied = set()
    alias_rows = con.execute('SELECT alias, roster_name, approved_by FROM name_alias ORDER BY created_at').fetchall()
    all_aliases = {r['alias'] for r in alias_rows}
    new_aliases = all_aliases - applied
    aliases_n = len(new_aliases)

    # 2. confusions — fold menu_corrections into dish_confusions.json
    conf = {'wrong_to_right': {}}
    if CONFUSIONS.exists():
        try:
            conf = json.loads(CONFUSIONS.read_text())
        except Exception:
            conf = {'wrong_to_right': {}}
    applied_conf = set()
    try:
        marker_conf = set(json.loads(MARKER.read_text()).get('confusions', []))
        applied_conf = marker_conf
    except Exception:
        pass
    corr_rows = con.execute('SELECT id, category, wrong, right FROM menu_corrections ORDER BY id').fetchall()
    new_conf = 0
    for r in corr_rows:
        if r['id'] in applied_conf:
            continue
        key = f"{r['category']}|{r['wrong']}|{r['right']}"
        conf['wrong_to_right'][key] = {'category': r['category'], 'wrong': r['wrong'], 'right': r['right']}
        applied_conf.add(r['id'])
        new_conf += 1
    CONFUSIONS.parent.mkdir(parents=True, exist_ok=True)
    CONFUSIONS.write_text(json.dumps(conf, ensure_ascii=False, indent=1))

    # 3. per-client exemplars — most recent real orders per client (few-shot set)
    EXEMPLAR_DIR.mkdir(parents=True, exist_ok=True)
    exemplar_clients = 0
    p = sqlite3.connect(f'file:{PROP}?mode=ro', uri=True)
    clients = p.execute(
        "SELECT DISTINCT client_name FROM client_menus "
        "WHERE source_sheet IN ('ocr_scan','drive_sync','day_shifted') "
        "AND menu_date >= '2026-07-20'").fetchall()
    for (cname,) in clients:
        rows = p.execute(
            "SELECT menu_date, day_code, shift, salad, soup, main, side FROM client_menus "
            "WHERE client_name=? AND source_sheet IN ('ocr_scan','drive_sync','day_shifted') "
            "ORDER BY menu_date DESC LIMIT 5", (cname,)).fetchall()
        if not rows:
            continue
        ex = EXEMPLAR_DIR / f'exemplars_{cname.replace(" ", "_").replace("/", "_")}.json'
        payload = {'client_name': cname, 'updated': datetime.now().isoformat(timespec='minutes'), 'orders': [
            {'menu_date': r[0], 'day_code': r[1], 'shift': r[2],
             'salad': r[3], 'soup': r[4], 'main': r[5], 'side': r[6]} for r in rows]}
        ex.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
        exemplar_clients += 1
    p.close()

    # marker update
    MARKER.write_text(json.dumps({'aliases': sorted(all_aliases), 'confusions': sorted(applied_conf)}))

    print(f'aliases={aliases_n} confusions={new_conf} exemplar-clients={exemplar_clients}')
    con.close()


if __name__ == '__main__':
    main()
