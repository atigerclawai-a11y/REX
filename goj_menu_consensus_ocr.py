#!/usr/bin/env python3
"""
GOJ Menu Consensus OCR System
Runs 2 local OCR engines (Tesseract, Paperless) and votes on results.
4-engine consensus OCR: Tesseract (local) + Google Drive OCR + Paperless (LAN) + Claude Vision.
Cloud engines approved by Kato 2026-06-18 — menu data (names + food choices) is not PHI for GOJ.
Confidence-based routing: high confidence → database, low confidence → flag queue for Rexxie.
Confidence-based storage: high confidence → database, low confidence → flag queue for Rexxie.
"""

import os
import sys
import json
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from difflib import SequenceMatcher, get_close_matches
import subprocess
import time
import urllib.request
import urllib.error

# Fix 1: macOS TMPDIR symlink — Leptonica doesn't follow /tmp → /private/tmp.
# Without this, every Tesseract call silently returns empty word lists.
if sys.platform == 'darwin':
    os.environ.setdefault('TMPDIR', '/private/tmp')

# OCR dependencies
try:
    from pdf2image import convert_from_path
    import pytesseract
    from PIL import Image, ImageEnhance, ImageFilter
except ImportError as e:
    print(f"WARNING: Missing PIL/pdf2image dependency: {e}", file=sys.stderr)

# Google API — OAuth2 installed-app flow (NOT service account)
try:
    from google.oauth2.credentials import Credentials as OAuthCredentials
    from google.auth.transport.requests import Request as AuthRequest
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
except ImportError:
    print("WARNING: Google API libraries not available", file=sys.stderr)

# Anthropic Claude Vision API
try:
    import anthropic
except ImportError:
    print("WARNING: Anthropic library not available", file=sys.stderr)


# ============================================================================
# CONSTANTS (canonical source: CC_menu_constants.py)
# ============================================================================
from CC_menu_constants import (
    SALADS, SOUPS, ALL_MAINS as MAINS, SIDES, DAY_MAP as DAYS, CHECKMARKS,
    MAINS_P1, MAINS_P2, ALL_MAINS, DAY_MAP, DAYS as DAYS_LIST,
)

# Learning manager — optional, degrades gracefully if module is missing
try:
    from CC_ocr_learning_manager import (
        load_store             as _load_learning_store,
        save_store             as _save_learning_store,
        record_high_confidence as _record_high_confidence,
    )
    _LEARNING_MANAGER_OK = True
except ImportError:
    _LEARNING_MANAGER_OK = False

GOOGLE_DRIVE_FOLDER_ID = "1OBrFP9NR_1lYm_PLHjXXgnISqtxMxuo4"
PAPERLESS_BASE = "http://localhost:8010"
PAPERLESS_TOKEN = "204f4af0226532176058cd174abec7a73311728a"

CONFIDENCE_THRESHOLDS = {
    "auto_accept": 0.75,
    "flag": 0.5,
}


# ============================================================================
# API KEY LOADER
# ============================================================================

def _load_api_key(key_name='ANTHROPIC_API_KEY') -> str:
    """Load API key from environment or .env file."""
    key = os.environ.get(key_name, '').strip()
    if key:
        return key

    # Try loading from .env in REX directory
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        try:
            with open(env_path) as f:
                for line in f:
                    if line.startswith(f'{key_name}='):
                        key = line.split('=', 1)[1].strip().strip('"\'')
                        if key:
                            return key
        except Exception:
            pass

    # Try parent .env
    env_path = os.path.expanduser('~/Desktop/REX/.env')
    if os.path.exists(env_path):
        try:
            with open(env_path) as f:
                for line in f:
                    if line.startswith(f'{key_name}='):
                        key = line.split('=', 1)[1].strip().strip('"\'')
                        if key:
                            return key
        except Exception:
            pass

    return key


# ============================================================================
# LEARNING DATABASE
# ============================================================================

def load_learning_corrections(learning_path):
    """Load OCR correction mappings from learning file."""
    if not os.path.exists(learning_path):
        return {"name_corrections": {}, "item_corrections": {}}

    try:
        with open(learning_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"WARNING: Failed to load learning file: {e}", file=sys.stderr)
        return {"name_corrections": {}, "item_corrections": {}}


def save_correction(learning_path, ocr_text, correct_value, field_type="item"):
    """Save a new correction to the learning file."""
    data = load_learning_corrections(learning_path)

    if field_type == "name":
        data["name_corrections"][ocr_text] = correct_value
    else:
        data["item_corrections"][ocr_text] = correct_value

    with open(learning_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def apply_learning(text, corrections):
    """Pre-correct known OCR errors before parsing."""
    for ocr_variant, correct_value in corrections.items():
        text = text.replace(ocr_variant, correct_value)
    return text


# ============================================================================
# ENGINE 1: TESSERACT OCR
# ============================================================================

def run_tesseract_ocr(pdf_path, learning_path):
    """Run Tesseract OCR on PDF with learning corrections."""
    try:
        images = convert_from_path(pdf_path, dpi=300)
        all_text = []

        tessdata_dir = _find_tessdata_dir()
        custom_config = f'--tessdata-dir {tessdata_dir} --psm 6' if tessdata_dir else '--psm 6'

        old_prefix = os.environ.get('TESSDATA_PREFIX')
        if tessdata_dir:
            os.environ['TESSDATA_PREFIX'] = tessdata_dir
        try:
            for image in images:
                # Preprocess
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(1.5)
                image = image.filter(ImageFilter.SHARPEN)

                # OCR
                try:
                    text = pytesseract.image_to_string(image, lang='rus+eng', config=custom_config)
                except Exception:
                    text = pytesseract.image_to_string(image, lang='eng', config=custom_config)

                all_text.append(text)
        finally:
            if old_prefix is not None:
                os.environ['TESSDATA_PREFIX'] = old_prefix
            elif 'TESSDATA_PREFIX' in os.environ:
                del os.environ['TESSDATA_PREFIX']

        combined_text = '\n'.join(all_text)

        # Apply learning corrections
        corrections = load_learning_corrections(learning_path)
        combined_text = apply_learning(combined_text, corrections.get("item_corrections", {}))

        return combined_text
    except Exception as e:
        print(f"ERROR: Tesseract OCR failed on {pdf_path}: {e}", file=sys.stderr)
        return None


def run_tesseract_ocr_grid(pdf_path, learning_path):
    """
    Position-aware Tesseract OCR for GOJ menu grid forms.
    Uses bounding-box data from image_to_data() to map checkmarks to (item, day).
    Replaces parse_menu_text() for the Tesseract engine.
    Returns a parsed dict directly (same shape as parse_menu_text output).
    """
    try:
        from pytesseract import Output as _Output

        images = convert_from_path(pdf_path, dpi=300)

        TESSDATA_DIR = '/opt/homebrew/share/tessdata'
        TESS_CONFIG = f'--tessdata-dir {TESSDATA_DIR} --psm 6'

        # Russian day header abbreviations → day code
        _DAY_HDR = {
            'ПН': 'M',  'ПОН': 'M',  'Пн': 'M',  'Пон': 'M',
            'ВТ': 'T',  'ВТО': 'T',  'Вт': 'T',
            'СР': 'W',  'Ср': 'W',   'СРЕ': 'W',
            'ЧТ': 'TH', 'ЧЕТ': 'TH', 'Чт': 'TH',
            'ПТ': 'F',  'ПЯТ': 'F',  'Пт': 'F',
            'СБ': 'SA', 'СУБ': 'SA', 'Сб': 'SA',
        }
        _CHECKMARK_CHARS = set('VvXxLl+*') | {'✓', '✔', '√', '■', '☑'}

        days_data = {d: {'salad': None, 'soup': None, 'main': None, 'side': None}
                     for d in ['M', 'T', 'W', 'TH', 'F', 'SA']}
        client_name = None

        # All canonical items → category (build once)
        item_cat = {}
        for item in SALADS: item_cat[item.upper()] = 'salad'
        for item in SOUPS:  item_cat[item.upper()] = 'soup'
        for item in MAINS:  item_cat[item.upper()] = 'main'
        for item in SIDES:  item_cat[item.upper()] = 'side'

        all_items = (
            [(s, 'salad') for s in SALADS] +
            [(s, 'soup')  for s in SOUPS]  +
            [(m, 'main')  for m in MAINS]  +
            [(s, 'side')  for s in SIDES]
        )

        for image in images:
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(1.5)
            image = image.filter(ImageFilter.SHARPEN)
            img_w = image.width

            try:
                d = pytesseract.image_to_data(image, lang='rus+eng',
                                              config=TESS_CONFIG,
                                              output_type=_Output.DICT)
            except Exception:
                d = pytesseract.image_to_data(image, lang='eng',
                                              config=TESS_CONFIG,
                                              output_type=_Output.DICT)

            words  = d['text']
            lefts  = d['left']
            tops   = d['top']
            wids   = d['width']
            hgts   = d['height']
            confs  = d['conf']
            n      = len(words)

            # ── Client name ───────────────────────────────────────────────
            for i, w in enumerate(words):
                if not w.strip(): continue
                # Fix 2: include Latin OCR lookalikes (ФИО→UMA, ИМЯ→HMA etc.)
                if any(kw in w.upper() for kw in ('ФИО', 'ИМЯ', 'ФАМИЛИЯ', 'UMA', 'HMA', 'FIO')):
                    y0 = tops[i]
                    parts = [words[j] for j in range(i+1, min(i+6, n))
                             if words[j].strip() and abs(tops[j]-y0) < 25
                             and not any(kw in words[j].upper()
                                         for kw in ('ФИО','ИМЯ','ДАТА','НЕДЕЛЯ','UMA','HMA','FIO'))]
                    if parts and not client_name:
                        client_name = ' '.join(parts[:4])
                    break

            # ── Day column positions ──────────────────────────────────────
            col_xs = {}
            for i, w in enumerate(words):
                ws = w.strip()
                code = _DAY_HDR.get(ws) or _DAY_HDR.get(ws.upper())
                if code and confs[i] > 20:
                    col_xs.setdefault(code, []).append(lefts[i] + wids[i]//2)

            if not col_xs:
                continue   # can't locate columns on this page

            centers = {c: int(sum(xs)/len(xs)) for c, xs in col_xs.items()}
            sorted_cols = sorted(centers.items(), key=lambda x: x[1])

            col_ranges = {}
            for idx, (code, xc) in enumerate(sorted_cols):
                xmin = 0 if idx == 0 else (sorted_cols[idx-1][1] + xc)//2
                xmax = img_w if idx == len(sorted_cols)-1 else (xc + sorted_cols[idx+1][1])//2
                col_ranges[code] = (xmin, xmax)

            def _day_for_x(x):
                for code, (xmin, xmax) in col_ranges.items():
                    if xmin <= x <= xmax:
                        return code
                return None

            # ── Item row positions (fuzzy match word sequences) ───────────
            clean_words = [(i, words[i].strip(), tops[i]+hgts[i]//2)
                           for i in range(n) if words[i].strip()]
            item_rows = []
            for item_name, category in all_items:
                parts = item_name.split()
                if not parts: continue
                for idx, (i, w, y) in enumerate(clean_words):
                    if SequenceMatcher(None, w.upper(), parts[0].upper()).ratio() < 0.75:
                        continue
                    ok = True
                    for k, iw in enumerate(parts[1:], 1):
                        if idx+k >= len(clean_words): ok = False; break
                        if SequenceMatcher(None, clean_words[idx+k][1].upper(),
                                           iw.upper()).ratio() < 0.70:
                            ok = False; break
                    if ok:
                        item_rows.append((y, item_name, category))
                        break

            # ── Checkmarks → (item, day) ──────────────────────────────────
            for i, w in enumerate(words):
                ws = w.strip()
                if not ws: continue
                is_ck = (ws in _CHECKMARK_CHARS or
                         (len(ws) == 1 and ws in 'VvXxLl+*') or
                         ws.lower() in ('да', 'yes'))
                if not is_ck: continue

                xc = lefts[i] + wids[i]//2
                yc = tops[i]  + hgts[i]//2
                day = _day_for_x(xc)
                if not day or not item_rows: continue

                closest = min(item_rows, key=lambda r: abs(r[0]-yc))
                if abs(closest[0]-yc) > 60: continue

                _, item_name, category = closest
                if days_data[day][category] is None:
                    days_data[day][category] = item_name

        # Apply learning corrections
        corrections = load_learning_corrections(learning_path)
        name_fixes  = corrections.get('name_corrections', {})
        item_fixes  = corrections.get('item_corrections', {})
        if client_name:
            client_name = name_fixes.get(client_name, client_name)
        for day in days_data:
            for field in days_data[day]:
                v = days_data[day][field]
                if v:
                    days_data[day][field] = item_fixes.get(v, v)

        return {
            'client_name': client_name,
            'week_date':   None,
            'days':        days_data,
            'source':      'tesseract_grid',
        }

    except Exception as e:
        print(f'ERROR: run_tesseract_ocr_grid failed: {e}', file=sys.stderr)
        return None


# ============================================================================
# ENGINE 1-STRUCTURED: TESSERACT WITH BOUNDING-BOX LAYOUT ANALYSIS
# Processes PDFs as page-pairs (2 pages per client). Uses image_to_data()
# bounding boxes to detect day columns by position, then assigns checkmarks
# to day columns by nearest x-coordinate. Handles batch PDFs correctly.
# ============================================================================

def _find_tessdata_dir():
    """Return the first tessdata directory that contains traineddata files, or None."""
    candidates = [
        '/opt/homebrew/share/tessdata',          # Mac Apple Silicon (Homebrew)
        '/usr/local/share/tessdata',              # Mac Intel (Homebrew)
        '/usr/share/tesseract-ocr/5/tessdata',   # Ubuntu 22+
        '/usr/share/tesseract-ocr/4.00/tessdata', # Ubuntu 20
        '/usr/share/tessdata',
        os.path.expanduser('~/.tesseract_data/tessdata'),
    ]
    for path in candidates:
        try:
            if os.path.isdir(path) and any(f.endswith('.traineddata') for f in os.listdir(path)):
                return path
        except OSError:
            continue
    return None


def _ocr_with_tessdata(image, *, lang='rus+eng', psm=6):
    """Run pytesseract.image_to_data, temporarily pinning TESSDATA_PREFIX so
    environment variables can't override the discovered tessdata location."""
    tessdata_dir = _find_tessdata_dir()

    # Build config: prefer explicit tessdata-dir flag
    cfg = f'--psm {psm}'
    if tessdata_dir:
        cfg = f'--tessdata-dir {tessdata_dir} --psm {psm}'

    # Temporarily pin TESSDATA_PREFIX to avoid env var conflicts
    old_prefix = os.environ.get('TESSDATA_PREFIX')
    if tessdata_dir:
        os.environ['TESSDATA_PREFIX'] = tessdata_dir
    try:
        data = pytesseract.image_to_data(image, lang=lang, config=cfg,
                                         output_type=pytesseract.Output.DICT)
        return data
    except Exception:
        # Russian data unavailable — fall back to English only
        try:
            data = pytesseract.image_to_data(image, lang='eng', config=f'--psm {psm}',
                                             output_type=pytesseract.Output.DICT)
            return data
        except Exception:
            return None
    finally:
        if old_prefix is not None:
            os.environ['TESSDATA_PREFIX'] = old_prefix
        elif 'TESSDATA_PREFIX' in os.environ:
            del os.environ['TESSDATA_PREFIX']


def _ocr_page_words(image):
    """Run pytesseract.image_to_data on a preprocessed PIL image.
    Returns list of {text, left, top, width, height, cx} for conf > 20."""
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(1.5)
    image = image.filter(ImageFilter.SHARPEN)

    data = _ocr_with_tessdata(image)
    if data is None:
        return []

    words = []
    for i in range(len(data['text'])):
        txt = str(data['text'][i]).strip()
        if txt and int(data['conf'][i]) > 20:
            l, t, w, h = (int(data[k][i]) for k in ('left', 'top', 'width', 'height'))
            words.append({'text': txt, 'left': l, 'top': t,
                          'width': w, 'height': h, 'cx': l + w // 2})
    return words


def _find_day_cols(words):
    """Find x-centers of day columns from header abbreviations in top 25% of page.
    Returns dict {day_code: x_center}, e.g. {'M': 320, 'T': 410, ...}"""
    RU_TO_CODE = {
        'ПН': 'M', 'ПОН': 'M',
        'ВТ': 'T', 'ВТО': 'T',
        'СР': 'W',
        'ЧТ': 'TH', 'ЧЕТ': 'TH',
        'ПТ': 'F', 'ПЯТ': 'F',
        'СБ': 'SA', 'СУБ': 'SA',
    }
    tops = [w['top'] for w in words if w['top'] > 0]
    if not tops:
        return {}
    ceiling = max(tops) * 0.25
    cols = {}
    for w in words:
        if w['top'] > ceiling:
            continue
        t = w['text'].upper().strip('.:-')
        for pat, code in RU_TO_CODE.items():
            if t == pat or t.startswith(pat):
                cols.setdefault(code, w['cx'])
                break
    return cols


def _item_row_y(words, item_name):
    """Return y (top) of the row containing a menu item via fuzzy first-word match.
    Also verifies a second word for multi-word items. Returns None if not found."""
    parts = item_name.split()
    first = parts[0].lower()
    second = parts[1].lower() if len(parts) > 1 else None

    for w in words:
        if SequenceMatcher(None, w['text'].lower(), first).ratio() < 0.68:
            continue
        y = w['top']
        if second:
            row_texts = [o['text'].lower() for o in words if abs(o['top'] - y) < 14]
            if not any(SequenceMatcher(None, rt, second).ratio() >= 0.65 for rt in row_texts):
                continue
        return y
    return None


def _checked_days_on_row(words, row_y, day_cols, tol=14, max_dist=90):
    """Return day codes that have a checkmark within tol pixels of row_y,
    assigned to the nearest day column within max_dist pixels."""
    if not day_cols:
        return []
    checked = []
    for w in words:
        if abs(w['top'] - row_y) > tol:
            continue
        if not (any(m in w['text'] for m in CHECKMARKS) or w['text'] in CHECKMARKS):
            continue
        best, best_d = None, max_dist
        for code, cx in day_cols.items():
            d = abs(w['cx'] - cx)
            if d < best_d:
                best_d, best = d, code
        if best and best not in checked:
            checked.append(best)
    return checked


def _extract_name_from_words(words, corrections):
    """Extract client name from words to the right of Имя: / ФИО: label."""
    # Fix 2: Latin OCR lookalikes for Cyrillic label text (ФИО→UMA, ИМЯ→HMA)
    TRIGGERS = {'ИМЯ', 'ФИО', 'УМА', 'ИМЕНА', 'NAME', 'UMA', 'HMA', 'FIO', 'DVA', 'IMА'}
    for w in words:
        if w['text'].upper().rstrip(':') not in TRIGGERS:
            continue
        row_y = w['top']
        right_edge = w['left'] + w['width']
        parts = sorted(
            (o for o in words
             if abs(o['top'] - row_y) < 12
             and o['left'] > right_edge
             and o['text'].upper().rstrip(':') not in TRIGGERS),
            key=lambda o: o['left']
        )
        raw = ' '.join(p['text'] for p in parts[:5])
        for bad, good in corrections.get('name_corrections', {}).items():
            raw = raw.replace(bad, good)
        name = ''.join(c for c in raw if c.isalpha() or c.isspace() or ord(c) > 127).strip()
        if len(name) > 3:
            return name
    return None


def run_tesseract_ocr_structured(pdf_path, learning_path):
    """
    Structured Tesseract engine using bounding-box layout analysis.
    Processes every 2-page pair in the PDF (one pair = one client form).
    Returns list of per-client result dicts ready for consensus_vote().
    Each dict: {client_name, week_date, days, _source, _confidence}
    """
    try:
        images = convert_from_path(pdf_path, dpi=300)
    except Exception as e:
        print(f"ERROR: PDF→image failed: {e}", file=sys.stderr)
        return []

    corrections = load_learning_corrections(learning_path)
    results = []

    for i in range(0, len(images), 2):
        p1_words = _ocr_page_words(images[i])
        p2_words = _ocr_page_words(images[i + 1]) if i + 1 < len(images) else []

        day_cols_p1 = _find_day_cols(p1_words)
        day_cols_p2 = _find_day_cols(p2_words) if p2_words else {}
        # Merge column positions — p1 takes priority
        day_cols = {**day_cols_p2, **day_cols_p1}

        client_name = _extract_name_from_words(p1_words, corrections)

        days = {d: {'salad': None, 'soup': None, 'main': None, 'side': None}
                for d in ['M', 'T', 'W', 'TH', 'F', 'SA']}

        # Page 1: salads + soups + MAINS_P1
        cols1 = day_cols_p1 or day_cols
        for field, items in [('salad', SALADS), ('soup', SOUPS), ('main', MAINS_P1)]:
            for item in items:
                y = _item_row_y(p1_words, item)
                if y is None:
                    continue
                for day in _checked_days_on_row(p1_words, y, cols1):
                    if days[day][field] is None:
                        days[day][field] = item

        # Page 2: MAINS_P2 + SIDES
        if p2_words:
            cols2 = day_cols_p2 or day_cols
            for field, items in [('main', MAINS_P2), ('side', SIDES)]:
                for item in items:
                    y = _item_row_y(p2_words, item)
                    if y is None:
                        continue
                    for day in _checked_days_on_row(p2_words, y, cols2):
                        if days[day][field] is None:
                            days[day][field] = item

        has_sel = any(v for d in days.values() for v in d.values() if v)
        conf = 0.75 if (client_name and has_sel) else (0.50 if client_name else 0.20)

        results.append({
            'client_name': client_name,
            'week_date':   None,
            'days':        days,
            '_source':     'tesseract_structured',
            '_confidence': conf,
        })

    return results


# ============================================================================
# ENGINE 2: GOOGLE DRIVE OCR
# ============================================================================

def get_google_creds(token_path="~/.rex_google_token.json"):
    """Load Google OAuth2 credentials (installed-app flow with saved token).
    Token is at ~/.rex_google_token.json — run setup_google_auth.command once to create it.
    Auto-refreshes using refresh_token when expired.
    """
    SCOPES = [
        'https://www.googleapis.com/auth/drive.file',      # upload + read files created by this app
        'https://www.googleapis.com/auth/drive.readonly',  # read any Drive file
        'https://www.googleapis.com/auth/documents'
    ]
    token_path = os.path.expanduser(token_path)

    try:
        if not os.path.exists(token_path):
            print(f"WARNING: Google token not found at {token_path}. Run setup_google_auth.command.", file=sys.stderr)
            return None

        creds = OAuthCredentials.from_authorized_user_file(token_path, SCOPES)

        # Auto-refresh on expiry using stored refresh_token
        if creds.expired and creds.refresh_token:
            creds.refresh(AuthRequest())
            with open(token_path, 'w') as f:
                f.write(creds.to_json())

        if not creds.valid:
            print("WARNING: Google token invalid even after refresh. Re-run setup_google_auth.command.", file=sys.stderr)
            return None

        return creds
    except Exception as e:
        print(f"WARNING: Failed to load Google credentials: {e}", file=sys.stderr)
        return None


def run_google_drive_ocr(pdf_path, token_path="~/.rex_google_token.json"):
    """Upload PDF to Google Drive, convert to Google Doc (triggers OCR), extract text."""
    try:
        creds = get_google_creds(token_path)
        if not creds:
            return None

        drive_service = build('drive', 'v3', credentials=creds)
        docs_service = build('docs', 'v1', credentials=creds)

        # Upload PDF to GOJ menus folder with MediaFileUpload
        file_metadata = {
            'name': f"menu_ocr_{uuid.uuid4().hex[:8]}.pdf",
            'parents': [GOOGLE_DRIVE_FOLDER_ID],
        }
        media_upload = MediaFileUpload(pdf_path, mimetype='application/pdf', resumable=False)
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media_upload,
            supportsAllDrives=True,
            fields='id'
        ).execute()

        file_id = file['id']

        # Copy to Google Docs (triggers OCR)
        copy_metadata = {
            'name': f"menu_ocr_{uuid.uuid4().hex[:8]}",
            'mimeType': 'application/vnd.google-apps.document'
        }

        copy_result = drive_service.files().copy(
            fileId=file_id,
            body=copy_metadata,
            supportsAllDrives=True
        ).execute()

        doc_id = copy_result['id']

        # Wait for OCR processing (up to 30 seconds)
        for _ in range(30):
            time.sleep(1)
            try:
                doc = docs_service.documents().get(documentId=doc_id).execute()
                # Extract text from doc
                text = ""
                for elem in doc.get('body', {}).get('content', []):
                    if 'paragraph' in elem:
                        for run in elem['paragraph'].get('elements', []):
                            if 'textRun' in run:
                                text += run['textRun'].get('content', '')

                if text.strip():
                    # Cleanup
                    drive_service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
                    drive_service.files().delete(fileId=doc_id, supportsAllDrives=True).execute()
                    return text
            except:
                pass

        # Cleanup on timeout
        try:
            drive_service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
            drive_service.files().delete(fileId=doc_id, supportsAllDrives=True).execute()
        except:
            pass

        return None
    except Exception as e:
        print(f"WARNING: Google Drive OCR failed: {e}", file=sys.stderr)
        return None


# ============================================================================
# ENGINE 3: PAPERLESS OCR
# ============================================================================

def run_paperless_ocr(pdf_path, week_date):
    """Upload PDF to Paperless-ngx, retrieve OCR'd content."""
    try:
        # Check connectivity WITH auth token (unauthenticated requests always return 401)
        try:
            ping_req = urllib.request.Request(
                f"{PAPERLESS_BASE}/api/documents/?page_size=1",
                headers={'Authorization': f'Token {PAPERLESS_TOKEN}'}
            )
            urllib.request.urlopen(ping_req, timeout=5)
        except urllib.error.URLError as e:
            print(f"WARNING: Paperless unreachable at {PAPERLESS_BASE}: {e}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"WARNING: Paperless ping failed: {e}", file=sys.stderr)
            return None

        # Upload via multipart/form-data (Paperless API requires this format)
        with open(pdf_path, 'rb') as pdf_file:
            pdf_data = pdf_file.read()

        boundary = uuid.uuid4().hex
        filename  = os.path.basename(pdf_path)
        body = (
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'
            f'Content-Type: application/pdf\r\n\r\n'
        ).encode('utf-8') + pdf_data + f'\r\n--{boundary}--\r\n'.encode('utf-8')

        headers = {
            'Authorization': f'Token {PAPERLESS_TOKEN}',
            'Content-Type': f'multipart/form-data; boundary={boundary}',
        }

        req = urllib.request.Request(
            f"{PAPERLESS_BASE}/api/documents/post_document/",
            data=body,
            headers=headers,
            method='POST'
        )

        response = urllib.request.urlopen(req, timeout=10)
        upload_result = json.loads(response.read().decode('utf-8'))

        # Paperless post_document returns a task UUID string (not a dict).
        # Older versions may return a dict with 'id'; handle both.
        if isinstance(upload_result, str):
            task_id = upload_result
        elif isinstance(upload_result, dict):
            task_id = upload_result.get('task_id') or upload_result.get('id')
        else:
            return None

        if not task_id:
            return None

        # Poll /api/tasks/?task_id=<uuid> until SUCCESS, then fetch doc content.
        doc_id = None
        for _ in range(30):
            time.sleep(2)
            try:
                task_req = urllib.request.Request(
                    f"{PAPERLESS_BASE}/api/tasks/?task_id={task_id}",
                    headers=headers
                )
                task_resp = urllib.request.urlopen(task_req, timeout=5)
                tasks = json.loads(task_resp.read().decode('utf-8'))
                # tasks is a list; find our task
                if isinstance(tasks, list) and tasks:
                    task = tasks[0]
                elif isinstance(tasks, dict):
                    task = tasks
                else:
                    continue
                if task.get('status') == 'SUCCESS':
                    doc_id = task.get('related_document')
                    break
                if task.get('status') in ('FAILURE', 'REVOKED'):
                    return None
            except Exception:
                pass

        if not doc_id:
            return None

        # Fetch the OCR'd content
        for _ in range(5):
            time.sleep(1)
            try:
                req = urllib.request.Request(
                    f"{PAPERLESS_BASE}/api/documents/{doc_id}/",
                    headers=headers
                )
                response = urllib.request.urlopen(req, timeout=5)
                doc = json.loads(response.read().decode('utf-8'))

                content = doc.get('content', '')
                if content.strip():
                    return content
            except:
                pass

        return None
    except Exception as e:
        print(f"WARNING: Paperless OCR failed: {e}", file=sys.stderr)
        return None


# ============================================================================
# ENGINE 4: CLAUDE VISION OCR
# ============================================================================

def run_claude_vision_ocr(pdf_path):
    """
    Engine 4: Claude Vision OCR
    Converts PDF pages to images and sends to Claude API for structured extraction.
    Returns list of parsed client records directly as structured dicts.
    Most powerful engine — understands form layout and context, not just raw text.
    """
    try:
        import base64
        import io

        # Use PyMuPDF (fitz) to render pages — no poppler/system dep needed
        try:
            import fitz  # PyMuPDF
            def _pdf_to_jpeg_b64(pdf_path, dpi=200):
                doc = fitz.open(str(pdf_path))
                mat = fitz.Matrix(dpi / 72, dpi / 72)
                result = []
                for page in doc:
                    pix = page.get_pixmap(matrix=mat)
                    result.append(pix.tobytes("jpeg"))
                return result
        except ImportError:
            # fallback to pdf2image if fitz somehow isn't available
            from pdf2image import convert_from_path
            def _pdf_to_jpeg_b64(pdf_path, dpi=200):
                pages = convert_from_path(str(pdf_path), dpi=dpi)
                out = []
                for img in pages:
                    buf = io.BytesIO()
                    img.save(buf, format='JPEG', quality=85)
                    out.append(buf.getvalue())
                return out

        # Try to get API key from environment or .env
        api_key = _load_api_key('ANTHROPIC_API_KEY')
        client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

        # Render all pages to JPEG bytes
        page_jpegs = _pdf_to_jpeg_b64(pdf_path, dpi=200)

        results = []

        # Process 2 pages at a time (each client form = 2 pages)
        for i in range(0, len(page_jpegs), 2):
            page_batch = page_jpegs[i:i+2]

            # Encode images to base64
            encoded_images = [base64.standard_b64encode(j).decode('utf-8') for j in page_batch]

            # Build the prompt with image content
            image_content = []
            for enc in encoded_images:
                image_content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": enc}
                })

            image_content.append({
                "type": "text",
                "text": """This is a Russian-language weekly menu form from Garden of Joy Adult Day Care in Brooklyn.

Extract the following information and return ONLY valid JSON, no other text:

{
  "client_name": "full name as written",
  "date_filled": "date if visible",
  "week_start": "YYYY-MM-DD (Monday of the week these menus apply to)",
  "days": {
    "M": {"salad": "item name or null", "soup": "item name or null", "main": "item name or null", "side": "item name or null"},
    "T": {"salad": null, "soup": null, "main": null, "side": null},
    "W": {"salad": null, "soup": null, "main": null, "side": null},
    "TH": {"salad": null, "soup": null, "main": null, "side": null},
    "F": {"salad": null, "soup": null, "main": null, "side": null},
    "SA": {"salad": null, "soup": null, "main": null, "side": null}
  }
}

The form has these sections:
- САЛАТЫ (Salads): Салат из баклажан, Салат весенний, Винегрет, Салат Днестр, Квашеная капуста, Оливье, Свекла, Селедка, Сало
- СУПЫ (Soups): Борщ зеленый, Борщ красный, Грибной суп, Куриный суп, Овощной суп, Харчо, Гороховый суп
- ГЛАВНОЕ БЛЮДО (Mains): Баса с помидорами под сыром, Блины с мясом, Блины с творогом, Вареники с картошкой, Голубцы, Гуляш, Дорадо запеченая, Жульен, Котлеты куриные, Куриные крылышки, Курица в терияки соусе, Пельмени, Поперечка, Салмон, Свиная отбивная, Цыпленок табака, Чалахач, Чебуреки, Шницель куриный
- ГАРНИР (Sides): Тушеная капуста, Картошка по деревенски, Пюре, Гречка, Паста, Рис, Жареная картошка, Без гарнира

Days are columns: Пон/Пн=Monday, Втор/Вт=Tuesday, Ср=Wednesday, Четв/Чт=Thursday, Пят/Пт=Friday, Суб/Сб=Saturday

A checkmark (✓, V, v, L, √, +, *, x, х, or filled box) next to an item in a day's column means that item was selected for that day.
Use the EXACT Russian item name from the lists above. Return null if no item is checked for that day/category.
Return ONLY the JSON object, nothing else."""
            })

            try:
                response = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=1024,
                    messages=[{"role": "user", "content": image_content}]
                )

                text = response.content[0].text.strip()
                # Extract JSON if wrapped in markdown
                if '```' in text:
                    text = text.split('```')[1]
                    if text.startswith('json'):
                        text = text[4:]

                parsed = json.loads(text)
                parsed['_source'] = 'claude_vision'
                parsed['_page_start'] = i + 1
                parsed['_confidence'] = 0.95  # Claude Vision is highly reliable
                results.append(parsed)

            except Exception as e:
                print(f"[Claude Vision] Page {i+1}-{i+2} error: {e}", file=sys.stderr)
                results.append(None)

        return results

    except Exception as e:
        print(f"WARNING: Claude Vision OCR failed: {e}", file=sys.stderr)
        return None


# ============================================================================
# TEXT PARSING
# ============================================================================

def parse_menu_text(text, source_name, learning_path):
    """Parse raw OCR text into structured menu data."""
    if not text:
        return None

    lines = text.split('\n')
    corrections = load_learning_corrections(learning_path)

    # Extract client name
    client_name = None
    for line in lines:
        if ':' in line:
            before_colon = line.split(':')[0].upper()
            # Fix 2: Latin OCR lookalikes for Cyrillic label text
            if any(x in before_colon for x in ['ИМЯ', 'УМА', 'ФИО', 'ИМЕНА', 'UMA', 'HMA', 'FIO']):
                parts = line.split(':')
                if len(parts) > 1:
                    potential_name = parts[-1].strip()
                    potential_name = ''.join(c for c in potential_name if c.isalpha() or c.isspace() or ord(c) > 127)
                    if len(potential_name) > 2:
                        client_name = potential_name
                        break

    # Extract week date
    week_date = None
    for line in lines:
        if any(x in line.upper() for x in ['ДАТА ЗАПОЛНЕНИЯ', 'НЕДЕЛЯ', 'WEEK']):
            # Try to extract date
            import re
            match = re.search(r'(\d{1,2})[./\-](\d{1,2})[./\-](\d{2,4})', line)
            if match:
                week_date = match.group(0)
                break

    # Extract daily selections
    days_data = {}
    for day_key, day_short in DAYS.items():
        if day_short not in days_data:
            days_data[day_short] = {
                'salad': None, 'soup': None, 'main': None, 'side': None
            }

        # Find checked items for this day
        day_context = '\n'.join([l for l in lines if day_key in l or day_short in l])

        if day_context:
            for salad in SALADS:
                if salad.lower() in day_context.lower() and _is_checked(day_context):
                    days_data[day_short]['salad'] = salad
                    break

            for soup in SOUPS:
                if soup.lower() in day_context.lower() and _is_checked(day_context):
                    days_data[day_short]['soup'] = soup
                    break

            for main in MAINS:
                if main.lower() in day_context.lower() and _is_checked(day_context):
                    days_data[day_short]['main'] = main
                    break

            for side in SIDES:
                if side.lower() in day_context.lower() and _is_checked(day_context):
                    days_data[day_short]['side'] = side
                    break

    return {
        'client_name': client_name,
        'week_date': week_date,
        'days': days_data,
        'source': source_name
    }


def _is_checked(text):
    """Simple check for presence of check marks."""
    return any(mark in text for mark in CHECKMARKS)


# ============================================================================
# CONSENSUS VOTING
# ============================================================================

def consensus_vote(results):
    """
    Vote on OCR results from multiple engines.
    Returns consensus with per-field confidence scores.

    Claude Vision authority rule: if a claude_vision result is present
    and its _confidence >= 0.90, it is treated as 3 votes instead of 1.
    This prevents low-quality Tesseract output from diluting a high-confidence
    Claude Vision result below the flag threshold.
    """
    valid_results = [r for r in results if r is not None]

    if not valid_results:
        return None

    # ── Claude Vision fast-path ───────────────────────────────────────────────
    # If Claude Vision returned a high-confidence structured result, trust it
    # directly without going through a vote that Tesseract garble could corrupt.
    claude_results = [r for r in valid_results
                      if r.get('_source') == 'claude_vision'
                      and float(r.get('_confidence', 0)) >= 0.90]
    if claude_results:
        cv = claude_results[0]
        # Normalise the structure so downstream code gets a consistent shape
        consensus = {
            'client_name': cv.get('client_name') or cv.get('candidate_name'),
            'week_date':   cv.get('week_start')  or cv.get('week_date'),
            'days':        cv.get('days', {}),
            'confidence': {'client_name': float(cv.get('_confidence', 0.95))},
            'engines_used': [r.get('_source', r.get('source', '?'))
                             for r in valid_results],
            'needs_review': False,
        }
        # Backfill per-day confidence at the Claude Vision level
        for day in consensus['days']:
            consensus['confidence'][day] = {
                k: float(cv.get('_confidence', 0.95))
                for k in ['salad', 'soup', 'main', 'side']
            }
        return consensus

    # ── Standard weighted vote ────────────────────────────────────────────────
    # Assign vote weights: claude_vision=3, others=1
    VOTE_WEIGHTS = {'claude_vision': 3}

    def _weight(r):
        src = r.get('_source') or r.get('source', '')
        return VOTE_WEIGHTS.get(src, 1)

    consensus = {
        'client_name': None,
        'week_date': None,
        'days': {},
        'confidence': {},
        'engines_used': [r.get('_source', r.get('source', '?')) for r in valid_results],
        'needs_review': False
    }

    total_weight = sum(_weight(r) for r in valid_results)

    # Vote on client name
    names = [r.get('client_name') for r in valid_results if r.get('client_name')]
    if names:
        name_votes = {}
        for r in valid_results:
            name = r.get('client_name')
            if name:
                name_votes[name] = name_votes.get(name, 0) + _weight(r)

        best_name = max(name_votes.items(), key=lambda x: x[1])
        consensus['client_name'] = best_name[0]
        consensus['confidence']['client_name'] = best_name[1] / total_weight

        if consensus['confidence']['client_name'] < CONFIDENCE_THRESHOLDS['flag']:
            consensus['needs_review'] = True

    # Vote on each day's items (weighted)
    days_to_check = ['M', 'T', 'W', 'TH', 'F', 'SA']
    for day in days_to_check:
        consensus['days'][day] = {
            'salad': None, 'soup': None, 'main': None, 'side': None
        }
        consensus['confidence'][day] = {
            'salad': 0.0, 'soup': 0.0, 'main': 0.0, 'side': 0.0
        }

        for item_type in ['salad', 'soup', 'main', 'side']:
            item_votes = {}
            for r in valid_results:
                item = r.get('days', {}).get(day, {}).get(item_type)
                if item:
                    item_votes[item] = item_votes.get(item, 0) + _weight(r)

            if item_votes:
                best_item = max(item_votes.items(), key=lambda x: x[1])
                consensus['days'][day][item_type] = best_item[0]
                consensus['confidence'][day][item_type] = best_item[1] / total_weight

                if consensus['confidence'][day][item_type] < CONFIDENCE_THRESHOLDS['flag']:
                    consensus['needs_review'] = True

    return consensus


# ============================================================================
# CLIENT MATCHING
# ============================================================================

def match_client(name_str, db_path):
    """Fuzzy match OCR'd name against database clients."""
    if not name_str:
        return None, None, 0.0

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # Try active-only query first; fall back to all clients if column missing
        try:
            cursor.execute("SELECT client_id, name FROM clients WHERE active = 1")
        except sqlite3.OperationalError:
            cursor.execute("SELECT client_id, name FROM clients")
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return None, None, 0.0

        clean_name = name_str.upper().strip()
        # Try both "First Last" and "Last First" orderings:
        # OCR tends to output names in First-Last order but the DB stores Last-First.
        # e.g. OCR: "Alexander Vayman" → also try "Vayman Alexander" to match DB.
        parts = clean_name.split()
        candidates = [clean_name]
        if len(parts) >= 2:
            # Move first word to end: "Alexander Vayman" → "Vayman Alexander"
            candidates.append(" ".join(parts[1:] + parts[:1]))

        best_match = None
        best_score = 0.0

        for client_id, db_name in rows:
            db_clean = db_name.upper().strip()
            for candidate in candidates:
                score = SequenceMatcher(None, candidate, db_clean).ratio()
                if score > best_score and score >= 0.6:
                    best_score = score
                    best_match = (client_id, db_name)

        if best_match:
            return best_match[0], best_match[1], best_score

        return None, None, 0.0
    except Exception as e:
        print(f"ERROR: Client matching failed: {e}", file=sys.stderr)
        return None, None, 0.0


# ============================================================================
# DATABASE OPERATIONS
# ============================================================================

def init_database(db_path):
    """Initialize database tables."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS client_menus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            client_name TEXT,
            week_start TEXT,
            day TEXT,
            salad TEXT,
            soup TEXT,
            main TEXT,
            side TEXT,
            confidence REAL,
            source_pdf TEXT,
            ocr_engines TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients(client_id)
        )
    """)

    conn.commit()
    conn.close()


def _get_target_service_week(consensus_week_date=None):
    """
    MENU FORWARD-WEEK RULE (2026-04-14):
    Menus are scanned for the FOLLOWING work week, not the current week.
    When scanned Monday–Sunday, the target week = next Monday.

    Priority order:
    1. If the consensus already extracted a week_date from the form, use it
       (the form itself says which week it's for — trust it)
    2. Otherwise calculate: next Monday from today
    """
    if consensus_week_date:
        # Trust the date extracted from the form — it is already forward-looking
        return consensus_week_date
    # No date on form — calculate: next Monday
    today = datetime.today().date()
    days_to_next_monday = (7 - today.weekday()) % 7
    if days_to_next_monday == 0:
        days_to_next_monday = 7   # Never use current Monday — always next week
    return (today + timedelta(days=days_to_next_monday)).isoformat()


def save_to_database(consensus, pdf_path, client_id, db_path):
    """Save high-confidence results to database. Returns (inserted, skipped) row counts."""
    if not consensus or not client_id:
        return 0, 0

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Apply forward-week rule: menu scans are for the following work week
    target_week = _get_target_service_week(consensus.get('week_date'))

    inserted = 0
    skipped  = 0
    for day in ['M', 'T', 'W', 'TH', 'F', 'SA']:
        day_data = consensus['days'].get(day, {})
        if any(day_data.values()):
            avg_conf = sum(consensus['confidence'][day].values()) / 4

            # Skip if identical row already exists (dedup by client+week+day)
            existing = cursor.execute(
                "SELECT id FROM client_menus WHERE client_id=? AND week_start=? AND day=?",
                (client_id, target_week, day)
            ).fetchone()
            if existing:
                skipped += 1
                continue

            cursor.execute("""
                INSERT INTO client_menus
                (client_id, client_name, week_start, day, salad, soup, main, side,
                 confidence, source_pdf, ocr_engines)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                client_id,
                consensus['client_name'],
                target_week,
                day,
                day_data.get('salad'),
                day_data.get('soup'),
                day_data.get('main'),
                day_data.get('side'),
                avg_conf,
                os.path.basename(pdf_path),
                ','.join(consensus.get('engines_used', []))
            ))
            inserted += 1

    conn.commit()
    conn.close()
    return inserted, skipped


# ============================================================================
# FLAGS QUEUE (for Rexxie)
# ============================================================================

def save_flag(consensus, pdf_path, flag_queue_path):
    """Save low-confidence result to flags queue."""
    flag = {
        'flag_id': str(uuid.uuid4()),
        'pdf_path': pdf_path,
        'timestamp': datetime.now().isoformat(),
        'candidate_name': consensus.get('client_name'),
        'matched_name': None,
        'matched_client_id': None,
        'name_confidence': consensus['confidence'].get('client_name', 0.0),
        'days': consensus['days'],
        'engine_agreements': {},
        'engines_used': consensus['engines_used'],
        'status': 'pending'
    }

    # Count agreements per field
    for day in ['M', 'T', 'W', 'TH', 'F', 'SA']:
        for item_type in ['salad', 'soup', 'main', 'side']:
            key = f"{day}_{item_type}"
            flag['engine_agreements'][key] = int(
                consensus['confidence'][day][item_type] * len(consensus['engines_used'])
            )

    # Append to queue
    flags = []
    if os.path.exists(flag_queue_path):
        with open(flag_queue_path, 'r', encoding='utf-8') as f:
            flags = json.load(f)

    flags.append(flag)

    with open(flag_queue_path, 'w', encoding='utf-8') as f:
        json.dump(flags, f, ensure_ascii=False, indent=2)


# ============================================================================
# MAIN PROCESSING
# ============================================================================

def process_pdf(pdf_path, db_path=None, learning_path=None, flag_queue_path=None):
    """
    4-engine consensus OCR. Active engines:
      Engine 1: Tesseract structured (bounding-box, on-machine, page-pair aware)
      Engine 2: Google Drive OCR (cloud — approved by Kato 2026-06-18, menu data non-PHI)
      Engine 3: Paperless-NGX (Tailscale LAN, full-PDF text fallback)
      Engine 4: Claude Vision (cloud — approved by Kato 2026-06-18, menu data non-PHI)
    Handles batch PDFs: each 2-page pair is one client. Returns list for batches,
    single dict for single-client PDFs (backward-compatible).
    """
    print(f"\nProcessing: {os.path.basename(pdf_path)}")

    if not os.path.exists(pdf_path):
        print(f"ERROR: PDF not found: {pdf_path}")
        return None

    # Engine 1: Tesseract structured — page-pair aware, returns list of per-client results
    print("  Engine 1: Tesseract structured (local)...", end=' ', flush=True)
    structured_results = run_tesseract_ocr_structured(pdf_path, learning_path)
    print(f"OK ({len(structured_results)} pair(s))" if structured_results else "FAIL")

    # Engine 2: Google Drive OCR — cloud, approved for menu data (names + food choices)
    print("  Engine 2: Google Drive OCR...", end=' ', flush=True)
    ocr_gdrive = run_google_drive_ocr(pdf_path)
    print("OK" if ocr_gdrive else "FAIL/UNAVAILABLE")
    parsed_gdrive = parse_menu_text(ocr_gdrive, "google_drive", learning_path) if ocr_gdrive else None

    # Engine 3: Paperless — local Tailscale, full-PDF text used as secondary name validator
    print("  Engine 3: Paperless (local Tailscale)...", end=' ', flush=True)
    ocr_paperless = run_paperless_ocr(pdf_path, datetime.now().strftime('%Y-%m-%d'))
    print("OK" if ocr_paperless else "FAIL/UNREACHABLE")
    parsed_paperless = parse_menu_text(ocr_paperless, "paperless", learning_path) if ocr_paperless else None

    # Engine 4: Claude Vision — cloud, approved for menu data (names + food choices)
    print("  Engine 4: Claude Vision...", end=' ', flush=True)
    claude_results = run_claude_vision_ocr(pdf_path)
    print(f"OK ({len(claude_results)} result(s))" if claude_results else "FAIL/NO KEY")

    if not structured_results:
        print("  WARNING: No OCR results from any active engine")
        return None

    all_consensus = []

    for idx, tess_result in enumerate(structured_results):
        if tess_result is None:
            print(f"  WARNING: structured_results[{idx}] is None — skipping")
            continue
        label = tess_result.get('client_name') or f"pair {idx + 1}"
        print(f"\n  [{idx + 1}/{len(structured_results)}] {label}")

        # Vote: all 4 engines. Claude Vision per-pair result matched by index.
        cv_result = claude_results[idx] if (claude_results and idx < len(claude_results)) else None
        consensus = consensus_vote([tess_result, parsed_gdrive, parsed_paperless, cv_result])
        if not consensus:
            print("    WARNING: No consensus")
            continue

        # Match client in DB
        client_id, matched_name, match_conf = match_client(consensus['client_name'], db_path)
        consensus['matched_client_id'] = client_id
        consensus['matched_client_name'] = matched_name
        consensus['match_confidence'] = match_conf

        # Name confidence is the primary decision signal
        avg_confidence = consensus['confidence'].get('client_name', 0.0)

        if consensus['needs_review'] or avg_confidence < CONFIDENCE_THRESHOLDS['flag'] or not client_id:
            print(f"    ACTION: FLAG (name conf: {avg_confidence:.1%})")
            save_flag(consensus, pdf_path, flag_queue_path)
            consensus['_inserted'] = 0
            consensus['_skipped']  = 0
        else:
            print(f"    ACTION: AUTO-ACCEPT (name conf: {avg_confidence:.1%})")
            ins, skp = save_to_database(consensus, pdf_path, client_id, db_path)
            consensus['_inserted'] = ins
            consensus['_skipped']  = skp
            print(f"    DB: {ins} inserted, {skp} skipped (already existed)")

            # Layer 1: auto-learn high-confidence name/item mappings
            # Only fires when both OCR confidence AND DB match confidence are ≥ 0.85
            if _LEARNING_MANAGER_OK and avg_confidence >= 0.85 and match_conf >= 0.85 and learning_path:
                try:
                    _store = _load_learning_store(learning_path)
                    # Build per-engine name readings for accuracy tracking
                    _eng_verdicts = {}
                    for _r in [tess_result, parsed_gdrive, parsed_paperless, cv_result]:
                        if _r:
                            _src = _r.get('_source') or _r.get('source', 'unknown')
                            _eng_verdicts[_src] = _r.get('client_name')
                    _store = _record_high_confidence(
                        _store,
                        ocr_name=consensus['client_name'],
                        canonical_name=matched_name,
                        ocr_items=None,
                        canonical_items=consensus['days'],
                        engine_verdicts=_eng_verdicts,
                    )
                    _store['stats']['last_run'] = datetime.now().isoformat()
                    _save_learning_store(learning_path, _store)
                    print(f"    LEARN: name mapping saved for '{consensus['client_name']}'")
                except Exception as _e:
                    print(f"    WARNING: auto-learn save failed: {_e}", file=sys.stderr)

        all_consensus.append(consensus)

    total_ins = sum(c.get('_inserted', 0) for c in all_consensus)
    total_skp = sum(c.get('_skipped',  0) for c in all_consensus)

    # Backward-compat: single result for single-client PDFs
    if len(all_consensus) == 1:
        r = all_consensus[0]
        r['inserted'] = r.pop('_inserted', 0)
        r['skipped']  = r.pop('_skipped',  0)
        return r
    if all_consensus:
        return {'inserted': total_ins, 'skipped': total_skp, '_results': all_consensus,
                'needs_review': any(c.get('needs_review', False) for c in all_consensus)}
    return None


def process_all_menus(menu_dir, db_path, learning_path, flag_queue_path):
    """Process all PDFs in a directory."""
    init_database(db_path)

    menu_path = Path(menu_dir)
    # Search recursively so week subdirectories (e.g. 2026-03-23/) are included
    pdfs = sorted(menu_path.glob('*.pdf')) + sorted(menu_path.glob('**/*.pdf'))
    # Deduplicate while preserving order
    seen = set()
    pdfs = [p for p in pdfs if not (p in seen or seen.add(p))]

    if not pdfs:
        print(f"ERROR: No PDFs found in {menu_dir}")
        return []

    print(f"\n{'='*70}")
    print(f"Processing {len(pdfs)} menu PDFs (4 OCR engines)")
    print(f"{'='*70}")

    results = []
    flagged = 0
    accepted = 0

    for pdf in pdfs:
        result = process_pdf(str(pdf), db_path, learning_path, flag_queue_path)
        if result:
            results.append(result)
            if result.get('needs_review', False):
                flagged += 1
            else:
                accepted += 1

    print(f"\n{'='*70}")
    print(f"SUMMARY: {len(results)} processed, {accepted} auto-accepted, {flagged} flagged")
    print(f"{'='*70}")

    return results


# ============================================================================
# CLI
# ============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description='GOJ Menu Consensus OCR System')
    parser.add_argument('--menu-dir', default=str(Path.home() / 'Documents' / 'goj files' / 'dashboard' / 'documents' / 'menus'),
                       help='Menu PDFs directory')
    parser.add_argument('--db', default=str(Path.home() / 'Documents' / 'goj files' / 'dashboard' / 'auth_tracker.db'),
                       help='Database path')
    parser.add_argument('--learning', default=str(Path.home() / 'Desktop' / 'REX' / 'goj_menu_learning.json'),
                       help='Learning file path')
    parser.add_argument('--flags', default=str(Path.home() / 'Desktop' / 'REX' / 'goj_menu_flags_queue.json'),
                       help='Flags queue path')
    parser.add_argument('--pdf', type=str, help='Process single PDF')

    args = parser.parse_args()

    if args.pdf:
        process_pdf(args.pdf, args.db, args.learning, args.flags)
    else:
        process_all_menus(args.menu_dir, args.db, args.learning, args.flags)


if __name__ == '__main__':
    main()


# Alias for CC_ocr_worker — accepts just a pdf_path, uses default DB/learning paths
def process_pdf_local(pdf_path: str) -> dict | None:
    """Worker-facing entry point for LOCAL ONLY mode.
    Always returns a dict with 'inserted' and 'skipped' keys so CC_ocr_worker
    can accurately report results (previously always got 0 for both).
    """
    _db     = str(Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db")
    _learn  = str(Path(__file__).resolve().parent / "goj_menu_learning.json")
    _flags  = str(Path(__file__).resolve().parent / "goj_menu_flags_queue.json")
    result = process_pdf(pdf_path, _db, _learn, _flags)
    if result is None:
        return {'inserted': 0, 'skipped': 0}
    if isinstance(result, dict) and 'inserted' not in result:
        result['inserted'] = result.get('_inserted', 0)
        result['skipped']  = result.get('_skipped',  0)
    return result
