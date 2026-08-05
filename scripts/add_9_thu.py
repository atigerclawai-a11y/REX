#!/usr/bin/env python3
"""ADD the 9 Carecenta Thu clients to day_TH_actual (they were missing).
Map via canonical_ids → auth_id, set TH=1 (S1 default — their times are all
1:15PM-5:15PM, shift info comes from the sign-in reality, keep S1 for now)."""
import re
import sqlite3
from rapidfuzz import fuzz

def norm(n):
    return ' '.join(sorted(re.sub(r'[^A-Z\'\- ]', '', n.upper()).split()))

con = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
con.row_factory = sqlite3.Row
cid_rows = con.execute('SELECT canonical_id, name, auth_id FROM canonical_ids').fetchall()
auth = {r['client_id']: r for r in con.execute('SELECT client_id, name, active, day_TH_actual FROM clients')}
cid_norms = [(norm(r['name']), r) for r in cid_rows]

targets = ['BEYLINA EMMA', 'Bardenshteyn Larisa', 'Bekerman Alla', 'Berezkin Mikhail',
           'Gendelman Anantoliy', 'Gendelman Liliya', 'Kormova Lyubov', 'Maglakelidze Mzia']

added = 0
for name in targets:
    nk = norm(name)
    best_r, bs = None, 0
    for cn, rr in cid_norms:
        s = fuzz.WRatio(nk, cn)
        if s > bs:
            best_r, bs = rr, s
    if best_r is None or bs < 85:
        print(f'  SKIP {name}: no auth match (best {bs:.0f})')
        continue
    r = best_r
    cl = auth.get(int(r['auth_id']))
    if cl is None:
        print(f'  SKIP {name}: no client row (auth_id {r["auth_id"]})')
        continue
    cur = cl['day_TH_actual']
    con.execute("UPDATE clients SET day_TH_actual=1 WHERE client_id=?", (int(r['auth_id']),))
    added += 1
    print(f'  ADDED {name} → {cl["name"]} (was TH={cur})')

con.commit()
s1 = con.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_TH_actual=1").fetchone()[0]
s2 = con.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_TH_actual=2").fetchone()[0]
print(f'\nday_TH_actual now: {s1}/{s2} = {s1+s2} (Carecenta truth: 149)')
con.close()
