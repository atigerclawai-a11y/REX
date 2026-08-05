#!/usr/bin/env python3
"""Check: does the 2.88MB full HTML contain ALL auth-active clients?
Count name spans in HTML vs auth active count. If HTML has fewer, the
scrape is missing clients → the 149 may be an undercount."""
import re
import sqlite3

html = open('/tmp/clients_full.html').read()
last_spans = re.findall(r'<span class="Last">([^<]+)</span>', html)
print(f'Last spans in full HTML: {len(last_spans)}')

# unique client names in HTML
names_in_html = set()
for m in re.finditer(r'<span class="Last">([^<]+)</span>\s*,\s*<span class="First">([^<]+)</span>', html):
    names_in_html.add((m.group(1).strip().lower(), m.group(2).strip().lower()))
print(f'unique name pairs in HTML: {len(names_in_html)}')

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
auth_active = a.execute("SELECT name FROM clients WHERE active=1").fetchall()
print(f'auth active: {len(auth_active)}')

# auth clients NOT in HTML at all
not_in_html = []
for (name,) in auth_active:
    parts = name.strip().lower().split()
    if not parts:
        continue
    found = any(ln == parts[0] and fn == parts[-1] for ln, fn in names_in_html)
    if not found:
        # try last name only
        found = any(ln == parts[0] for ln, fn in names_in_html)
    if not found:
        not_in_html.append(name)
print(f'auth active NOT in HTML ({len(not_in_html)}):')
for n in not_in_html[:40]:
    print(f'  {n}')
a.close()
