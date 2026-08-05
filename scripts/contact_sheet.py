#!/usr/bin/env python3
"""Create a CONTACT SHEET: one PDF page per doc (first page, scaled) + number label.
Plus a numbered INDEX page. This lets Kato identify each doc quickly."""
import fitz
import json
import os

docs = json.load(open('/tmp/manifest_34.json'))
links = json.load(open('/tmp/manifest_34_links.json'))

OUT = '/Users/mainsobhelper/Desktop/REX/unreadable_34'
contact = fitz.open()

# Index page
idx = fitz.open()
ipage = idx.new_page(width=612, height=792)
y = 40
ipage.insert_text((40, y), "GOJ UNREADABLE DOCS — INDEX (34 docs) — reply with # + what it is", fontsize=14, fontname="helv-bold")
y += 20
for n, doc, pages, link, dst in links:
    ipage.insert_text((40, y), f"#{n:02d}  {doc}  ({pages}pp)", fontsize=9)
    y += 13
    if y > 770:
        y = 40
contact.insert_pdf(idx)

# Contact pages: 6 per page
per_page = 6
for i in range(0, len(docs), per_page):
    page = contact.new_page(width=792, height=612)
    batch = docs[i:i+per_page]
    for j, (docname, pages, path) in enumerate(batch):
        n = i + j + 1
        x = 20 + (j % 2) * 400
        y = 20 + (j // 2) * 200
        page.insert_text((x, y), f"#{n:02d} {docname} ({pages}pp)", fontsize=11, fontname="helv-bold")
        try:
            d = fitz.open(path)
            fp = d[0].get_pixmap(matrix=fitz.Matrix(0.7, 0.7))
            img_path = f'/tmp/contact_{n}.png'
            fp.save(img_path)
            page.insert_image(fitz.Rect(x, y+8, x+360, y+180), filename=img_path)
            d.close()
        except Exception as e:
            page.insert_text((x, y+50), f'(render fail: {e})', fontsize=8)

contact.save(f'{OUT}/UNREADABLE_CONTACT_SHEET.pdf')
print(f'contact sheet saved: {OUT}/UNREADABLE_CONTACT_SHEET.pdf ({contact.page_count} pages)')
