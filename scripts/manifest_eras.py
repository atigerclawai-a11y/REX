#!/usr/bin/env python3
"""Which manifest docs are week-31 era (July 29+) vs older? The older ones are
week-30 forms (belong to Jul 27-31 dates, not this week)."""
import json
import os

mf = '/Users/mainsobhelper/Desktop/REX/.page_guard_recover.json'
docs = json.load(open(mf)) if os.path.exists(mf) else []

print('manifest docs by era:')
for d in docs:
    docname = d[0] if isinstance(d, (list, tuple)) else (d if isinstance(d, str) else d.get('doc', ''))
    # extract date from doc id: doc00680820260727160512 → 20260727
    import re
    m = re.search(r'(\d{8})', docname)
    date = m.group(1) if m else '????'
    era = 'W31 (Jul29+)' if date >= '20260729' else ('W30 (Jul27-28)' if date >= '20260727' else 'OLDER')
    print(f'  {docname[:26]}: {date} {era}')
