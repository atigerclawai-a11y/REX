#!/usr/bin/env python3
"""Debug: check raw values at the 3 UNKNOWN rows in the final table."""
import json

rows = json.load(open('/tmp/matched_table_final.json'))
for r in rows:
    if not r['match']:
        print(f"new#{r['n']} orig-raw={r['raw']!r} doc={r['doc']} page={r['page']}")
# also find where Gukovskaja landed
for r in rows:
    if r['match'] and 'Gukovskaja' in r['match']:
        print(f"Gukovskaja at new#{r['n']} raw={r['raw']!r} doc={r['doc']} page={r['page']}")
for r in rows:
    if r['match'] and 'Uchitel Rozalia' in r['match']:
        print(f"Uchitel Rozalia at new#{r['n']} raw={r['raw']!r} doc={r['doc']} page={r['page']}")
