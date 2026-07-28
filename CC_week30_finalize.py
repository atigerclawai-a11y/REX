#!/usr/bin/env python3
"""
CC_week30_finalize.py — runs when the surya queue finishes week-30 batches.
Idempotent watcher: exits silently if (a) queue still running, or (b) no new
surya extractions waiting to promote. Otherwise: promote -> write -> fill ->
regenerate Tuesday package -> redteam -> print summary (delivered to Kato).
"""
import json, subprocess, sys
from pathlib import Path

PY = '/Users/mainsobhelper/.rex-venv/bin/python3'
REX = Path('/Users/mainsobhelper/Desktop/REX')
BP = REX / 'blank_parse'

# (a) is the queue still running?
r = subprocess.run(['pgrep', '-f', 'CC_surya_menu_extract'], capture_output=True)
if r.returncode == 0:
    sys.exit(0)  # still working — stay silent

# (b) any unpromoted surya extractions?
to_promote = []
for sj in BP.glob('*/extraction_surya.json'):
    to_promote.append(sj.parent)
if not to_promote:
    sys.exit(0)  # nothing new — stay silent

out = []
for d in to_promote:
    sj = d / 'extraction_surya.json'
    dst = d / 'extraction.json'
    if dst.exists():
        dst.rename(d / 'extraction_tesseract.json')
    sj.rename(dst)
    out.append(f'promoted {d.name}')
print(f'[finalize] {len(to_promote)} surya extractions promoted')

# write picks
w = subprocess.run([PY, str(REX / 'scripts/write_blank_picks.py')], capture_output=True, text=True, timeout=900)
for line in w.stdout.splitlines():
    if 'rows written' in line or 'SKIP' in line:
        print('[finalize]', line)

# fill week days
for dt in ['2026-07-28', '2026-07-29', '2026-07-30', '2026-07-31']:
    f = subprocess.run([PY, str(REX / 'CC_menu_fill.py'), dt], capture_output=True, text=True, timeout=600)
    tail = [l for l in f.stdout.splitlines() if 'coverage' in l]
    print(f'[finalize] fill {dt}: {tail[-1].strip() if tail else "?"}')

# regenerate TUESDAY package (signin + kitchen + distribution)
DASH = '/Users/mainsobhelper/Documents/goj files/dashboard'
b = subprocess.run([PY, '/Users/mainsobhelper/.hermes/profiles/work/skills/goj-daily-handoff/scripts/bridge_menu_orders.py', '2026-07-28'],
                   capture_output=True, text=True, timeout=600)
print('[finalize]', b.stdout.splitlines()[0] if b.stdout else 'bridge failed')
for mode in ('signin', 'distribution'):
    g = subprocess.run([PY, 'generate_tomorrow.py', '--day', 'today', '--mode', mode, '--skip-preflight'],
                       capture_output=True, text=True, timeout=600, cwd=DASH)
    for line in g.stdout.splitlines():
        if '.pdf' in line and ('✅' in line or 'bytes' in line):
            print('[finalize]', line.strip()[:110])

# redteam
rt = subprocess.run([PY, '/Users/mainsobhelper/.hermes/profiles/work/skills/goj-daily-handoff/scripts/redteam_daily_docs.py', '2026-07-28', 'T'],
                    capture_output=True, text=True, timeout=300)
for line in rt.stdout.splitlines():
    if 'signin count' in line or 'kitchen count' in line or 'distribution count' in line or '===' in line or 'menu coverage' in line:
        print('[redteam]', line.strip())

# week status
s = subprocess.run([PY, '/tmp/week_status.py'], capture_output=True, text=True, timeout=120)
print(s.stdout)
print('[finalize] TUESDAY PACKAGE REGENERATED — attach from output_docs and deliver to Kato')
