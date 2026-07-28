#!/usr/bin/env python3
"""
CC_ocr_exception_report.py — OCR Exception Report PDF Generator
================================================================
When OCR encounters a page it cannot confidently read, generates a
single-page PDF with:
  - The original scanned page image
  - The OCR's best guess(es)
  - Why it's uncertain
  - Space for Kato's decision

Sends to Telegram for review, then Kato replies with decision.

Usage:
    from CC_ocr_exception_report import generate_exception_pdf, send_for_review
    report_path = generate_exception_pdf(pdf_path, page_num, client_name, field, 
                                          ocr_value, candidates, confidence)
    send_for_review(report_path, client_name, field)
"""

import fitz  # pymupdf
import io
import json
from pathlib import Path
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── Fonts ───────────────────────────────────────────────────────────
FONT_DIR = Path.home() / "Documents/goj files/fonts"
try:
    pdfmetrics.registerFont(TTFont('DejaVu', str(FONT_DIR / 'DejaVuSans.ttf')))
    pdfmetrics.registerFont(TTFont('DejaVuBold', str(FONT_DIR / 'DejaVuSans-Bold.ttf')))
except Exception:
    pass  # fall back to Helvetica

# ── Paths ───────────────────────────────────────────────────────────
OUTPUT_DIR = Path.home() / "Desktop/REX/ocr_exceptions"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── PDF Generation ──────────────────────────────────────────────────

def generate_exception_pdf(
    pdf_path: str,
    page_num: int,
    client_name: str,
    field: str,
    ocr_value: str,
    candidates: list[str],
    confidence: float,
    context_lines: str = "",
) -> Path:
    """
    Generate a one-page exception report PDF.
    
    Args:
        pdf_path: Path to the original scanned PDF
        page_num: 1-indexed page number with the problem
        client_name: Client whose menu item is unclear
        field: Which field (salad/soup/main/side)
        ocr_value: What OCR read
        candidates: Alternative possibilities
        confidence: OCR confidence (0-1)
        context_lines: Surrounding OCR text for context
    
    Returns: Path to generated report PDF
    """
    
    # Extract the page as an image
    doc = fitz.open(pdf_path)
    page = doc[page_num - 1]
    
    # Render page at 150 DPI for reasonable file size
    mat = fitz.Matrix(150/72, 150/72)
    pix = page.get_pixmap(matrix=mat)
    img_data = pix.tobytes("png")
    doc.close()
    
    # Save temp image
    img_path = OUTPUT_DIR / f"_temp_page_{page_num}.png"
    with open(img_path, "wb") as f:
        f.write(img_data)
    
    # Build PDF
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_name = f"OCR_Exception_{client_name.replace(' ','_')}_{field}_{timestamp}.pdf"
    report_path = OUTPUT_DIR / report_name
    
    doc = SimpleDocTemplate(
        str(report_path), pagesize=letter,
        leftMargin=30, rightMargin=30, topMargin=20, bottomMargin=20
    )
    
    title_style = ParagraphStyle('T', fontName='DejaVuBold', fontSize=14, alignment=TA_CENTER, spaceAfter=4)
    h2_style    = ParagraphStyle('H2', fontName='DejaVuBold', fontSize=11, spaceBefore=8, spaceAfter=3)
    body_style  = ParagraphStyle('B', fontName='DejaVu', fontSize=9, leading=12)
    warn_style  = ParagraphStyle('W', fontName='DejaVuBold', fontSize=10, textColor=colors.red)
    field_rus = {"salad": "Салат", "soup": "Суп", "main": "Главное", "side": "Гарнир"}.get(field, field)
    
    elements = [
        Paragraph("⚠️ GARDEN OF JOY — OCR EXCEPTION", title_style),
        Paragraph(f"Требуется решение • {datetime.now().strftime('%d.%m.%Y %H:%M')}", title_style),
        Spacer(1, 6),
    ]
    
    # Problem summary
    elements.append(Paragraph(f"Клиент: <b>{client_name}</b>", h2_style))
    elements.append(Paragraph(f"Поле: <b>{field_rus}</b> • Файл: {Path(pdf_path).name} • Стр. {page_num}", body_style))
    elements.append(Spacer(1, 4))
    
    # OCR result
    elements.append(Paragraph("Что распознал OCR:", h2_style))
    conf_pct = f"{confidence:.0%}"
    conf_color = "red" if confidence < 0.5 else "orange" if confidence < 0.7 else "green"
    elements.append(Paragraph(
        f"<b>«{ocr_value}»</b> — уверенность: <font color='{conf_color}'><b>{conf_pct}</b></font>",
        body_style
    ))
    
    # Candidates
    if candidates:
        elements.append(Paragraph("Возможные варианты:", h2_style))
        for i, c in enumerate(candidates):
            elements.append(Paragraph(f"  {i+1}. {c}", body_style))
    
    # Why uncertain
    elements.append(Paragraph("Причина неопределённости:", h2_style))
    if confidence < 0.4:
        reason = "Очень низкая уверенность — текст нечитаем или повреждён."
    elif confidence < 0.6:
        reason = "Несколько возможных вариантов с близкой вероятностью."
    elif confidence < 0.75:
        reason = "Один вариант найден, но качество изображения низкое."
    else:
        reason = "Результат выше порога, но требует проверки из-за нестандартного написания."
    elements.append(Paragraph(reason, body_style))
    
    # Context
    if context_lines:
        elements.append(Paragraph("Контекст (окружающий текст):", h2_style))
        for line in context_lines.split('\n')[:5]:
            if line.strip():
                elements.append(Paragraph(f"  <i>{line[:100]}</i>", body_style))
    
    # Page image
    elements.append(Spacer(1, 6))
    elements.append(Paragraph("Страница документа:", h2_style))
    
    # Scale image to fit
    img = Image(str(img_path), width=450, height=320)
    elements.append(img)
    
    # Decision space
    elements.append(Spacer(1, 10))
    elements.append(Paragraph("—" * 60, body_style))
    elements.append(Paragraph("<b>РЕШЕНИЕ:</b> (напишите правильный вариант или «OK» для принятия)", warn_style))
    elements.append(Paragraph(f"Клиент: {client_name} • Поле: {field_rus} • OCR: «{ocr_value}»", body_style))
    elements.append(Paragraph("—" * 60, body_style))
    
    doc.build(elements)
    
    # Cleanup temp image
    img_path.unlink(missing_ok=True)
    
    return report_path


# ── Telegram Integration ────────────────────────────────────────────

def send_for_review(report_path: Path, client_name: str, field: str) -> bool:
    """
    Send the exception report to Kato via Telegram.
    Uses the existing CC_ocr_telegram_fallback module.
    """
    try:
        from CC_ocr_telegram_fallback import flag_for_review
        
        field_rus = {"salad": "Салат", "soup": "Суп", "main": "Главное", "side": "Гарнир"}.get(field, field)
        
        flag_for_review(
            source="ocr_oversight",
            file_path=report_path,
            reason=f"Не могу прочитать «{field_rus}» для {client_name}. См. PDF отчёт.",
            partial={"field": field, "client": client_name},
            bot="rex_of_gold",
        )
        return True
    except Exception as e:
        print(f"Telegram send failed: {e}")
        return False


# ── Batch report generation ─────────────────────────────────────────

def generate_batch_exception_report(exceptions: list[dict], output_name: str = None) -> Path:
    """
    Generate a multi-page PDF with all exceptions from a batch.
    One client per page, with the problem field highlighted.
    
    Args:
        exceptions: list of {pdf_path, page_num, client_name, field, ocr_value, candidates, confidence}
        output_name: optional filename
    
    Returns: Path to report PDF
    """
    if output_name is None:
        output_name = f"OCR_Exceptions_Batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    
    report_path = OUTPUT_DIR / output_name
    doc = SimpleDocTemplate(str(report_path), pagesize=letter,
                            leftMargin=30, rightMargin=30, topMargin=20, bottomMargin=20)
    
    title_style = ParagraphStyle('T', fontName='DejaVuBold', fontSize=14, alignment=TA_CENTER)
    body_style  = ParagraphStyle('B', fontName='DejaVu', fontSize=9, leading=11)
    
    elements = [
        Paragraph("⚠️ GOJ OCR — Отчёт об исключениях", title_style),
        Paragraph(f"Всего: {len(exceptions)} нераспознанных полей • {datetime.now().strftime('%d.%m.%Y')}", title_style),
        Spacer(1, 10),
    ]
    
    # Summary table
    field_counts = {}
    for e in exceptions:
        f = e['field']
        field_counts[f] = field_counts.get(f, 0) + 1
    
    elements.append(Paragraph("Сводка по полям:", body_style))
    summary = " • ".join([f"{k}: {v}" for k, v in field_counts.items()])
    elements.append(Paragraph(summary, body_style))
    elements.append(Spacer(1, 6))
    
    # Detail table
    data = [["Клиент", "Поле", "OCR", "Увер.", "Варианты"]]
    for e in exceptions:
        cands = ", ".join(e['candidates'][:2]) if e.get('candidates') else "—"
        data.append([
            Paragraph(e['client_name'], body_style),
            e['field'],
            e['ocr_value'],
            f"{e['confidence']:.0%}",
            cands[:60]
        ])
    
    t = Table(data, colWidths=[140, 55, 100, 45, 170])
    t.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,-1), 'DejaVu'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#C00000')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#fff0f0')]),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ]))
    elements.append(t)
    
    doc.build(elements)
    return report_path
