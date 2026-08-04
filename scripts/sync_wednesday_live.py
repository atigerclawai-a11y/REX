#!/usr/bin/env python3
"""ID-FIRST Wednesday sync (Kato 2026-08-03): match LIVE Carecenta roster
(AM 73 / PM 95) to canonical_ids by name → update day_W_actual keyed by
canonical_id. Zero DELETE/DROP — UPDATE only. Backup taken before run.
"""
import json
import re
import sqlite3
from pathlib import Path

AUTH = Path.home() / 'Documents/goj files/dashboard/auth_tracker.db'
ROSTER = Path('/tmp/wednesday_live_roster.json')

data = json.loads(ROSTER.read_text())
roster_am = [n.upper() for n in data['am']]
roster_pm = [n.upper() for n in data['pm']]


def norm(n):
    """'Last, First' or 'Last First' or 'First Last' → sorted tokens joined."""
    toks = re.sub(r'[^A-Z\'\- ]', '', n.upper()).split()
    return ' '.join(sorted(toks))


# canonical_ids: canonical_id → (name, auth_id, prop_id)
con = sqlite3.connect(str(AUTH))
con.row_factory = sqlite3.Row
cid_rows = con.execute('SELECT canonical_id, name, auth_id FROM canonical_ids').fetchall()
by_norm = {}
for r in cid_rows:
    by_norm.setdefault(norm(r['name']), []).append(r)

am_norm = {norm(n) for n in roster_am}
pm_norm = {norm(n) for n in roster_pm}

# fuzzy fallback for spelling variants (Mariia/Maria, Sofiya/Sofia, Tatiana/Tatyana…)
try:
    from rapidfuzz import fuzz
    FUZZY = True
except Exception:
    FUZZY = False

cid_norms_list = sorted((norm(r['name']), r) for r in cid_rows)
fuzzy_map = {}  # roster_norm → canonical row


def fuzzy_find(norm_key):
    if norm_key in fuzzy_map:
        return fuzzy_map[norm_key]
    if FUZZY:
        best, best_score = None, 0
        for cn, r in cid_norms_list:
            s = fuzz.WRatio(norm_key, cn)
            if s > best_score:
                best, best_score = r, s
        if best_score >= 85:
            fuzzy_map[norm_key] = best
            return best
    return None


# ZERO-THEN-SET (proven Mon/Tue pattern, Kato 2026-08-03): clear stale day_W
# values FIRST so only LIVE roster clients count — no overcount from old data.
con.execute('UPDATE clients SET day_W_actual=0 WHERE active=1')
con.commit()

matched_am = matched_pm = unmatched = 0
unmatched_names = []
fuzzy_hits = []
for r in cid_rows:
    key = norm(r['name'])
    shift = 1 if key in am_norm else (2 if key in pm_norm else None)
    if shift == 1:
        matched_am += 1
    elif shift == 2:
        matched_pm += 1
    else:
        unmatched += 1
        unmatched_names.append(r['name'])
    if shift is not None:
        cur = con.execute('SELECT day_W_actual FROM clients WHERE client_id=?',
                          (r['auth_id'],)).fetchone()
        if cur is not None and cur['day_W_actual'] != shift:
            con.execute('UPDATE clients SET day_W_actual=? WHERE client_id=?',
                        (shift, r['auth_id']))
con.commit()

# roster names with NO canonical ID — try fuzzy
roster_norm = {norm(n) for n in roster_am + roster_pm}
cid_norms = {norm(r['name']) for r in cid_rows}
no_cid = sorted(n for n in set(roster_norm) - cid_norms)
resolved = []
for n in list(no_cid):
    r = fuzzy_find(n)
    if r is not None:
        resolved.append((n, r['name'], r['canonical_id']))
        no_cid.remove(n)
        # apply the shift for the fuzzy-resolved client too
        shift = 1 if n in am_norm else (2 if n in pm_norm else None)
        if shift is not None:
            cur = con.execute('SELECT day_W_actual FROM clients WHERE client_id=?',
                              (r['auth_id'],)).fetchone()
            if cur is not None and cur['day_W_actual'] != shift:
                con.execute('UPDATE clients SET day_W_actual=? WHERE client_id=?',
                            (shift, r['auth_id']))
con.commit()
con.close()
print(f'ID-first sync: matched AM={matched_am} PM={matched_pm} unmatched(auth not on roster)={unmatched}')
print(f'fuzzy-resolved roster names ({len(resolved)}):')
for orig, canon, cid in resolved:
    print(f'  {orig} → {canon} [{cid}]')
print(f'STILL no canonical_id ({len(no_cid)}):')
for n in no_cid:
    print(f'  {n}')
