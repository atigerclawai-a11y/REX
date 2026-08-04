#!/usr/bin/env python3
"""What processes touch auth_tracker.db? Find the zeroing writer + DB mtime."""
import os
import subprocess
from datetime import datetime

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
st = os.stat(AUTH)
print(f'auth DB mtime: {datetime.fromtimestamp(st.st_mtime).strftime("%m-%d %H:%M:%S")}')

# who's running that might write auth
r = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
for line in r.stdout.splitlines():
    if any(k in line for k in ['auth_tracker', 'carecenta', 'signin', 'sync', 'sweep', 'bridge']):
        parts = line.split(None, 10)
        if len(parts) > 10:
            print(f'  {parts[10][:90]}')
