#!/usr/bin/env python3
"""Test parser standalone (copy of the fixed function)."""
import re
from datetime import datetime

def parse_signin_md(md_text):
    date_match = re.search(r'Date:\s*([A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})', md_text)
    shift_match = re.search(r'Shift:\s*(\d)', md_text)
    dt = None
    if date_match:
        try:
            dt = datetime.strptime(date_match.group(1).strip(), "%A, %B %d, %Y").strftime("%Y-%m-%d")
        except ValueError:
            try:
                dt = datetime.strptime(date_match.group(1).strip(), "%A, %b %d, %Y").strftime("%Y-%m-%d")
            except ValueError:
                pass
    shift = shift_match.group(1) if shift_match else None
    names = []
    for row in re.finditer(r'<tr>(.*?)</tr>', md_text, re.S):
        tds = re.findall(r'<td[^>]*>(.*?)</td>', row.group(1), re.S)
        if len(tds) < 2:
            continue
        if tds[0].strip().lower() in ('no', 'n') or tds[1].strip().lower() == 'name':
            continue
        num = tds[0].strip()
        if not num.isdigit():
            continue
        name = re.sub(r'<[^>]+>', '', tds[1]).strip()
        if name and re.match(r'^[A-Za-zА-Яа-яЁё\'\- ]+$', name) and len(name.split()) >= 2:
            names.append(name)
    seen = set()
    uniq = []
    for n in names:
        if n not in seen:
            seen.add(n)
            uniq.append(n)
    return {"date": dt, "shift": shift, "names": uniq, "name_count": len(uniq)}

import glob
for md in sorted(glob.glob('/Users/mainsobhelper/Desktop/REX/signin_ocr_full/*/ocr/*.md')):
    txt = open(md, errors='ignore').read()
    parsed = parse_signin_md(txt)
    print(f'{md.split("/")[-2]}: date={parsed["date"]} shift={parsed["shift"]} names={parsed["name_count"]}')
    if parsed['names']:
        print(f'   first: {parsed["names"][:3]}')
        print(f'   last: {parsed["names"][-2:]}')
