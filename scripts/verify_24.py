#!/usr/bin/env python3
"""Verify the 24: are they in Carecenta under ANY spelling (surname match)?
Or truly absent from Thursday?"""
import difflib
import json

cc = json.load(open('/tmp/thursday_live_full.json'))
cc_set = {n.lower() for n in cc}
cc_all_names = sorted(cc_set)

targets = ['Aronchik Bronya', 'Astrakhan Bella', 'Breicher Larisa', 'Britavskaya Sofiya',
           'Brodskaya Lidiya', 'Buslayeva Alisa', 'Chebotareva Galina', 'Chepizhko Raya',
           'Chupikova Elvira', 'Coniglio Vera', 'Diadia Valentina', 'Dirul Serghei',
           'Dmitriyeva Tamara', 'Dodik Sima', 'Dovgalyuk Zelda', 'Dranikov Berta',
           'Drochik Oleg', 'Elbert Milla', 'Erlikhman Rita', 'Fedorova Olga',
           'Feldman Klavdya', 'Firdman Mark', 'Fridman Mikhail', 'Furman Vladimir']

for t in targets:
    low = t.lower()
    sur = low.split()[0]
    # surname matches in Carecenta Thursday
    sur_hits = [n for n in cc_set if n.split()[0] == sur]
    # fuzzy over whole name
    best, br = None, 0
    for c in cc_set:
        r = difflib.SequenceMatcher(None, low, c).ratio()
        if r > br:
            best, br = c, r
    if sur_hits or br >= 0.85:
        print(f'  {t}: surname={sur_hits or "NONE"} fuzzy={best}({br:.2f})')
    else:
        print(f'  ⚠️ {t}: NOT in Carecenta Thursday at all (best fuzzy {best} {br:.2f})')
