#!/usr/bin/env python3
"""Chupikova Elvira: check her vision marks + full DB history for a main."""
import json
import sqlite3

# vision marks
for f in ['/tmp/w31_marks_4.json', '/tmp/w31_marks_5.json', '/tmp/w31_marks_1.json']:
    try:
        d = json.load(open(f))
        for k, v in d.items():
            # find by checking batch 5 names
            pass
    except Exception:
        pass

batch = json.load(open('/tmp/w31_batch_5.json'))
for b in batch:
    if b['name'] == 'Chupikova Elvira':
        print(f'batch5 form n={b["n"]} doc={b["doc"]} page={b["page"]}')
        m5 = json.load(open('/tmp/w31_marks_5.json'))
        print('marks:', json.dumps(m5.get(str(b['n']), {}), ensure_ascii=False))

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
print('\nfull history:')
for r in p.execute("""SELECT menu_date, day_code, salad, soup, main, side, source_sheet
    FROM client_menus WHERE client_name='Chupikova Elvira'
    ORDER BY menu_date DESC LIMIT 8"""):
    print(f"  {r[0]} {r[1]}: {r[2]}|{r[3]}|{r[4]}|{r[5]} [{r[6]}]")
p.close()
