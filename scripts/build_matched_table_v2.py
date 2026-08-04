#!/usr/bin/env python3
"""Rebuild matched table EXCLUDING doc006880 forms (already vision-applied to DB).
Also vision-read the remaining genuine unknowns (006921 x4 + stragglers) and fold in."""
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
VF = '/tmp/vision_fixes.json'
if os.path.exists(VF):
    for k, v in json.load(open(VF)).items():
        results[k] = v

# EXCLUDE doc006880 forms — already vision-applied to DB
EXCLUDE_DOC = 'doc00688020260729073901'
rows = []
excluded = 0
for m in MANIFEST:
    if m['doc'] == EXCLUDE_DOC:
        excluded += 1
        continue
    n = m['n']
    raw = results.get(str(n)) or results.get(n)
    name, score = best_match(raw)
    rows.append({'n': n, 'doc': m['doc'], 'page': m['page'], 'raw': raw, 'match': name, 'score': score})

# renumber sequentially 1..N
for i, r in enumerate(rows, 1):
    r['n'] = i

named = sum(1 for r in rows if r['match'])
unknown = [r for r in rows if not r['match']]
print(f'EXCLUDED 880: {excluded}')
print(f'TOTAL {len(rows)} | matched {named} | UNKNOWN {len(unknown)}')
json.dump(rows, open('/tmp/matched_table_v2.json', 'w'), indent=1)

for r in rows:
    tag = r['match'] or '*** UNKNOWN ***'
    print(f"#{r['n']}  {tag}  (focr: {r['raw'] or '—'})")
print(f'\nUNKNOWN: {[(r["n"], r["doc"], r["page"]) for r in unknown]}')
