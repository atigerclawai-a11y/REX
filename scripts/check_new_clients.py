#!/usr/bin/env python3
"""Check Spektor/Nirsheberg/Zheliabovska in auth (any spelling) + canonical_ids."""
import sqlite3

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
print('=== auth search ===')
for frag in ['Spektor', 'Nirsheberg', 'Zheliabovska', 'Zheliabovskaya', 'Zhelabovska', 'Kormova']:
    rows = a.execute("SELECT name, active, client_id FROM clients WHERE name LIKE ?", (f'%{frag}%',)).fetchall()
    print(f'  {frag}: {rows}')

print('\n=== canonical_ids search ===')
for frag in ['Spektor', 'Nirsheberg', 'Zheliabovska', 'Kormova']:
    rows = a.execute("SELECT canonical_id, name FROM canonical_ids WHERE name LIKE ?", (f'%{frag}%',)).fetchall()
    print(f'  {frag}: {rows}')

# what does the Carecenta full export say about them?
import glob, json, os
for f in sorted(glob.glob('/Users/mainsobhelper/goj/data/carecenta_authorizations_*.json'))[-3:]:
    print(f'\n{os.path.basename(f)}:')
    try:
        data = json.load(open(f))
        clients = data if isinstance(data, list) else data.get('clients', data.get('data', []))
        for c in clients:
            nm = c.get('name', c.get('client_name', ''))
            if any(x in nm for x in ['Spektor', 'Nirsheberg', 'Zheliabovska', 'Kormova']):
                print(f'  {nm}: {json.dumps(c, ensure_ascii=False)[:200]}')
    except Exception as e:
        print(f'  err {e}')
a.close()
