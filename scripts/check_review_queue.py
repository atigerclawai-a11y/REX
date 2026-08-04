#!/usr/bin/env python3
"""Check the OCR review queue in goj_proprietary.db + garbled review PDF contents."""
import json
import sqlite3
from pathlib import Path

PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
con = sqlite3.connect(PROP)
con.row_factory = sqlite3.Row

# find review/queue tables
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print('goj_proprietary tables:', tables)

for t in tables:
    if 'review' in t.lower() or 'queue' in t.lower() or 'quarant' in t.lower():
        try:
            rows = con.execute(f'SELECT * FROM {t} LIMIT 3').fetchall()
            print(f'\n=== {t}: {len(rows)} sample rows ===')
            for r in rows:
                print(dict(r))
        except Exception as e:
            print(f'{t}: err {e}')
con.close()

# garbled PDF — how many pages?
import fitz
pdf = fitz.open('/Users/mainsobhelper/Desktop/REX/garbled_review/GOJ_garbled_names_review.pdf')
print(f'\nGOJ_garbled_names_review.pdf: {pdf.page_count} pages')
for i in range(min(3, pdf.page_count)):
    t = pdf[i].get_text()[:200].replace('\n', ' | ')
    print(f'  p{i+1}: {t}')
pdf.close()
