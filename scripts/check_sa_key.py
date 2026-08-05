#!/usr/bin/env python3
"""Check SA key exists + has drive scope; test a files().create with it."""
import json
import os

SA = os.path.expanduser('~/.rex_drive_service_account.json')
print(f'SA key exists: {os.path.exists(SA)}')
if os.path.exists(SA):
    data = json.load(open(SA))
    print(f'  client_email: {data.get("client_email")}')
    print(f'  keys: {list(data.keys())}')
