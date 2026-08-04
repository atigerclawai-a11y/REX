#!/usr/bin/env python3
"""Check: the 26 collision clients — do they attend Tue/Wed, and do they now
have ocr_scan rows? Regenerate needed?"""
import json
import sqlite3

# names that were in batch 4 (n 1-30 collision range) — get from batch 4
b4 = json.load(open('/tmp/w31_batch_4.json'))
names_b4 = set()
for x in b4[:30]:
    names_b4.add(x.get('match') or x.get('name'))
print(f'batch-4 n1-30 (collision range): {len(names_b4)} clients')

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
attends = []
for n in sorted(names_b4):
    r = a.execute("SELECT day_T_actual, day_W_actual FROM clients WHERE name=?", (n,)).fetchone()
    if r and (r[0] in (1, 2) or r[1] in (1, 2)):
        ocr = p.execute("""SELECT COUNT(*) FROM client_menus
            WHERE client_name=? AND menu_date IN ('2026-08-04','2026-08-05')
            AND source_sheet='ocr_scan'""", (n,)).fetchone()[0]
        attends.append((n, r[0], r[1], ocr))
print(f'attending Tue/Wed: {len(attends)}')
for n, t, w, ocr in attends:
    print(f'  {n} (Tue={t} Wed={w}) ocr_rows={ocr}')
a.close()
p.close()
