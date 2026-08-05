#!/usr/bin/env python3
"""Show exact 9 garbage cells (find_garbage_dishes output) + fix Minogina W."""
import subprocess

r = subprocess.run(['python3', '/Users/mainsobhelper/Desktop/REX/scripts/find_garbage_dishes.py'],
                   capture_output=True, text=True, cwd='/Users/mainsobhelper/Desktop/REX',
                   env={'PATH': '/Users/mainsobhelper/.rex-venv/bin:/usr/bin:/bin'})
print(r.stdout[-2500:])
