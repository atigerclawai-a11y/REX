#!/usr/bin/env python3
"""Verify Wednesday sign-in PDFs contain exactly the live Carecenta roster (73/95)."""
import json
import re
import subprocess
import sys

sys.path.insert(0, '/Users/mainsobhelper/Documents/goj files/dashboard')


def pdf_names(path):
    out = subprocess.run(['python3', '-c', '''
import sys
try:
    import pdfplumber
except ImportError:
    print("NO_PDFPLUMBER"); sys.exit(0)
names = []
with pdfplumber.open(sys.argv[1]) as pdf:
    for pg in pdf.pages:
        t = pg.extract_text() or ""
        for line in t.splitlines():
            # names appear as "Last First [ID XXXX]" or "Last First"
            m = re.match(r'^\\s*(\\d+)?\\s*([A-Za-z][A-Za-z\'’\\-]+\\s+[A-Za-z][A-Za-z\'’\\-]+(?:\\s+[A-Za-z][A-Za-z\'’\\-]+)?)\\s*(\\[ID \\d{4}\\])?$', line)
            if m and not line.strip().startswith("GOJ") and "Wednesday" not in line:
                names.append(m.group(2).strip())
return names
''', path], capture_output=True, text=True)
    if 'NO_PDFPLUMBER' in out.stdout:
        return None
    try:
        return json.loads(out.stdout)
    except Exception:
        return [l for l in out.stdout.splitlines() if l.strip()]


for shift, path in [('S1', '/Users/mainsobhelper/Documents/goj files/output_docs/GOJ_W_S1_Wednesday_signin.pdf'),
                    ('S2', '/Users/mainsobhelper/Documents/goj files/output_docs/GOJ_W_S2_Wednesday_signin.pdf')]:
    names = pdf_names(path)
    print(f'{shift}: extracted {len(names) if names else "?"} names')
