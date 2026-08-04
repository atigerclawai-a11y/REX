#!/usr/bin/env python3
"""Full dump of client #46 in each distribution sheet + their DB plates."""
import fitz
import os
import sqlite3

OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'

# DB plates for the #46 clients found earlier
p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
p.row_factory = sqlite3.Row
for date, name in [('2026-08-04', 'Mikhaylova Sofiya'), ('2026-08-04', 'Tsiklauri Donara'),
                   ('2026-08-05', 'Nikonovych Halyna'), ('2026-08-05', 'Kushnir Isaak')]:
    rows = p.execute("SELECT * FROM client_menus WHERE menu_date=? AND client_name=?", (date, name)).fetchall()
    print(f'DB {date} {name}:')
    for r in rows:
        print(f"  S{r['shift']} [{r['source_sheet']}]: salad={r['salad']!r} soup={r['soup']!r} main={r['main']!r} side={r['side']!r}")
p.close()

# distribution sheet entries — full text around each #46
print('\n=== distribution sheet #46 entries (full) ===')
for f, want in [('GOJ_W_S1_Wednesday_distribution.pdf', 'Nikonovych'),
                ('GOJ_W_S2_Wednesday_distribution.pdf', 'Kushnir'),
                ('GOJ_T_S1_Tuesday_distribution.pdf', 'Mikhaylova'),
                ('GOJ_T_S2_Tuesday_distribution.pdf', 'Tsiklauri')]:
    path = os.path.join(OUT, f)
    doc = fitz.open(path)
    lines = []
    for pg in doc:
        for l in pg.get_text().splitlines():
            l = l.strip()
            if l:
                lines.append(l)
    doc.close()
    for i, l in enumerate(lines):
        if want.lower() in l.lower():
            print(f'--- {f} @line {i+1} ---')
            for j in range(max(0, i - 1), min(len(lines), i + 7)):
                print(f'  [{j+1}] {lines[j]}')
