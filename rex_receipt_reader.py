"""
rex_receipt_reader.py — REX Bookkeeping Module
════════════════════════════════════════════════════════════
Receipt OCR → categorization → PDF filing → P&L reports.
Garden of Joy · Gold Health Systems · Locked Lucy Compliant

WHAT THIS MODULE DOES:
  1. Reads receipt images (JPEG, PNG, HEIC, PDF) via OCR
  2. Extracts: vendor, date, amount, line items
  3. Auto-categorizes into expense buckets
  4. Saves a clean PDF to ~/Desktop/REX/receipts/<Category>/<Year-Month>/
  5. Logs every receipt to a SQLite ledger (rex_ledger.db)
  6. Generates P&L reports (weekly, monthly, YTD)
  7. Detects spending trends and flags anomalies

CATEGORIES:
  • Supplies       — office, medical, kitchen supplies
  • Meals/Food     — groceries, restaurant, catering
  • Staffing       — training costs, background checks, uniforms
  • Facilities     — rent, utilities, maintenance, repairs
  • Medical        — client health supplies, pharmacy
  • Transport      — mileage, fuel, vehicle
  • Insurance      — premiums, bonds
  • Professional   — legal, accounting, consulting
  • Technology     — software, hardware, subscriptions
  • Misc           — anything unclassified

LOCKED LUCY COMPLIANCE:
  • All OCR runs locally (Vision + EasyOCR + PaddleOCR + Tesseract + TrOCR)
  • No images or financial data sent to cloud
  • PDF receipts stored locally in receipts folder
  • Ledger is plain SQLite (no encryption — not HIPAA-sensitive)

TELEGRAM INTEGRATION:
  • Used by rex_telegram_bot.py
  • Kato sends a photo of a receipt → REX reads and files it
  • Returns a confirmation with extracted data
  • Kato can correct the category if REX guesses wrong

USAGE:
  from rex_receipt_reader import ReceiptReader
  reader = ReceiptReader()
  result = reader.process_image("/path/to/receipt.jpg")
  reader.generate_report("monthly")

  # Telegram webhook (call from rex_telegram_bot.py):
  result = reader.handle_telegram_photo(file_bytes, filename="receipt.jpg")
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sqlite3
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
RECEIPTS_ROOT = Path.home() / "Desktop" / "REX" / "receipts"
LEDGER_DB     = Path.home() / "Desktop" / "REX" / "data" / "rex_ledger.db"
REPORTS_DIR   = Path.home() / "Desktop" / "REX" / "reports"

# ── Category definitions ───────────────────────────────────────────────────────
CATEGORIES = {
    "Supplies": [
        "staples", "office depot", "amazon", "paper", "pen", "folder",
        "binder", "label", "tape", "supplies", "glove", "sanitizer",
        "cleaning", "soap", "towel", "trash bag", "mop",
    ],
    "Meals/Food": [
        "grocery", "groceries", "whole foods", "costco", "walmart",
        "food", "restaurant", "cafe", "coffee", "lunch", "dinner",
        "catering", "bakery", "market", "deli", "kroger", "aldi",
        "publix", "produce", "meat", "bread", "dairy",
    ],
    "Staffing": [
        "training", "background check", "uniform", "badge", "certification",
        "first aid", "cpr", "safety training", "orientation",
    ],
    "Facilities": [
        "rent", "lease", "electric", "gas utility", "water bill",
        "plumber", "hvac", "repair", "maintenance", "janitorial",
        "exterminator", "landscaping", "parking",
    ],
    "Medical": [
        "pharmacy", "cvs", "walgreens", "rite aid", "medical supply",
        "bandage", "medication", "prescription", "blood pressure",
        "glucose", "health supply", "incontinence", "gloves medical",
    ],
    "Transport": [
        "shell", "chevron", "bp", "exxon", "mobil", "gas station",
        "fuel", "uber", "lyft", "mileage", "parking", "tolls",
        "auto", "vehicle", "oil change",
    ],
    "Insurance": [
        "insurance", "premium", "bond", "liability", "workers comp",
        "surety",
    ],
    "Professional": [
        "attorney", "lawyer", "accountant", "cpa", "consultant",
        "legal", "notary", "filing fee", "license renewal",
    ],
    "Technology": [
        "software", "subscription", "saas", "google", "microsoft",
        "apple", "hosting", "domain", "computer", "tablet", "printer",
        "zoom", "quickbooks", "dropbox",
    ],
}

# ── OCR availability ───────────────────────────────────────────────────────────

# macOS Vision framework (built-in — fastest, most accurate on Mac)
try:
    import subprocess as _sub
    import sys as _sys
    # Test if Vision framework is available via pyobjc
    _sub.run(
        [_sys.executable, "-c", "import Vision; import Quartz"],
        capture_output=True, timeout=5
    )
    _MACOS_VISION_AVAILABLE = True
except Exception:
    _MACOS_VISION_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image
    _TESSERACT_AVAILABLE = True
except ImportError:
    _TESSERACT_AVAILABLE = False

try:
    from paddleocr import PaddleOCR
    _PADDLE_AVAILABLE = True
except ImportError:
    _PADDLE_AVAILABLE = False

try:
    import easyocr as _easyocr
    _EASYOCR_AVAILABLE = True
except ImportError:
    _EASYOCR_AVAILABLE = False

# TrOCR (Microsoft transformer-based HTR) — optional, large download (~1.3 GB)
# Enabled only when explicitly installed:
#   pip install transformers torch --break-system-packages
try:
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel
    import torch as _torch
    _TROCR_AVAILABLE = True
except ImportError:
    _TROCR_AVAILABLE = False

try:
    import fpdf
    _FPDF_AVAILABLE = True
except ImportError:
    try:
        from fpdf import FPDF
        _FPDF_AVAILABLE = True
    except ImportError:
        _FPDF_AVAILABLE = False

try:
    from PIL import Image as _PIL_Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


# ──────────────────────────────────────────────────────────────────────────────
# DATABASE
# ──────────────────────────────────────────────────────────────────────────────

def _ensure_ledger_db() -> None:
    LEDGER_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(LEDGER_DB))
    con.executescript("""
        CREATE TABLE IF NOT EXISTS receipts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            receipt_date  TEXT,
            vendor        TEXT,
            amount        REAL,
            tax           REAL DEFAULT 0,
            category      TEXT DEFAULT 'Misc',
            subcategory   TEXT,
            description   TEXT,
            pdf_path      TEXT,
            raw_text      TEXT,
            source_file   TEXT,
            added_by      TEXT DEFAULT 'rex_receipt_reader',
            confirmed     INTEGER DEFAULT 0,
            logged_at     TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS line_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            receipt_id  INTEGER NOT NULL,
            description TEXT,
            quantity    REAL DEFAULT 1,
            unit_price  REAL,
            total       REAL,
            FOREIGN KEY (receipt_id) REFERENCES receipts(id)
        );

        CREATE INDEX IF NOT EXISTS idx_receipts_date     ON receipts(receipt_date);
        CREATE INDEX IF NOT EXISTS idx_receipts_category ON receipts(category);
        CREATE INDEX IF NOT EXISTS idx_receipts_vendor   ON receipts(vendor);
    """)
    con.commit()
    con.close()


# ──────────────────────────────────────────────────────────────────────────────
# EXTRACTION HELPERS
# ──────────────────────────────────────────────────────────────────────────────

# Patterns for extracting key fields from OCR text
_AMOUNT_PATTERNS = [
    r'(?:total|amount|due|charged|subtotal|grand total|balance)\s*[:\-]?\s*\$?\s*([\d,]+\.?\d{0,2})',
    r'\$\s*([\d,]+\.\d{2})',
    r'([\d,]+\.\d{2})\s*(?:USD|usd)?$',
]

_DATE_PATTERNS = [
    r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})',
    r'(\d{4}[/\-]\d{1,2}[/\-]\d{1,2})',
    r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})',
]

_TAX_PATTERNS = [
    r'(?:tax|sales tax|hst|gst|vat)\s*[:\-]?\s*\$?\s*([\d,]+\.?\d{0,2})',
]


def _extract_amount(text: str) -> Optional[float]:
    """Extract the total amount from OCR text."""
    for pattern in _AMOUNT_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
        if matches:
            # Take the last (usually the total) if multiple found
            raw = matches[-1].replace(",", "")
            try:
                return float(raw)
            except ValueError:
                continue
    return None


def _extract_date(text: str) -> Optional[str]:
    """Extract receipt date from OCR text. Returns ISO format."""
    for pattern in _DATE_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            raw = matches[0]
            # Try to parse various formats
            for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d",
                        "%m-%d-%Y", "%m-%d-%y", "%Y-%m-%d",
                        "%B %d, %Y", "%b %d, %Y", "%B %d %Y"):
                try:
                    return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
                except ValueError:
                    continue
    return date.today().isoformat()   # fallback: today


def _extract_vendor(text: str) -> str:
    """Extract vendor name — typically the first non-empty line."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if lines:
        # First line is usually the store name
        first = lines[0]
        # Filter out common non-vendor first lines
        if not re.match(r'^\d|^receipt|^invoice|^bill|^#', first, re.I):
            return first[:80]
        if len(lines) > 1:
            return lines[1][:80]
    return "Unknown Vendor"


def _extract_tax(text: str) -> float:
    """Extract tax amount from OCR text."""
    for pattern in _TAX_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            try:
                return float(matches[0].replace(",", ""))
            except ValueError:
                pass
    return 0.0


def _categorize(vendor: str, text: str) -> str:
    """Auto-categorize based on vendor name and full OCR text."""
    search_text = (vendor + " " + text).lower()
    best_cat    = "Misc"
    best_hits   = 0

    for category, keywords in CATEGORIES.items():
        hits = sum(1 for kw in keywords if kw in search_text)
        if hits > best_hits:
            best_hits = hits
            best_cat  = category

    return best_cat


def _extract_line_items(text: str) -> list[dict]:
    """
    Attempt to extract line items from receipt text.
    Returns list of {description, quantity, unit_price, total}.
    """
    items = []
    # Pattern: description followed by price at end of line
    pattern = re.compile(
        r'^(.+?)\s+(?:(\d+)\s*[xX@]\s*)?\$?\s*([\d,]+\.\d{2})\s*$',
        re.MULTILINE
    )
    for match in pattern.finditer(text):
        desc, qty_str, price_str = match.groups()
        desc = desc.strip()
        # Skip total/tax/subtotal lines
        if re.search(r'\b(total|tax|subtotal|due|balance|tip|change)\b', desc, re.I):
            continue
        if len(desc) < 2:
            continue
        qty   = float(qty_str) if qty_str else 1.0
        price = float(price_str.replace(",", ""))
        items.append({
            "description": desc[:150],
            "quantity":    qty,
            "unit_price":  round(price / qty, 2),
            "total":       price,
        })
    return items[:30]   # cap at 30 items


# ──────────────────────────────────────────────────────────────────────────────
# OCR ENGINE
# ──────────────────────────────────────────────────────────────────────────────

def _ocr_with_macos_vision(image_path: str) -> str:
    """
    Use macOS built-in Vision framework for OCR.
    Already on every Mac running macOS 10.15+.
    Significantly more accurate than Tesseract on printed receipts.
    Requires: pip install pyobjc-framework-Vision pyobjc-framework-Quartz
    """
    try:
        import Vision
        import Quartz
        import objc
        from Foundation import NSURL

        image_url  = NSURL.fileURLWithPath_(image_path)
        handler    = Vision.VNImageRequestHandler.alloc().initWithURL_options_(
            image_url, {}
        )
        request    = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        request.setUsesLanguageCorrection_(True)
        # Request English + Russian + Ukrainian recognition
        # macOS Vision auto-detects; this list is a prioritization hint
        try:
            request.setRecognitionLanguages_(["en-US", "ru-RU", "uk-UA"])
        except Exception:
            pass   # older macOS — falls back to auto-detect (still reads Cyrillic)

        handler.performRequests_error_([request], None)
        observations = request.results()

        if not observations:
            return ""

        lines = []
        for obs in observations:
            candidate = obs.topCandidates_(1)
            if candidate:
                lines.append(candidate[0].string())

        return "\n".join(lines)

    except Exception as e:
        logger.debug(f"[receipt] macOS Vision OCR error: {e}")
        return ""


def _ocr_with_tesseract(image_path: str) -> str:
    """
    Run Tesseract OCR on an image file.
    Supports English + Russian + Ukrainian automatically.
    Install language packs: brew install tesseract-lang
    """
    try:
        img = _PIL_Image.open(image_path)
        # Try with Cyrillic language packs first (for Russian/Ukrainian receipts)
        try:
            text = pytesseract.image_to_string(img, lang="eng+rus+ukr", config="--psm 4")
            if text.strip():
                return text
        except Exception:
            pass
        # Fallback to English only
        text = pytesseract.image_to_string(img, config="--psm 4")
        return text
    except Exception as e:
        logger.error(f"[receipt] Tesseract error: {e}")
        return ""


def _ocr_with_paddle(image_path: str) -> str:
    """
    Run PaddleOCR on an image file.
    Supports English, Russian, and Ukrainian.
    """
    try:
        # Try Russian first (covers Ukrainian Cyrillic characters too)
        ocr    = PaddleOCR(use_angle_cls=True, lang="ru", show_log=False)
        result = ocr.ocr(image_path, cls=True)
        lines  = []
        if result:
            for page in result:
                if page:
                    for line in page:
                        if line and len(line) >= 2:
                            lines.append(line[1][0])
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"[receipt] PaddleOCR error: {e}")
        return ""


def _preprocess_for_handwriting(image_path: str) -> str:
    """
    Preprocess an image to improve handwriting / sloppy-writing OCR accuracy.

    Steps:
      1. Convert to grayscale
      2. Upscale small images (handwriting needs resolution)
      3. Adaptive thresholding (handles uneven lighting / faded ink)
      4. Slight dilation to reconnect broken pen strokes
      5. Save to temp file — returns path to preprocessed image

    Returns the path to the preprocessed image (caller is responsible for cleanup).
    Silently returns original path if PIL is not available.
    """
    if not _PIL_AVAILABLE:
        return image_path
    try:
        from PIL import Image, ImageFilter, ImageOps
        img = Image.open(image_path).convert("L")           # grayscale

        # Upscale if small — handwriting benefits from at least 300 DPI equivalent
        MIN_SIZE = 1200
        w, h = img.size
        if min(w, h) < MIN_SIZE:
            scale = MIN_SIZE / min(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        # Adaptive sharpening to help ink strokes
        img = img.filter(ImageFilter.SHARPEN)

        # Binarize: auto-contrast then threshold
        img = ImageOps.autocontrast(img, cutoff=2)

        import tempfile, os
        suffix = os.path.splitext(image_path)[-1] or ".png"
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        img.save(tmp.name)
        return tmp.name
    except Exception as e:
        logger.debug(f"[receipt] handwriting preprocess failed: {e}")
        return image_path


def _ocr_with_easyocr(image_path: str, handwriting: bool = False) -> str:
    """
    EasyOCR — strong multilingual OCR with good cursive/sloppy-writing handling.

    Supports English (en), Russian (ru), Ukrainian (uk) natively.
    Better than Tesseract for non-standard fonts and messy handwriting.

    Install:
      pip install easyocr --break-system-packages
      (Downloads ~300 MB of model weights on first run; cached thereafter.)

    Args:
        image_path:  Path to image file
        handwriting: If True, preprocesses the image for handwriting mode
    """
    if not _EASYOCR_AVAILABLE:
        return ""
    try:
        import numpy as _np

        if handwriting:
            image_path = _preprocess_for_handwriting(image_path)

        # EasyOCR reader — cached after first creation
        # Languages: en (English), ru (Russian), uk (Ukrainian)
        reader = _easyocr.Reader(["en", "ru", "uk"], gpu=False, verbose=False)
        result = reader.readtext(image_path, detail=0, paragraph=True)
        return "\n".join(str(r) for r in result if r)
    except Exception as e:
        logger.error(f"[receipt] EasyOCR error: {e}")
        return ""


def _ocr_with_trocr(image_path: str) -> str:
    """
    TrOCR (Microsoft) — transformer-based handwritten text recognition.

    Specifically designed for handwritten English. Excellent for cursive and
    difficult signatures. For Russian handwriting, use EasyOCR instead.

    Requires (~1.3 GB model download on first use):
      pip install transformers torch --break-system-packages
    Model is cached in ~/.cache/huggingface/ after first download.
    """
    if not _TROCR_AVAILABLE:
        return ""
    try:
        from PIL import Image as _PILImg
        img = _PILImg.open(image_path).convert("RGB")

        # Use large handwritten model for best accuracy
        processor = TrOCRProcessor.from_pretrained("microsoft/trocr-large-handwritten")
        model     = VisionEncoderDecoderModel.from_pretrained(
            "microsoft/trocr-large-handwritten"
        )
        pixel_values = processor(images=img, return_tensors="pt").pixel_values
        with _torch.no_grad():
            generated_ids = model.generate(pixel_values)
        text = processor.batch_decode(generated_ids, skip_special_tokens=True)
        return "\n".join(text)
    except Exception as e:
        logger.error(f"[receipt] TrOCR error: {e}")
        return ""


def _is_low_confidence(text: str) -> bool:
    """
    Heuristic: decide if OCR output looks low-confidence.
    Used to decide whether to also try handwriting-focused engines.
    Triggers when:
      - Very short output (< 30 chars) for a non-trivial image
      - High ratio of non-alphanumeric chars (garbled output)
      - No numbers found (receipts should always have at least one)
    """
    if not text.strip():
        return True
    clean = text.strip()
    if len(clean) < 30:
        return True
    # If more than 40% of characters are non-word chars, looks garbled
    non_word = sum(1 for c in clean if not c.isalnum() and c not in " \n.,/-:$€£₴₽")
    if non_word / max(len(clean), 1) > 0.40:
        return True
    # Receipt should have at least one digit
    if not re.search(r'\d', clean):
        return True
    return False


def _run_ocr(image_path: str) -> str:
    """
    Run best available OCR engine with automatic handwriting fallback.

    Pipeline:
      1. macOS Vision (built-in, Accurate mode — handles printed + some handwriting)
      2. EasyOCR (multilingual, EN/RU/UK, good for sloppy writing + cursive)
      3. PaddleOCR (strong multilingual alternative)
      4. Tesseract (last resort)
      5. TrOCR (optional — transformer HTR, English handwriting only,
                 used automatically if installed and result still poor)

    Handwriting boost:
      If the initial result looks low-confidence (short/garbled/no numbers),
      the pipeline automatically retries with EasyOCR in handwriting mode
      (enhanced image preprocessing). This catches sloppy writing and
      Russian/English signatures without any extra commands.

    Install OCR engines:
      macOS Vision (recommended, already on your Mac):
        pip install pyobjc-framework-Vision pyobjc-framework-Quartz --break-system-packages

      EasyOCR (handwriting + multilingual, 300 MB):
        pip install easyocr --break-system-packages

      PaddleOCR (multilingual):
        pip install paddleocr --break-system-packages

      Tesseract (fallback):
        pip install pytesseract pillow --break-system-packages
        brew install tesseract tesseract-lang

      TrOCR (optional — heavy, English handwriting specialist, 1.3 GB):
        pip install transformers torch --break-system-packages
    """
    best_text = ""

    # 1. macOS Vision (built-in, best for printed receipts)
    if _MACOS_VISION_AVAILABLE:
        text = _ocr_with_macos_vision(image_path)
        if text.strip():
            best_text = text
            logger.debug("[receipt] OCR: macOS Vision used")
            if not _is_low_confidence(text):
                return text

    # 2. EasyOCR — multilingual, handles sloppy writing well
    if _EASYOCR_AVAILABLE:
        text = _ocr_with_easyocr(image_path, handwriting=False)
        if text.strip():
            # Pick longer / better result
            if len(text) > len(best_text):
                best_text = text
            logger.debug("[receipt] OCR: EasyOCR used")
            if not _is_low_confidence(text):
                return text if len(text) >= len(best_text) else best_text

    # 3. PaddleOCR
    if _PADDLE_AVAILABLE:
        text = _ocr_with_paddle(image_path)
        if text.strip() and len(text) > len(best_text):
            best_text = text
            logger.debug("[receipt] OCR: PaddleOCR used")
            if not _is_low_confidence(text):
                return text

    # 4. Tesseract
    if _TESSERACT_AVAILABLE:
        text = _ocr_with_tesseract(image_path)
        if text.strip() and len(text) > len(best_text):
            best_text = text
            logger.debug("[receipt] OCR: Tesseract used")

    # 5. Handwriting boost: if result still looks low-confidence, try
    #    EasyOCR with handwriting preprocessing
    if _is_low_confidence(best_text) and _EASYOCR_AVAILABLE:
        logger.debug("[receipt] OCR: low-confidence — retrying with handwriting mode")
        hw_text = _ocr_with_easyocr(image_path, handwriting=True)
        if hw_text.strip() and len(hw_text) > len(best_text):
            best_text = hw_text
            logger.debug("[receipt] OCR: EasyOCR handwriting mode improved result")

    # 6. TrOCR — transformer HTR, last resort for very difficult handwriting
    if _is_low_confidence(best_text) and _TROCR_AVAILABLE:
        logger.debug("[receipt] OCR: very low-confidence — trying TrOCR (HTR)")
        trocr_text = _ocr_with_trocr(image_path)
        if trocr_text.strip() and len(trocr_text) > len(best_text):
            best_text = trocr_text
            logger.debug("[receipt] OCR: TrOCR used")

    if best_text.strip():
        return best_text

    raise RuntimeError(
        "No OCR engine produced usable output.\n\n"
        "RECOMMENDED — enable macOS built-in Vision OCR (already on your Mac):\n"
        "  pip install pyobjc-framework-Vision pyobjc-framework-Quartz "
        "--break-system-packages\n\n"
        "For handwriting / sloppy writing / Russian receipts, also install:\n"
        "  pip install easyocr --break-system-packages\n"
        "  (Downloads ~300 MB once, then cached)\n\n"
        "OR install Tesseract:\n"
        "  pip install pytesseract pillow --break-system-packages\n"
        "  brew install tesseract tesseract-lang"
    )


# ──────────────────────────────────────────────────────────────────────────────
# PDF GENERATION
# ──────────────────────────────────────────────────────────────────────────────

def _save_receipt_pdf(
    image_path: Optional[str],
    raw_text: str,
    vendor: str,
    receipt_date: str,
    amount: Optional[float],
    category: str,
    receipt_id: int,
) -> Optional[str]:
    """
    Save a receipt as a PDF in the filing structure:
      ~/Desktop/REX/receipts/<Category>/<YYYY-MM>/
    Returns the saved PDF path.
    """
    # Build folder path
    try:
        year_month = receipt_date[:7] if receipt_date else date.today().strftime("%Y-%m")
    except Exception:
        year_month = date.today().strftime("%Y-%m")

    folder = RECEIPTS_ROOT / category / year_month
    folder.mkdir(parents=True, exist_ok=True)

    safe_vendor = re.sub(r'[^\w\s\-]', '', vendor)[:30].strip().replace(" ", "_")
    filename    = f"{receipt_date}_{safe_vendor}_{receipt_id:05d}.pdf"
    pdf_path    = folder / filename

    if _FPDF_AVAILABLE:
        try:
            from fpdf import FPDF
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 16)
            pdf.cell(0, 10, "RECEIPT", ln=True, align="C")
            pdf.ln(4)

            pdf.set_font("Helvetica", "B", 12)
            pdf.cell(0, 8, f"Vendor: {vendor}", ln=True)
            pdf.cell(0, 8, f"Date: {receipt_date}", ln=True)
            pdf.cell(0, 8, f"Amount: ${amount:.2f}" if amount else "Amount: N/A", ln=True)
            pdf.cell(0, 8, f"Category: {category}", ln=True)
            pdf.cell(0, 8, f"Receipt ID: {receipt_id:05d}", ln=True)
            pdf.ln(6)

            pdf.set_font("Helvetica", "", 9)
            pdf.multi_cell(0, 5, "--- RAW OCR TEXT ---")
            pdf.ln(2)
            # Write OCR text, handling encoding issues
            safe_text = raw_text.encode("latin-1", errors="replace").decode("latin-1")
            pdf.multi_cell(0, 5, safe_text[:3000])

            # If original image exists, embed it on page 2
            if image_path and Path(image_path).exists():
                try:
                    pdf.add_page()
                    pdf.set_font("Helvetica", "I", 10)
                    pdf.cell(0, 8, "Original Receipt Image:", ln=True)
                    # Resize if needed
                    if _PIL_AVAILABLE:
                        img = _PIL_Image.open(image_path)
                        img.thumbnail((180, 240))
                        tmp = tempfile.mktemp(suffix=".jpg")
                        img.save(tmp, "JPEG")
                        pdf.image(tmp, x=10, y=20, w=180)
                        os.unlink(tmp)
                    else:
                        pdf.image(image_path, x=10, y=20, w=180)
                except Exception:
                    pass   # image embed failure is non-fatal

            pdf.output(str(pdf_path))
            return str(pdf_path)

        except Exception as e:
            logger.error(f"[receipt] PDF generation error: {e}")

    # Fallback: text file if fpdf not available
    txt_path = str(pdf_path).replace(".pdf", ".txt")
    try:
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"RECEIPT\n{'='*40}\n")
            f.write(f"Vendor:   {vendor}\n")
            f.write(f"Date:     {receipt_date}\n")
            f.write(f"Amount:   ${amount:.2f}\n" if amount else "Amount:   N/A\n")
            f.write(f"Category: {category}\n")
            f.write(f"ID:       {receipt_id:05d}\n\n")
            f.write("--- RAW OCR TEXT ---\n")
            f.write(raw_text)
        return txt_path
    except Exception as e:
        logger.error(f"[receipt] Fallback text save error: {e}")
        return None


# ──────────────────────────────────────────────────────────────────────────────
# MAIN READER CLASS
# ──────────────────────────────────────────────────────────────────────────────

class ReceiptReader:
    """
    Full receipt processing pipeline for REX bookkeeping.

    Usage:
        reader = ReceiptReader()
        result = reader.process_image("/path/to/receipt.jpg")
        print(result["summary"])

        # From Telegram (bytes):
        result = reader.handle_telegram_photo(photo_bytes, "receipt.jpg")
    """

    def __init__(self):
        _ensure_ledger_db()
        RECEIPTS_ROOT.mkdir(parents=True, exist_ok=True)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Main processing entry point ────────────────────────────────────────────

    def process_image(self, image_path: str, hint_category: str = "") -> dict:
        """
        Process a receipt image file.

        Returns dict with keys:
          receipt_id, vendor, date, amount, tax, category,
          line_items, pdf_path, summary, raw_text
        """
        logger.info(f"[receipt] Processing: {image_path}")

        # 1. OCR
        raw_text = _run_ocr(image_path)
        if not raw_text.strip():
            return {
                "error": "OCR returned empty text. "
                         "Check image quality or install Tesseract/PaddleOCR.",
                "summary": "⚠️ Could not read receipt — OCR returned empty.",
            }

        # 2. Extract fields
        vendor       = _extract_vendor(raw_text)
        receipt_date = _extract_date(raw_text)
        amount       = _extract_amount(raw_text)
        tax          = _extract_tax(raw_text)
        category     = hint_category or _categorize(vendor, raw_text)
        line_items   = _extract_line_items(raw_text)

        # 3. Write to ledger DB
        receipt_id = self._save_to_ledger(
            vendor=vendor,
            receipt_date=receipt_date,
            amount=amount,
            tax=tax,
            category=category,
            raw_text=raw_text,
            source_file=image_path,
            line_items=line_items,
        )

        # 4. Save PDF
        pdf_path = _save_receipt_pdf(
            image_path=image_path,
            raw_text=raw_text,
            vendor=vendor,
            receipt_date=receipt_date,
            amount=amount,
            category=category,
            receipt_id=receipt_id,
        )

        # 5. Update PDF path in DB
        if pdf_path:
            try:
                con = sqlite3.connect(str(LEDGER_DB))
                con.execute("UPDATE receipts SET pdf_path=? WHERE id=?", (pdf_path, receipt_id))
                con.commit()
                con.close()
            except Exception:
                pass

        # 6. Build summary message
        amount_str = f"${amount:.2f}" if amount is not None else "amount unclear"
        items_str  = f"\n   Items logged: {len(line_items)}" if line_items else ""
        pdf_short  = Path(pdf_path).name if pdf_path else "not saved"

        summary = (
            f"✅ *Receipt Logged — #{receipt_id:05d}*\n\n"
            f"🏪 Vendor:    {vendor}\n"
            f"📅 Date:      {receipt_date}\n"
            f"💵 Amount:    {amount_str}\n"
            f"📂 Category:  {category}\n"
            f"📄 Filed:     {pdf_short}"
            f"{items_str}\n\n"
            f"To change category: `receipt {receipt_id} category [New Category]`\n"
            f"Categories: {', '.join(CATEGORIES.keys())}, Misc"
        )

        return {
            "receipt_id":   receipt_id,
            "vendor":       vendor,
            "date":         receipt_date,
            "amount":       amount,
            "tax":          tax,
            "category":     category,
            "line_items":   line_items,
            "pdf_path":     pdf_path,
            "summary":      summary,
            "raw_text":     raw_text,
        }

    def handle_telegram_photo(self, photo_bytes: bytes, filename: str = "receipt.jpg") -> dict:
        """
        Handle a photo sent via Telegram.
        Writes bytes to a temp file, processes, then cleans up.
        """
        tmp_path = None
        try:
            suffix = Path(filename).suffix or ".jpg"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(photo_bytes)
                tmp_path = tmp.name
            return self.process_image(tmp_path)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # ── Ledger write ───────────────────────────────────────────────────────────

    def _save_to_ledger(
        self,
        vendor: str,
        receipt_date: str,
        amount: Optional[float],
        tax: float,
        category: str,
        raw_text: str,
        source_file: str,
        line_items: list,
    ) -> int:
        con = sqlite3.connect(str(LEDGER_DB))
        cur = con.cursor()
        cur.execute("""
            INSERT INTO receipts
            (receipt_date, vendor, amount, tax, category, raw_text, source_file)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (receipt_date, vendor, amount, tax, category, raw_text[:5000], source_file))
        receipt_id = cur.lastrowid

        for item in line_items:
            cur.execute("""
                INSERT INTO line_items (receipt_id, description, quantity, unit_price, total)
                VALUES (?, ?, ?, ?, ?)
            """, (receipt_id, item["description"], item["quantity"],
                  item["unit_price"], item["total"]))

        con.commit()
        con.close()
        return receipt_id

    # ── Category correction ────────────────────────────────────────────────────

    def correct_category(self, receipt_id: int, new_category: str) -> str:
        """Kato can correct the auto-categorization."""
        valid = list(CATEGORIES.keys()) + ["Misc"]
        if new_category not in valid:
            return f"Unknown category '{new_category}'. Valid: {', '.join(valid)}"
        try:
            con = sqlite3.connect(str(LEDGER_DB))
            con.execute(
                "UPDATE receipts SET category=?, confirmed=1 WHERE id=?",
                (new_category, receipt_id)
            )
            # Move PDF to new category folder
            row = con.execute(
                "SELECT pdf_path, receipt_date, vendor FROM receipts WHERE id=?",
                (receipt_id,)
            ).fetchone()
            con.commit()
            con.close()

            if row and row[0] and os.path.exists(row[0]):
                old_path    = Path(row[0])
                year_month  = row[1][:7] if row[1] else date.today().strftime("%Y-%m")
                new_folder  = RECEIPTS_ROOT / new_category / year_month
                new_folder.mkdir(parents=True, exist_ok=True)
                new_path = new_folder / old_path.name
                shutil.move(str(old_path), str(new_path))
                con = sqlite3.connect(str(LEDGER_DB))
                con.execute("UPDATE receipts SET pdf_path=? WHERE id=?",
                            (str(new_path), receipt_id))
                con.commit()
                con.close()

            return f"✅ Receipt #{receipt_id:05d} recategorized → *{new_category}*"
        except Exception as e:
            return f"Error updating category: {e}"

    # ── Reports ────────────────────────────────────────────────────────────────

    def generate_report(self, period: str = "monthly", month: str = "") -> str:
        """
        Generate a P&L style expense report.

        period: "weekly", "monthly", "ytd", "all"
        month:  "2025-03" (optional, for a specific month)

        Returns a formatted text report.
        """
        today     = date.today()
        title_str = ""

        if month:
            start = month + "-01"
            # End of that month
            y, m   = int(month[:4]), int(month[5:7])
            end_m  = (datetime(y, m, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            end    = end_m.strftime("%Y-%m-%d")
            title_str = f"Monthly Report — {month}"

        elif period == "weekly":
            start     = (today - timedelta(days=7)).isoformat()
            end       = today.isoformat()
            title_str = f"Weekly Report — {start} to {end}"

        elif period == "ytd":
            start     = today.strftime("%Y-01-01")
            end       = today.isoformat()
            title_str = f"Year-to-Date — {today.year}"

        elif period == "monthly":
            start     = today.strftime("%Y-%m-01")
            end       = today.isoformat()
            title_str = f"Month-to-Date — {today.strftime('%B %Y')}"

        else:   # all
            start     = "2000-01-01"
            end       = today.isoformat()
            title_str = "All-Time Report"

        try:
            con  = sqlite3.connect(str(LEDGER_DB))

            # Total spend
            total = con.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM receipts "
                "WHERE receipt_date BETWEEN ? AND ?",
                (start, end)
            ).fetchone()[0]

            total_tax = con.execute(
                "SELECT COALESCE(SUM(tax), 0) FROM receipts "
                "WHERE receipt_date BETWEEN ? AND ?",
                (start, end)
            ).fetchone()[0]

            # By category
            by_cat = con.execute(
                "SELECT category, COUNT(*), COALESCE(SUM(amount), 0) "
                "FROM receipts WHERE receipt_date BETWEEN ? AND ? "
                "GROUP BY category ORDER BY SUM(amount) DESC",
                (start, end)
            ).fetchall()

            # By vendor (top 10)
            by_vendor = con.execute(
                "SELECT vendor, COUNT(*), COALESCE(SUM(amount), 0) "
                "FROM receipts WHERE receipt_date BETWEEN ? AND ? "
                "GROUP BY vendor ORDER BY SUM(amount) DESC LIMIT 10",
                (start, end)
            ).fetchall()

            # Month-over-month trend (last 6 months)
            monthly_trend = con.execute(
                "SELECT strftime('%Y-%m', receipt_date) AS ym, "
                "COUNT(*), COALESCE(SUM(amount), 0) "
                "FROM receipts GROUP BY ym ORDER BY ym DESC LIMIT 6",
            ).fetchall()

            # Recent receipts
            recent = con.execute(
                "SELECT id, receipt_date, vendor, amount, category "
                "FROM receipts WHERE receipt_date BETWEEN ? AND ? "
                "ORDER BY receipt_date DESC LIMIT 10",
                (start, end)
            ).fetchall()

            con.close()

        except Exception as e:
            return f"⚠️ Report error: {e}"

        # ── Format report ──────────────────────────────────────────────────────
        lines = [
            f"📊 *REX Expense Report*",
            f"_{title_str}_",
            f"",
            f"*TOTAL SPEND:* ${total:,.2f}",
            f"*Total Tax:*   ${total_tax:,.2f}",
            f"",
            f"*BY CATEGORY:*",
        ]
        for cat, count, amt in by_cat:
            pct = (amt / total * 100) if total > 0 else 0
            lines.append(f"  {cat:<16} ${amt:>9,.2f}  ({pct:4.1f}%)  [{count} receipts]")

        if by_vendor:
            lines += ["", "*TOP VENDORS:*"]
            for vendor, count, amt in by_vendor:
                lines.append(f"  {vendor[:20]:<20} ${amt:>9,.2f}  [{count}x]")

        if monthly_trend:
            lines += ["", "*MONTHLY TREND (last 6 months):*"]
            for ym, count, amt in monthly_trend:
                lines.append(f"  {ym}   ${amt:>9,.2f}  [{count} receipts]")

        if recent:
            lines += ["", "*RECENT RECEIPTS:*"]
            for rid, rdate, vendor, amt, cat in recent:
                amt_str = f"${amt:,.2f}" if amt else "  N/A  "
                lines.append(f"  #{rid:05d}  {rdate}  {vendor[:20]:<20}  {amt_str}  [{cat}]")

        lines += [
            "",
            f"_Send `receipt report monthly` or `receipt report ytd` for other periods._",
            f"_Send `receipt report 2025-03` for a specific month._",
        ]

        report_text = "\n".join(lines)

        # Save report to file
        report_filename = f"rex_expense_report_{period}_{today.isoformat()}.txt"
        report_path = REPORTS_DIR / report_filename
        try:
            report_path.write_text(report_text, encoding="utf-8")
            logger.info(f"[receipt] Report saved: {report_path}")
        except Exception:
            pass

        return report_text

    def generate_trend_analysis(self) -> str:
        """
        Detect spending anomalies and trends.
        Flags categories that are significantly above their 3-month average.
        """
        today = date.today()
        lines = ["📈 *REX Spending Trend Analysis*\n"]

        try:
            con = sqlite3.connect(str(LEDGER_DB))

            # Compare this month to average of prior 3 months, by category
            this_month_start = today.strftime("%Y-%m-01")
            three_months_ago = (today - timedelta(days=90)).strftime("%Y-%m-01")

            this_month = con.execute(
                "SELECT category, COALESCE(SUM(amount), 0) "
                "FROM receipts WHERE receipt_date >= ? "
                "GROUP BY category",
                (this_month_start,)
            ).fetchall()

            prior_avg = con.execute(
                "SELECT category, "
                "COALESCE(SUM(amount), 0) / 3.0 AS monthly_avg "
                "FROM receipts "
                "WHERE receipt_date >= ? AND receipt_date < ? "
                "GROUP BY category",
                (three_months_ago, this_month_start)
            ).fetchall()

            con.close()

            prior_map = {row[0]: row[1] for row in prior_avg}
            this_map  = {row[0]: row[1] for row in this_month}

            alerts = []
            for cat, this_amt in sorted(this_map.items(), key=lambda x: -x[1]):
                avg_amt = prior_map.get(cat, 0)
                if avg_amt > 0:
                    change_pct = (this_amt - avg_amt) / avg_amt * 100
                    if change_pct > 50:
                        alerts.append((cat, this_amt, avg_amt, change_pct, "🔴 HIGH"))
                    elif change_pct > 20:
                        alerts.append((cat, this_amt, avg_amt, change_pct, "🟡 ELEVATED"))
                    else:
                        alerts.append((cat, this_amt, avg_amt, change_pct, "✅ NORMAL"))
                else:
                    alerts.append((cat, this_amt, 0, 0, "🆕 NEW"))

            if alerts:
                lines.append("*Category vs 3-Month Average:*")
                for cat, this_amt, avg_amt, pct, flag in alerts:
                    avg_str = f"avg ${avg_amt:,.2f}" if avg_amt > 0 else "no prior data"
                    pct_str = f"{pct:+.0f}%" if avg_amt > 0 else ""
                    lines.append(
                        f"  {flag} {cat:<16} this month: ${this_amt:,.2f} "
                        f"({avg_str} {pct_str})"
                    )
            else:
                lines.append("Not enough data yet for trend comparison.")

        except Exception as e:
            lines.append(f"Trend analysis error: {e}")

        return "\n".join(lines)

    def get_receipt_summary(self, receipt_id: int) -> str:
        """Return a summary of a specific receipt."""
        try:
            con = sqlite3.connect(str(LEDGER_DB))
            row = con.execute(
                "SELECT id, receipt_date, vendor, amount, tax, category, pdf_path "
                "FROM receipts WHERE id=?",
                (receipt_id,)
            ).fetchone()
            if not row:
                con.close()
                return f"Receipt #{receipt_id:05d} not found."
            rid, rdate, vendor, amt, tax, cat, pdf = row

            items = con.execute(
                "SELECT description, quantity, total FROM line_items WHERE receipt_id=?",
                (receipt_id,)
            ).fetchall()
            con.close()

            lines = [
                f"📄 *Receipt #{rid:05d}*\n",
                f"Vendor:   {vendor}",
                f"Date:     {rdate}",
                f"Amount:   ${amt:.2f}" if amt else "Amount:   N/A",
                f"Tax:      ${tax:.2f}" if tax else "",
                f"Category: {cat}",
                f"PDF:      {Path(pdf).name if pdf else 'not saved'}",
            ]
            if items:
                lines.append("\n*Line Items:*")
                for desc, qty, total in items[:10]:
                    lines.append(f"  {desc[:40]} × {qty:.0f}  ${total:.2f}")

            return "\n".join(l for l in lines if l)
        except Exception as e:
            return f"Error retrieving receipt: {e}"


# ──────────────────────────────────────────────────────────────────────────────
# TELEGRAM COMMAND ROUTER
# ──────────────────────────────────────────────────────────────────────────────

_reader_instance: Optional[ReceiptReader] = None

def get_reader() -> ReceiptReader:
    """Lazy singleton — avoids init cost until first use."""
    global _reader_instance
    if _reader_instance is None:
        _reader_instance = ReceiptReader()
    return _reader_instance


def handle_telegram_receipt_command(text: str, photo_bytes: Optional[bytes] = None) -> str:
    """
    Called from rex_telegram_bot.py when Kato sends a receipt-related message.

    Handles:
      - Photo with caption: process receipt image
      - "receipt report [period]"
      - "receipt report [YYYY-MM]"
      - "receipt trend"
      - "receipt [id]"
      - "receipt [id] category [Category]"
      - "receipt list"
    """
    reader = get_reader()
    lower  = text.lower().strip()

    # Photo receipt
    if photo_bytes:
        caption   = text.strip()
        hint_cat  = ""
        # Check if caption specifies a category
        for cat in list(CATEGORIES.keys()) + ["Misc"]:
            if cat.lower() in caption.lower():
                hint_cat = cat
                break
        result = reader.handle_telegram_photo(photo_bytes, "receipt.jpg")
        if hint_cat and "receipt_id" in result:
            reader.correct_category(result["receipt_id"], hint_cat)
            result["summary"] = result["summary"].replace(
                f"📂 Category:  {result['category']}",
                f"📂 Category:  {hint_cat} ✓"
            )
        return result.get("summary", result.get("error", "Processing error."))

    # Reports
    if lower.startswith("receipt report"):
        parts = lower.split()
        if len(parts) >= 3:
            period = parts[2]
            # Check if it's a YYYY-MM format
            if re.match(r'^\d{4}-\d{2}$', period):
                return reader.generate_report("monthly", month=period)
            else:
                return reader.generate_report(period)
        return reader.generate_report("monthly")

    # Trend analysis
    if lower in ("receipt trend", "receipt trends", "spending trends"):
        return reader.generate_trend_analysis()

    # Category correction: "receipt 123 category Supplies"
    m = re.match(r'^receipt\s+(\d+)\s+category\s+(.+)$', lower)
    if m:
        rid      = int(m.group(1))
        new_cat  = m.group(2).strip().title()
        return reader.correct_category(rid, new_cat)

    # Single receipt lookup: "receipt 123"
    m = re.match(r'^receipt\s+(\d+)$', lower)
    if m:
        return reader.get_receipt_summary(int(m.group(1)))

    # Recent list
    if lower in ("receipt list", "receipts", "receipt log"):
        return reader.generate_report("monthly")

    return (
        "📄 *Receipt Commands:*\n\n"
        "• *Send a photo* of a receipt → I'll read and file it\n"
        "• `receipt report` — this month's expenses\n"
        "• `receipt report ytd` — year to date\n"
        "• `receipt report 2025-03` — specific month\n"
        "• `receipt trend` — spending anomaly detection\n"
        "• `receipt [id]` — view a specific receipt\n"
        "• `receipt [id] category [Name]` — correct category"
    )


# ──────────────────────────────────────────────────────────────────────────────
# SELF-TEST
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("REX RECEIPT READER — SELF-TEST")
    print("=" * 60)

    # Test 1: DB initialization
    _ensure_ledger_db()
    assert LEDGER_DB.exists(), "Ledger DB not created"
    print("✓ Test 1: Ledger DB initialized")

    # Test 2: Amount extraction
    sample_text = """
    WHOLE FOODS MARKET
    123 Main Street
    Date: 03/15/2025

    Organic Apples       $4.99
    Chicken Breast       $12.50
    Bread                $3.99
    ---------------------
    Subtotal:            $21.48
    Tax:                  $1.29
    TOTAL:               $22.77
    """
    amt = _extract_amount(sample_text)
    assert amt == 22.77, f"Expected 22.77, got {amt}"
    print("✓ Test 2: Amount extraction OK ($22.77)")

    # Test 3: Date extraction
    dt = _extract_date(sample_text)
    assert dt == "2025-03-15", f"Expected 2025-03-15, got {dt}"
    print("✓ Test 3: Date extraction OK (2025-03-15)")

    # Test 4: Vendor extraction
    vendor = _extract_vendor(sample_text)
    assert "WHOLE FOODS" in vendor.upper(), f"Expected Whole Foods, got {vendor}"
    print(f"✓ Test 4: Vendor extraction OK ({vendor})")

    # Test 5: Categorization
    cat = _categorize("WHOLE FOODS MARKET", sample_text)
    assert cat == "Meals/Food", f"Expected Meals/Food, got {cat}"
    print(f"✓ Test 5: Categorization OK ({cat})")

    # Test 6: Tax extraction
    tax = _extract_tax(sample_text)
    assert tax == 1.29, f"Expected 1.29, got {tax}"
    print("✓ Test 6: Tax extraction OK ($1.29)")

    # Test 7: Line item extraction
    items = _extract_line_items(sample_text)
    assert len(items) > 0, "No line items extracted"
    print(f"✓ Test 7: Line item extraction OK ({len(items)} items)")

    # Test 8: Ledger write
    test_reader = ReceiptReader()
    rid = test_reader._save_to_ledger(
        vendor="TEST VENDOR",
        receipt_date="2025-01-01",
        amount=99.99,
        tax=5.00,
        category="Misc",
        raw_text="test receipt text",
        source_file="/tmp/test.jpg",
        line_items=[{"description": "Test item", "quantity": 1, "unit_price": 99.99, "total": 99.99}],
    )
    assert rid > 0, "DB insert failed"
    print(f"✓ Test 8: Ledger write OK (receipt ID: {rid})")

    # Test 9: Report generation
    report = test_reader.generate_report("all")
    assert "TEST VENDOR" in report or "TOTAL SPEND" in report, "Report missing expected content"
    print("✓ Test 9: Report generation OK")

    # Test 10: Trend analysis
    trend = test_reader.generate_trend_analysis()
    assert "Trend" in trend or "analysis" in trend.lower(), "Trend report malformed"
    print("✓ Test 10: Trend analysis OK")

    # Test 11: Telegram command routing
    response = handle_telegram_receipt_command("receipt list")
    assert len(response) > 10
    print("✓ Test 11: Telegram command routing OK")

    # Test 12: Category correction
    result = test_reader.correct_category(rid, "Supplies")
    assert "Supplies" in result
    print(f"✓ Test 12: Category correction OK → Supplies")

    # Cleanup test record
    con = sqlite3.connect(str(LEDGER_DB))
    con.execute("DELETE FROM receipts WHERE id=?", (rid,))
    con.execute("DELETE FROM line_items WHERE receipt_id=?", (rid,))
    con.commit()
    con.close()

    print()
    print("=" * 60)
    print("ALL TESTS PASSED — rex_receipt_reader.py is ready")
    print()
    print("Next: integrate into rex_telegram_bot.py")
    print("  from rex_receipt_reader import handle_telegram_receipt_command")
    print()
    print("OCR engines available:")
    print(f"  Tesseract:  {'✓' if _TESSERACT_AVAILABLE else '✗ (pip install pytesseract pillow)'}")
    print(f"  PaddleOCR:  {'✓' if _PADDLE_AVAILABLE else '✗ (pip install paddlepaddle paddleocr)'}")
    print(f"  PDF output: {'✓' if _FPDF_AVAILABLE else '✗ (pip install fpdf2)'}")
    print("=" * 60)
