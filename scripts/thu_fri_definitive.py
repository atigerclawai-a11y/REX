#!/usr/bin/env python3
"""DEFINITIVE parse of the saved full Clients.aspx HTML (all 399 clients).
Matches BOTH time formats: '9AM-1PM ...' (S1) and '1:15PM-5:15PM ...' (S2),
same as the accepted Wednesday pipeline (assemble_wed.py).
Day5=Thu Aug6, Day6=Fri Aug7. Output per-day rosters with shift."""
import json
import re

html = open('/tmp/clients_full.html').read()

clients = []
for m in re.finditer(r'<span class="Last">([^<]+)</span>\s*,\s*<span class="First">([^<]+)</span>', html):
    last, first = m.group(1).strip(), m.group(2).strip()
    name = f'{last} {first}'
    start = m.start()
    row_start = html.rfind('<tr', 0, start)
    row_end = html.find('</tr>', start)
    if row_start == -1 or row_end == -1:
        continue
    row = html[row_start:row_end]
    days = {}
    for d in range(1, 8):
        cell = re.search(rf'class="Day{d}"[^>]*>(.*?)</td>', row, re.S)
        if cell:
            c = cell.group(1)
            # capture the apptime span content: e.g. '9AM-1PM VILLAGECAR' or '1:15PM-5:15PM ELDE'
            t = re.search(r'class="apptime">([^<]+)</span>', c)
            if t:
                days[d] = t.group(1).strip()
    clients.append({'name': name, 'days': days})

print(f'Total clients parsed: {len(clients)}')

def classify(time_str):
    t = (time_str or '').upper()
    if '9AM' in t or '10AM' in t or '8AM' in t or 'AM' in t:
        return 1  # S1 (morning)
    if '1:15PM' in t or 'PM' in t:
        return 2  # S2 (afternoon)
    return None

day_names = {1: 'SUN', 2: 'MON', 3: 'TUE', 4: 'WED', 5: 'THU', 6: 'FRI', 7: 'SAT'}
for d in [5, 6]:
    s1 = [c['name'] for c in clients if d in c['days'] and classify(c['days'][d]) == 1]
    s2 = [c['name'] for c in clients if d in c['days'] and classify(c['days'][d]) == 2]
    no_shift = [c['name'] for c in clients if d in c['days'] and classify(c['days'][d]) is None]
    print(f'\n=== {day_names[d]} Aug {"6" if d==5 else "7"} ===')
    print(f'  S1 (AM): {len(s1)}')
    print(f'  S2 (PM): {len(s2)}')
    print(f'  TOTAL: {len(s1)+len(s2)}  (unclassified: {len(no_shift)} {no_shift[:5]})')
    # sample times for sanity
    sample = [(c['name'], c['days'][d]) for c in clients if d in c['days']][:5]
    for n, t in sample:
        print(f'    {n}: {t}')

# save full rosters
out = {
    'thu': {'s1': sorted(set(c['name'] for c in clients if 5 in c['days'] and classify(c['days'][5])==1)),
            's2': sorted(set(c['name'] for c in clients if 5 in c['days'] and classify(c['days'][5])==2))},
    'fri': {'s1': sorted(set(c['name'] for c in clients if 6 in c['days'] and classify(c['days'][6])==1)),
            's2': sorted(set(c['name'] for c in clients if 6 in c['days'] and classify(c['days'][6])==2))},
}
json.dump(out, open('/tmp/thu_fri_definitive.json', 'w'), ensure_ascii=False, indent=1)
print('\nsaved /tmp/thu_fri_definitive.json')
