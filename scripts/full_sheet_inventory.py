#!/usr/bin/env python3
"""Full week-31 sheet inventory + Monday actuals check."""
import os
from datetime import datetime

OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'
print('=== ALL GOJ_* PDFs with mtime ===')
for f in sorted(os.listdir(OUT)):
    if f.endswith('.pdf'):
        p = os.path.join(OUT, f)
        mt = datetime.fromtimestamp(os.path.getmtime(p)).strftime('%m-%d %H:%M')
        print(f'  {mt}  {f}')
