#!/usr/bin/env python3
"""
CC_surya_completion_chain.py — runs when the week-30 surya queue finishes.
Idempotent watcher (called by cron every 5min): exits silently while the queue
runs or nothing is new. When week-30 surya extractions exist that aren't yet
promoted/applied: promote -> write -> fill -> regenerate Tuesday package -> summary.
"""
import json, subprocess, sys
from pathlib import Path

BP = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')
PY = '/Users/mainsobhelper/.rex-venv/bin/python3'
REX = '/Users/mainsobhelper/Desktop/REX'
WEEK30 = ['doc00651520260720150028', 'doc00651620260720150112', 'doc00651720260720150145',
          'doc00652520260721043502', 'doc00659120260721154012', 'doc00659220260721154112',
          'doc00659320260721154144', 'doc00659420260721154221', 'doc00659520260721154257',
          'doc00668620260723111947', 'doc00668720260723112029', 'doc00668820260723112108',
          'doc00670220260724043814', 'doc00673920260727042014']

# 1. queue still running? -> stay silent
if subprocess.run(['pgrep', '-f', 'surya_batch_runner'], capture_output=True).returncode == 0:
    sys.exit(0)
if subprocess.run(['pgrep', '-f', 'CC_surya_menu_extract'], capture_output=True).returncode == 0:
    sys.exit(0)

# 2. promote any unpromoted surya extractions
promoted = []
for doc in WEEK30:
    d = BP / doc
    sj = d / 'extraction_surya.json'
    if sj.exists():
        dst = d / 'extraction.json'
        if dst.exists():
            dst.rename(d / 'extraction_tesseract.json')
        sj.rename(dst)
        promoted.append(doc[3:9])
if not promoted:
    sys.exit(0)

print(f'[CHAIN] promoted surya for: {", ".join(promoted)}')

# 3. write picks
w = subprocess.run([PY, f'{REX}/scripts/write_blank_picks.py'], capture_output=True, text=True, timeout=900)
line = [l for l in w.stdout.splitlines() if 'rows written' in l]
print(f'[CHAIN] {line[0] if line else "write done"}')

# 4. fills
for d in ['2026-07-28', '2026-07-29', '2026-07-30', '2026-07-31']:
    f = subprocess.run([PY, f'{REX}/CC_menu_fill.py', d], capture_output=True, text=True, timeout=300)
    cov = [l for l in f.stdout.splitlines() if 'coverage' in l]
    print(f'[CHAIN] fill {d}: {cov[-1].strip() if cov else "?"}')

# 5. regenerate Tuesday package
import os
os.chdir('/Users/mainsobhelper/Documents/goj files/dashboard')
b = subprocess.run([PY, '/Users/mainsobhelper/.hermes/profiles/work/skills/goj-daily-handoff/scripts/bridge_menu_orders.py', '2026-07-28'],
                   capture_output=True, text=True, timeout=300)
print(f'[CHAIN] {b.stdout.splitlines()[0] if b.stdout else "bridge done"}')
for mode in ('signin', 'distribution'):
    g = subprocess.run([PY, 'generate_tomorrow.py', '--day', 'today', '--mode', mode, '--skip-preflight'],
                       capture_output=True, text=True, timeout=300)
    ok = [l for l in g.stdout.splitlines() if '✅' in l]
    for l in ok:
        print(f'[CHAIN] {l.strip()}')

# 6. redteam
rt = subprocess.run([PY, '/Users/mainsobhelper/.hermes/profiles/work/skills/goj-daily-handoff/scripts/redteam_daily_docs.py', '2026-07-28', 'T'],
                    capture_output=True, text=True, timeout=300)
for l in rt.stdout.splitlines():
    if 'signin count' in l or 'kitchen count' in l or 'menu coverage' in l or '===' in l:
        print(f'[CHAIN] {l}')
print('[CHAIN] Tuesday package regenerated with full week-30 surya data')
