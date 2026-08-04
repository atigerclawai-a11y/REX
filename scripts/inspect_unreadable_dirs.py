#!/usr/bin/env python3
"""Inspect garbled_review + menu_ocr_quarantine + CC_rex_review.db queue."""
import os
import sqlite3
from pathlib import Path

REX = Path('/Users/mainsobhelper/Desktop/REX')

for d in ['garbled_review', 'menu_ocr_quarantine', 'quarantine']:
    p = REX / d
    if p.exists():
        files = sorted(p.iterdir())
        print(f'=== {d}/ ({len(files)} items) ===')
        for f in files[:20]:
            print(f'  {f.name} ({f.stat().st_size})')
        if len(files) > 20:
            print(f'  ... +{len(files)-20} more')

# review queue DB
db = REX / 'CC_rex_review.db'
if db.exists():
    con = sqlite3.connect(str(db))
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    print(f'\nCC_rex_review.db tables: {tables}')
    for t in tables:
        try:
            n = con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
            print(f'  {t}: {n} rows')
        except Exception as e:
            print(f'  {t}: err {e}')
    con.close()
