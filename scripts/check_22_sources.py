#!/usr/bin/env python3
"""Check: are the 22 in the matched table (197) or the unreadable manifest (232)?
Their forms may have been confirmed but under a different name spelling."""
import json

names22 = ['Bolotin Marina', 'Dovgalyuk Zelda', 'Gamkrelidze Mikhail', 'Krayz Raisa',
           'Lazovskiy Lina', 'Lazovskiy Valeriy', 'Matanseva Ofelia', 'Mikhaylova Sofiya',
           'Minogina Ninel', 'Nikolaeva Galina', 'Safonov Anatoliy', 'Sekh Stefaniia',
           'Shadkhan Bella', 'Shkolnik Betya', 'Shteyman Faina', 'Shumaeva Anna',
           'Shvayko Nelli', 'Umanskaya Yelena', 'Volov Boris', 'Yermakov Marat',
           'Zabizhin Grigoriy', 'Zhelabovska Nadia']
surnames = {n.split()[0].lower() for n in names22}

# matched table
mt = json.load(open('/tmp/matched_table_final.json'))
print('matched table:')
for r in mt:
    nm = r.get('match', '')
    if nm.split() and nm.split()[0].lower() in surnames:
        print(f'  {nm} → n={r["n"]} doc={r["doc"][:20]} page={r["page"]}')

# unreadable manifest
um = json.load(open('/tmp/unreadable_full_manifest.json'))
print('\nunreadable manifest:')
for r in um:
    nm = r.get('name', '')
    if nm.split() and nm.split()[0].lower() in surnames:
        print(f'  {nm} → n={r.get("n")} doc={str(r.get("doc"))[:20]} page={r.get("page")}')
