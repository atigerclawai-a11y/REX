#!/usr/bin/env python3
"""Rebuild review PDF with best-guess names printed on each page."""
import json
from pathlib import Path
from PIL import Image
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader

results = json.load(open('/tmp/unread_focr_matched.json'))
OUT_PDF = '/Users/mainsobhelper/Desktop/REX/garbled_review/GOJ_unreadable_forms_review_JUL27-28.pdf'

c = rl_canvas.Canvas(OUT_PDF, pagesize=letter)
W, H = letter
for r in results:
    img_path = r['file']
    # resolve full path
    full = Path('/Users/mainsobhelper/Desktop/REX/garbled_review') / img_path
    img = ImageReader(str(full))
    iw, ih = img.getSize()
    scale = min((W - 80) / iw, (H - 170) / ih)
    dw, dh = iw * scale, ih * scale
    x = (W - dw) / 2
    y = H - 100 - dh
    c.drawImage(img, x, y, dw, dh)
    c.setFont('Helvetica-Bold', 13)
    c.drawString(40, H - 40, f"#{r['idx']}  {r['file'].replace('UNREAD_','').replace('.png','')}")
    c.setFont('Helvetica-Bold', 15)
    c.setFillColorRGB(0, 0.4, 0)
    guess = r.get('match') or r.get('read_name') or '???'
    conf = r.get('conf', 0)
    c.drawString(40, H - 62, f"BEST GUESS: {guess}  ({conf:.0f}%)")
    c.setFillColorRGB(0, 0, 0)
    c.setFont('Helvetica', 10)
    c.drawString(40, H - 80, f"OCR read: {r.get('read_name')}")
    c.showPage()
c.save()
print(f'REVIEW PDF rebuilt: {OUT_PDF} ({len(results)} forms, guesses printed)')
