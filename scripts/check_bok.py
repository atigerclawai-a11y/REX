#!/usr/bin/env python3
"""Check Bok Lyudmila: vision marks + current DB rows."""
import json
import sqlite3

# marks
for bf, mf in [('/tmp/w31_batch_1.json', '/tmp/w31_marks_1.json'),
               ('/tmp/w31_batch_2.json', '/tmp/w31_marks_2.json'),
               ('/tmp/w31_batch_3.json', '/tmp/w31_marks_3.json'),
               ('/tmp/w31_batch_4.json', '/tmp/w31_marks_4.json'),
               ('/tmp/w31_batch_5.json', '/tmp/w31_marks_5.json')]:
    try:
        batch = json.load(open(bf))
        marks = json.load(open(mf))
        for x in batch:
            if x.get('name') == 'Bok Lyudmila' or x.get('match') == 'Bok Lyudmila':
                print(f'marks in {mf.split("/")[-1]} n={x["n"]}: {json.dumps(marks.get(str(x["n"]), {}), ensure_ascii=False)[:300]}')
    except Exception:
        pass

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
print('\nDB rows this week:')
for r in p.execute("""SELECT menu_date, day_code, salad, soup, main, side, source_sheet
    FROM client_menus WHERE client_name='Bok Lyudmila'
    AND menu_date BETWEEN '2026-08-03' AND '2026-08-07' ORDER BY menu_date"""):
    print(f'  {r[0]} {r[1]}: {r[2]}|{r[3]}|{r[4]}|{r[5]} [{r[6]}]')
print('\nHistory:')
for r in p.execute("""SELECT menu_date, day_code, salad, soup, main, side, source_sheet
    FROM client_menus WHERE client_name='Bok Lyudmila' AND menu_date < '2026-08-03'
    ORDER BY menu_date DESC LIMIT 5"""):
    print(f'  {r[0]} {r[1]}: {r[2]}|{r[3]}|{r[4]}|{r[5]} [{r[6]}]')
p.close()
