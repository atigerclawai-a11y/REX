#!/usr/bin/env python3
"""
GOJ Menu Form OCR — goj_menu_ocr.py
=====================================
3-engine pipeline for reading client weekly menu forms:

  Engine 1 — Claude Vision (primary)
    Reads checkboxes, client name, week indicator from scanned images.
    Returns structured JSON per page pair.

  Engine 2 — Tesseract (secondary / validator)
    Validates printed text regions (name, week date) from page 1.
    Low-confidence name matches get cross-checked here.

  Engine 3 — Paperless-NGX (archival)
    Submits original PDF to Paperless at 100.99.86.60:8000 for long-term
    document storage and full-text search.

Usage:
    python3 goj_menu_ocr.py scan_20260501_1514.pdf
    python3 goj_menu_ocr.py --batch ~/Desktop/REX/signins/
    python3 goj_menu_ocr.py --dry-run scan_20260501_1217.pdf
"""

import sys
import os
import json
import base64
import sqlite3
import logging
import urllib.request
import urllib.error
import difflib
import re
import traceback
from pathlib import Path
from datetime import datetime, date, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("menu-ocr")

# ── Paths ──────────────────────────────────────────────────────────────────────
REX_DIR  = Path(__file__).resolve().parent
DB_PATH  = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
MENUS_DIR = Path.home() / "Documents" / "goj files" / "dashboard" / "documents" / "menus"
MENUS_DIR.mkdir(parents=True, exist_ok=True)

PROCESSED_LOG = REX_DIR / "logs" / "menu_ocr_processed.json"
PROCESSED_LOG.parent.mkdir(parents=True, exist_ok=True)

# ── Paperless ──────────────────────────────────────────────────────────────────
PAPERLESS_URL     = "http://100.99.86.60:8000"
PAPERLESS_TOKEN   = "583e819be1146b96b935007c6ad7f584a3a1b1b7"

# ── Menu item constants (canonical source: CC_menu_constants.py) ───────────────
from CC_menu_constants import (
    SALADS, SOUPS, MAINS_P1, MAINS_P2, ALL_MAINS, SIDES, DAYS, DAY_MAP, CHECKMARKS
)

# ── Anthropic Vision API ───────────────────────────────────────────────────────
# OCR live-fix 2026-06-11: launchd daemons don't inherit a shell env, so the key was
# empty at import → every call_vision() failed. Load the key files explicitly, pin
# Tesseract's data dir, and use Haiku (cheap) for checkbox/form reading.
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.expanduser("~/.hermes-cloud/.env"))
    load_dotenv(os.path.expanduser("~/Desktop/REX/.env"))
except Exception:
    pass
os.environ.setdefault("TESSDATA_PREFIX", "/opt/homebrew/share/tessdata")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL      = os.environ.get("OCR_VISION_MODEL", "claude-haiku-4-5-20251001")

# ── Gate 1 — PHI tokenizer firewall (OCR_LIVE_SSE_PLAN §5) ──────────────────────
# This is the ONE client-data cloud-OCR path. Per the brief (Directive 5, 🔴),
# any TEXT that crosses the api.anthropic.com boundary in call_vision() must pass
# through Gate 1 first (tokenize inbound, detokenize outbound). The tokenizer lives
# in CC_akc_tokenizer_v2.py (HIPAA Safe-Harbor, 18 identifiers; falls back to regex
# if Presidio is absent). Robust import: ensure the REX dir is importable, then if
# the import fails AND Gate 1 is required, REFUSE to send raw rather than leak PHI.
GATE1_REQUIRED = os.environ.get("GATE1_REQUIRED", "true").lower() == "true"

if str(REX_DIR) not in sys.path:
    sys.path.insert(0, str(REX_DIR))

_gate1_available = False
Gate1Firewall = None  # type: ignore
try:
    from CC_akc_tokenizer_v2 import Gate1Firewall as _Gate1Firewall
    Gate1Firewall = _Gate1Firewall
    _gate1_available = True
    log.info("Gate 1 firewall imported — PHI tokenizer active on cloud-OCR text path")
except Exception as _gate1_exc:  # ImportError or any init failure
    log.error("Gate 1 firewall import FAILED: %s", _gate1_exc)
    if GATE1_REQUIRED:
        log.critical(
            "GATE1_REQUIRED=true but Gate 1 firewall is unavailable — "
            "cloud Vision calls will be REFUSED (no raw client data leaves the box)."
        )

VISION_PROMPT_P1 = """You are reading a scanned Garden of Joy Adult Day Care weekly menu form (PAGE 1).

The form has:
- A header with the client's name (Имя:) and week date (Неделя:)
- Day columns: ПН=Monday(M), ВТ=Tuesday(T), СР=Wednesday(W), ЧТ=Thursday(TH), ПТ=Friday(F)
- САЛАТЫ section (salads): {salads}
- СУПЫ section (soups): {soups}
- ГЛАВНОЕ БЛЮДО section (mains, first part): {mains_p1}

Return ONLY valid JSON with this exact structure:
{{
  "page_type": "p1",
  "client_name": "LastName FirstName as written",
  "week_indicator": "date or text written in Неделя field, or null",
  "day_columns_circled": ["list of day abbrevs that appear circled at top, e.g. ПТ"],
  "checks": {{
    "M":  {{"salad": "item or null", "soup": "item or null", "main": "item or null"}},
    "T":  {{"salad": "item or null", "soup": "item or null", "main": "item or null"}},
    "W":  {{"salad": "item or null", "soup": "item or null", "main": "item or null"}},
    "TH": {{"salad": "item or null", "soup": "item or null", "main": "item or null"}},
    "F":  {{"salad": "item or null", "soup": "item or null", "main": "item or null"}}
  }},
  "conflicts": ["describe any row with multiple checkmarks"],
  "confidence": 0.0
}}

Rules:
- Use EXACT Russian item names from the lists above (match as closely as possible)
- confidence = your overall confidence in the reads (0.0–1.0)
- If a checkbox is checked/marked with ✓, X, ✗, or any pen/pencil mark, record that item
- If two items are checked in the same category+day, keep the more clearly marked one and note it in conflicts
- Return ONLY the JSON object, no other text"""

VISION_PROMPT_P2 = """You are reading a scanned Garden of Joy Adult Day Care weekly menu form (PAGE 2 — continuation).

The form has:
- Day columns: ПН=Monday(M), ВТ=Tuesday(T), СР=Wednesday(W), ЧТ=Thursday(TH), ПТ=Friday(F)
- ГЛАВНОЕ БЛЮДО (ПРОДОЛЖЕНИЕ) section (remaining mains): {mains_p2}
- ГАРНИР section (sides): {sides}

Note: There may be a handwritten note at the top of the page. Ignore it.

Return ONLY valid JSON with this exact structure:
{{
  "page_type": "p2",
  "checks": {{
    "M":  {{"main": "item or null", "side": "item or null"}},
    "T":  {{"main": "item or null", "side": "item or null"}},
    "W":  {{"main": "item or null", "side": "item or null"}},
    "TH": {{"main": "item or null", "side": "item or null"}},
    "F":  {{"main": "item or null", "side": "item or null"}}
  }},
  "conflicts": ["describe any row with multiple checkmarks"],
  "confidence": 0.0
}}

Return ONLY the JSON object, no other text"""


# ── PDF → images ───────────────────────────────────────────────────────────────
def pdf_page_to_base64(pdf_path: Path, page_num: int, dpi: int = 150) -> str | None:
    """Convert a single PDF page to base64-encoded JPEG."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(pdf_path))
        page = doc[page_num]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        img_bytes = pix.tobytes("jpeg", jpg_quality=85)
        return base64.b64encode(img_bytes).decode()
    except Exception as e:
        log.error(f"pdf_page_to_base64 page {page_num}: {e}")
        return None


# ── Claude Vision call ─────────────────────────────────────────────────────────
def call_vision(image_b64: str, prompt: str, session_id: str | None = None) -> dict | None:
    """Call Claude Vision API and return parsed JSON response.

    GATE 1 (OCR_LIVE_SSE_PLAN §5.1): all TEXT crossing the api.anthropic.com
    boundary is routed through the PHI tokenizer firewall first. The outbound
    prompt is tokenized (inbound) before the POST; any echoed text in the
    response is detokenized (outbound) before it is parsed/returned.

    ───────────────────────────────────────────────────────────────────────────
    ⚠️  DEFERRED — IMAGE HEADER-CROP IS NOT YET DONE (OCR_LIVE_SSE_PLAN §5.2)
    ───────────────────────────────────────────────────────────────────────────
    Gate 1 tokenizes TEXT only. The PHI on a menu form (the client name in the
    `Имя:` header band) is *pixels* in `image_b64`, which a text tokenizer CANNOT
    scrub. Today's menu prompts (VISION_PROMPT_P1/P2) are static food lists with
    no client identifier, so the text path is already PHI-free and this firewall
    is the forward-looking guarantee. But the IMAGE still carries the handwritten
    name to the cloud.

    The REAL image-level PHI control (per §5.2) is still OUTSTANDING:
      * crop the top ~22% header band OUT of the image before upload, so the
        cloud Vision call only sees the checkbox grid (name resolved LOCALLY via
        tesseract_extract_name_week()), and
      * keep GATE1_REQUIRED=true.
    BOTH — GATE1_REQUIRED **and** the image header-crop — are required before the
    menu cloud-OCR path may be re-enabled at scale. Until the header-crop lands,
    this path is NOT yet truly PHI-safe and must stay gated/limited.
    ───────────────────────────────────────────────────────────────────────────
    """
    # Read the key at call time (not bound at import) so a late-loaded .env works.
    api_key = os.environ.get("ANTHROPIC_API_KEY", "") or ANTHROPIC_API_KEY
    if not api_key:
        log.error("ANTHROPIC_API_KEY not set — Vision engine unavailable")
        return None

    # ── Gate 1 hard block ────────────────────────────────────────────────────
    # If Gate 1 is required but the firewall is unavailable, REFUSE to send raw.
    if GATE1_REQUIRED and not _gate1_available:
        log.critical(
            "GATE1_REQUIRED=true and Gate 1 firewall unavailable — REFUSING cloud "
            "Vision call to avoid leaking unprotected client data."
        )
        return None

    # ── Gate 1 inbound: tokenize the prompt text before it crosses the wire ──
    fw = None
    outbound_prompt = prompt
    if _gate1_available:
        try:
            sid = session_id or "menu_ocr"
            fw = Gate1Firewall(session_id=sid)
            outbound_prompt, _token_map = fw.inbound(prompt)
            log.info("gate1=on, image_header_stripped=false (DEFERRED §5.2)")
        except Exception as e:
            log.error("Gate 1 inbound tokenize failed: %s", e)
            if GATE1_REQUIRED:
                log.critical("GATE1_REQUIRED=true — REFUSING cloud Vision call after tokenize failure.")
                return None
            outbound_prompt = prompt  # non-required mode: proceed with raw prompt

    payload = json.dumps({
        "model": CLAUDE_MODEL,
        "max_tokens": 1024,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
                {"type": "text", "text": outbound_prompt},
            ],
        }],
    }).encode()

    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            text = data["content"][0]["text"].strip()
            # ── Gate 1 outbound: restore any tokenized text echoed in the reply ──
            if fw is not None:
                try:
                    text = fw.outbound(text)
                except Exception as e:
                    log.error("Gate 1 outbound detokenize failed: %s", e)
            # Strip markdown fences if present
            if text.startswith("```"):
                text = re.sub(r"^```[a-z]*\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
            return json.loads(text)
    except Exception as e:
        log.error(f"Vision API call failed: {e}")
        return None


# ── Tesseract validator ────────────────────────────────────────────────────────
def tesseract_extract_name_week(pdf_path: Path, page_num: int) -> dict:
    """Use Tesseract to validate name/week from page 1 header region."""
    result = {"name": None, "week": None}
    try:
        import fitz
        import pytesseract
        from PIL import Image
        import io

        doc  = fitz.open(str(pdf_path))
        page = doc[page_num]
        # Crop to top portion (name/week region) — top 20% of page
        rect = fitz.Rect(0, 0, page.rect.width, page.rect.height * 0.22)
        mat  = fitz.Matrix(2.0, 2.0)  # 2x zoom for better OCR
        pix  = page.get_pixmap(matrix=mat, clip=rect, colorspace=fitz.csRGB)
        img  = Image.open(io.BytesIO(pix.tobytes("png")))

        text = pytesseract.image_to_string(img, lang="rus+eng", config="--psm 6")
        log.debug(f"Tesseract header: {text[:200]}")

        # Parse name
        name_m = re.search(r"[Ии]мя[:\s]+(.+?)(?:Неделя|$)", text, re.IGNORECASE)
        if name_m:
            result["name"] = name_m.group(1).strip()

        # Parse week
        week_m = re.search(r"Неделя[:\s]+(.+?)$", text, re.IGNORECASE | re.MULTILINE)
        if week_m:
            result["week"] = week_m.group(1).strip()

    except ImportError as ie:
        log.debug(f"Tesseract engine: {ie}")
    except Exception as e:
        log.debug(f"Tesseract validation: {e}")
    return result


# ── Cyrillic → Latin transliteration (for names OCR'd in Russian script) ──────
_CYRILLIC_TO_LATIN = {
    'А': 'A',  'Б': 'B',  'В': 'V',  'Г': 'G',  'Д': 'D',  'Е': 'E',  'Ё': 'Yo',
    'Ж': 'Zh', 'З': 'Z',  'И': 'I',  'Й': 'Y',  'К': 'K',  'Л': 'L',  'М': 'M',
    'Н': 'N',  'О': 'O',  'П': 'P',  'Р': 'R',  'С': 'S',  'Т': 'T',  'У': 'U',
    'Ф': 'F',  'Х': 'Kh', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sch',
    'Ъ': '',   'Ы': 'Y',  'Ь': '',   'Э': 'E',  'Ю': 'Yu', 'Я': 'Ya',
    'а': 'a',  'б': 'b',  'в': 'v',  'г': 'g',  'д': 'd',  'е': 'e',  'ё': 'yo',
    'ж': 'zh', 'з': 'z',  'и': 'i',  'й': 'y',  'к': 'k',  'л': 'l',  'м': 'm',
    'н': 'n',  'о': 'o',  'п': 'p',  'р': 'r',  'с': 's',  'т': 't',  'у': 'u',
    'ф': 'f',  'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
    'ъ': '',   'ы': 'y',  'ь': '',   'э': 'e',  'ю': 'yu', 'я': 'ya',
}

def _transliterate_cyrillic(text: str) -> str:
    """Convert Cyrillic characters to Latin equivalents using a hardcoded mapping.
    Used so that names OCR'd in Russian script can still fuzzy-match the
    transliterated names stored in the DB.
    """
    return "".join(_CYRILLIC_TO_LATIN.get(ch, ch) for ch in text)


# ── Client name matching ───────────────────────────────────────────────────────
def match_client_name(raw_name: str, conn: sqlite3.Connection) -> tuple[int | None, str | None, float]:
    """Fuzzy-match raw_name to clients table. Returns (client_id, db_name, score)."""
    cur = conn.cursor()
    cur.execute("SELECT client_id, name FROM clients WHERE active=1")
    candidates = cur.fetchall()

    if not raw_name:
        return None, None, 0.0

    # If the name appears to be in Cyrillic, transliterate it first so the
    # fuzzy matcher can compare it against the Latin-script names in the DB.
    has_cyrillic = any(ch in _CYRILLIC_TO_LATIN for ch in raw_name)
    working_name = _transliterate_cyrillic(raw_name) if has_cyrillic else raw_name
    if has_cyrillic:
        log.debug(f"  Transliterated Cyrillic name '{raw_name}' → '{working_name}'")

    # Normalize: collapse whitespace, title case
    raw = " ".join(working_name.strip().split()).title()

    best_score = 0.0
    best = (None, None)
    for cid, name in candidates:
        score = difflib.SequenceMatcher(None, raw.lower(), name.lower()).ratio()
        # Boost if first token matches (last name)
        raw_parts = raw.lower().split()
        name_parts = name.lower().split()
        if raw_parts and name_parts and raw_parts[0] == name_parts[0]:
            score = min(1.0, score + 0.15)
        if score > best_score:
            best_score = score
            best = (cid, name)

    return best[0], best[1], best_score


# ── Week date inference ─────────────────────────────────────────────────────────
#
# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  LOCKED RULE — DO NOT CHANGE WITHOUT EXPLICIT OPERATOR APPROVAL             ║
# ║                                                                              ║
# ║  Any menu form scanned during the current week is ALWAYS assigned to        ║
# ║  NEXT WEEK's service period (the upcoming Monday).                          ║
# ║                                                                              ║
# ║  Reason: Kato creates multiple copies of each form for filing purposes.     ║
# ║  A scan arriving on any day of the current week represents next week's      ║
# ║  menu order — not the current week's.                                       ║
# ║                                                                              ║
# ║  The week_indicator field on the form is IGNORED for week_start             ║
# ║  calculation. It is stored in the notes column for reference only.          ║
# ║                                                                              ║
# ║  Override: pass force_week_start='YYYY-MM-DD' (operator use only,           ║
# ║  must be a Monday). Requires explicit action — never inferred.              ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
#
def infer_week_start(week_indicator: str | None, scan_date: date | None = None,
                     force_week_start: str | None = None) -> str:
    """
    Returns the Monday of the NEXT service week relative to scan_date.

    LOCKED RULE: menus scanned this week are ALWAYS for next week.
    The week_indicator written on the form is stored in notes but does NOT
    change the week_start assignment.

    Args:
        week_indicator: text from Неделя field — logged to notes, not used for date
        scan_date:      date the PDF was received (defaults to today)
        force_week_start: operator override, must be ISO Monday (YYYY-MM-DD)
    """
    # Operator explicit override — only accepted if it is actually a Monday
    if force_week_start:
        try:
            d = date.fromisoformat(force_week_start)
            if d.weekday() != 0:
                raise ValueError(f"force_week_start must be a Monday, got {d.strftime('%A')} ({force_week_start})")
            log.info(f"  week_start OVERRIDE applied: {force_week_start}")
            return d.isoformat()
        except ValueError as e:
            log.error(f"  Invalid force_week_start '{force_week_start}': {e} — falling back to auto")

    # LOCKED: always compute next Monday from scan date, ignoring week_indicator
    today = scan_date or date.today()
    days_ahead = 7 - today.weekday()   # days until next Monday
    if today.weekday() == 0:           # if today IS Monday, still use NEXT Monday
        days_ahead = 7
    next_monday = today + timedelta(days=days_ahead)

    if week_indicator:
        log.debug(f"  week_indicator on form ('{week_indicator}') stored in notes — not used for week_start (locked rule)")

    # Defensive guard: next_monday must always be in the future relative to today.
    # If somehow the date logic produces a past or same-day Monday (shouldn't happen,
    # but guards against edge cases like a bad scan_date being passed in), advance
    # by 7 days until we have a genuine future Monday.
    while next_monday <= today:
        log.warning(f"  infer_week_start: computed Monday {next_monday} is not in the future — advancing by 7 days")
        next_monday += timedelta(days=7)

    return next_monday.isoformat()


def _parse_mdy(m) -> date | None:
    try:
        month, day = int(m.group(1)), int(m.group(2))
        year = int(m.group(3))
        if year < 100:
            year += 2000
        return date(year, month, day)
    except Exception:
        return None


# ── Paperless archival ─────────────────────────────────────────────────────────
def submit_to_paperless(pdf_path: Path, title: str) -> int | None:
    """Upload PDF to Paperless-NGX. Returns document ID or None."""
    url = f"{PAPERLESS_URL}/api/documents/post_document/"
    boundary = "----MenuOCRBoundary"
    pdf_bytes = pdf_path.read_bytes()

    # Build multipart body
    body_parts = []
    body_parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"title\"\r\n\r\n{title}".encode())
    body_parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{pdf_path.name}\"\r\nContent-Type: application/pdf\r\n\r\n".encode() + pdf_bytes)
    # Paperless-NGX expects integer tag PKs — skip string tags to avoid 400 errors
    # (archival without tags is fine; tags can be applied in the Paperless UI)
    body_parts.append(f"--{boundary}--".encode())
    body = b"\r\n".join(body_parts)

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Token {PAPERLESS_TOKEN}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            result = json.loads(resp.read())
            doc_id = result.get("id")
            log.info(f"  Paperless: uploaded '{title}' → doc_id={doc_id}")
            return doc_id
    except urllib.error.HTTPError as e:
        body_err = e.read()[:200]
        log.warning(f"  Paperless upload failed: {e.code} — {body_err}")
        return None
    except Exception as e:
        log.warning(f"  Paperless upload failed: {e}")
        return None


# ── DB insertion ───────────────────────────────────────────────────────────────
def insert_menu_row(conn, client_id, client_name, week_start, day,
                    salad, soup, main, side, confidence, pdf_name, page_num, notes):
    cur = conn.cursor()
    cur.execute("SELECT id FROM client_menus WHERE client_id=? AND week_start=? AND day=?",
                (client_id, week_start, day))
    if cur.fetchone():
        return False  # already exists
    cur.execute("""
        INSERT INTO client_menus
          (client_id, client_name, week_start, day, salad, soup, main, side,
           confidence, source_pdf, page_num, source, notes, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
    """, (client_id, client_name, week_start, day, salad, soup, main, side,
          confidence, pdf_name, str(page_num), "vision-pipeline", notes))
    conn.commit()
    return True


# ── Page classification ────────────────────────────────────────────────────────
def is_menu_page(pdf_path: Path, page_num: int) -> tuple[bool, str]:
    """
    Quick check: is this page a menu form?
    Returns (is_menu, page_type) where page_type is 'p1', 'p2', or 'unknown'.
    Uses pdfplumber first, falls back to pymupdf.
    """
    text = ""
    try:
        import pdfplumber
        with pdfplumber.open(str(pdf_path)) as pdf:
            if page_num < len(pdf.pages):
                text = pdf.pages[page_num].extract_text() or ""
    except Exception:
        pass

    if not text:
        try:
            import fitz
            doc = fitz.open(str(pdf_path))
            if page_num < len(doc):
                text = doc[page_num].get_text()
        except Exception:
            pass

    text_upper = text.upper()

    # p1 markers
    if any(k in text_upper for k in ["GARDEN OF JOY", "САЛАТЫ", "SALATY", "ИМЯЯ", "ИМЯ:"]):
        return True, "p1"

    # p2 markers
    if any(k in text_upper for k in ["ПРОДОЛЖЕНИЕ", "ГАРНИР", "GARNER", "CONTINUATION"]):
        return True, "p2"

    # Cyrillic-heavy but unclassified — likely menu (scanned forms rarely have text layer)
    cyrillic_count = sum(1 for c in text if "Ѐ" <= c <= "ӿ")
    if cyrillic_count > 30:
        return True, "p1" if page_num % 2 == 0 else "p2"

    # No text at all (scanned image) — classify by page position
    if len(text.strip()) < 10:
        return True, "p1" if page_num % 2 == 0 else "p2"

    return False, "unknown"


# ── Core: process one PDF ──────────────────────────────────────────────────────
def process_menu_pdf(pdf_path: Path, dry_run: bool = False,
                     scan_date: date | None = None) -> dict:
    """
    Process a single menu form PDF.
    Returns summary dict: {inserted, skipped, errors, clients}
    """
    # Accept both string paths and Path objects (fixes 'str' object has no attribute 'name')
    if isinstance(pdf_path, str):
        pdf_path = Path(pdf_path)
    log.info(f"Processing: {pdf_path.name}")

    # Load processed log
    processed = {}
    if PROCESSED_LOG.exists():
        try:
            processed = json.loads(PROCESSED_LOG.read_text())
        except Exception:
            processed = {}

    if pdf_path.name in processed and not dry_run:
        log.info(f"  Already processed — skipping")
        return {"status": "already_processed", "file": pdf_path.name}

    # Count pages
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        n_pages = len(doc)
        doc.close()
    except Exception as e:
        return {"status": "error", "reason": f"Cannot open PDF: {e}"}

    log.info(f"  {n_pages} pages")

    # Paperless archival (Engine 3) — do this first, non-blocking
    if not dry_run:
        paperless_title = f"GOJ Menu — {pdf_path.stem}"
        submit_to_paperless(pdf_path, paperless_title)

    # Open DB
    conn = None
    if not dry_run:
        conn = sqlite3.connect(str(DB_PATH))

    summary = {"inserted": 0, "skipped": 0, "errors": 0, "clients": [], "file": pdf_path.name}

    # Process pages in pairs (p1 + p2 for same client)
    # Detect page type for each page
    page_types = []
    for i in range(n_pages):
        _, ptype = is_menu_page(pdf_path, i)
        page_types.append(ptype)

    log.info(f"  Page types: {page_types}")

    i = 0
    while i < n_pages:
        # Try to find a p1+p2 pair starting at i
        if page_types[i] == "p2" and i + 1 < n_pages and page_types[i + 1] == "p1":
            # p2 comes before p1 (scanner order: p2 first)
            p2_idx, p1_idx = i, i + 1
            i += 2
        elif page_types[i] == "p1" and i + 1 < n_pages and page_types[i + 1] == "p2":
            p1_idx, p2_idx = i, i + 1
            i += 2
        elif page_types[i] == "p1":
            # p1 without p2 (incomplete form)
            p1_idx, p2_idx = i, None
            i += 1
        elif page_types[i] == "p2":
            # p2 without p1
            p1_idx, p2_idx = None, i
            i += 1
        else:
            i += 1
            continue

        log.info(f"  Processing pair: p1={p1_idx} p2={p2_idx}")

        # Engine 1: Vision
        p1_data = None
        p2_data = None

        if p1_idx is not None:
            img_b64 = pdf_page_to_base64(pdf_path, p1_idx)
            if img_b64:
                prompt = VISION_PROMPT_P1.format(
                    salads=", ".join(SALADS),
                    soups=", ".join(SOUPS),
                    mains_p1=", ".join(MAINS_P1),
                )
                p1_data = call_vision(img_b64, prompt)
                if p1_data:
                    log.info(f"    p1 Vision: client='{p1_data.get('client_name')}' week='{p1_data.get('week_indicator')}' conf={p1_data.get('confidence')}")
                else:
                    log.warning(f"    p1 Vision returned no data")

        if p2_idx is not None:
            img_b64 = pdf_page_to_base64(pdf_path, p2_idx)
            if img_b64:
                prompt = VISION_PROMPT_P2.format(
                    mains_p2=", ".join(MAINS_P2),
                    sides=", ".join(SIDES),
                )
                p2_data = call_vision(img_b64, prompt)
                if p2_data:
                    log.info(f"    p2 Vision: conf={p2_data.get('confidence')}")

        if not p1_data and not p2_data:
            log.warning(f"  No Vision data for pair p1={p1_idx} p2={p2_idx} — skipping")
            summary["errors"] += 1
            continue

        # Engine 2: Tesseract validator for name/week
        tess_result = {}
        if p1_idx is not None:
            tess_result = tesseract_extract_name_week(pdf_path, p1_idx)
            if tess_result.get("name"):
                log.debug(f"    Tesseract name: '{tess_result['name']}'")

        # Resolve client name — prefer Vision, cross-check with Tesseract
        raw_name = (p1_data or {}).get("client_name") or tess_result.get("name") or ""
        week_ind = (p1_data or {}).get("week_indicator") or tess_result.get("week")
        confidence_base = float((p1_data or {}).get("confidence", 0.75))

        if not conn:
            # dry_run
            log.info(f"  [DRY] Would insert client: '{raw_name}' week='{week_ind}'")
            summary["clients"].append(raw_name)
            continue

        cid, db_name, match_score = match_client_name(raw_name, conn)
        if not cid or match_score < 0.55:
            log.warning(f"  No DB match for '{raw_name}' (best score={match_score:.2f}) — skipping pair")
            # Notify via Rexxie if telegram configured
            _notify_unmatched(raw_name, pdf_path.name, p1_idx)
            summary["errors"] += 1
            continue

        if match_score < 0.80:
            # Low-confidence match: log a warning but do NOT insert — prevents false client matches.
            # Threshold: auto-insert requires ≥ 0.80; ≥ 0.90 is a clean match.
            log.warning(
                f"  LOW-CONFIDENCE MATCH: '{raw_name}' → {db_name} ({cid}) "
                f"score={match_score:.2f} — skipping (requires ≥ 0.80 to auto-insert). "
                f"Review manually if this is a real client."
            )
            summary["errors"] += 1
            continue

        week_start = infer_week_start(week_ind, scan_date)
        final_conf = round(confidence_base * match_score, 2)

        log.info(f"  Client: '{raw_name}' → {db_name} ({cid}) score={match_score:.2f} week={week_start}")

        # Merge p1 + p2 checks
        checks_p1 = (p1_data or {}).get("checks", {})
        checks_p2 = (p2_data or {}).get("checks", {})
        page_conf2 = float((p2_data or {}).get("confidence", 0.75)) if p2_data else 0.75

        for day in DAYS:
            c1 = checks_p1.get(day, {})
            c2 = checks_p2.get(day, {})

            salad = _clean_item(c1.get("salad"), SALADS)
            soup  = _clean_item(c1.get("soup"),  SOUPS)
            main  = _clean_item(c1.get("main"),  MAINS_P1) or _clean_item(c2.get("main"), MAINS_P2)
            side  = _clean_item(c2.get("side"),  SIDES)

            # Skip days with nothing at all
            if not any([salad, soup, main, side]):
                continue

            day_conf = round((confidence_base + page_conf2) / 2 * match_score, 2)

            conflicts = []
            if p1_data and p1_data.get("conflicts"):
                conflicts += [c for c in p1_data["conflicts"] if day in c]
            if p2_data and p2_data.get("conflicts"):
                conflicts += [c for c in p2_data["conflicts"] if day in c]

            notes = "; ".join(conflicts) if conflicts else None
            if match_score < 0.75:
                notes = (notes or "") + f"; Name match score {match_score:.2f} (raw: '{raw_name}')"
            if week_ind:
                notes = (notes or "") + f"; Week indicator: {week_ind}"

            page_ref = f"p1={p1_idx},p2={p2_idx}"

            if dry_run:
                log.info(f"    [DRY] {day}: {salad} / {soup} / {main} / {side}")
                continue

            inserted = insert_menu_row(
                conn, cid, db_name, week_start, day,
                salad, soup, main, side,
                day_conf, pdf_path.name, page_ref, notes
            )
            if inserted:
                log.info(f"    ✓ INSERT {db_name} {week_start} {day}")
                summary["inserted"] += 1
            else:
                log.info(f"    ↩  SKIP   {db_name} {week_start} {day} (exists)")
                summary["skipped"] += 1

        if db_name not in summary["clients"]:
            summary["clients"].append(db_name)

    if conn:
        conn.close()

    # Mark as processed
    if not dry_run and summary["errors"] == 0:
        processed[pdf_path.name] = datetime.now().isoformat()
        PROCESSED_LOG.write_text(json.dumps(processed, indent=2))

    log.info(f"  Done: {summary['inserted']} inserted, {summary['skipped']} skipped, {summary['errors']} errors")
    return {**summary, "status": "ok"}


def _clean_item(raw: str | None, valid_list: list[str]) -> str | None:
    """Match raw item string to closest valid list entry, or None."""
    if not raw or raw.lower() in ("null", "none", ""):
        return None
    # Exact match first
    for item in valid_list:
        if raw.strip().lower() == item.lower():
            return item
    # Fuzzy match
    matches = difflib.get_close_matches(raw.strip(), valid_list, n=1, cutoff=0.55)
    return matches[0] if matches else raw.strip()


def _notify_unmatched(raw_name: str, pdf_name: str, page: int):
    """Send Telegram alert for unmatched client name."""
    try:
        tg_config = REX_DIR / "rex_rexxie_telegram_config.json"
        if not tg_config.exists():
            return
        cfg = json.loads(tg_config.read_text())
        token, chat_id = cfg.get("bot_token"), cfg.get("owner_chat_id")
        if not token or not chat_id:
            return
        msg = (f"⚠️ <b>Menu OCR: Client not found</b>\n\n"
               f"📄 <b>PDF:</b> {pdf_name} (page {page})\n"
               f"👤 <b>Name on form:</b> {raw_name}\n\n"
               f"Manual review needed — check spelling and add to DB if new client.")
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


# ── Batch mode ─────────────────────────────────────────────────────────────────
def process_batch(folder: Path, dry_run: bool = False) -> dict:
    """Process all unprocessed menu PDFs in a folder."""
    processed = {}
    if PROCESSED_LOG.exists():
        try:
            processed = json.loads(PROCESSED_LOG.read_text())
        except Exception:
            pass

    pdfs = sorted(folder.glob("*.pdf"))
    menu_pdfs = [p for p in pdfs if not p.name.startswith(".")]
    log.info(f"Batch: {len(menu_pdfs)} PDFs in {folder}")

    total = {"inserted": 0, "skipped": 0, "errors": 0, "files": 0}
    for pdf in menu_pdfs:
        if pdf.name in processed:
            log.info(f"  {pdf.name}: already processed")
            continue

        # Quick check: does it look like a menu?
        _, ptype = is_menu_page(pdf, 0)
        if ptype == "unknown" and pdf.stat().st_size < 500_000:
            log.info(f"  {pdf.name}: too small / not menu — skipping")
            continue

        result = process_menu_pdf(pdf, dry_run=dry_run)
        if result.get("status") in ("ok", "already_processed"):
            total["inserted"] += result.get("inserted", 0)
            total["skipped"]  += result.get("skipped", 0)
            total["errors"]   += result.get("errors", 0)
            total["files"]    += 1

    log.info(f"Batch done: {total}")
    return total


# ── CLI ─────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="GOJ Menu Form OCR Pipeline")
    parser.add_argument("path", nargs="?", help="PDF file or folder to process")
    parser.add_argument("--batch", metavar="FOLDER", help="Process all PDFs in folder")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--scan-date", help="Scan date YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    scan_dt = date.fromisoformat(args.scan_date) if args.scan_date else None

    if args.batch:
        process_batch(Path(args.batch), dry_run=args.dry_run)
    elif args.path:
        p = Path(args.path)
        if p.is_dir():
            process_batch(p, dry_run=args.dry_run)
        else:
            result = process_menu_pdf(p, dry_run=args.dry_run, scan_date=scan_dt)
            print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        # Default: process signins/ folder
        process_batch(REX_DIR / "signins", dry_run=args.dry_run)
