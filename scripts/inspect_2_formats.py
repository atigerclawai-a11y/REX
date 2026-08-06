#!/usr/bin/env python3
"""Inspect doc006889 + doc006891 formats for date/shift extraction."""
import re

for doc in ['doc00688920260729104631', 'doc00689120260729104710']:
    md = f'/Users/mainsobhelper/Desktop/REX/signin_ocr_full/{doc}/ocr/{doc}.md'
    txt = open(md, errors='ignore').read()
    print(f'=== {doc} ({len(txt)} chars) ===')
    # find date-like text
    dates = re.findall(r'[A-Za-z]+day,? [A-Za-z]+ \d{1,2},? \d{4}|[A-Za-z]+day,? \d{1,2}?|Date[:\s]*', txt)
    print(f'  date-ish matches: {dates[:5]}')
    # look for shift indicators
    shifts = re.findall(r'shift\s*[:\s]*(\d)|(\d)(?:st|nd|rd|th)\s*shift', txt, re.I)
    print(f'  shift-ish: {shifts[:5]}')
    # first 300 chars of table area
    print(f'  head 300: {txt[:300]!r}')
    print()
