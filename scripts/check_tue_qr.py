#!/usr/bin/env python3
"""Spot-check QR on the new Tuesday menu PDFs (page 2 of S1, page 2 of S2)."""
import fitz
import os

OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'
for f, pg in [('Menus_Tue_Aug04_S1_LIVE.pdf', 2), ('Menus_Tue_Aug04_S2_LIVE.pdf', 2)]:
    p = os.path.join(OUT, f)
    doc = fitz.open(p)
    page = doc[pg - 1]
    pix = page.get_pixmap(dpi=200)
    out_png = f'/tmp/{f.replace(".pdf", "")}_p{pg}.png'
    pix.save(out_png)
    print(f'{f} page {pg} → {out_png} ({pix.width}x{pix.height})')
    doc.close()
