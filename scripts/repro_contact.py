#!/usr/bin/env python3
"""Minimal repro: which call fails?"""
import fitz
import json
import os

FONT = '/Users/mainsobhelper/Documents/goj files/fonts/DejaVuSans.ttf'
print('font exists:', os.path.exists(FONT))

try:
    idx = fitz.open()
    ipage = idx.new_page(width=612, height=792)
    ipage.insert_text((40, 40), "TEST", fontsize=14, fontname="helv-bold")
    print('index insert OK')
except Exception as e:
    print(f'INDEX FAIL: {e}')

try:
    contact = fitz.open()
    contact.insert_pdf(idx)
    print('insert_pdf OK')
except Exception as e:
    print(f'INSERT_PDF FAIL: {e}')

try:
    d = fitz.open('/Users/mainsobhelper/Desktop/REX/menu_intake_stable/doc00688020260729073901.pdf')
    print('doc open OK, pages:', d.page_count)
    fp = d[0].get_pixmap(matrix=fitz.Matrix(0.7, 0.7))
    fp.save('/tmp/contact_test.png')
    print('pixmap OK')
    page = contact.new_page(width=792, height=612)
    page.insert_image(fitz.Rect(20, 20, 380, 200), filename='/tmp/contact_test.png')
    print('insert_image OK')
    d.close()
except Exception as e:
    print(f'DOC FAIL: {e}')
