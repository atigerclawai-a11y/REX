#!/usr/bin/env python3
"""Check whatsapp bridge intel log + detector state for day-change messages."""
import json
import os

INTEL = '/Users/mainsobhelper/.whatsapp_bridge/intel_log.jsonl'
if os.path.exists(INTEL):
    lines = open(INTEL, errors='ignore').read().splitlines()
    print(f'intel_log: {len(lines)} entries')
    # last 20 entries
    for l in lines[-25:]:
        try:
            e = json.loads(l)
            ts = e.get('ts', e.get('timestamp', ''))[:16]
            txt = str(e.get('text', e.get('body', e.get('message', ''))))[:160]
            chat = e.get('chat', e.get('group', ''))[:30]
            print(f'  [{ts}] {chat}: {txt}')
        except Exception:
            print(f'  RAW: {l[:160]}')

# detector state
st = '/Users/mainsobhelper/.whatsapp_bridge/detector_state.json'
if os.path.exists(st):
    print(f'\ndetector_state: {open(st).read()[:400]}')
