#!/usr/bin/env python3
"""Verify contact sheet renders + check Sorits Lev review item."""
import fitz

d = fitz.open('/Users/mainsobhelper/Desktop/REX/unreadable_34/UNREADABLE_CONTACT_SHEET.pdf')
print(f'pages: {d.page_count}')
t = d[0].get_text()
print(f'page1 (index) text head: {t[:150]!r}')
# check page 2 has thumbnails (images)
p2 = d[1]
imgs = p2.get_images()
print(f'page2 images: {len(imgs)}')
d.close()
