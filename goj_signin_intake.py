#!/usr/bin/env python3
"""
GOJ Document Intake — goj_signin_intake.py
==========================================
Universal drop zone for all scanned GOJ forms.
Drop any scan PDF into ~/Desktop/REX/signins/ — this script
identifies what it is and routes it to the right place.

Sheet types and destinations:
  • signin   → ~/Desktop/REX/              GOJ_M_S1_Monday_signin.pdf
  • drivers  → ~/Desktop/REX/              GOJ_M_S1_Monday_drivers.pdf
  • menu     → ~/Documents/goj files/dashboard/documents/menus/
                                            menu_YYYY-MM-DD_S{shift}.pdf
  • auth     → ~/Documents/goj files/dashboard/documents/authorization/<ClientName>/
               Staging if name unknown:    ~/Documents/goj files/dashboard/documents/authorization/_incoming/
               (run_auth_linker.py picks them up and registers in DB)
  • kitchen  → ~/Desktop/REX/              GOJ_M_S1_Monday_kitchen.pdf
  • unknown  → flagged for manual review (file NOT moved)

Detection strategy:
  1. pdfplumber — works when scanner firmware adds a text layer (fastest)
  2. pymupdf    — fallback text extractor
  3. Paperless  — submits to Paperless-NGX (100.99.86.60:8000) for OCR
                  same instance used by goj_signin_ocr_processor.py

Usage:
    python3 goj_signin_intake.py               # process all pending PDFs in signins/
    python3 goj_signin_intake.py --watch       # loop every 10s, auto-process new arrivals
    python3 goj_signin_intake.py --dry-run     # show what would happen, write nothing
    python3 goj_signin_intake.py path/to/file  # process one specific file
"""

import json
import os
import re
import sys
import shutil
import sqlite3
import time
import logging
import difflib
import urllib.request
from pathlib import Path
from datetime import datetime, date

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("signin_intake")

# ── V4 Rexonasence patch — event emission + content staging ───────────────────
try:
    from goj_signin_intake_v4_patch import (
        emit_doc_event, emit_russian_found, emit_ocr_fallback,
        route_ambiguous_doc, route_low_confidence_doc,
        ContentUpdateQueue,
    )
    from rex_events import EventType as _EventType
    _content_queue = ContentUpdateQueue()
    _V4_INTAKE_OK = True
except Exception as _v4_intake_err:
    _V4_INTAKE_OK = False
    _content_queue = None
    log.debug(f"[v4] intake patch not loaded (non-fatal): {_v4_intake_err}")
    def emit_doc_event(*_a, **_kw): pass       # type: ignore
    def emit_russian_found(*_a, **_kw): pass   # type: ignore
    def emit_ocr_fallback(*_a, **_kw): pass    # type: ignore
    def route_ambiguous_doc(*_a, **_kw): return 0  # type: ignore
    def route_low_confidence_doc(*_a, **_kw): return 0  # type: ignore

# ── Paths ──────────────────────────────────────────────────────────────────────
REX_DIR     = Path(__file__).resolve().parent
SIGNINS_DIR = REX_DIR / "signins"
SIGNIN_OUT  = REX_DIR
MENUS_OUT   = Path.home() / "Documents" / "goj files" / "dashboard" / "documents" / "menus"
AUTH_OUT    = Path.home() / "Documents" / "goj files" / "dashboard" / "documents" / "authorization"
AUTH_STAGE  = AUTH_OUT / "_incoming"          # staging when client name is unknown
AUTH_DB     = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
DONE_LOG    = SIGNINS_DIR / ".processed.json"

# ── Paperless ──────────────────────────────────────────────────────────────────
PAPERLESS_URL     = "http://100.99.86.60:8000"
PAPERLESS_TOKEN   = "583e819be1146b96b935007c6ad7f584a3a1b1b7"
PAPERLESS_HEADERS = {"Authorization": f"Token {PAPERLESS_TOKEN}"}

# ── Sheet detection keywords ───────────────────────────────────────────────────

SIGNIN_KEYWORDS = [
    "SIGN-IN SHEET", "SIGN IN SHEET",
    "GARDEN OF JOY ADULT DAY CARE CENTER",
    "Insurance Plan", "Total present", "Staff signature", "SIGN-IN",
    "CH", "TR",
    # 5.14 template (2026-05-14) added Time In / Time Out, dropped CH, header "Plan"
    "Time In", "Time Out", "Plan",
]

DRIVER_KEYWORDS = [
    "ROUTE \u2014", "ROUTE -", "ROUTE:",
    "Driver:", "Driver Name", "Driver Signature",
    "Total clients",
]

MENU_KEYWORDS = [
    # Russian food items that appear on filled client menu forms
    "\u0431\u043e\u0440\u0449",                             # борщ
    "\u0441\u0443\u043f",                                   # суп
    "\u043a\u043e\u0442\u043b\u0435\u0442\u0430",          # котлета
    "\u0441\u0430\u043b\u0430\u0442",                       # салат
    "\u0440\u044b\u0431\u0430",                             # рыба
    "\u043a\u0443\u0440\u0438\u0446\u0430",                # курица
    "\u043a\u0430\u0448\u0430",                             # каша
    "\u043c\u0435\u043d\u044e",                             # меню
    # English markers
    "Salad Choice", "Soup Choice", "Main Choice",
    "Weekly Menu", "MENU ORDER", "Menu Order Form",
    "GOJ Weekly Menu", "FOOD PREFERENCE",
    "Mon", "Tue", "Wed", "Thu", "Fri",   # day columns on menu form
]

KITCHEN_KEYWORDS = [
    "KITCHEN PREP ORDER", "KITCHEN PREP",
    "QTY", "Prepped", "Served", "SALADS", "SECTION",
]

DISTRIBUTION_KEYWORDS = [
    "FOOD DISTRIBUTION SHEET", "FOOD DISTRIBUTION",
    "Check box after each delivery", "Main + Side",
]

AUTH_KEYWORDS = [
    # Insurance authorization letter markers
    "Authorization", "Auth Number", "Auth #", "Authorization Number",
    "Prior Authorization", "PA Number",
    "Member ID", "Member Number", "Member Name",
    "Effective Date", "Authorization Period",
    "Units Authorized", "Visits Authorized",
    "Adult Day", "Adult Day Care", "Day Health Program",
    "Garden of Joy",
    # Insurer names
    "Anthem", "Molina", "HealthFirst", "SWH", "Aetna",
    "Centene", "WellCare",
    "MetroPlus", "EmblemHealth",
    # Auth doc structural terms
    "ICD-10", "Diagnosis Code", "NPI", "Provider Number",
    "Date of Service", "Level of Care", "Service Type",
]

SKIP_KEYWORDS = [
    "Policies and Procedures", "Fire Drill", "Incident Report",
    "Staff Training", "HIPAA Notice",
]

SHEET_KEYWORD_MAP = {
    "signin":       SIGNIN_KEYWORDS,
    "drivers":      DRIVER_KEYWORDS,
    "menu":         MENU_KEYWORDS,
    "kitchen":      KITCHEN_KEYWORDS,
    "distribution": DISTRIBUTION_KEYWORDS,
    "auth":         AUTH_KEYWORDS,
}

# ── Day / month ────────────────────────────────────────────────────────────────
DOW_TO_ABBREV = {
    0: ("M", "Monday"), 1: ("T", "Tuesday"), 2: ("W", "Wednesday"),
    3: ("TH", "Thursday"), 4: ("F", "Friday"),
    5: ("Sa", "Saturday"), 6: ("Su", "Sunday"),
}
MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


# ── Text extraction ────────────────────────────────────────────────────────────

def extract_text_pdfplumber(path: Path) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            return "\n".join(p.extract_text() or "" for p in pdf.pages)
    except ImportError:
        return ""
    except Exception as e:
        log.debug(f"pdfplumber: {e}")
        return ""


def extract_text_pymupdf(path: Path) -> str:
    try:
        import fitz
        doc = fitz.open(str(path))
        return "\n".join(page.get_text() for page in doc)
    except ImportError:
        return ""
    except Exception as e:
        log.debug(f"pymupdf: {e}")
        return ""


def extract_text_paperless(path: Path) -> str:
    """Upload to Paperless-NGX, wait for OCR, return text, then delete temp doc.

    FAIL-FAST: Paperless lives over Tailscale; when that host is down it used to
    hang the whole intake (~120s/file → 600s launchd timeout). We now probe it in
    3s and skip immediately if unreachable, so local OCR stays the fast path."""
    try:
        import urllib.request as _u
        _u.urlopen(_u.Request(f"{PAPERLESS_URL}/api/", headers=PAPERLESS_HEADERS), timeout=3).read(1)
    except Exception:
        log.info("  Paperless unreachable (3s probe) — skipping, staying local-first")
        return ""
    try:
        log.info("  → Submitting to Paperless OCR (15-60s)...")
        # Use requests for multipart upload — avoids urllib boundary encoding issues (HTTP 415)
        try:
            import requests as _req
            with open(path, "rb") as fh:
                r = _req.post(
                    f"{PAPERLESS_URL}/api/documents/post_document/",
                    headers={"Authorization": f"Token {PAPERLESS_TOKEN}"},
                    files={"document": (path.name, fh, "application/pdf")},
                    timeout=30,
                )
            r.raise_for_status()
            raw_resp = r.content
        except ImportError:
            # Fallback to urllib if requests isn't installed
            import email.generator, email.mime.multipart, email.mime.application
            boundary = "GOJIntakeBoundary20260412"
            file_data = path.read_bytes()
            body = (
                f"--{boundary}\r\n"
                f"Content-Disposition: form-data; name=\"document\"; filename=\"{path.name}\"\r\n"
                f"Content-Type: application/pdf\r\n\r\n"
            ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()
            req = urllib.request.Request(
                f"{PAPERLESS_URL}/api/documents/post_document/",
                data=body, method="POST",
            )
            req.add_header("Authorization", f"Token {PAPERLESS_TOKEN}")
            req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
            with urllib.request.urlopen(req, timeout=30) as r2:
                raw_resp = r2.read()
        try:
            resp = json.loads(raw_resp)
        except Exception:
            # Paperless-NGX ≥1.17 returns a plain task UUID string, not JSON dict
            resp = raw_resp.decode().strip().strip('"')

        # Handle both old (dict) and new (plain-string UUID) Paperless responses
        if isinstance(resp, str):
            task_id = resp if resp else None
        elif isinstance(resp, dict):
            task_id = resp.get("task_id") or resp.get("id")
        else:
            task_id = None
        if not task_id:
            log.warning("  Paperless: no task_id in response")
            return ""

        doc_id = None
        for _ in range(8):          # ~32s cap (was 120s) — fail-fast if OCR stalls
            time.sleep(4)
            try:
                with urllib.request.urlopen(
                    urllib.request.Request(
                        f"{PAPERLESS_URL}/api/tasks/?task_id={task_id}",
                        headers=PAPERLESS_HEADERS,
                    ), timeout=15
                ) as r:
                    tasks = json.loads(r.read())
                if isinstance(tasks, list) and tasks:
                    task = tasks[0]
                    if task.get("status") == "SUCCESS":
                        doc_id = task.get("related_document")
                        break
                    elif task.get("status") in ("FAILURE", "REVOKED"):
                        log.warning(f"  Paperless task failed: {task.get('result')}")
                        return ""
            except Exception:
                pass

        if not doc_id:
            log.warning("  Paperless timed out — no doc ID returned")
            return ""

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{PAPERLESS_URL}/api/documents/{doc_id}/",
                headers=PAPERLESS_HEADERS,
            ), timeout=15
        ) as r:
            doc = json.loads(r.read())
        text = doc.get("content", "")

        # Delete temp doc from Paperless
        try:
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{PAPERLESS_URL}/api/documents/{doc_id}/",
                    method="DELETE", headers=PAPERLESS_HEADERS,
                ), timeout=10
            )
        except Exception:
            pass

        return text

    except Exception as e:
        log.warning(f"  Paperless error: {e}")
        return ""


def extract_mineru_via_paperless(path: Path) -> str:
    """
    Upload to Paperless (storage/archiving), then parse with MinerU instead of
    Paperless's built-in OCR. Paperless handles document management; MinerU
    handles structured extraction (tables, Cyrillic, multi-column).
    
    Flow: Upload → Paperless stores → MinerU parses local file → return markdown.
    """
    # Step 1: Upload to Paperless for archiving
    try:
        import urllib.request as _u
        _u.urlopen(_u.Request(f"{PAPERLESS_URL}/api/", headers=PAPERLESS_HEADERS), timeout=3).read(1)
    except Exception:
        log.info("  Paperless unreachable — falling back to local MinerU")
        return _try_mineru(path)
    
    try:
        import requests as _req
        log.info("  → Uploading to Paperless (archive) + MinerU parse...")
        with open(path, "rb") as fh:
            r = _req.post(
                f"{PAPERLESS_URL}/api/documents/post_document/",
                headers={"Authorization": f"Token {PAPERLESS_TOKEN}"},
                files={"document": (path.name, fh, "application/pdf")},
                timeout=30,
            )
        r.raise_for_status()
        log.info("  ✓ Archived in Paperless")
    except Exception as e:
        log.warning(f"  Paperless upload failed: {e} — parsing locally only")
    
    # Step 2: Parse with MinerU on the local file
    return _try_mineru(path)


def _try_mineru(path: Path) -> str:
    """Try MinerU pipeline backend. Returns markdown text or ''."""
    try:
        from CC_mineru_parse import parse_pdf
        log.info("  → MinerU pipeline (CPU) — parsing document...")
        result = parse_pdf(str(path))
        if result.get("md_path") and not result.get("error"):
            md_text = Path(result["md_path"]).read_text(encoding="utf-8")
            if len(md_text.strip()) > 30:
                log.info(f"  ✓ MinerU: {result['pages']} pages, {result['elements']} elements, {result['elapsed_s']}s")
                return md_text
        log.warning(f"  MinerU failed: {result.get('error', 'no text extracted')}")
    except ImportError:
        log.info("  MinerU not installed (CC_mineru_parse.py not found) — skipping")
    except Exception as e:
        log.warning(f"  MinerU error: {e}")
    return ""


def extract_text_tesseract(path: Path) -> str:
    """Local Tesseract OCR — works offline, no Tailscale needed.
    Uses PyMuPDF (fitz) to render pages — no poppler/pdf2image required."""
    try:
        import pytesseract
        import fitz  # PyMuPDF — already in debate-chamber venv, no poppler needed
        from PIL import Image
        import io as _io
        log.info("  → Running local Tesseract OCR...")
        doc = fitz.open(str(path))
        mat = fitz.Matrix(300 / 72, 300 / 72)  # 300 dpi
        texts = []
        for page in doc:
            pix = page.get_pixmap(matrix=mat)
            img = Image.open(_io.BytesIO(pix.tobytes("png")))
            # Try English + Russian (covers GOJ menus and sign-in sheets)
            try:
                text = pytesseract.image_to_string(img, lang="eng+rus")
            except Exception:
                text = pytesseract.image_to_string(img, lang="eng")
            texts.append(text)
        result = "\n".join(texts).strip()
        if result:
            log.info(f"  ✅ Tesseract extracted {len(result)} chars")
        return result
    except ImportError as e:
        log.debug(f"  Tesseract skipped — missing dependency: {e}")
        return ""
    except Exception as e:
        log.warning(f"  Tesseract error: {e}")
        return ""


def extract_text_claude_vision(path: Path) -> str:
    """
    Claude Vision OCR — reads handwritten and low-quality scanned PDFs.
    Converts each page to a JPEG via PyMuPDF (no poppler needed) and asks
    Claude to transcribe all visible text.
    Used as last-resort fallback when Tesseract and Paperless both fail.
    """
    try:
        import base64
        import fitz   # PyMuPDF — no poppler/pdf2image required
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY") or _load_api_key_from_env()
        client  = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

        log.info("  → Claude Vision: converting PDF to images (PyMuPDF)...")
        doc = fitz.open(str(path))
        mat = fitz.Matrix(200 / 72, 200 / 72)  # 200 dpi
        all_text = []

        for i, fitz_page in enumerate(doc):
            pix = fitz_page.get_pixmap(matrix=mat)
            b64 = base64.standard_b64encode(pix.tobytes("jpeg")).decode("utf-8")

            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2000,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
                        },
                        {
                            "type": "text",
                            "text": (
                                "Transcribe ALL text visible in this scanned document page. "
                                "This is a Garden of Joy Adult Day Care Center form. "
                                "Include every word, name, date, checkbox label, and number you can see. "
                                "Preserve the original layout as much as possible. "
                                "If handwritten names or Russian (Cyrillic) text are present, "
                                "include them exactly as written. "
                                "Return ONLY the transcribed text, nothing else."
                            ),
                        },
                    ],
                }],
            )
            page_text = resp.content[0].text.strip()
            if page_text:
                all_text.append(page_text)
                log.debug(f"  Claude Vision page {i+1}: {len(page_text)} chars")

        result = "\n\n".join(all_text)
        if result:
            log.info(f"  ✅ Claude Vision extracted {len(result)} chars")
        return result

    except ImportError as e:
        log.debug(f"  Claude Vision skipped — missing dependency: {e}")
        return ""
    except Exception as e:
        log.warning(f"  Claude Vision error: {e}")
        return ""


def _extract_doc_features(path: Path, text: str) -> dict:
    """
    Extract a compact feature fingerprint from a document for pattern learning.
    These features are stored so future identical / similar docs auto-classify.
    """
    import unicodedata
    features: dict = {}

    # ── File attributes ───────────────────────────────────────────────────────
    features["filename_stem"] = path.stem.lower()
    features["file_size_kb"]  = round(path.stat().st_size / 1024, 1) if path.exists() else 0

    # ── Text stats ────────────────────────────────────────────────────────────
    features["char_count"]    = len(text)
    features["line_count"]    = len([l for l in text.splitlines() if l.strip()])

    # Cyrillic ratio (Russian docs score high)
    cyr = sum(1 for c in text if unicodedata.name(c, "").startswith("CYRILLIC"))
    features["cyrillic_ratio"] = round(cyr / max(len(text), 1), 3)

    # ── Keyword signals ───────────────────────────────────────────────────────
    upper = text.upper()
    features["has_auth_keywords"]  = any(k.upper() in upper for k in AUTH_KEYWORDS[:8])
    features["has_menu_keywords"]  = any(k.upper() in upper for k in MENU_KEYWORDS[:8])
    features["has_signin_keywords"]= any(k.upper() in upper for k in SIGNIN_KEYWORDS[:6])
    features["has_driver_keywords"]= any(k.upper() in upper for k in DRIVER_KEYWORDS[:5])

    # Top 12 non-trivial words (4+ chars, alpha only)
    words = [w.lower() for w in re.findall(r"[A-Za-zА-Яа-яЁё]{4,}", text)]
    freq: dict = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    features["top_words"] = sorted(freq, key=lambda w: -freq[w])[:12]

    # Checkbox / checkmark density
    checkmarks = sum(text.count(c) for c in "✓✔☑☒□■✕✗✘xхXХ+*")
    features["checkmark_density"] = round(checkmarks / max(features["line_count"], 1), 2)

    return features


def _score_pattern_match(features: dict, pattern: dict) -> float:
    """
    Compare current document features against a saved learned pattern.
    Returns a confidence score 0.0 – 1.0.
    """
    score = 0.0
    total = 0.0

    # Cyrillic ratio similarity (within 0.15 band)
    diff = abs(features.get("cyrillic_ratio", 0) - pattern.get("cyrillic_ratio", 0))
    score += max(0, 1 - diff / 0.15) * 2.0; total += 2.0

    # Keyword boolean matches
    for k in ("has_auth_keywords", "has_menu_keywords", "has_signin_keywords", "has_driver_keywords"):
        if features.get(k) == pattern.get(k):
            score += 1.0
        total += 1.0

    # Top word overlap
    a_words = set(features.get("top_words", []))
    b_words = set(pattern.get("top_words", []))
    if a_words and b_words:
        overlap = len(a_words & b_words) / max(len(a_words | b_words), 1)
        score += overlap * 3.0; total += 3.0

    # Checkmark density proximity
    cd_diff = abs(features.get("checkmark_density", 0) - pattern.get("checkmark_density", 0))
    score += max(0, 1 - cd_diff) * 1.0; total += 1.0

    return round(score / total, 3) if total > 0 else 0.0


def _check_learned_patterns(path: Path, text: str) -> str | None:
    """
    Check if the document matches a previously learned classification pattern.
    Returns the doc type string ('menu', 'signin', etc.) if confidence ≥ 0.72, else None.
    """
    patterns_path = REX_DIR / "goj_doc_patterns.json"
    if not patterns_path.exists():
        return None
    try:
        patterns = json.loads(patterns_path.read_text())
    except Exception:
        return None

    if not patterns:
        return None

    features = _extract_doc_features(path, text)
    best_type  = None
    best_score = 0.0

    for p in patterns:
        s = _score_pattern_match(features, p.get("features", {}))
        if s > best_score:
            best_score = s
            best_type  = p.get("doc_type")

    CONFIDENCE_THRESHOLD = 0.72
    if best_score >= CONFIDENCE_THRESHOLD:
        log.info(f"  🧠 Pattern match: '{best_type}' (confidence {best_score:.0%}) — auto-classifying")
        return best_type
    return None


def _save_learned_pattern(path: Path, text: str, doc_type: str):
    """
    Save a confirmed document classification as a learned pattern.
    Future documents with similar features will auto-classify.
    """
    patterns_path = REX_DIR / "goj_doc_patterns.json"
    try:
        patterns = json.loads(patterns_path.read_text()) if patterns_path.exists() else []
    except Exception:
        patterns = []

    features = _extract_doc_features(path, text)
    entry = {
        "doc_type":   doc_type,
        "filename":   path.name,
        "learned_at": datetime.now().isoformat(),
        "features":   features,
    }
    patterns.append(entry)

    # Keep last 200 patterns — rolling window
    if len(patterns) > 200:
        patterns = patterns[-200:]

    try:
        patterns_path.write_text(json.dumps(patterns, indent=2, ensure_ascii=False))
        log.info(f"  🧠 Learned pattern saved: '{doc_type}' ({path.name})")
    except Exception as e:
        log.warning(f"  _save_learned_pattern: {e}")


def _save_pending_classification(path: Path, reason: str, text: str) -> str:
    """
    Save a pending document to the classification queue.
    Returns the short key (8-char hash) used in callback data.
    """
    import hashlib
    key = hashlib.sha1(str(path).encode()).hexdigest()[:8]

    queue_path = REX_DIR / "logs" / "pending_doc_classifications.json"
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        queue = json.loads(queue_path.read_text()) if queue_path.exists() else {}
    except Exception:
        queue = {}

    queue[key] = {
        "file_path":    str(path),
        "filename":     path.name,
        "reason":       reason,
        "text_preview": text[:600],
        "created_at":   datetime.now().isoformat(),
    }
    queue_path.write_text(json.dumps(queue, indent=2, ensure_ascii=False))
    return key


def _pdf_first_page_jpeg(pdf_path: str, out_path: str, dpi: int = 150) -> bool:
    """
    Render the first page of a PDF to a JPEG at out_path.
    Tries PyMuPDF (fitz) first, then falls back to pdf2image.
    Returns True on success.
    """
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        page = doc[0]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        pix.save(out_path)
        doc.close()
        return True
    except Exception:
        pass
    try:
        from pdf2image import convert_from_path
        images = convert_from_path(pdf_path, dpi=dpi, first_page=1, last_page=1)
        if images:
            images[0].save(out_path, "JPEG", quality=85)
            return True
    except Exception:
        pass
    return False


def _tg_send_photo_file(token: str, chat_id: int, image_path: str, caption: str = "") -> bool:
    """
    Send a local image file to Telegram chat via multipart/form-data.
    Returns True on success.
    """
    import io, mimetypes
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    boundary = "----TgBotBoundary"
    mime_type, _ = mimetypes.guess_type(image_path)
    if not mime_type:
        mime_type = "image/jpeg"
    try:
        with open(image_path, "rb") as fh:
            img_data = fh.read()
        body = io.BytesIO()
        def _field(name: str, value: str):
            body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
        def _file_field(name: str, filename: str, data: bytes, ctype: str):
            body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\nContent-Type: {ctype}\r\n\r\n".encode())
            body.write(data)
            body.write(b"\r\n")
        _field("chat_id", str(chat_id))
        if caption:
            _field("caption", caption[:1024])
            _field("parse_mode", "HTML")
        _file_field("photo", Path(image_path).name, img_data, mime_type)
        body.write(f"--{boundary}--\r\n".encode())
        body_bytes = body.getvalue()
        req = urllib.request.Request(
            url, data=body_bytes,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result.get("ok", False)
    except Exception as e:
        log.warning(f"_tg_send_photo_file: {e}")
        return False


def _notify_rexxie_unknown_doc(path: Path, reason: str, text_preview: str) -> bool:
    """
    Send a Telegram inline-keyboard message asking Kato to classify an unknown document.
    Options match Kato's specified taxonomy. The bot handles the reply and routes the file.
    Also saves the pending state so the bot can act on Kato's selection.
    Sends a page-1 preview image first so Kato can see the actual document.
    """
    try:
        cfg_path = REX_DIR / "rex_rexxie_telegram_config.json"
        if not cfg_path.exists():
            log.warning("  _notify_rexxie: config not found — skipping Telegram alert")
            return False
        d       = json.loads(cfg_path.read_text())
        token   = d.get("bot_token", "")
        chat_id = d.get("owner_chat_id", 0)
        if not token or not chat_id:
            log.warning("  _notify_rexxie: missing bot_token or owner_chat_id")
            return False

        # Save to pending queue so the bot can route on reply
        key = _save_pending_classification(path, reason, text_preview)

        # ── GOJ v2.0 — Send page-1 preview so Kato can see the document ──────
        if str(path).lower().endswith(".pdf"):
            import tempfile, os as _os
            _preview_jpg = tempfile.mktemp(suffix=".jpg")
            _preview_ok  = _pdf_first_page_jpeg(str(path), _preview_jpg)
            if _preview_ok:
                _tg_send_photo_file(
                    token, chat_id, _preview_jpg,
                    caption=f"📄 <b>{path.name}</b>\n<i>Page 1 — preview</i>",
                )
                try:
                    _os.unlink(_preview_jpg)
                except Exception:
                    pass
            else:
                log.warning(f"  _notify_rexxie: could not render preview for {path.name}")

        preview_clean = text_preview.replace("<", "&lt;").replace(">", "&gt;").strip()

        msg = (
            f"🤔 <b>Unrecognized Scan — Need Your Input</b>\n\n"
            f"📄 <b>File:</b> <code>{path.name}</code>\n"
            f"⚠️ <b>Issue:</b> {reason}\n\n"
            f"<b>Text preview:</b>\n<code>{preview_clean[:280]}</code>\n\n"
            f"<b>What is this document?</b>"
        )

        # Inline keyboard — matches Kato's exact taxonomy
        keyboard = [
            [
                {"text": "🍽 1. Menu",          "callback_data": f"classify:{key}:menu"},
                {"text": "🔒 2. Authorization", "callback_data": f"classify:{key}:auth"},
            ],
            [
                {"text": "✍️ 3. Sign In",       "callback_data": f"classify:{key}:signin"},
                {"text": "🚗  Drivers Sheet",   "callback_data": f"classify:{key}:drivers"},
            ],
            [
                {"text": "📁 4. Client Paperwork", "callback_data": f"classify:{key}:client_paperwork"},
                {"text": "👤 5. Staff Files",      "callback_data": f"classify:{key}:staff_files"},
            ],
            [
                {"text": "❓ 6. Misc / Specify",   "callback_data": f"classify:{key}:misc"},
                {"text": "🗑 Skip / Discard",      "callback_data": f"classify:{key}:skip"},
            ],
        ]

        url     = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({
            "chat_id":      chat_id,
            "text":         msg,
            "parse_mode":   "HTML",
            "reply_markup": {"inline_keyboard": keyboard},
        }).encode()
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = json.loads(resp.read()).get("ok", False)
        if ok:
            log.info(f"  📲 Rexxie sent classification keyboard for {path.name} (key={key})")
        return ok
    except Exception as e:
        log.warning(f"  _notify_rexxie error: {e}")
        return False


def _load_api_key_from_env() -> str:
    """Try to load ANTHROPIC_API_KEY from ~/Desktop/REX/.env if not in environment."""
    try:
        env_path = Path.home() / "Desktop" / "REX" / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("ANTHROPIC_API_KEY=") and "=" in line:
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


def get_text(path: Path, use_mineru: bool = False) -> str:
    """
    Text extraction with Paperless → MinerU pipeline for scanned PDFs.
    
    Flow:
      1. pdfplumber/pymupdf (fast, works on text-layer PDFs)
      2. Paperless upload + MinerU parse (scanned PDFs — archive + structured extraction)
      3. Tesseract (local OCR fallback)
      4. Paperless OCR (legacy, Tailscale-needed)
      5. Claude Vision (cloud, PHI-gated)
    
    Set use_mineru=True to force Paperless+MinerU even on text-layer PDFs (better tables).
    """
    
    # Step 0: FORCE Paperless+MinerU mode (--parser mineru flag)
    if use_mineru:
        text = extract_mineru_via_paperless(path)
        if text:
            return text

    # Step 1: Try PDF text layer (fastest — works when scanner adds text layer)
    for fn in [extract_text_pdfplumber, extract_text_pymupdf]:
        text = fn(path)
        if len(text.strip()) > 30:
            return text

    # Step 2: AUTO MinerU via Paperless — scanned PDF detected (no text layer).
    # Paperless handles archiving; MinerU handles structured extraction.
    log.info("  No text layer — scanned PDF detected. Uploading to Paperless + MinerU parse...")
    text = extract_mineru_via_paperless(path)
    if text:
        return text

    log.info("  Paperless+MinerU unavailable or failed — falling back to Tesseract...")

    # Step 3: Try local Tesseract (offline, no Tailscale needed)
    text = extract_text_tesseract(path)
    if len(text.strip()) > 30:
        return text

    # Step 4: Fall back to Paperless (best quality, needs Tailscale)
    log.info("  Tesseract found nothing — falling back to Paperless OCR")
    text = extract_text_paperless(path)
    if len(text.strip()) > 30:
        return text

    # Step 5: Claude Vision — CLOUD OCR. PHI GATE: sign-in/auth/attendance sheets are
    # patient data and must NOT go to a cloud model. Off by default; only runs if
    # ALLOW_CLOUD_OCR is explicitly set (use only for non-PHI docs). When disabled,
    # local OCR "failures" fall through to the unknown-doc/review path — no silent loss.
    if os.environ.get("ALLOW_CLOUD_OCR", "").lower() in ("1", "true", "yes"):
        log.info("  Paperless found nothing — trying Claude Vision (handwriting reader)...")
        return extract_text_claude_vision(path)
    log.info("  Local OCR exhausted; cloud OCR disabled (PHI) — routing doc to review.")
    return ""


# ── Classification ─────────────────────────────────────────────────────────────

def detect_sheet_type(text: str, path: Path | None = None) -> str | None:
    """
    Detect the document type using:
      1. Skip-list (administrative docs we ignore)
      2. Learned patterns from previous Kato confirmations  ← NEW
      3. Keyword scoring across all known sheet types
    """
    upper = text.upper()

    for kw in SKIP_KEYWORDS:
        if kw.upper() in upper:
            return None

    # ── Learned pattern check (highest priority) ─────────────────────────────
    if path is not None:
        learned = _check_learned_patterns(path, text)
        if learned:
            return learned

    # ── Keyword scoring ───────────────────────────────────────────────────────
    scores: dict[str, int] = {
        t: sum(1 for kw in kws if kw.upper() in upper)
        for t, kws in SHEET_KEYWORD_MAP.items()
    }
    log.debug(f"  Scores: {scores}")

    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        return None

    # Merge distribution → menu (same destination)
    if best == "distribution":
        best = "menu"

    # Tie-break: signin vs drivers
    if scores["signin"] == scores["drivers"] and scores["signin"] > 0:
        if "Insurance Plan" in text:
            return "signin"
        if "Address" in text and "Phone" in text:
            return "drivers"

    return best


# ── Client name extraction (for auth docs) ────────────────────────────────────

def _get_known_client_names() -> list[str]:
    """Pull client names from auth_tracker.db if available."""
    try:
        if not AUTH_DB.exists():
            return []
        conn = sqlite3.connect(str(AUTH_DB))
        cur  = conn.cursor()
        cur.execute("SELECT name FROM clients WHERE active = 1")
        names = [row[0] for row in cur.fetchall()]
        conn.close()
        return names
    except Exception:
        return []


def _extract_client_name_from_auth(text: str) -> str | None:
    """
    Try to find a client name in an authorization letter.
    Looks for:  Member Name: <name>  /  Patient: <name>  /  Beneficiary: <name>
    Then fuzzy-matches against the clients table.
    """
    patterns = [
        r"Member\s+Name[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
        r"Patient\s+Name[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
        r"Beneficiary[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
        r"Recipient[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
        r"Enrollee[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
        r"Name[:\s]+([A-Z][a-z]+(?:,\s*[A-Z][a-z]+)?)",
    ]

    raw_name = None
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            raw_name = m.group(1).strip()
            break

    if not raw_name:
        return None

    # Normalize: "Last, First" → "First Last"
    if "," in raw_name:
        parts = [p.strip() for p in raw_name.split(",", 1)]
        raw_name = f"{parts[1]} {parts[0]}"

    # Fuzzy-match against known clients
    known_names = _get_known_client_names()
    if known_names:
        matches = difflib.get_close_matches(
            raw_name.lower(),
            [n.lower() for n in known_names],
            n=1, cutoff=0.75,
        )
        if matches:
            idx = [n.lower() for n in known_names].index(matches[0])
            return known_names[idx]   # return properly cased name from DB

    return raw_name  # best guess from text if no DB match


def _client_folder_name(client_name: str) -> str:
    """Convert 'Halas Teresa' → 'Halas_Teresa' for folder naming."""
    return client_name.strip().replace(" ", "_").replace(",", "")


# ── Date / shift extraction ────────────────────────────────────────────────────

def extract_date(text: str) -> date | None:
    # "Date: April 14, 2026"
    m = re.search(r"Date[:\s]+([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", text, re.IGNORECASE)
    if m:
        mon = MONTH_NAMES.get(m.group(1).lower())
        if mon:
            try:
                return date(int(m.group(3)), mon, int(m.group(2)))
            except ValueError:
                pass

    # "Date: 04/14/2026"
    m = re.search(r"Date[:\s]+(\d{1,2})/(\d{1,2})/(\d{4})", text, re.IGNORECASE)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError:
            pass

    # "Date: 2026-04-14"
    m = re.search(r"Date[:\s]+(\d{4})-(\d{2})-(\d{2})", text, re.IGNORECASE)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # "Monday, April 14, 2026"
    m = re.search(
        r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+"
        r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})",
        text, re.IGNORECASE,
    )
    if m:
        mon = MONTH_NAMES.get(m.group(1).lower())
        if mon:
            try:
                return date(int(m.group(3)), mon, int(m.group(2)))
            except ValueError:
                pass

    # "Week of April 14, 2026" (menu forms)
    m = re.search(r"[Ww]eek\s+of\s+([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", text)
    if m:
        mon = MONTH_NAMES.get(m.group(1).lower())
        if mon:
            try:
                return date(int(m.group(3)), mon, int(m.group(2)))
            except ValueError:
                pass

    # "Effective Date: 03/01/2026" or "From: 03/01/2026" (auth letters)
    m = re.search(
        r"(?:Effective Date|Auth(?:orization)? (?:From|Start)|From Date)[:\s]+(\d{1,2})/(\d{1,2})/(\d{4})",
        text, re.IGNORECASE,
    )
    if m:
        try:
            return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError:
            pass

    return None


def extract_shift(text: str) -> str | None:
    m = re.search(r"Shift[:\s]+([12])", text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"\bS([12])\b", text[:400])
    if m:
        return m.group(1)
    return None


# ── Filename builders ──────────────────────────────────────────────────────────

def signin_filename(sheet_type: str, sheet_date: date, shift: str) -> str:
    abbrev, weekday = DOW_TO_ABBREV[sheet_date.weekday()]
    return f"GOJ_{abbrev}_S{shift}_{weekday}_{sheet_type}.pdf"


def menu_filename(sheet_date: date, shift: str | None) -> str:
    date_str  = sheet_date.isoformat()
    shift_str = f"_S{shift}" if shift else ""
    return f"menu_{date_str}{shift_str}.pdf"


def auth_filename(client_name: str | None, original_name: str) -> str:
    today     = date.today().isoformat()
    stem      = Path(original_name).stem
    if client_name:
        safe = _client_folder_name(client_name)
        return f"auth_{safe}_{today}.pdf"
    return f"auth_{stem}_{today}.pdf"


# ── Core processor ─────────────────────────────────────────────────────────────

def process_file(path: Path, dry_run: bool = False, use_mineru: bool = False) -> dict:
    log.info(f"Processing: {path.name}")
    path = path.resolve()

    # V4: emit doc.received event
    try:
        emit_doc_event("doc.received", path.name,
                       metadata={"size_bytes": path.stat().st_size, "dry_run": dry_run})
    except Exception:
        pass

    text = get_text(path, use_mineru=use_mineru)
    if not text or len(text.strip()) < 10:
        result = {"status": "error", "reason": "No text could be extracted", "file": str(path)}
        log.warning(f"  ✗ {result['reason']}")
        # V4: emit OCR fallback event
        try:
            emit_ocr_fallback(path.name, engine_used="all", reason="No text extracted from any engine")
        except Exception:
            pass
        return result

    sheet_type = detect_sheet_type(text, path=path)
    sheet_date = extract_date(text)
    shift      = extract_shift(text)

    # ── Auth documents — special handling ──────────────────────────────────────
    if sheet_type == "auth":
        client_name = _extract_client_name_from_auth(text)
        out_name    = auth_filename(client_name, path.name)

        if client_name:
            out_dir = AUTH_OUT / _client_folder_name(client_name)
            route_note = f"client folder: {_client_folder_name(client_name)}/"
        else:
            out_dir    = AUTH_STAGE
            route_note = "⚠ staging (_incoming/) — client name not found in text"

        out_path = out_dir / out_name

        if dry_run:
            log.info(f"  DRY RUN → [auth] {route_note} / {out_name}")
            return {
                "status":      "dry_run",
                "source":      str(path),
                "destination": str(out_path),
                "type":        "auth",
                "client":      client_name or "unknown",
            }

        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(path), str(out_path))
        path.rename(path.parent / f".done_{path.name}")
        log.info(f"  ✅ → {route_note}/{out_name}")

        return {
            "status":      "ok",
            "output":      str(out_path),
            "type":        "auth",
            "client":      client_name or "unknown",
            "staged":      client_name is None,
            "note":        route_note,
        }

    # ── Auto-skip receipts, bills, and known non-GOJ documents ──────────────
    # Kato said stop asking about these. They're email receipts (Anthropic, etc.)
    # and never GOJ operational documents.
    _receipt_keywords = [
        "receipt", "invoice", "date paid", "bill to", "receipt number",
        "invoice number", "anthropic", "openai", "stripe", "github",
        "apple.com/bill", "google payments", "microsoft 365",
    ]
    _text_lower = text.lower()
    if any(kw in _text_lower for kw in _receipt_keywords):
        # Check it's NOT a GOJ document (some GOJ docs may say "receipt")
        if not any(g in _text_lower for g in [
            "garden of joy", "sign in", "sign-in", "driver", "menu",
            "kitchen", "client", "authorization", "medicaid",
        ]):
            log.info(
                f"  🧾 Auto-skipped receipt: {path.name} "
                f"(matched: {[kw for kw in _receipt_keywords if kw in _text_lower][:3]})"
            )
            # Move to .done_ so it never reprocesses
            path.rename(path.parent / f".done_{path.name}")
            return {
                "status": "skipped",
                "reason": "auto-skip: receipt/bill (not a GOJ document)",
                "file":   str(path),
            }

    # ── Require date for all other types ───────────────────────────────────────
    issues = []
    if not sheet_type:
        issues.append("cannot determine sheet type (signin / driver / menu / kitchen / auth)")
    if not sheet_date:
        issues.append("cannot find date in document")

    if issues:
        # Ask Rexxie via Telegram instead of silently failing or mis-classifying
        _notify_rexxie_unknown_doc(path, "; ".join(issues), text[:200])
        # V4: also route into formal unresolved queue for tracking
        try:
            route_ambiguous_doc(
                path.name,
                reason="; ".join(issues),
                detected_types=[sheet_type] if sheet_type else [],
                confidence=0.0,
            )
        except Exception:
            pass
        result = {
            "status":       "ambiguous",
            "reason":       "; ".join(issues),
            "file":         str(path),
            "text_preview": text[:300].replace("\n", " "),
        }
        log.warning(f"  ⚠ {result['reason']} — Rexxie notified")
        return result

    # ── Route by type ──────────────────────────────────────────────────────────
    is_menu = sheet_type == "menu"

    if is_menu:
        out_dir  = MENUS_OUT
        out_name = menu_filename(sheet_date, shift)
    else:
        out_dir = SIGNIN_OUT
        if not shift:
            log.warning("  Shift not found — defaulting to S1")
            shift = "1"
        out_name = signin_filename(sheet_type, sheet_date, shift)

    out_path = out_dir / out_name

    if dry_run:
        log.info(f"  DRY RUN → [{sheet_type}] {out_dir.name}/{out_name}")
        return {
            "status":      "dry_run",
            "source":      str(path),
            "destination": str(out_path),
            "type":        sheet_type,
        }

    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(path), str(out_path))
    path.rename(path.parent / f".done_{path.name}")
    log.info(f"  ✅ → {out_dir.name}/{out_name}")

    # V4: emit doc.classified + doc.filed events
    try:
        emit_doc_event("doc.classified", path.name,
                       metadata={"doc_type": sheet_type, "confidence": 1.0})
        emit_doc_event("doc.filed", path.name,
                       metadata={"destination": str(out_path), "doc_type": sheet_type,
                                 "date": str(sheet_date), "shift": shift or "S?"})
    except Exception:
        pass

    # ── Menu OCR pipeline — extract checkbox selections into DB ───────────────
    if is_menu:
        try:
            import importlib.util, sys as _sys
            _ocr_mod_path = Path(__file__).resolve().parent / "goj_menu_ocr.py"
            _spec = importlib.util.spec_from_file_location("goj_menu_ocr", _ocr_mod_path)
            _ocr  = importlib.util.module_from_spec(_spec)
            _sys.modules.setdefault("goj_menu_ocr", _ocr)
            _spec.loader.exec_module(_ocr)

            log.info(f"  → Running menu OCR pipeline on {out_path.name}...")
            ocr_result = _ocr.process_menu_pdf(
                pdf_path=out_path,
                dry_run=False,
                scan_date=str(sheet_date),
            )
            inserted = ocr_result.get("inserted", 0)
            skipped  = ocr_result.get("skipped",  0)
            errors   = ocr_result.get("errors",   [])
            log.info(f"  ✅ Menu OCR: {inserted} rows inserted, {skipped} skipped"
                     + (f", {len(errors)} errors" if errors else ""))
        except Exception as _ocr_err:
            log.warning(f"  ⚠ Menu OCR pipeline error (file saved OK): {_ocr_err}")

        # V4: stage content update for tracking (never auto-publishes)
        if _content_queue is not None:
            try:
                _content_queue.stage(
                    source_document=path.name,
                    extracted_content=text[:2000],
                    proposed_dest="dashboard/menus",
                    confidence=1.0,
                )
            except Exception:
                pass

    return {
        "status":  "ok",
        "output":  str(out_path),
        "type":    sheet_type,
        "date":    str(sheet_date),
        "shift":   shift or "—",
        "is_menu": is_menu,
    }


# ── State tracking ─────────────────────────────────────────────────────────────

def load_processed() -> set:
    if DONE_LOG.exists():
        try:
            return set(json.loads(DONE_LOG.read_text()))
        except Exception:
            return set()
    return set()


def save_processed(done: set):
    DONE_LOG.write_text(json.dumps(sorted(done), indent=2))


# ── Run modes ──────────────────────────────────────────────────────────────────

def run_once(dry_run: bool = False, use_mineru: bool = False):
    SIGNINS_DIR.mkdir(parents=True, exist_ok=True)
    done = load_processed()

    pending = [
        f for f in sorted(SIGNINS_DIR.glob("*.pdf"))
        if not f.name.startswith(".done_") and f.name not in done
    ]

    if not pending:
        log.info(f"No pending PDFs in {SIGNINS_DIR}")
        return

    log.info(f"Found {len(pending)} file(s)")
    results = []
    for f in pending:
        result = process_file(f, dry_run=dry_run, use_mineru=use_mineru)
        results.append(result)
        if result["status"] == "ok" and not dry_run:
            done.add(f.name)
            save_processed(done)

    ok_list  = [r for r in results if r["status"] == "ok"]
    dry_list = [r for r in results if r["status"] == "dry_run"]
    amb_list = [r for r in results if r["status"] == "ambiguous"]
    err_list = [r for r in results if r["status"] == "error"]

    menus_routed = [r for r in ok_list if r.get("is_menu")]
    auths_routed = [r for r in ok_list if r.get("type") == "auth"]
    auths_staged = [r for r in auths_routed if r.get("staged")]

    print(f"\n{'='*60}")
    if dry_run:
        print(f"  DRY RUN — {len(dry_list)} file(s):")
        for r in dry_list:
            dest = Path(r["destination"])
            print(f"    [{r['type']:8}] {Path(r['source']).name}")
            print(f"              → {dest.parent.name}/{dest.name}")
    else:
        print(f"  Done: {len(ok_list)} routed | {len(amb_list)} need review | {len(err_list)} errors")
        for r in ok_list:
            out  = Path(r["output"])
            icon = {"signin": "📋", "drivers": "🚗", "menu": "🍽",
                    "auth": "📄", "kitchen": "🍳"}.get(r["type"], "📁")
            if r["type"] == "auth":
                note = f"  client: {r['client']}"
                if r.get("staged"):
                    note += " ⚠ STAGED — review needed"
                print(f"    {icon} {out.parent.name}/{out.name}{note}")
            else:
                print(f"    {icon} {out.parent.name}/{out.name}  ({r['type']}, {r['date']}, Shift {r['shift']})")

        if menus_routed:
            print(f"\n  🍽  {len(menus_routed)} menu(s) routed → menus/ folder")
            print(f"      Run 'menu ocr' in Rexxie to process them into the database.")

        if auths_staged:
            print(f"\n  ⚠  {len(auths_staged)} auth doc(s) in _incoming/ — client name not detected.")
            print(f"     Move to the correct client folder manually, then run:")
            print(f"     python3 ~/Desktop/REX/run_auth_linker.py")
        elif auths_routed:
            print(f"\n  📄 {len(auths_routed)} auth doc(s) routed. Run auth linker to register in DB:")
            print(f"     python3 ~/Desktop/REX/run_auth_linker.py")

    if amb_list:
        print(f"\n  ⚠  NEEDS REVIEW ({len(amb_list)}):")
        for r in amb_list:
            print(f"    {Path(r['file']).name}: {r['reason']}")
            print(f"      Preview: {r.get('text_preview', '')[:120]}")

    if err_list:
        print(f"\n  ✗  ERRORS ({len(err_list)}):")
        for r in err_list:
            print(f"    {Path(r['file']).name}: {r['reason']}")

    print(f"{'='*60}\n")


def watch_mode(use_mineru: bool = False):
    SIGNINS_DIR.mkdir(parents=True, exist_ok=True)
    log.info(f"Watching {SIGNINS_DIR}  (every 10s — Ctrl+C to stop)")
    done = load_processed()
    while True:
        pending = [
            f for f in sorted(SIGNINS_DIR.glob("*.pdf"))
            if not f.name.startswith(".done_") and f.name not in done
        ]
        for f in pending:
            result = process_file(f, use_mineru=use_mineru)
            if result["status"] == "ok":
                done.add(f.name)
                save_processed(done)
        time.sleep(10)


# ── Entry ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]
    use_mineru = "--parser" in args and "mineru" in args
    # Strip --parser and its value from args for remaining processing
    clean_args = []
    skip_next = False
    for a in args:
        if skip_next:
            skip_next = False
            continue
        if a == "--parser":
            skip_next = True
            continue
        clean_args.append(a)
    
    if not clean_args:
        run_once(use_mineru=use_mineru)
    elif clean_args[0] == "--watch":
        watch_mode(use_mineru=use_mineru)
    elif clean_args[0] == "--dry-run":
        run_once(dry_run=True, use_mineru=use_mineru)
    else:
        target = Path(clean_args[0])
        if not target.exists():
            print(f"ERROR: File not found: {target}")
            sys.exit(1)
        result = process_file(target, use_mineru=use_mineru)
        print(json.dumps(result, indent=2))
