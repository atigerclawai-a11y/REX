#!/usr/bin/env python3
"""Trace batch-4 apply: Shefer Bella (#1 in matched table), Uchitel Vilyam, Shklovsky Gita."""
import json
import sqlite3

# matched table rows for these clients
mt = json.load(open('/tmp/matched_table_final.json'))
for want in ['Shefer Bella', 'Uchitel Vilyam', 'Shklovsky Gita', 'Khashimova Zukhra']:
    for r in mt:
        if r['match'] == want:
            print(f'{want}: table# n={r["n"]} doc={r["doc"]} page={r["page"]}')
            # find marks in batch files
            for bf, mf in [('/tmp/w31_batch_4.json', '/tmp/w31_marks_4.json'),
                           ('/tmp/w31_forms.json', '/tmp/w31_marks_1.json')]:
                try:
                    batch = json.load(open(bf))
                    marks = json.load(open(mf))
                except Exception:
                    continue
                for b in batch:
                    if b.get('match') == want or b.get('name') == want:
                        n = str(b['n'])
                        print(f'  batch {bf.split("/")[-1]} n={n}: marks={json.dumps(marks.get(n, {}), ensure_ascii=False)[:150]}')
                break
            break

# search DB for any spelling of these names
p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
for frag in ['Shefer', 'Uchitel', 'Shklovsky', 'Khashimova']:
    rows = p.execute("""SELECT DISTINCT client_name FROM client_menus WHERE client_name LIKE ?""",
                     (f'%{frag}%',)).fetchall()
    print(f'\nDB names containing {frag}: {[r[0] for r in rows]}')
p.close()
