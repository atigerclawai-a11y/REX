#!/usr/bin/env python3
"""Check the 4 leaking clients: their forms/vision marks + history."""
import json
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
p.row_factory = sqlite3.Row

for name in ['Shuper Klavdia', 'Khalfin Inna', 'Matanseva Ofelia', 'Minogina Ninel']:
    print(f'\n===== {name} =====')
    # vision marks if in batches
    for bf in ['/tmp/w31_forms.json', '/tmp/w31_batch_4.json', '/tmp/w31_batch_5.json']:
        try:
            batch = json.load(open(bf))
        except Exception:
            continue
        for b in batch:
            if b.get('name') == name or b.get('match') == name:
                n = str(b['n'])
                for mf in ['/tmp/w31_marks_1.json', '/tmp/w31_marks_2.json', '/tmp/w31_marks_3.json',
                           '/tmp/w31_marks_4.json', '/tmp/w31_marks_5.json']:
                    try:
                        m = json.load(open(mf))
                        if n in m:
                            print(f'  vision marks: {json.dumps(m[n], ensure_ascii=False)[:400]}')
                    except Exception:
                        pass
    # rows this week
    for r in p.execute("""SELECT menu_date, day_code, salad, soup, main, side, source_sheet
        FROM client_menus WHERE client_name=? AND menu_date BETWEEN '2026-08-03' AND '2026-08-07'
        ORDER BY menu_date""", (name,)):
        print(f"  DB {r['menu_date']} {r['day_code']}: {r['salad']}|{r['soup']}|{r['main']}|{r['side']} [{r['source_sheet']}]")
    # recent history
    for r in p.execute("""SELECT menu_date, day_code, salad, soup, main, side, source_sheet
        FROM client_menus WHERE client_name=? AND menu_date < '2026-08-03'
        ORDER BY menu_date DESC LIMIT 4""", (name,)):
        print(f"  HIST {r['menu_date']} {r['day_code']}: {r['salad']}|{r['soup']}|{r['main']}|{r['side']} [{r['source_sheet']}]")
p.close()
