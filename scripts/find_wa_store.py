#!/usr/bin/env python3
"""Find the WhatsApp bridge message store + check Polyak/Kravets handling."""
import json
import os
import glob

# look for the bridge DB or JSON store
candidates = [
    os.path.expanduser('~/.whatsapp_bridge'),
    '/tmp/whatsapp_bridge',
    '/Users/mainsobhelper/Desktop/REX/whatsapp_bridge',
    '/Users/mainsobhelper/Documents/goj files/data/whatsapp',
]
for d in candidates:
    if os.path.isdir(d):
        print(f'\n=== {d} ===')
        for f in sorted(os.listdir(d))[-12:]:
            print(f'  {f}')

# check for a messages db/json anywhere recent
for pat in ['/tmp/whatsapp*.json', '/tmp/*whatsapp*.json', '/tmp/wa_*.json']:
    for f in glob.glob(pat):
        print(f'glob: {f}')
