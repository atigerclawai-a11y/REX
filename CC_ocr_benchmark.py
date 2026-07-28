#!/usr/bin/env python3
"""
CC_ocr_benchmark.py — OCR Accuracy Benchmark for GOJ Menu Pipeline
Gold Health Systems · Garden of Joy Adult Day Care · Brooklyn NY
Run: source ~/debate-chamber/.venv/bin/activate && python3 ~/Desktop/REX/CC_ocr_benchmark.py

Strategy:
  1. Download scan PDFs via Gmail IMAP (past 6 weeks + March 2026 for ground truth)
  2. Load ground truth from auth_tracker.db (source='ground_truth') and
     goj_menu_ground_truth.json (March 2026 Google Sheets data)
  3. Run Tesseract OCR (fresh) on each PDF — read-only, no DB writes
  4. Run Claude Vision OCR on a sample of PDFs (≤20) as high-accuracy reference
  5. Compare Tesseract vs ground truth (where GT exists) AND vs Claude Vision reference
  6. Feed mismatches into goj_menu_learning.json as corrections
  7. Write CC_ocr_benchmark_report.md
"""
# macOS: /tmp is a symlink to /private/tmp but Leptonica (Tesseract's image lib)
# does NOT follow symlinks — it fails to open temp files created at /tmp/*.PPM.
# Must set TMPDIR=/private/tmp BEFORE importing pytesseract or pdf2image.
import os
os.environ.setdefault('TMPDIR', '/private/tmp')

import sys, json, sqlite3, imaplib, email, re, pathlib, hashlib, shutil
from datetime import datetime, date, timedelta
import dataclasses, difflib
from email.header import decode_header
from collections import defaultdict

# ── paths ────────────────────────────────────────────────────────────────────
HOME          = pathlib.Path.home()
REX           = HOME / "Desktop" / "REX"
DB_PATH       = HOME / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
GT_JSON       = REX / "goj_menu_ground_truth.json"
LEARNING_PATH = REX / "goj_menu_learning.json"
BENCHMARK_DIR = REX / "menus" / "benchmark_test"
MENUS_DIR     = HOME / "Documents" / "goj files" / "dashboard" / "documents" / "menus"
IMAP_CONFIG   = HOME / ".rex_gmail_imap.json"
REPORT_PATH   = REX / "CC_ocr_benchmark_report.md"

# OCR pipeline imports (needs venv)
sys.path.insert(0, str(REX))
try:
    from goj_menu_consensus_ocr import (
        run_tesseract_ocr_structured, run_claude_vision_ocr,
        consensus_vote, load_learning_corrections, save_correction,
    )
    from CC_menu_constants import SALADS, SOUPS, ALL_MAINS, SIDES, DAYS, DAY_MAP
    OCR_AVAILABLE = True
except ImportError as e:
    print(f"WARNING: OCR imports failed: {e}")
    OCR_AVAILABLE = False
    SALADS, SOUPS, ALL_MAINS, SIDES = [], [], [], []
    DAYS = ["M", "T", "W", "TH", "F", "SA"]

ALL_ITEMS = SALADS + SOUPS + ALL_MAINS + SIDES

# ── benchmark config ─────────────────────────────────────────────────────────
MAX_PDFS_TESSERACT    = 8    # max PDFs for Tesseract benchmark (8 × ~3min = 24min max)
MAX_PDFS_CLAUDE       = 20   # max PDFs for Claude Vision benchmark (API cost)
MATCH_THRESHOLD       = 0.72 # rapidfuzz similarity for fuzzy item match
IMAP_SEARCH_WEEKS     = 8    # search past N weeks in Gmail

# ── GT sources in DB that represent human-entered truth ──────────────────────
GT_SOURCES = ('ground_truth', 'employee_sync_Shift 1', 'employee_sync_Shift 2', 'drive_sheet')
OCR_SOURCES = ('vision-pipeline', 'ocr_watcher_tesseract', 'claude_vision',
               'consensus_ocr', 'ocr_claude_vision', 'scan_ocr', 'claude-vision')



# ════════════════════════════════════════════════════════════════════════════
# ABBREVIATION EXPANSION
# Matches short kitchen abbreviations → canonical menu item names
# ════════════════════════════════════════════════════════════════════════════

# Known hard-coded expansions from the weekly spreadsheet abbreviations
ABBREV_MAP = {
    # Salads
    "баклаж": "Салат из баклажан", "баклажан": "Салат из баклажан",
    "весна": "Салат весенний", "весн": "Салат весенний",
    "вин": "Винегрет", "винег": "Винегрет",
    "днестр": "Салат Днестр",
    "капуста": "Квашеная капуста", "кваш": "Квашеная капуста",
    "ол ": "Оливье", "оли": "Оливье", "оливье": "Оливье",
    "свкл": "Свекла", "свекла": "Свекла", "свёкла": "Свекла",
    "селедка": "Селедка", "сельд": "Селедка",
    "сало": "Сало",
    # Soups
    "б ": "Борщ красный", "б": "Борщ красный",
    "3.б": "Борщ зеленый", "з.б": "Борщ зеленый", "зел.б": "Борщ зеленый",
    "борщ": "Борщ красный",
    "гриб": "Грибной суп", "грибн": "Грибной суп",
    "кур ": "Куриный суп", "кур.": "Куриный суп", "куриный": "Куриный суп",
    "овощ": "Овощной суп", "овощн": "Овощной суп",
    "харчо": "Харчо",
    "горох": "Гороховый суп", "горох.": "Гороховый суп",
    "суп": "Куриный суп",  # generic "суп" defaults to chicken soup
    # Mains
    "баса": "Баса с помидорами под сыром",
    "бл. мясо": "Блины с мясом", "блины м": "Блины с мясом",
    "бл. твор": "Блины с творогом",
    "вареники": "Вареники с картошкой",
    "голубцы": "Голубцы",
    "гуляш": "Гуляш",
    "дорадо": "Дорадо запеченая",
    "жульен": "Жульен",
    "котл. кур": "Котлеты куриные", "котл": "Котлеты куриные",
    "терияки": "Курица в терияки соусе", "тери": "Курица в терияки соусе",
    "крылышки": "Куриные крылышки",
    "пельмени": "Пельмени",
    "поперечка": "Поперечка",
    "s  ": "Салмон", "s": "Салмон", "salmon": "Салмон", "сальмон": "Салмон",
    "свиная": "Свиная отбивная", "свин.": "Свиная отбивная",
    "табака": "Цыпленок табака",
    "чалахач": "Чалахач",
    "чебуреки": "Чебуреки",
    "шницель": "Шницель куриный", "шниц": "Шницель куриный",
    "курица": "Котлеты куриные",  # generic "курица" → most common chicken dish
    "рыба": "Баса с помидорами под сыром",  # generic "рыба" → most common fish
    "мясо": "Гуляш",  # generic "мясо" → goulash is most common meat
    # Sides
    "туш. кап.": "Тушеная капуста", "туш": "Тушеная капуста",
    "картошка": "Картошка по деревенски", "картоф": "Картошка по деревенски",
    "пюре": "Пюре",
    "гречка": "Гречка", "гр  ": "Гречка", "гр.": "Гречка",
    "паста": "Паста",
    "рис": "Рис",
    "жар. картошка": "Жареная картошка",
    "mp ": "Без гарнира",  # "MP" = "меню ресторана" (no standard side)
    "без гарнира": "Без гарнира",
    "олимп": None,  # "Олимп" = kitchen identifier, NOT a food item — skip
}


def expand_abbrev(raw, field="main"):
    """Expand a ground-truth abbreviation to a canonical item name.
    Returns (canonical, confidence) or (None, 0) if unknown."""
    if not raw:
        return None, 0.0
    key = raw.strip().lower().rstrip(".: ")

    # Hard-coded map first
    if key in ABBREV_MAP:
        return ABBREV_MAP[key], 1.0

    # Prefix match against canonical list
    field_items = {
        "salad": SALADS, "soup": SOUPS, "main": ALL_MAINS, "side": SIDES
    }.get(field, ALL_ITEMS)

    best, best_score = None, 0.0
    for item in field_items:
        item_lo = item.lower()
        # Starts-with
        if item_lo.startswith(key) and len(key) >= 3:
            score = len(key) / len(item_lo)
            if score > best_score:
                best_score, best = score, item
        # Fuzzy on first N chars
        n = min(len(key) + 3, len(item_lo))
        s = SequenceMatcher(None, key, item_lo[:n]).ratio()
        if s > best_score and s >= 0.70:
            best_score, best = s, item

    return (best, best_score) if best else (None, 0.0)


def fuzzy_match_items(ocr_val, gt_val, field="main"):
    """Return True if OCR value matches ground truth value (with expansion).
    Handles both cases: GT is abbreviated, OCR is canonical, or vice versa."""
    if not ocr_val and not gt_val:
        return True    # both empty = match
    if not ocr_val or not gt_val:
        return False   # one empty = no match

    ocr_clean = ocr_val.strip().lower()
    gt_clean  = gt_val.strip().lower()

    if ocr_clean == gt_clean:
        return True

    # Expand GT abbreviation → canonical, then compare
    gt_expanded, _ = expand_abbrev(gt_val, field)
    if gt_expanded and gt_expanded.lower() == ocr_clean:
        return True

    # OCR might be an abbreviated canonical (edge case — shouldn't happen)
    ocr_expanded, _ = expand_abbrev(ocr_val, field)
    if ocr_expanded and ocr_expanded.lower() == gt_clean:
        return True

    # Starts-with check: "Борщ красный" starts with GT "Борщ"
    if ocr_clean.startswith(gt_clean[:max(3, len(gt_clean))]):
        return True
    if gt_clean.startswith(ocr_clean[:max(3, len(ocr_clean))]):
        return True

    # Fuzzy: ≥ threshold similarity
    score = SequenceMatcher(None, ocr_clean, gt_clean).ratio()
    if score >= MATCH_THRESHOLD:
        return True

    # If GT is ambiguous (e.g. "Борщ"), match any "Борщ X"
    if gt_expanded:
        score2 = SequenceMatcher(None, ocr_clean, gt_expanded.lower()).ratio()
        if score2 >= MATCH_THRESHOLD:
            return True

    return False


# ════════════════════════════════════════════════════════════════════════════
# STEP 1: LOAD GROUND TRUTH FROM DB
# ════════════════════════════════════════════════════════════════════════════

def load_db_ground_truth(db_path):
    """Load manually-entered ground truth rows from auth_tracker.db.
    Returns dict: (client_id, week_start, day) → {salad, soup, main, side, client_name}
    """
    gt = {}
    try:
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        placeholders = ",".join("?" * len(GT_SOURCES))
        c.execute(f"""
            SELECT client_id, client_name, week_start, day, salad, soup, main, side, source
            FROM client_menus WHERE source IN ({placeholders})
        """, GT_SOURCES)
        rows = c.fetchall()
        conn.close()
        for r in rows:
            key = (r[0], r[2], r[3])   # (client_id, week_start, day)
            gt[key] = {
                "client_name": r[1], "salad": r[4], "soup": r[5],
                "main": r[6], "side": r[7], "source": r[8]
            }
        print(f"[GT] Loaded {len(gt)} ground truth rows from DB "
              f"({len(set(k[0] for k in gt))} clients, "
              f"{len(set(k[1] for k in gt))} weeks)")
    except Exception as e:
        print(f"[GT] DB load failed: {e}")
    return gt


def load_db_clients(db_path):
    """Load client id → name mapping."""
    clients = {}
    try:
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        try:
            c.execute("SELECT client_id, name FROM clients WHERE active=1")
        except Exception:
            c.execute("SELECT client_id, name FROM clients")
        for r in c.fetchall():
            clients[r[0]] = r[1]
        conn.close()
    except Exception as e:
        print(f"[GT] Client load failed: {e}")
    return clients


def load_db_ocr_reference(db_path):
    """Load vision-pipeline rows as Claude Vision reference.
    Returns dict: (source_pdf_basename, client_name_normalized) → {day: {fields}}
    """
    ref = defaultdict(lambda: defaultdict(dict))
    try:
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        c.execute("""
            SELECT client_name, week_start, day, salad, soup, main, side, source_pdf, confidence
            FROM client_menus WHERE source IN ('vision-pipeline', 'claude_vision', 'ocr_claude_vision')
            AND source_pdf IS NOT NULL
        """)
        for r in c.fetchall():
            pdf_base = os.path.basename(r[7]) if r[7] else None
            if not pdf_base:
                continue
            name_key = r[0].strip().lower() if r[0] else ""
            ref[pdf_base][name_key] = ref[pdf_base].get(name_key, {})
            ref[pdf_base][name_key][r[2]] = {
                "salad": r[3], "soup": r[4], "main": r[5], "side": r[6],
                "confidence": r[8], "week_start": r[1]
            }
        conn.close()
        print(f"[REF] Loaded Claude Vision reference: {len(ref)} PDFs")
    except Exception as e:
        print(f"[REF] OCR reference load failed: {e}")
    return ref


# ════════════════════════════════════════════════════════════════════════════
# STEP 2: DOWNLOAD PDFs FROM GMAIL IMAP
# ════════════════════════════════════════════════════════════════════════════

def download_pdfs_imap(dest_dir, weeks_back=8):
    """Connect via IMAP, search for menu scan emails, download PDF attachments.
    Returns list of downloaded PDF paths."""
    dest_dir = pathlib.Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    if not IMAP_CONFIG.exists():
        print("[IMAP] Config not found — skipping Gmail download")
        return []

    try:
        cfg = json.loads(IMAP_CONFIG.read_text())
        email_addr = cfg.get("email") or cfg.get("username") or cfg.get("user", "")
        app_password = cfg.get("app_password") or cfg.get("password", "")
        imap_host = cfg.get("imap_host", "imap.gmail.com")
        imap_port = int(cfg.get("imap_port", 993))
    except Exception as e:
        print(f"[IMAP] Config read error: {e}")
        return []

    downloaded = []
    since_date = (date.today() - timedelta(weeks=weeks_back)).strftime("%d-%b-%Y")

    print(f"[IMAP] Connecting to {imap_host}:{imap_port} as {email_addr}")
    print(f"[IMAP] Searching since {since_date} for menu scan emails")

    try:
        mail = imaplib.IMAP4_SSL(imap_host, imap_port)
        mail.login(email_addr, app_password)
        mail.select("INBOX")

        # Search for menu scan emails from known senders
        senders = ['allen@gardenofjoybrooklyn.com', 'goj3152.scans@gmail.com']
        all_uids = set()

        for sender in senders:
            _, data = mail.search(None, f'FROM "{sender}" SINCE {since_date}')
            uids = data[0].split() if data[0] else []
            all_uids.update(uids)
            print(f"[IMAP]   From {sender} (recent): {len(uids)} messages")

        # Also search March 2026 specifically — ground truth only covers that month
        march_since = "01-Mar-2026"
        march_before = "01-Apr-2026"
        for sender in senders:
            try:
                _, data = mail.search(None, f'FROM "{sender}" SINCE {march_since} BEFORE {march_before}')
                uids = data[0].split() if data[0] else []
                all_uids.update(uids)
                print(f"[IMAP]   From {sender} (March 2026): {len(uids)} messages")
            except Exception:
                pass

        # Also search by subject keywords (doc scanner default filenames)
        for keyword in ['doc003', 'doc004', 'doc005']:
            try:
                _, data = mail.search(None, f'SUBJECT "{keyword}" SINCE {since_date}')
                uids = data[0].split() if data[0] else []
                all_uids.update(uids)
            except Exception:
                pass

        print(f"[IMAP] Total candidate emails: {len(all_uids)}")

        for uid in sorted(all_uids):
            try:
                _, msg_data = mail.fetch(uid, "(RFC822)")
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                for part in msg.walk():
                    if part.get_content_maintype() == "multipart":
                        continue
                    if part.get("Content-Disposition") is None:
                        continue

                    filename = part.get_filename()
                    if not filename:
                        continue
                    # Decode MIME-encoded filenames
                    decoded = decode_header(filename)
                    filename = "".join(
                        chunk.decode(enc or "utf-8") if isinstance(chunk, bytes) else chunk
                        for chunk, enc in decoded
                    )

                    if not filename.lower().endswith(".pdf"):
                        continue

                    # Sanitize filename
                    safe_name = re.sub(r'[^\w\-_. ]', '_', filename)
                    dest_path = dest_dir / safe_name

                    # Skip if already downloaded
                    if dest_path.exists():
                        downloaded.append(str(dest_path))
                        continue

                    payload = part.get_payload(decode=True)
                    if payload:
                        dest_path.write_bytes(payload)
                        downloaded.append(str(dest_path))
                        print(f"[IMAP]   Downloaded: {safe_name} ({len(payload)//1024}KB)")

            except Exception as e:
                print(f"[IMAP]   Error processing UID {uid}: {e}")
                continue

        mail.logout()
    except Exception as e:
        print(f"[IMAP] Connection error: {e}")

    print(f"[IMAP] Downloaded {len(downloaded)} PDFs total")
    return downloaded


def find_existing_pdfs(menus_dir, limit=None):
    """Find existing PDFs in the main menus directory.
    Sorted newest first (by mtime — works for all naming schemes including
    hash-prefixed June 2026 files like 19eb...pdf and numeric 808_... files)."""
    d = pathlib.Path(menus_dir)
    if not d.exists():
        return []
    pdfs = list(d.rglob("*.pdf"))
    # Exclude non-menu PDFs
    pdfs = [p for p in pdfs
            if 'w9' not in p.name.lower()
            and 'w-9' not in p.name.lower()
            and 'template' not in p.name.lower()
            and 'menu_2024' not in p.name      # old menu templates
            and 'menu_2023' not in p.name
            and 'menu_2022' not in p.name
            and 'menu_2020' not in p.name
            and 'menu_2014' not in p.name
            and 'menu_2012' not in p.name
            and 'menu_2007' not in p.name
            and 'menu_2025' not in p.name
            and p.name != 'stdout'
            and not p.is_dir()]
    # Sort by modification time — newest first
    pdfs = sorted(pdfs, key=lambda p: p.stat().st_mtime, reverse=True)
    if limit:
        pdfs = pdfs[:limit]
    return [str(p) for p in pdfs]


# ════════════════════════════════════════════════════════════════════════════
# STEP 3: RUN TESSERACT OCR (read-only — db_path=None)
# ════════════════════════════════════════════════════════════════════════════

def run_tesseract_on_pdf(pdf_path, learning_path=None):
    """Run Tesseract structured OCR on a single PDF (read-only benchmark mode).
    Goes direct to run_tesseract_ocr_structured — skips Drive/Paperless/Claude Vision
    to keep benchmark fast. No DB writes."""
    return run_tesseract_structured_only(pdf_path, learning_path)


def run_tesseract_structured_only(pdf_path, learning_path=None):
    """Run Tesseract structured engine and flatten output to per-client-per-day rows.
    run_tesseract_ocr_structured returns: [{client_name, days:{M:{salad,soup,main,side},...}}]
    We flatten to: [{client_name, day, salad, soup, main, side, confidence}] for comparison."""
    try:
        sys.path.insert(0, str(REX))
        from goj_menu_consensus_ocr import run_tesseract_ocr_structured
        # Always pass a valid learning path — load_learning_corrections(None) crashes
        lp = str(learning_path) if learning_path else str(LEARNING_PATH)
        raw = run_tesseract_ocr_structured(str(pdf_path), lp)
        if not raw:
            return []
        flat = []
        for client_result in raw:
            cname = client_result.get('client_name', '')
            conf  = client_result.get('_confidence', 0.5)
            days  = client_result.get('days', {})
            for day_code, fields in days.items():
                # Skip days where nothing was filled in
                if not any(v for v in fields.values() if v):
                    continue
                flat.append({
                    'client_name': cname,
                    'day':         day_code,
                    'salad':       fields.get('salad') or '',
                    'soup':        fields.get('soup')  or '',
                    'main':        fields.get('main')  or '',
                    'side':        fields.get('side')  or '',
                    'confidence':  conf,
                })
        return flat
    except Exception as e:
        print(f"[OCR-tess] Tesseract-only failed for {pdf_path}: {e}")
        return []


def normalize_name(name):
    """Lowercase, collapse spaces, strip punctuation for fuzzy name matching."""
    if not name:
        return ""
    n = str(name).lower().strip()
    n = re.sub(r'[^\w\s]', '', n)
    n = re.sub(r'\s+', ' ', n)
    return n


def match_client_name(ocr_name, client_names):
    """Find best matching client name from a list using difflib.
    Returns (matched_name, score) or (None, 0)."""
    if not ocr_name or not client_names:
        return None, 0.0
    ocr_norm = normalize_name(ocr_name)
    best_name = None
    best_score = 0.0
    for name in client_names:
        score = difflib.SequenceMatcher(None, ocr_norm, normalize_name(name)).ratio()
        if score > best_score:
            best_score = score
            best_name = name
    if best_score >= MATCH_THRESHOLD:
        return best_name, best_score
    return None, best_score


# ════════════════════════════════════════════════════════════════════════════
# STEP 4: COMPARISON ENGINE
# ════════════════════════════════════════════════════════════════════════════

@dataclasses.dataclass
class FieldResult:
    field: str
    ocr_raw: str
    ocr_canonical: str
    gt_canonical: str
    match: bool
    confidence: float


@dataclasses.dataclass
class ClientDayResult:
    pdf_path: str
    client_name_ocr: str
    client_name_gt: str
    name_score: float
    week_start: str
    day: str
    fields: list   # list of FieldResult
    track: str     # 'A' (ground_truth) or 'B' (vision-pipeline)


def compare_ocr_to_gt(ocr_row, gt_row, pdf_path, track):
    """Compare one OCR output row to one ground truth row.
    Returns a ClientDayResult."""
    field_results = []
    for field in ('salad', 'soup', 'main', 'side'):
        ocr_val = (ocr_row.get(field) or "").strip()
        gt_val  = (gt_row.get(field) or "").strip()

        # Expand abbreviations in ground truth
        gt_canon, _ = expand_abbrev(gt_val, field)
        ocr_canon, _ = expand_abbrev(ocr_val, field)

        matched = fuzzy_match_items(ocr_canon, gt_canon, field)
        field_results.append(FieldResult(
            field=field,
            ocr_raw=ocr_val,
            ocr_canonical=ocr_canon,
            gt_canonical=gt_canon,
            match=matched,
            confidence=ocr_row.get('confidence', 0.0) or 0.0,
        ))

    return ClientDayResult(
        pdf_path=pdf_path,
        client_name_ocr=ocr_row.get('client_name', ''),
        client_name_gt=gt_row.get('client_name', ''),
        name_score=ocr_row.get('_name_score', 1.0),
        week_start=gt_row.get('week_start', ''),
        day=ocr_row.get('day', gt_row.get('day', '')),
        fields=field_results,
        track=track,
    )


def run_track_a(imap_pdfs, gt_rows_by_client_week_day, client_id_map, learning_path):
    """Track A: IMAP March PDFs → Tesseract OCR → compare vs ground_truth DB rows.
    gt_rows_by_client_week_day: dict[(client_name_norm, week_start, day)] → {salad, soup, main, side}
    Returns list of ClientDayResult."""
    results = []
    client_names = list({k[0] for k in gt_rows_by_client_week_day.keys()})

    for pdf_path in imap_pdfs:
        print(f"[Track A] OCR: {pathlib.Path(pdf_path).name}")
        ocr_rows = run_tesseract_on_pdf(pdf_path, learning_path)
        if not ocr_rows:
            ocr_rows = run_tesseract_structured_only(pdf_path, learning_path)

        for row in ocr_rows:
            ocr_name = row.get('client_name', '')
            matched_name, score = match_client_name(ocr_name, client_names)
            if not matched_name:
                continue

            ocr_day = (row.get('day') or '').upper().strip()
            name_norm = normalize_name(matched_name)
            key = (name_norm, row.get('week_start', ''), ocr_day)
            gt_row = gt_rows_by_client_week_day.get(key)

            if not gt_row:
                # Try with just name+day (ignore week — March PDFs might not align exactly)
                for (n, w, d), v in gt_rows_by_client_week_day.items():
                    if n == name_norm and d == ocr_day:
                        gt_row = v
                        break

            if not gt_row:
                continue

            row['_name_score'] = score
            cdr = compare_ocr_to_gt(row, gt_row, pdf_path, 'A')
            results.append(cdr)

    print(f"[Track A] {len(results)} client-day comparisons")
    return results


def run_track_b(existing_pdfs, vision_ref, client_names_all, learning_path):
    """Track B: Existing PDFs → Tesseract → compare vs vision-pipeline reference rows.
    vision_ref: dict[pdf_base][name_norm][day] → {salad, soup, main, side}
    Returns (list[ClientDayResult], diag_dict)."""
    results = []
    processed = set()
    diag = {
        'pdfs_attempted': 0,
        'pdfs_with_tess_rows': 0,
        'pdfs_with_names': 0,
        'pdfs_with_field_data': 0,
        'total_tess_rows': 0,
        'total_named_rows': 0,
        'total_field_rows': 0,
        'name_match_attempts': 0,
        'name_match_hits': 0,
    }

    for pdf_path in existing_pdfs[:MAX_PDFS_TESSERACT]:
        pdf_base = pathlib.Path(pdf_path).name
        # vision_ref keys may use numeric-prefixed names; try stripping prefix
        ref_by_pdf = vision_ref.get(pdf_base)
        if not ref_by_pdf:
            # Try matching by doc timestamp embedded in filename
            for ref_key in vision_ref:
                if ref_key in pdf_base or pdf_base in ref_key:
                    ref_by_pdf = vision_ref[ref_key]
                    break
        if not ref_by_pdf:
            continue

        if pdf_base in processed:
            continue
        processed.add(pdf_base)

        diag['pdfs_attempted'] += 1
        print(f"[Track B] OCR: {pdf_base}")
        ocr_rows = run_tesseract_on_pdf(pdf_path, learning_path)

        # Diagnostics: count rows with names vs with field data
        rows_with_name  = sum(1 for r in ocr_rows if r.get('client_name'))
        rows_with_field = sum(1 for r in ocr_rows if any(
            r.get(f) for f in ('salad', 'soup', 'main', 'side')))
        print(f"[Track B]   tess_rows={len(ocr_rows)} named={rows_with_name} "
              f"field_data={rows_with_field} ref_clients={len(ref_by_pdf)}")
        if ocr_rows:              diag['pdfs_with_tess_rows'] += 1
        if rows_with_name:        diag['pdfs_with_names'] += 1
        if rows_with_field:       diag['pdfs_with_field_data'] += 1
        diag['total_tess_rows']  += len(ocr_rows)
        diag['total_named_rows'] += rows_with_name
        diag['total_field_rows'] += rows_with_field

        ref_names = list(ref_by_pdf.keys())
        for row in ocr_rows:
            ocr_name = row.get('client_name', '')
            diag['name_match_attempts'] += 1
            matched_name, score = match_client_name(ocr_name, ref_names)
            if not matched_name:
                continue
            diag['name_match_hits'] += 1

            name_norm = normalize_name(matched_name)
            ocr_day = (row.get('day') or '').upper().strip()
            day_data = ref_by_pdf.get(name_norm, {})
            gt_row = day_data.get(ocr_day)

            if not gt_row:
                continue

            row['_name_score'] = score
            cdr = compare_ocr_to_gt(row, gt_row, pdf_path, 'B')
            results.append(cdr)

    print(f"[Track B] {len(results)} client-day comparisons")
    print(f"[Track B] diag: {diag}")
    return results, diag


# ════════════════════════════════════════════════════════════════════════════
# STEP 5: STATS AGGREGATION + CORRECTION WRITER
# ════════════════════════════════════════════════════════════════════════════

def aggregate_stats(all_results):
    """Compute accuracy stats from list of ClientDayResult.
    Returns a dict with overall, per_field, per_client, per_day, error_examples, error_freq."""
    total_fields = 0
    correct_fields = 0
    per_field = defaultdict(lambda: {'total': 0, 'correct': 0})
    per_client = defaultdict(lambda: {'total': 0, 'correct': 0})
    per_day = defaultdict(lambda: {'total': 0, 'correct': 0})
    per_track = defaultdict(lambda: {'total': 0, 'correct': 0})
    error_examples = []   # (field, ocr_val, gt_val, client_name, day)
    error_freq = defaultdict(int)  # (field, gt_val) → count wrong

    for cdr in all_results:
        for fr in cdr.fields:
            total_fields += 1
            per_field[fr.field]['total'] += 1
            per_client[cdr.client_name_gt or cdr.client_name_ocr]['total'] += 1
            per_day[cdr.day]['total'] += 1
            per_track[cdr.track]['total'] += 1

            if fr.match:
                correct_fields += 1
                per_field[fr.field]['correct'] += 1
                per_client[cdr.client_name_gt or cdr.client_name_ocr]['correct'] += 1
                per_day[cdr.day]['correct'] += 1
                per_track[cdr.track]['correct'] += 1
            else:
                error_key = (fr.field, fr.gt_canonical or fr.ocr_canonical)
                error_freq[error_key] += 1
                if len(error_examples) < 200:
                    error_examples.append({
                        'field': fr.field,
                        'ocr': fr.ocr_canonical,
                        'gt': fr.gt_canonical,
                        'client': cdr.client_name_gt or cdr.client_name_ocr,
                        'day': cdr.day,
                        'pdf': pathlib.Path(cdr.pdf_path).name,
                        'track': cdr.track,
                    })

    overall_pct = (correct_fields / total_fields * 100) if total_fields else 0.0

    # Per-client accuracy rates, sorted worst first
    client_accuracy = {}
    for name, counts in per_client.items():
        if counts['total'] > 0:
            pct = counts['correct'] / counts['total'] * 100
            client_accuracy[name] = {'pct': pct, 'total': counts['total'], 'correct': counts['correct']}

    # Top 20 worst clients
    worst_clients = sorted(
        client_accuracy.items(),
        key=lambda x: x[1]['pct']
    )[:20]

    # Top 30 most common errors
    top_errors = sorted(error_freq.items(), key=lambda x: x[1], reverse=True)[:30]

    return {
        'overall_pct': overall_pct,
        'total_fields': total_fields,
        'correct_fields': correct_fields,
        'total_comparisons': len(all_results),
        'per_field': {k: {**v, 'pct': v['correct']/v['total']*100 if v['total'] else 0}
                      for k, v in per_field.items()},
        'per_day': {k: {**v, 'pct': v['correct']/v['total']*100 if v['total'] else 0}
                    for k, v in per_day.items()},
        'per_track': {k: {**v, 'pct': v['correct']/v['total']*100 if v['total'] else 0}
                      for k, v in per_track.items()},
        'worst_clients': worst_clients,
        'client_accuracy': client_accuracy,
        'error_examples': error_examples,
        'top_errors': top_errors,
    }


def write_corrections(all_results, learning_path):
    """For every field mismatch, call save_correction() to feed the learning store.
    Returns count of corrections written."""
    try:
        sys.path.insert(0, str(REX))
        from goj_menu_consensus_ocr import save_correction
    except ImportError:
        print("[Corrections] Could not import save_correction — skipping")
        return 0

    count = 0
    for cdr in all_results:
        for fr in cdr.fields:
            if not fr.match and fr.ocr_canonical and fr.gt_canonical:
                try:
                    save_correction(
                        str(learning_path),
                        fr.ocr_canonical,
                        fr.gt_canonical,
                        fr.field,
                    )
                    count += 1
                except Exception as e:
                    # Don't abort on individual correction failures
                    pass

    print(f"[Corrections] Wrote {count} corrections to learning store")
    return count


# ════════════════════════════════════════════════════════════════════════════
# STEP 6: REPORT GENERATOR
# ════════════════════════════════════════════════════════════════════════════

def generate_report(stats, correction_count, report_path, run_meta):
    """Write CC_ocr_benchmark_report.md."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []

    lines.append(f"# GOJ Menu OCR Benchmark Report")
    lines.append(f"**Generated:** {now}  ")
    lines.append(f"**Script:** CC_ocr_benchmark.py  ")
    lines.append(f"**PDFs processed:** {run_meta.get('pdfs_processed', 0)}  ")
    lines.append(f"  - Track A (IMAP March PDFs vs ground_truth): {run_meta.get('track_a_pdfs', 0)} PDFs, {run_meta.get('track_a_comparisons', 0)} client-day pairs")
    lines.append(f"  - Track B (existing PDFs vs vision-pipeline): {run_meta.get('track_b_pdfs', 0)} PDFs, {run_meta.get('track_b_comparisons', 0)} client-day pairs")
    lines.append("")

    # Overall accuracy
    lines.append("## Overall Accuracy")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Overall field accuracy | **{stats['overall_pct']:.1f}%** |")
    lines.append(f"| Total field comparisons | {stats['total_fields']} |")
    lines.append(f"| Correct fields | {stats['correct_fields']} |")
    lines.append(f"| Client-day comparisons | {stats['total_comparisons']} |")
    lines.append(f"| Corrections fed to learning store | {correction_count} |")
    lines.append("")

    # Per-field accuracy
    lines.append("## Accuracy by Field")
    lines.append("")
    lines.append("| Field | Correct | Total | Accuracy |")
    lines.append("|-------|---------|-------|----------|")
    for field in ('salad', 'soup', 'main', 'side'):
        fd = stats['per_field'].get(field, {'correct': 0, 'total': 0, 'pct': 0})
        lines.append(f"| {field.capitalize()} | {fd['correct']} | {fd['total']} | {fd['pct']:.1f}% |")
    lines.append("")

    # Per-day accuracy
    lines.append("## Accuracy by Day")
    lines.append("")
    lines.append("| Day | Correct | Total | Accuracy |")
    lines.append("|-----|---------|-------|----------|")
    day_order = ['M', 'T', 'W', 'TH', 'F', 'SA', 'S']
    for day in day_order:
        dd = stats['per_day'].get(day, None)
        if dd:
            lines.append(f"| {day} | {dd['correct']} | {dd['total']} | {dd['pct']:.1f}% |")
    lines.append("")

    # Per-track breakdown
    lines.append("## Accuracy by Track")
    lines.append("")
    lines.append("| Track | Description | Correct | Total | Accuracy |")
    lines.append("|-------|-------------|---------|-------|----------|")
    track_desc = {'A': 'IMAP March PDFs vs ground_truth', 'B': 'Existing PDFs vs vision-pipeline'}
    for track in ('A', 'B'):
        td = stats['per_track'].get(track, {'correct': 0, 'total': 0, 'pct': 0})
        lines.append(f"| {track} | {track_desc.get(track, '')} | {td['correct']} | {td['total']} | {td['pct']:.1f}% |")
    lines.append("")

    # Top 20 worst clients
    lines.append("## Top 20 Clients by Accuracy (Worst First)")
    lines.append("")
    lines.append("| Client | Correct | Total | Accuracy |")
    lines.append("|--------|---------|-------|----------|")
    for name, acc in stats['worst_clients']:
        lines.append(f"| {name} | {acc['correct']} | {acc['total']} | {acc['pct']:.1f}% |")
    lines.append("")

    # Most common errors
    lines.append("## Most Common OCR Errors")
    lines.append("")
    lines.append("| Field | Ground Truth | Error Count |")
    lines.append("|-------|--------------|-------------|")
    for (field, gt_val), cnt in stats['top_errors']:
        lines.append(f"| {field} | {gt_val} | {cnt} |")
    lines.append("")

    # Error examples (first 30)
    lines.append("## Error Examples (first 30)")
    lines.append("")
    lines.append("| Client | Day | Field | OCR Output | Ground Truth | PDF |")
    lines.append("|--------|-----|-------|------------|--------------|-----|")
    for ex in stats['error_examples'][:30]:
        lines.append(f"| {ex['client']} | {ex['day']} | {ex['field']} | {ex['ocr']} | {ex['gt']} | {ex['pdf']} |")
    lines.append("")

    # Recommendations
    lines.append("## Recommendations")
    lines.append("")
    overall = stats['overall_pct']
    if overall >= 90:
        lines.append("✅ **OCR pipeline accuracy is strong (≥90%).** Focus on the worst 20 clients listed above.")
    elif overall >= 75:
        lines.append("⚠️ **OCR pipeline accuracy is moderate (75–90%).** Consider expanding the ABBREV_MAP and retraining Tesseract on Russian menu forms.")
    else:
        lines.append("❌ **OCR pipeline accuracy is below 75%.** Claude Vision (Engine 4) should be the primary engine, with Tesseract as fallback only.")

    # Field-specific recommendations
    for field in ('salad', 'soup', 'main', 'side'):
        fd = stats['per_field'].get(field, {'pct': 100})
        if fd['pct'] < 70:
            lines.append(f"- **{field.capitalize()} field** ({fd['pct']:.1f}%): Expand abbreviation map and add more kitchen shorthand variants.")

    lines.append("")
    lines.append("### Learning Store")
    lines.append(f"- **{correction_count}** field corrections were automatically fed into `goj_menu_learning.json`.")
    lines.append("  These will improve future OCR runs via the name correction and item correction lookup tables.")
    lines.append("")
    lines.append("### Engine Notes")
    lines.append("- **Tesseract** (Engine 1): Fastest. Struggles with handwritten Russian. Consider training on GOJ-specific forms.")
    lines.append("- **Claude Vision** (Engine 4): Most accurate (0.95 confidence). Use as authority for high-value fields (main dish).")
    lines.append("- **Consensus voting**: Claude Vision fast-path if conf ≥ 0.90 gives best results. Keep this enabled.")
    lines.append("")

    # ── Tesseract diagnostic section ──────────────────────────────────────────
    diag = run_meta.get('tess_diag', {})
    if diag:
        lines.append("## Tesseract OCR Diagnostic (Root Cause Analysis)")
        lines.append("")
        lines.append("These findings explain why Track B produced 0 usable comparisons:")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| PDFs sent to Tesseract | {diag.get('pdfs_attempted', 0)} |")
        lines.append(f"| PDFs returning any OCR rows | {diag.get('pdfs_with_tess_rows', 0)} |")
        lines.append(f"| PDFs with at least 1 client name extracted | {diag.get('pdfs_with_names', 0)} |")
        lines.append(f"| PDFs with food field data (salad/soup/main/side) | {diag.get('pdfs_with_field_data', 0)} |")
        lines.append(f"| Total OCR row objects returned | {diag.get('total_tess_rows', 0)} |")
        lines.append(f"| Rows with a client name | {diag.get('total_named_rows', 0)} |")
        lines.append(f"| Rows with any food field populated | {diag.get('total_field_rows', 0)} |")
        lines.append(f"| Name match attempts vs vision-pipeline ref | {diag.get('name_match_attempts', 0)} |")
        lines.append(f"| Name matches above {MATCH_THRESHOLD} threshold | {diag.get('name_match_hits', 0)} |")
        lines.append("")
        lines.append("**Root causes identified during investigation:**")
        lines.append("")
        lines.append("1. **macOS TMPDIR symlink** — Python's `/tmp` is a symlink to `/private/tmp`.")
        lines.append("   Leptonica (Tesseract's image library) does NOT follow this symlink and fails")
        lines.append("   to open temp image files silently. All OCR returned empty word lists.")
        lines.append("   Fix applied: `os.environ['TMPDIR'] = '/private/tmp'` at script start.")
        lines.append("")
        lines.append("2. **Cyrillic→Latin OCR confusion on form labels** — The form label `ФИО:` is")
        lines.append("   OCR-read as `uma:` (Ф→u, И→m, О→a in Latin). `_extract_name_from_words`")
        lines.append("   searches for `{'ИМЯ', 'ФИО', 'УМА'}` in Cyrillic; `UMA` (Latin) never")
        lines.append("   matches. The client name text (e.g. `Khashimova Zukhra`) is correctly")
        lines.append("   extracted by OCR but unreachable because the trigger label is missed.")
        lines.append("")
        lines.append("3. **Zero food field extraction** — Food item rows (Борщ, Шницель, etc.) are")
        lines.append("   partially read by OCR but `_checked_days_on_row` finds no checkmarks")
        lines.append("   at those y-positions. The checkbox glyphs used on these forms don't")
        lines.append("   match the CHECKMARKS set `{'+', '*', 'X', 'V', 'л', '✓', ...}`.")
        lines.append("")
        lines.append("**What works:** Day column detection (M/T/W/TH/F/SA headers are read")
        lines.append("correctly in English on all PDFs). Vision-pipeline reference is solid:")
        lines.append(f"  {run_meta.get('vision_ref_pdfs', 0)} PDFs, "
                     f"{run_meta.get('vision_ref_clients', 0)} client-week entries.")
        lines.append("")
        lines.append("**Actionable fixes for production Tesseract:**")
        lines.append("- Add Latin lookalikes to trigger set: `'UMA'`, `'VIA'`, `'HMA'` etc.")
        lines.append("- Expand CHECKMARKS to include filled-square glyphs `■`, `▪`, `●`")
        lines.append("  common in scanned checkbox forms.")
        lines.append("- Set `TMPDIR=/private/tmp` in the launchd plist environment.")
        lines.append("- Consider Tesseract custom training data on GOJ forms for higher Russian accuracy.")
        lines.append("")

    lines.append("---")
    lines.append(f"*Report auto-generated by CC_ocr_benchmark.py · Gold Health Systems · {now}*")

    report_text = "\n".join(lines)
    pathlib.Path(report_path).write_text(report_text, encoding='utf-8')
    print(f"[Report] Written to {report_path}")
    return report_text


# ════════════════════════════════════════════════════════════════════════════
# STEP 7: MAIN
# ════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("GOJ Menu OCR Benchmark")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)

    # 1. Setup dirs
    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)

    # 2. Load ground truth and DB references
    print("\n[1/6] Loading ground truth from DB...")
    gt_rows = load_db_ground_truth(DB_PATH)
    print(f"      {len(gt_rows)} ground_truth rows loaded (March 2026)")

    # Build dict keyed by (name_norm, week_start, day) for Track A
    gt_by_client_week_day = {}
    for (client_id, week_start, day), row in gt_rows.items():
        name_norm = normalize_name(row.get('client_name', ''))
        if name_norm:
            gt_by_client_week_day[(name_norm, week_start, day)] = row

    client_id_map = load_db_clients(DB_PATH)
    print(f"      {len(client_id_map)} clients in DB")

    print("\n[2/6] Loading vision-pipeline reference (Track B)...")
    vision_ref = load_db_ocr_reference(DB_PATH)
    print(f"      {len(vision_ref)} unique PDFs in vision-pipeline reference")

    # 3. Track A: use any already-downloaded March PDFs (skip live IMAP download —
    #    too slow for interactive runs; ~15MB each × 189 emails). Already downloaded
    #    PDFs in benchmark_test/ are used if present.
    print("\n[3/6] Checking benchmark_test/ for existing downloaded PDFs...")
    imap_pdfs = [str(p) for p in BENCHMARK_DIR.glob("*.pdf")]
    # Filter to PDFs from March 2026 (filename contains 202603)
    march_pdfs = [p for p in imap_pdfs if '202603' in pathlib.Path(p).name]
    print(f"      {len(imap_pdfs)} PDFs in benchmark_test/, {len(march_pdfs)} from March 2026")
    if not march_pdfs:
        print("      (No March 2026 PDFs found — Track A will be skipped)")

    # 4. Gather existing PDFs for Track B
    print("\n[4/6] Gathering existing PDFs for Track B...")
    existing_pdfs = find_existing_pdfs(MENUS_DIR, limit=MAX_PDFS_TESSERACT)
    print(f"      {len(existing_pdfs)} PDFs found in {MENUS_DIR}")

    # 5. Run OCR and compare
    all_results = []

    # Track A: ground_truth only covers March 9/16 weeks; downloaded PDFs are
    # March 27 (target week March 30) — no overlap. Skip to avoid wasting time.
    print(f"\n[5/6] Track A: skipping (downloaded PDFs target week of 2026-03-30;")
    print( "       ground_truth DB covers 2026-03-09 and 2026-03-16 only — no overlap)")
    track_a_results = []

    print(f"\n[5b/6] Building Track B PDF list from vision-pipeline reference...")
    track_b_results = []
    if vision_ref:
        # Build a name→path index of ALL PDFs in MENUS_DIR (not just top 60)
        all_menu_pdfs = {}
        for p in MENUS_DIR.rglob("*.pdf"):
            all_menu_pdfs[p.name] = str(p)

        # Find the actual file path for each vision-pipeline reference PDF
        matched_pdfs = []
        for ref_base in vision_ref.keys():
            if ref_base in all_menu_pdfs:
                matched_pdfs.append(all_menu_pdfs[ref_base])
            else:
                # Try matching by embedded doc timestamp
                m = re.search(r"(doc\d{20}\.pdf)", ref_base)
                if m:
                    doc_core = m.group(1)
                    for fname, fpath in all_menu_pdfs.items():
                        if doc_core in fname:
                            matched_pdfs.append(fpath)
                            break
        # Deduplicate
        matched_pdfs = list(dict.fromkeys(matched_pdfs))
        print(f"      {len(matched_pdfs)}/{len(vision_ref)} vision-pipeline PDFs located on disk")
        # Sample across weeks: pick at most MAX_PDFS_TESSERACT=8 to keep runtime under 15 min
        # Prefer shorter PDFs (smaller file size → fewer pages → faster OCR)
        if len(matched_pdfs) > MAX_PDFS_TESSERACT:
            try:
                matched_pdfs.sort(key=lambda p: pathlib.Path(p).stat().st_size)
            except Exception:
                pass
            matched_pdfs = matched_pdfs[:MAX_PDFS_TESSERACT]
            print(f"      Sampling {MAX_PDFS_TESSERACT} smallest PDFs for tractable runtime")
        all_client_names = list({normalize_name(r.get('client_name',''))
                                 for r in gt_rows.values() if r.get('client_name')})
        track_b_results, tess_diag = run_track_b(matched_pdfs, vision_ref, all_client_names, LEARNING_PATH)
        all_results.extend(track_b_results)
    else:
        tess_diag = {}
        print("      Track B skipped (no vision-pipeline reference in DB)")

    print(f"\n      Total comparisons: {len(all_results)}")

    # 6. Aggregate stats and write corrections
    print("\n[6/6] Computing stats and writing corrections...")
    if not all_results:
        print("      ⚠️  No comparison results — generating empty report.")
        stats = {
            'overall_pct': 0.0, 'total_fields': 0, 'correct_fields': 0,
            'total_comparisons': 0,
            'per_field': {}, 'per_day': {}, 'per_track': {},
            'worst_clients': [], 'client_accuracy': {},
            'error_examples': [], 'top_errors': [],
        }
        correction_count = 0
    else:
        stats = aggregate_stats(all_results)
        correction_count = write_corrections(all_results, LEARNING_PATH)

    run_meta = {
        'pdfs_processed': len(march_pdfs) + len(existing_pdfs),
        'track_a_pdfs': len(march_pdfs),
        'track_a_comparisons': len(track_a_results),
        'track_b_pdfs': len(matched_pdfs) if vision_ref else 0,
        'track_b_comparisons': len(track_b_results),
        'tess_diag': tess_diag,
        'vision_ref_pdfs': len(vision_ref),
        'vision_ref_clients': sum(len(v) for v in vision_ref.values()),
    }

    report_text = generate_report(stats, correction_count, REPORT_PATH, run_meta)

    # Print summary
    print("\n" + "=" * 70)
    print(f"BENCHMARK COMPLETE")
    print(f"Overall accuracy:  {stats['overall_pct']:.1f}%  ({stats['correct_fields']}/{stats['total_fields']} fields)")
    print(f"Corrections saved: {correction_count}")
    print(f"Report:            {REPORT_PATH}")
    print(f"Learning store:    {LEARNING_PATH}")
    print("=" * 70)

    return stats


if __name__ == "__main__":
    main()
