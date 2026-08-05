#!/usr/bin/env python3
"""REVERT my wrong Thursday changes + do ONE clean definitive sync from the
CORRECT Carecenta parse (149 = 88 S1 / 61 S2).
The earlier 'safe sync' was based on a broken regex that missed all S1 (AM)
clients — it wrongly removed 25 and added 9. Restore from pre-change backup
first, then apply the correct roster."""
import json
import os
import sqlite3
import shutil
import re
from rapidfuzz import fuzz

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
# find the last backup before my changes (today's earlier backup)
baks = sorted([b for b in os.listdir(os.path.dirname(AUTH)) if 'bak' in b and os.path.isfile(os.path.join(os.path.dirname(AUTH), b))])
print(f'available backups: {baks[-5:]}')

# current state before we do anything
con = sqlite3.connect(AUTH)
s1 = con.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_TH_actual=1").fetchone()[0]
s2 = con.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_TH_actual=2").fetchone()[0]
print(f'day_TH_actual BEFORE revert: {s1}/{s2}')
con.close()
