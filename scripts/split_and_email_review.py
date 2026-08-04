#!/usr/bin/env python3
"""Split the unreadable review into per-batch PDFs (Jul 27 / Jul 29 / Jul 30 / Jul 31)
and email each piece separately."""
import json
import os
import smtplib
from pathlib import Path
from PIL import Image
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

MANIFEST = json.load(open('/tmp/unreadable_full_manifest.json'))
TMP = Path('/tmp/name_crops_jpg')
OUTDIR = Path('/Users/mainsobhelper/Desktop/REX/garbled_review')
creds = json.load(open(os.path.expanduser('~/.rex_gmail_imap.json')))
SENDER = creds.get('user') or creds.get('email')
PASS = creds.get('password') or creds.get('app_password')
TO = 'atigerclawai@gmail.com'

# group by batch (doc prefix)
BATCHES = {
    'Jul27': lambda d: '20260727' in d,
    'Jul29': lambda d: '20260729' in d,
    'Jul30': lambda d: '20260730' in d,
    'Jul31': lambda d: '20260731' in d,
}

def build_pdf(entries, out_path, title):
    c = rl_canvas.Canvas(str(out_path), pagesize=(612, 792))
    W, H = 612, 792
    MARGIN = 36
    for m in entries:
        img_path = TMP / f"F{m['n']:03d}.jpg"
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.setFont('Helvetica-Bold', 13)
        c.drawString(MARGIN, H - 40, f"#{m['n']}  —  {m['doc']}  p{m['page']}")
        c.setFont('Helvetica', 9)
        c.setFillColorRGB(0.3, 0.3, 0.3)
        c.drawString(MARGIN, H - 54, 'BEST GUESS: (focr running — see follow-up email)')
        ir = ImageReader(str(img_path))
        iw, ih = ir.getSize()
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
    return out_path

def email_pdf(pdf_path, subject, note):
    msg = MIMEMultipart()
    msg['From'] = SENDER
    msg['To'] = TO
    msg['Subject'] = subject
    msg.attach(MIMEText(note, 'plain'))
    part = MIMEBase('application', 'pdf')
    part.set_payload(open(pdf_path, 'rb').read())
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(pdf_path))
    msg.attach(part)
    with smtplib.SMTP('smtp.gmail.com', 587) as s:
        s.starttls()
        s.login(SENDER, PASS)
        s.send_message(msg)
    print(f'EMAILED {os.path.basename(pdf_path)} ({os.path.getsize(pdf_path)/1e6:.1f} MB, {len(entries)} forms)')

# build + email per batch
for label, pred in BATCHES.items():
    entries = [m for m in MANIFEST if pred(m['doc'])]
    if not entries:
        print(f'{label}: none')
        continue
    pdf_path = OUTDIR / f'GOJ_unreadable_{label}_forms.pdf'
    build_pdf(entries, pdf_path, label)
    pdf_pages = len(entries)
    email_pdf(pdf_path,
              f'GOJ unreadable forms {label} batch — {len(entries)} forms (part of the 232)',
              f'Kato — {label} batch of unreadable forms: #{entries[0]["n"]}-#{entries[-1]["n"]} '
              f'({len(entries)} forms). Reply "#N = Correct Name" or "all correct".\n')
