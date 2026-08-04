#!/usr/bin/env python3
"""Kitchen sheets: dump full line list — find line 46 and check section totals vs client counts."""
import fitz
import os
import sqlite3

OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'

# client counts from auth
AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
con = sqlite3.connect(AUTH)
t_counts = {1: con.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_T_actual=1").fetchone()[0],
            2: con.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_T_actual=2").fetchone()[0]}
w_counts = {1: con.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_W_actual=1").fetchone()[0],
            2: con.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_W_actual=2").fetchone()[0]}
con.close()
print(f'client counts: Tue S1={t_counts[1]} S2={t_counts[2]} | Wed S1={w_counts[1]} S2={w_counts[2]}')

# menu rows with salad
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
p = sqlite3.connect(PROP)
for date, day in [('2026-08-04', 'T'), ('2026-08-05', 'W')]:
    for shift in ('1', '2'):
        total = p.execute("SELECT COUNT(*) FROM client_menus WHERE menu_date=? AND shift=? AND main!='' AND main NOT LIKE '%заказ не размещен%'", (date, shift)).fetchone()[0]
        with_salad = p.execute("SELECT COUNT(*) FROM client_menus WHERE menu_date=? AND shift=? AND salad!='' AND salad IS NOT NULL", (date, shift)).fetchone()[0]
        with_soup = p.execute("SELECT COUNT(*) FROM client_menus WHERE menu_date=? AND shift=? AND soup!='' AND soup IS NOT NULL", (date, shift)).fetchone()[0]
        print(f'  {date} S{shift}: rows={total} with_salad={with_salad} with_soup={with_soup}')
p.close()

print('\n=== kitchen sheet line 46 context ===')
for f in ['GOJ_T_S1_Tuesday_kitchen.pdf', 'GOJ_T_S2_Tuesday_kitchen.pdf',
          'GOJ_W_S1_Wednesday_kitchen.pdf', 'GOJ_W_S2_Wednesday_kitchen.pdf']:
    path = os.path.join(OUT, f)
    doc = fitz.open(path)
    lines = []
    for pg in doc:
        t = pg.get_text()
        for l in t.splitlines():
            l = l.strip()
            if l:
                lines.append(l)
    doc.close()
    print(f'\n--- {f} (line 46 = "{lines[45] if len(lines) > 45 else "N/A"}") ---')
    for i in range(38, min(56, len(lines))):
        print(f'  [{i+1}] {lines[i]}')
