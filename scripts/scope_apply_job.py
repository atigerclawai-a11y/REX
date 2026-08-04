#!/usr/bin/env python3
"""Scope the apply job: how many confirmed clients are Tue/Wed scheduled (immediate
deliverables), and per-doc footer week from form images."""
import json
import sqlite3

ROWS = json.load(open('/tmp/matched_table_final.json'))
AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
con = sqlite3.connect(AUTH)

tue_wed = {'tue_s1': [], 'tue_s2': [], 'wed_s1': [], 'wed_s2': [], 'neither': []}
for r in ROWS:
    name = r['match']
    row = con.execute("SELECT day_T_actual, day_W_actual FROM clients WHERE name=?", (name,)).fetchone()
    if row is None:
        tue_wed['neither'].append((r['n'], name, 'NOT-IN-AUTH'))
        continue
    t, w = row
    if t == 1:
        tue_wed['tue_s1'].append(name)
    elif t == 2:
        tue_wed['tue_s2'].append(name)
    if w == 1:
        tue_wed['wed_s1'].append(name)
    elif w == 2:
        tue_wed['wed_s2'].append(name)
    if t not in (1, 2) and w not in (1, 2):
        tue_wed['neither'].append((r['n'], name))
con.close()

print(f"Tue S1: {len(tue_wed['tue_s1'])} | Tue S2: {len(tue_wed['tue_s2'])} | "
      f"Wed S1: {len(tue_wed['wed_s1'])} | Wed S2: {len(tue_wed['wed_s2'])} | neither: {len(tue_wed['neither'])}")
print('\nneither (not Tue/Wed scheduled):')
for n, name in tue_wed['neither'][:40]:
    print(f'  #{n} {name}')
