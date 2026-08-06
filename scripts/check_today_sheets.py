#!/usr/bin/env python3
"""Check today's (Aug 5) sheets on disk: mtime + page counts vs truth (73/96).
Also check the goj-daily-handoff skill for Drive references."""
import fitz
import os
import sqlite3
from datetime import datetime

OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'
print('=== AUG 5 SHEETS ON DISK ===')
for f in ['GOJ_W_S1_Wednesday_signin.pdf', 'GOJ_W_S2_Wednesday_signin.pdf',
          'GOJ_W_S1_Wednesday_kitchen.pdf', 'GOJ_W_S2_Wednesday_kitchen.pdf']:
    p = os.path.join(OUT, f)
    if os.path.exists(p):
        mt = datetime.fromtimestamp(os.stat(p).st_mtime).strftime('%m-%d %H:%M:%S')
        try:
            doc = fitz.open(p)
            pages = doc.page_count
            doc.close()
        except Exception:
            pages = '?'
        print(f'  {f}: {pages} pages ({mt})')
    else:
        print(f'  {f}: MISSING')

print('\n=== AUTH TRUTH ===')
a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
s1 = a.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_W_actual=1").fetchone()[0]
s2 = a.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_W_actual=2").fetchone()[0]
print(f'  Wed Aug5 auth: {s1}/{s2} (Carecenta truth 73/96)')
a.close()
