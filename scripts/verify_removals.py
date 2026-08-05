#!/usr/bin/env python3
"""Verify removals: for each removed client, is there a Carecenta Thu roster
name with the SAME SURNAME (which would mean they DO attend, variant spelling)?"""
import json

thu = json.load(open('/tmp/thursday_live_full.json'))
roster = {n.lower(): n for n in thu}

removed = ['Aronchik Bronya', 'Astrakhan Bella', 'Breicher Larisa', 'Britavskaya Sofiya',
           'Brodskaya Lidiya', 'Buslayeva Alisa', 'Chebotareva Galina', 'Chepizhko Raya',
           'Chupikova Elvira', 'Coniglio Vera', 'Diadia Valentina', 'Dirul Serghei',
           'Dmitriyeva Tamara', 'Dodik Sima', 'Dovgalyuk Zelda', 'Dranikov Berta',
           'Drochik Oleg', 'Egorova Valentina', 'Elbert Milla', 'Erlikhman Rita',
           'Fedorova Olga', 'Feldman Klavdya', 'Firdman Mark', 'Fridman Mikhail',
           'Furman Vladimir']

print('=== removed clients: surname check against Carecenta Thu roster ===')
problems = []
for name in removed:
    sur = name.split()[0].lower()
    hits = [rn for rn in roster if rn.split()[0] == sur]
    if hits:
        print(f'  ⚠️ {name}: SAME SURNAME in roster: {hits} → MAYBE WRONGLY REMOVED')
        problems.append(name)
    else:
        print(f'  ✓ {name}: no surname match, removal OK')

print(f'\n{len(problems)} potential wrongful removals')
