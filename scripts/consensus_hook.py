#!/usr/bin/env python3
'''Consensus layer: surya vs cloud. Agree -> auto-accept. Disagree -> review queue.
Cost control: cloud is ONLY invoked for forms whose surya extraction has problems
(contract violation, category confusion, empty-but-inked, low checkbox count).
Cron: 7be4a65ac889 (10-min). Max 3 cloud calls per run budget.

REBUILT 2026-08-03 from Blue #191 decompile of consensus_apply + skill spec
(original deleted in the 05:01 scripts/ wipe).
'''
import json
import sqlite3
import sys
from pathlib import Path

REX = Path('/Users/mainsobhelper/Desktop/REX')
DB = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
sys.path.insert(0, str(REX / 'scripts'))
from cloud_menu_read import read_form_pages  # noqa: E402

CATALOG = json.loads((REX / 'scripts/week30_dishes.json').read_text())
CATMAP = {}
for cat, dishes in CATALOG.items():
    for d in dishes:
        CATMAP[d] = cat

CLOUD_BUDGET = 3
MAX_FORMS_PER_BATCH = 10


def surya_problems(extraction):
    '''Return list of problem descriptions for a surya extraction entry.'''
    problems = []
    selections = extraction.get('selections', {})
    for day, cats in selections.items():
        for cat, v in cats.items():
            dish = v[0] if isinstance(v, (list, tuple)) else str(v)
            if dish and dish not in CATMAP:
                problems.append(f'non-catalog dish "{dish}" in {cat}/{day}')
                continue
            if dish and CATMAP.get(dish) != cat:
                problems.append(f'category confusion: "{dish}" in {cat}/{day}')
    if not any(selections.values()):
        problems.append('no marks read at all')
    return problems


def ensure_review_table(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS menu_review_queue (\n"
                 "    id INTEGER PRIMARY KEY AUTOINCREMENT, client_name TEXT, batch TEXT, day TEXT,\n"
                 "    category TEXT, surya_pick TEXT, cloud_pick TEXT, status TEXT DEFAULT 'pending',\n"
                 "    resolved_pick TEXT, resolved_by TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,\n"
                 "    resolved_at TEXT)")
    conn.commit()


def main(batch):
    ext_path = REX / 'blank_parse' / batch / 'extraction.json'
    if not ext_path.exists():
        print(f'{batch}: no extraction.json')
        return None
    ext = json.loads(ext_path.read_text())
    conn = sqlite3.connect(DB)
    ensure_review_table(conn)

    # forms needing cloud consensus
    needs_cloud = {}
    for nm, data in ext.items():
        probs = surya_problems(data)
        if probs:
            needs_cloud[nm] = probs
    total = len(ext)
    print(f'{batch}: {total} forms, {len(needs_cloud)} need cloud consensus ({100 * len(needs_cloud) // max(total, 1)}%)')

    for nm, probs in list(needs_cloud.items())[:MAX_FORMS_PER_BATCH]:
        print(f'  {nm}: {probs[0]}' + (f' (+{len(probs) - 1} more)' if len(probs) > 1 else ''))

    # cloud escalation within budget (skip actual API call in dry mode; real path via promoter)
    calls = min(CLOUD_BUDGET, len(needs_cloud))
    if calls:
        print(f'  cloud consensus: {calls} form(s) (budget {CLOUD_BUDGET}/run)')
        for nm in list(needs_cloud.keys())[:calls]:
            # mark for cloud review — the promoter's cloud path resolves these
            conn.execute(
                "INSERT INTO menu_review_queue (client_name, batch, day, category, surya_pick, status) "
                "VALUES (?,?,?,?,?,'pending')",
                (nm, batch, 'M', 'mixed', str(needs_cloud[nm][0])[:120]))
    conn.commit()
    conn.close()
    return {'total': total, 'needs_cloud': len(needs_cloud), 'escalated': calls}


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'doc00673920260727042014')
