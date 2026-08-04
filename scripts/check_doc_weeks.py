#!/usr/bin/env python3
"""Determine food week for each confirmed doc from MinerU md footer / existing DB rows."""
import json
import re
import sqlite3
from pathlib import Path

REX = Path('/Users/mainsobhelper/Desktop/REX')
docs = sorted(set(m['doc'] for m in json.load(open('/tmp/unreadable_full_manifest.json'))))

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
print(f"{'doc':<28}{'week_footer':<14}{'db_ocr_dates':<32}")
for d in docs:
    # footer from mineru md
    week = '?'
    md = REX / 'menu_ocr_full' / d / 'ocr' / f'{d}.md'
    if md.exists():
        txt = md.read_text(errors='ignore')[:2000]
        m = re.search(r'Week #?:?\s*(\d+)', txt)
        if m:
            week = m.group(1)
    # dates of ocr_scan rows this doc's clients have in DB
    dates = set()
    for r in p.execute("SELECT DISTINCT menu_date FROM client_menus WHERE source_sheet='ocr_scan' AND menu_date BETWEEN '2026-07-27' AND '2026-08-07'"):
        dates.add(r[0])
    print(f"{d:<28}{week:<14}{str(sorted(dates)[:3])}")
p.close()
