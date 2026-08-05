#!/usr/bin/env python3
"""Check clients.json (BASE_DIR/clients.json) — used to filter menu clients by active."""
import json
import os
from pathlib import Path

# The generator: BASE_DIR = Path(__file__).resolve().parent.parent = goj files/
BASE = Path('/Users/mainsobhelper/Documents/goj files')
clients_p = BASE / 'clients.json'
print(f'clients.json exists: {clients_p.exists()}')
if clients_p.exists():
    data = json.load(open(clients_p))
    n = len(data) if isinstance(data, list) else len(data.get('clients', data))
    print(f'clients: {n}')
    if isinstance(data, list) and data:
        print(f'  sample: {str(data[0])[:120]}')
    elif isinstance(data, dict):
        for k in list(data.keys())[:3]:
            print(f'  key {k}: {str(data[k])[:80]}')

# also check what the generator's reconciliation does with 0
print(f'\norders mtime: {os.path.getmtime(str(BASE / "data" / "GOJ_Menu_Orders.json"))}')
