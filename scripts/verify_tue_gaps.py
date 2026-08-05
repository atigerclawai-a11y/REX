#!/usr/bin/env python3
"""Verify the Tue NO-MATCH names against auth with fuzzy surname matching."""
import difflib
import json
import sqlite3

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
auth_names = [r[0] for r in a.execute("SELECT name FROM clients WHERE active=1")]
auth_sur = {}
for n in auth_names:
    parts = n.split()
    if parts:
        auth_sur.setdefault(parts[0].lower(), []).append(n)

for target in ['Kononovych Olexandra', 'Meltzer Eugene', 'Meltzer Larisa', 'Perepelytsya Lyubov']:
    sur = target.split()[0].lower()
    print(f'\n{target}:')
    exact = [n for n in auth_names if n.lower() == target.lower()]
    if exact:
        print(f'  EXACT: {exact}')
        continue
    if sur in auth_sur:
        print(f'  surname: {auth_sur[sur]}')
        continue
    # fuzzy
    best, br = None, 0
    for s in auth_sur:
        r = difflib.SequenceMatcher(None, sur, s).ratio()
        if r > br:
            best, br = s, r
    print(f'  fuzzy best: {best} ({br:.2f}) → {auth_sur.get(best, [])}')
    # also search LIKE partial
    for n in auth_names:
        if sur[:4] in n.lower() or n.lower()[:4] in sur:
            print(f'  partial: {n}')
a.close()
