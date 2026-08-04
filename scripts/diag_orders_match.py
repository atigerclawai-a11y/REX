#!/usr/bin/env python3
"""Diagnose why orders don't match auth roster names."""
import json
import sqlite3

d = json.load(open('/Users/mainsobhelper/Documents/goj files/dashboard/data/GOJ_Menu_Orders.json'))
entry = d.get('2026-08-05', {})
names = list(entry.keys())
print(f'orders entries: {len(entry)}')

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
auth = {r[0] for r in a.execute('SELECT name FROM clients WHERE active=1')}
a.close()

matched = [n for n in names if n in auth]
unmatched = [n for n in names if n not in auth]
print(f'exact-match to auth roster: {len(matched)}/{len(names)}')
print(f'unmatched ({len(unmatched)}):')
for n in unmatched[:15]:
    print(f'  {n}')
