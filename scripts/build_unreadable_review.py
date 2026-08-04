#!/usr/bin/env python3
"""Build unreadable-forms review PDF: crop name region of each unreadable form,
number them, one per page, ready for Kato to identify."""
import os
from pathlib import Path
from PIL import Image
import fitz

REX = Path('/Users/mainsobhelper/Desktop/REX')
BASE = REX / 'blank_parse'
OUTDIR = REX / 'garbled_review'
OUTDIR.mkdir(exist_ok=True)

targets = [
    ('doc00680820260727160512', [7, 15, 17, 19, 23, 25, 35, 41, 43]),
    ('doc00680920260727160541', [1, 3, 9, 11, 13, 17, 21, 23, 25, 27, 33]),
    ('doc00681120260727160643', [1, 3, 5, 7, 9, 13, 15, 19, 21, 27]),
]

items = []
idx = 0
for doc, pages in targets:
    d = BASE / doc
    for p in pages:
        idx += 1
        # use source PDF for a fresh high-dpi render of the name region
        src_pdf = None
        for base in (REX / 'menu_intake_stable', Path('/Users/mainsobhelper/Documents/goj files/scans/ocr_processed'), Path('/tmp/ocr_done_all'), REX):
            hits = list(base.glob(f'*{doc}*.pdf'))
            if hits:
                src_pdf = hits[0]
                break
        if src_pdf is None:
            print(f'MISSING PDF for {doc} p{p}')
            continue
        pdf = fitz.open(str(src_pdf))
        page = pdf.load_page(p - 1)
        r = page.rect
        # name region: top 24% (Имя: line)
        clip = fitz.Rect(r.x0 + 20, r.y0 + 10, r.x1 - 20, r.y0 + r.height * 0.24)
        pix = page.get_pixmap(dpi=200, clip=clip)
        fn = OUTDIR / f'UNREAD_{idx:02d}_{doc}_p{p}.png'
        pix.save(str(fn))
        pdf.close()
        items.append({'idx': idx, 'doc': doc, 'page': p, 'image': str(fn)})
        print(f'  [{idx:02d}] {doc} p{p} → {fn.name}')

# build review PDF — name region image + label
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader

OUT_PDF = OUTDIR / 'GOJ_unreadable_forms_review_JUL27-28.pdf'
c = rl_canvas.Canvas(str(OUT_PDF), pagesize=letter)
W, H = letter
for it in items:
    img = ImageReader(it['image'])
    iw, ih = img.getSize()
    # fit image to page with margin, keep aspect
    scale = min((W - 80) / iw, (H - 140) / ih)
    dw, dh = iw * scale, ih * scale
    x = (W - dw) / 2
    y = H - 90 - dh
    c.drawImage(img, x, y, dw, dh)
    c.setFont('Helvetica-Bold', 12)
    c.drawString(40, H - 50, f"#{it['idx']}  —  {it['doc']}  page {it['page']}")
    c.drawString(40, H - 68, 'BEST GUESS: ___  (Kato: write the client name)')
    c.showPage()
c.save()
print(f'\nREVIEW PDF: {OUT_PDF} ({len(items)} forms)')
