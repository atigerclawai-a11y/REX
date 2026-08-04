#!/usr/bin/env python3
"""Full diagnostic verification: kitchen sections clean, garbage, parity, coverage."""
import sqlite3
import subprocess
import fitz
import os
from datetime import datetime

OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'

print('=== KITCHEN SECTIONS (soups in SALADS check) ===')
for f in ['GOJ_T_S1_Tuesday_kitchen.pdf', 'GOJ_T_S2_Tuesday_kitchen.pdf',
          'GOJ_W_S1_Wednesday_kitchen.pdf', 'GOJ_W_S2_Wednesday_kitchen.pdf']:
    p = os.path.join(OUT, f)
    if not os.path.exists(p):
        print(f'  {f}: MISSING')
        continue
    mt = datetime.fromtimestamp(os.stat(p).st_mtime).strftime('%H:%M:%S')
    doc = fitz.open(p)
    txt = doc[0].get_text()
    # find SALADS section content
    salad_block = ''
    in_salads = False
    for line in txt.splitlines():
        if 'САЛАТЫ' in line.upper() or 'SALADS' in line.upper():
            in_salads = True
            continue
        if in_salads and ('СУПЫ' in line.upper() or 'SOUPS' in line.upper()):
            break
        if in_salads:
            salad_block += line + ' '
    # check for soup names in salad block
    soup_words = ['Борщ', 'Суп', 'Харчо', 'Гороховый', 'Куриный суп']
    bad = [w for w in soup_words if w in salad_block]
    doc.close()
    status = '❌ LEAK' if bad else '✅ clean'
    print(f'  {f} ({mt}): {status}')

print('\n=== GARBAGE ===')
r = subprocess.run(['python3', 'scripts/find_garbage_dishes.py'], capture_output=True, text=True,
                   cwd='/Users/mainsobhelper/Desktop/REX',
                   env={'PATH': '/Users/mainsobhelper/.rex-venv/bin:/usr/bin:/bin'})
for line in r.stdout.splitlines():
    if 'non-canonical' in line:
        print(f'  {line.strip()}')

print('\n=== PARITY (week 31, per source) ===')
for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    rows = con.execute("""SELECT source_sheet, COUNT(*) FROM client_menus
        WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07' GROUP BY 1 ORDER BY 2 DESC""").fetchall()
    print(f'  {db.split("/")[-1]}: {rows}')
    con.close()
