#!/usr/bin/env python3
"""Generate GOJ Sunday Shift 1 sign-in sheet PDF."""
import os
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                Paragraph, Spacer)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

SRC = "/tmp/sunday_clients.txt"
OUT_DIR = "/Users/mainsobhelper/Desktop/REX/signin_lists"
OUT = os.path.join(OUT_DIR, "GOJ_2026-07-26_S1_SIGNIN.pdf")

DATE_STR = "July 26, 2026"
SHIFT = "1"
PER_PAGE = 11

# ---- Load clients ----
clients = []
with open(SRC) as f:
    for line in f:
        line = line.rstrip("\n")
        if not line.strip():
            continue
        # strip leading numbering "N\t" if present
        if "\t" in line:
            _, rest = line.split("\t", 1)
        else:
            rest = line
        parts = rest.split("|")
        if len(parts) < 3:
            continue
        name = parts[0].strip()
        payer = parts[1].strip()
        tr = parts[2].strip()
        clients.append((name, payer, tr))

total = len(clients)
num_pages = (total + PER_PAGE - 1) // PER_PAGE

os.makedirs(OUT_DIR, exist_ok=True)

# ---- Styles ----
styles = getSampleStyleSheet()
header_style = ParagraphStyle("hdr", parent=styles["Normal"],
                              fontName="Helvetica-Bold", fontSize=14,
                              alignment=TA_CENTER, leading=17)
sub_style = ParagraphStyle("sub", parent=styles["Normal"],
                           fontName="Helvetica", fontSize=10,
                           alignment=TA_CENTER, leading=13)
cell_style = ParagraphStyle("cell", parent=styles["Normal"],
                            fontName="Helvetica", fontSize=10, leading=12)
cell_head = ParagraphStyle("cellh", parent=styles["Normal"],
                           fontName="Helvetica-Bold", fontSize=10, leading=12)

COL_WIDTHS = [0.3*inch, 2.2*inch, 2.2*inch, 0.4*inch,
              0.8*inch, 0.8*inch, 1.0*inch]
HEADERS = ["No", "Name", "Plan", "TR", "Time In", "Time Out", "Signature"]

FOOTER_TEXT = ("3152 Brighton 6 St, Brooklyn NY 11235 | "
               "Garden of Joy Adult Day Care Center")


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawCentredString(letter[0] / 2.0, 0.3 * inch, FOOTER_TEXT)
    canvas.restoreState()


doc = SimpleDocTemplate(OUT, pagesize=letter,
                        leftMargin=0.5*inch, rightMargin=0.5*inch,
                        topMargin=0.5*inch, bottomMargin=0.5*inch)

story = []

for page in range(num_pages):
    page_num = page + 1
    start = page * PER_PAGE
    chunk = clients[start:start + PER_PAGE]

    story.append(Paragraph(
        "GARDEN OF JOY ADULT DAY CARE CENTER — SIGN-IN SHEET",
        header_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"Date: {DATE_STR}&nbsp;&nbsp;&nbsp;Shift: {SHIFT}&nbsp;&nbsp;&nbsp;"
        f"Total: {total}&nbsp;&nbsp;&nbsp;Page {page_num}/{num_pages}",
        sub_style))
    story.append(Spacer(1, 8))

    data = [[Paragraph(h, cell_head) for h in HEADERS]]
    for i, (name, payer, tr) in enumerate(chunk):
        idx = start + i + 1
        data.append([
            Paragraph(str(idx), cell_style),
            Paragraph(name, cell_style),
            Paragraph(payer, cell_style),
            Paragraph(tr, cell_style),
            "", "", "",
        ])

    tbl = Table(data, colWidths=COL_WIDTHS, rowHeights=[0.35*inch] +
                [0.55*inch]*len(chunk))
    ts = [
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#444444")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    # alternating row colors for body rows
    for r in range(1, len(data)):
        if r % 2 == 1:
            ts.append(("BACKGROUND", (0, r), (-1, r),
                       colors.HexColor("#EEEEEE")))
        else:
            ts.append(("BACKGROUND", (0, r), (-1, r), colors.white))
    tbl.setStyle(TableStyle(ts))
    story.append(tbl)

    # Last page totals line
    if page_num == num_pages:
        story.append(Spacer(1, 20))
        story.append(Paragraph(
            "Total present: ______&nbsp;&nbsp;&nbsp;"
            "Staff signature: ___________________________&nbsp;&nbsp;&nbsp;"
            "Date: __________",
            cell_style))

    if page_num < num_pages:
        from reportlab.platypus import PageBreak
        story.append(PageBreak())

doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(f"Wrote {OUT}: {total} clients across {num_pages} pages")
