#!/usr/bin/env python3
"""Check Carecenta day mapping against known truths: Tue should be ~139, Wed ~169."""
import json

cc = json.load(open('/tmp/carecenta_clients_week.json'))
day_counts = {}
for name, days in cc:
    for d in days:
        day_counts[d] = day_counts.get(d, 0) + 1
print('Carecenta day counts (Day1-7):')
for d in sorted(day_counts):
    print(f'  Day{d}: {day_counts[d]}')

# expected: Mon ~164, Tue 136-139, Wed ~168, Thu ~165, Fri ~169
# Day1=Aug2(Sun), Day2=Aug3(Mon), Day3=Aug4(Tue), Day4=Aug5(Wed), Day5=Aug6(Thu), Day6=Aug7(Fri), Day7=Aug8(Sat)
