#!/usr/bin/env python3
"""Decode Monday's full-day client convention: compare MON_AM/MON_PM lists vs day_M_actual."""
import re
import sqlite3

src = open('/tmp/sync_final_live.py').read()
MON_AM = re.search(r'MON_AM = """(.*?)"""', src, re.S).group(1).split('|')
MON_PM = re.search(r'MON_PM = """(.*?)"""', src, re.S).group(1).split('|')
am = {x.strip() for x in MON_AM}
pm = {x.strip() for x in MON_PM}
both = am & pm
print(f'MON_AM={len(am)} MON_PM={len(pm)} in-BOTH={len(both)}')
print('clients in BOTH Mon lists:', sorted(both))

con = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
con.row_factory = sqlite3.Row


def norm(n):
    return ' '.join(sorted(re.sub(r'[^A-Z\'\- ]', '', n.upper()).split()))


rows = con.execute('SELECT client_id, name, day_M_actual FROM clients WHERE active=1').fetchall()
by_norm = {norm(r['name']): r for r in rows}
con.close()

print('\nfull-day Mon clients -> day_M_actual (what shift were they stored as?):')
for b in sorted(both):
    r = by_norm.get(norm(b))
    print(f'  {b}: day_M={r["day_M_actual"] if r else "??"}')
