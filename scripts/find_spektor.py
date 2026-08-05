#!/usr/bin/env python3
"""Find Spektor/Nirsheberg in Carecenta authorizations export (xls or json)."""
import glob
import json
import os

# check the xls files
xls_files = sorted(glob.glob('/Users/mainsobhelper/goj/data/carecenta_authorizations_*.xls'),
                   key=os.path.getmtime, reverse=True)
print(f'xls files: {[os.path.basename(f) for f in xls_files[:4]]}')
js_files = sorted(glob.glob('/Users/mainsobhelper/goj/data/carecenta_authorizations_*.json'),
                  key=os.path.getmtime, reverse=True)
print(f'json files: {[os.path.basename(f) for f in js_files[:4]]}')

# try reading the newest xls with pandas
if xls_files:
    import pandas as pd
    newest = xls_files[0]
    print(f'\nreading {os.path.basename(newest)}...')
    try:
        df = pd.read_excel(newest)
        print(f'cols: {list(df.columns)[:10]}')
        mask = df.astype(str).apply(lambda r: r.str.contains('Spektor|Nirsheberg', case=False).any(), axis=1)
        hits = df[mask]
        print(f'rows: {len(hits)}')
        for _, row in hits.iterrows():
            print(f'  {dict(row)[:8] if isinstance(dict(row), dict) else row.tolist()[:8]}')
    except Exception as e:
        print(f'  xls read failed: {e}')

# try the JSON exports
for f in js_files[:2]:
    print(f'\n=== {os.path.basename(f)} ===')
    try:
        data = json.load(open(f))
        items = data if isinstance(data, list) else data.get('clients', data.get('data', []))
        for c in items:
            nm = str(c.get('name', c.get('client_name', c.get('Name', ''))))
            if 'Spektor' in nm or 'Nirsheberg' in nm:
                print(f'  {nm}: {str(c)[:250]}')
    except Exception as e:
        print(f'  err: {e}')
