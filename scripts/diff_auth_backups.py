#!/usr/bin/env python3
"""Diff auth_tracker day_*_actual between now and backups to find what changed at 06:04:49."""
import sqlite3
from pathlib import Path

AUTH = Path('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
BAK_DIR = Path('/Users/mainsobhelper/Documents/goj files/backups')

# find backups of auth_tracker
baks = sorted(BAK_DIR.glob('*auth_tracker*'), key=lambda p: p.stat().st_mtime, reverse=True)
print(f'backups found ({len(baks)}):')
for b in baks[:8]:
    print(f'  {b.name} {b.stat().st_mtime}')

def get_counts(db):
    con = sqlite3.connect(db)
    out = {}
    for col in ['day_M_actual', 'day_T_actual', 'day_W_actual', 'day_TH_actual', 'day_F_actual']:
        s1 = con.execute(f"SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=1").fetchone()[0]
        s2 = con.execute(f"SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=2").fetchone()[0]
        out[col] = (s1, s2)
    con.close()
    return out

print('\ncurrent:', get_counts(AUTH))
for b in baks[:4]:
    try:
        print(f'{b.name}: {get_counts(str(b))}')
    except Exception as e:
        print(f'{b.name}: ERR {e}')
