#!/usr/bin/env python3
"""Inspect a failed sign-in PDF: what does the text layer look like?"""
import fitz

d = fitz.open('/Users/mainsobhelper/Desktop/REX/signin_intake/doc00700820260731112335.pdf')
print(f'pages: {d.page_count}')
for i in range(min(2, d.page_count)):
    t = d[i].get_text()
    print(f'--- page {i+1} ({len(t)} chars) ---')
    print(t[:800])
d.close()
