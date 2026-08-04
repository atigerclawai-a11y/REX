#!/usr/bin/env python3
"""Render Wednesday menu pages at 200dpi and decode QR (final quality gate)."""
import os
import subprocess

OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'
TMP = '/tmp/wed_qr_check'
os.makedirs(TMP, exist_ok=True)

import fitz
for tag, fname in [('s1', 'Menus_Wed_Aug05_S1_LIVE.pdf'), ('s2', 'Menus_Wed_Aug05_S2_LIVE.pdf')]:
    doc = fitz.open(os.path.join(OUT, fname))
    for i in (0, 1):
        pix = doc[i].get_pixmap(dpi=200)
        pix.save(os.path.join(TMP, f'{tag}_p{i+1}.png'))
    doc.close()
    print(f'{fname}: rendered pages 1-2')

# decode QRs
for tag in ('s1', 's2'):
    for p in (1, 2):
        png = os.path.join(TMP, f'{tag}_p{p}.png')
        r = subprocess.run(['zbarimg', '-q', '--raw', png], capture_output=True, text=True)
        print(f'{tag}_p{p} QR: {r.stdout.strip() if r.stdout.strip() else "(none on this page)"}')
