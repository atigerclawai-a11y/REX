#!/usr/bin/env python3
"""Worker ETA: count calls done vs needed, estimate finish time."""
import re
from pathlib import Path

BASE = Path('/Users/mainsobhelper/.hermes/profiles/work/cache/delegation/live')

jobs = {
    'deleg_5811a93d/task-0.log': 106,
    'deleg_5811a93d/task-1.log': 106,
    'deleg_5811a93d/task-2.log': 106,
    'deleg_e252661e/task-0.log': 80,
    'deleg_e252661e/task-1.log': 60,
}

total_done = 0
total_need = sum(jobs.values())
for f, need in jobs.items():
    p = BASE / f
    if not p.exists():
        print(f'{f}: NO LOG')
        continue
    txt = p.read_text(errors='ignore')
    done = txt.count('vision_analyze ok')
    total_done += done
    # rate: last calls timestamps
    times = re.findall(r'(\d{2}:\d{2}:\d{2}) result', txt)
    print(f'{f}: {done}/{need} calls ({100*done/need:.0f}%)')
print(f'\nTOTAL: {total_done}/{total_need} calls ({100*total_done/total_need:.0f}%)')
