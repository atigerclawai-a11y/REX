#!/usr/bin/env python3
"""Match focr reads to roster clients — confirm each unreadable form's owner."""
import json
import re
import sqlite3
from pathlib import Path

results = json.load(open('/tmp/unread_focr.json'))
con = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
roster = [r[0] for r in con.execute("SELECT name FROM clients WHERE active=1")]
con.close()


def norm(n):
    return re.sub(r'[^a-z\'\- ]', '', n.lower()).strip()


def extract_name(focr_txt):
    m = re.search(r'Имя:\s*([A-Za-zА-Яа-я\'\-]+(?:\s+[A-Za-zА-Яа-я\'\-]+)+)', focr_txt)
    if m:
        return m.group(1).strip()
    m = re.search(r'мя:\s*([A-Za-zА-Яа-я\'\-]+(?:\s+[A-Za-zА-Яа-я\'\-]+)+)', focr_txt)
    if m:
        return m.group(1).strip()
    return None


from rapidfuzz import fuzz
matched = unmatched = 0
for r in results:
    name = extract_name(r['focr'])
    r['read_name'] = name
    if not name:
        r['match'] = None
        r['conf'] = 0
        unmatched += 1
        continue
    nn = norm(name)
    best, bs = None, 0
    for ro in roster:
        s = fuzz.WRatio(nn, norm(ro))
        if s > bs:
            best, bs = ro, s
    r['match'] = best
    r['conf'] = bs
    if bs >= 90:
        matched += 1
    else:
        unmatched += 1

print(f'matched (>=90): {matched}, low/no: {unmatched}')
for r in results:
    flag = '✓' if r.get('conf', 0) >= 90 else '⚠'
    print(f'  [{r["idx"]:02d}] {flag} read="{r.get("read_name")}" → {r.get("match")} ({r.get("conf", 0):.0f}%)')

json.dump(results, open('/tmp/unread_focr_matched.json', 'w'), ensure_ascii=False, indent=1)
