#!/usr/bin/env python3
"""FINAL matched table: exclude doc006880 (applied) + doc006921 (sign-in roster),
merge all vision fixes, renumber 1..N, output for chat + email."""
import json
import os
import sqlite3
from difflib import SequenceMatcher

GUESSES = '/tmp/unreadable_guesses.json'
MANIFEST = json.load(open('/tmp/unreadable_full_manifest.json'))
AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'

con = sqlite3.connect(AUTH)
roster = [r[0] for r in con.execute("SELECT name FROM clients WHERE active=1")]
con.close()

def norm(s):
    return ' '.join(s.strip().lower().split())

def best_match(raw):
    if not raw:
        return (None, 0)
    n = norm(raw)
    for r in roster:
        if norm(r) == n:
            return (r, 100)
    parts = n.split()
    best, best_s = None, 0
    for r in roster:
        rn = norm(r)
        rtoks = set(rn.split())
        ntoks = set(parts)
        inter = len(rtoks & ntoks)
        if inter == 0:
            continue
        s = int(100 * inter / max(len(rtoks), len(ntoks)))
        s += int(SequenceMatcher(None, n, rn).ratio() * 40)
        if s > best_s:
            best, best_s = r, s
    return (best, best_s)

results = json.load(open(GUESSES))
# ALL vision fixes (8 total — keys are MANIFEST numbers, verified)
VF = '/tmp/vision_fixes.json'
if os.path.exists(VF):
    for k, v in json.load(open(VF)).items():
        results[k] = v

# excludes: doc006880 (already applied to DB) + doc006921 (sign-in roster, not menus)
EXCLUDE_DOCS = {'doc00688020260729073901', 'doc00692120260730070429'}

rows = []
excluded = 0
for m in MANIFEST:
    if m['doc'] in EXCLUDE_DOCS:
        excluded += 1
        continue
    n = m['n']
    raw = results.get(str(n)) or results.get(n)
    name, score = best_match(raw)
    rows.append({'n': len(rows) + 1, 'doc': m['doc'], 'page': m['page'],
                 'raw': raw, 'match': name, 'score': score})

named = sum(1 for r in rows if r['match'])
unknown = [r for r in rows if not r['match']]
print(f'EXCLUDED: {excluded} (880 applied + 921 sign-in)')
print(f'TOTAL {len(rows)} | matched {named} | UNKNOWN {len(unknown)}')
json.dump(rows, open('/tmp/matched_table_final.json', 'w'), indent=1)

# clean output for chat
for r in rows:
    tag = r['match'] or '*** UNKNOWN ***'
    print(f"#{r['n']:>3}  {tag}")
if unknown:
    print(f'\nUNKNOWN: {[(r["n"], r["doc"], r["page"]) for r in unknown]}')
