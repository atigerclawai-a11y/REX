#!/usr/bin/env python3
"""Build the complete unreadable review PDF (232 forms) — numbered, JPEG-compressed
name crops, one per page. Emails after build."""
import json
import os
import subprocess
from pathlib import Path
from PIL import Image
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader

MANIFEST = json.load(open('/tmp/unreadable_full_manifest.json'))
OUT_PDF = '/Users/mainsobhelper/Desktop/REX/garbled_review/GOJ_unreadable_forms_ALL_JUL27-31.pdf'

# compress each crop to JPEG (max width 1200, q80)
tmp = Path('/tmp/name_crops_jpg')
tmp.mkdir(exist_ok=True)
entries = []
for m in MANIFEST:
    src = m['crop']
    dst = tmp / f"F{m['n']:03d}.jpg"
    if not dst.exists():
        img = Image.open(src).convert('RGB')
        if img.width > 1200:
            h = int(img.height * 1200 / img.width)
            img = img.resize((1200, h), Image.LANCZOS)
        img.save(dst, 'JPEG', quality=80)
    entries.append((m, dst))

c = rl_canvas.Canvas(OUT_PDF, pagesize=(612, 792))  # letter
W, H = 612, 792
MARGIN = 36
for m, img_path in entries:
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont('Helvetica-Bold', 13)
    c.drawString(MARGIN, H - 40, f"#{m['n']}  —  {m['doc']}  p{m['page']}")
    c.setFont('Helvetica', 9)
    c.setFillColorRGB(0.3, 0.3, 0.3)
    c.drawString(MARGIN, H - 54, 'BEST GUESS: (focr running in background — see follow-up email)')
    ir = ImageReader(str(img_path))
    iw, ih = ir.getSize()
    # fit image in page width, name region is short → place at top under header
    avail_w = W - 2 * MARGIN
    scale = avail_w / iw
    dw = avail_w
    dh = ih * scale
    y = H - 64 - dh
    if y < MARGIN:
        scale = (H - 64 - MARGIN) / ih
        dw = iw * scale
        dh = ih * scale
        y = H - 64 - dh
    c.drawImage(ir, MARGIN + (avail_w - dw) / 2, y, width=dw, height=dh)
    c.showPage()
c.save()
print(f'PDF built: {OUT_PDF} ({len(entries)} pages, {os.path.getsize(OUT_PDF)/1e6:.1f} MB)')
