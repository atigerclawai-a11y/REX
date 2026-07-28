#!/usr/bin/env python3
"""
rex_vision_flag_processor.py — Vision OCR Flag Queue Processor
═══════════════════════════════════════════════════════════════
Rexonasence v4 · Garden of Joy · Chairman Authority

PURPOSE:
  The flag queue (goj_menu_flags_queue.json) holds menu OCR results that
  Tesseract couldn't confidently read — primarily handwritten Russian forms.
  This processor runs each flagged item through Claude Vision (Engine 4),
  which understands form layout and handwriting, and saves results to the DB.

USAGE:
  python3 rex_vision_flag_processor.py              # process all unresolved flags
  python3 rex_vision_flag_processor.py --dry-run    # show what would happen, write nothing
  python3 rex_vision_flag_processor.py --limit 5    # process at most 5 flags
  python3 rex_vision_flag_processor.py --flag-id 570  # process one specific flag

HOW IT WORKS:
  1. Load goj_menu_flags_queue.json
  2. For each unresolved flag:
     a. Download the PDF from Paperless-NGX (Tailscale 100.99.86.60:8000)
     b. Run Claude Vision OCR on it
     c. Match the extracted client name against the DB
     d. If match confidence >= 0.7 → save to client_menus table
     e. Mark the flag as resolved
  3. Print a summary of processed / saved / skipped

REQUIRES:
  pip install anthropic pymupdf
  Paperless-NGX running at 100.99.86.60:8000 (Tailscale)
  ANTHROPIC_API_KEY in ~/Desktop/REX/.env

After processing, run goj_menu_consensus_ocr.py normally for new PDFs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import sqlite3
import tempfile
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────────────────────
REX_DIR       = Path(__file__).resolve().parent
FLAGS_PATH    = REX_DIR / "goj_menu_flags_queue.json"
LEARNING_PATH = REX_DIR / "goj_menu_learning.json"
DB_PATH       = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
ENV_PATH      = REX_DIR / ".env"

# Mac-native menus folder (where UUID-flagged PDFs live)
MENUS_DIR = Path.home() / "Documents" / "goj files" / "dashboard" / "documents" / "menus"

# ── Paperless ──────────────────────────────────────────────────────────────────
PAPERLESS_URL   = "http://100.99.86.60:8000"
PAPERLESS_TOKEN = "583e819be1146b96b935007c6ad7f584a3a1b1b7"

# ── Thresholds ─────────────────────────────────────────────────────────────────
CLIENT_MATCH_MIN   = 0.60   # minimum fuzzy-match score to accept a client name
VISION_CONFIDENCE  = 0.90   # Claude Vision self-reported confidence threshold


# ─────────────────────────────────────────────────────────────────────────────
# Environment
# ─────────────────────────────────────────────────────────────────────────────

def _load_api_key() -> str:
    """Load ANTHROPIC_API_KEY from env or .env file."""
    key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if key:
        return key
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            if line.startswith('ANTHROPIC_API_KEY='):
                key = line.split('=', 1)[1].strip().strip('"\'')
                if key:
                    os.environ['ANTHROPIC_API_KEY'] = key
                    return key
    return ''


def _check_paperless() -> bool:
    """Return True if Paperless-NGX is reachable."""
    try:
        req = urllib.request.Request(
            f"{PAPERLESS_URL}/api/documents/?page_size=1",
            headers={"Authorization": f"Token {PAPERLESS_TOKEN}"}
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Paperless PDF download
# ─────────────────────────────────────────────────────────────────────────────

def download_pdf_from_paperless(doc_id: int, dest_path: str) -> bool:
    """
    Download the original PDF for a Paperless document.
    Returns True on success.
    """
    url = f"{PAPERLESS_URL}/api/documents/{doc_id}/download/"
    try:
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Token {PAPERLESS_TOKEN}"}
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read()
        with open(dest_path, 'wb') as f:
            f.write(data)
        return os.path.getsize(dest_path) > 100
    except Exception as e:
        print(f"  ⚠️  Download failed for doc {doc_id}: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Claude Vision OCR (standalone, no consensus needed)
# ─────────────────────────────────────────────────────────────────────────────

def run_vision_on_pdf(pdf_path: str) -> list[dict]:
    """
    Run Claude Vision OCR on a PDF.
    Returns list of parsed client records (one per 2-page spread).
    Raises RuntimeError if anthropic is not installed or API key is missing.
    """
    try:
        import anthropic
    except ImportError:
        raise RuntimeError(
            "anthropic library not installed.\n"
            "Run: pip install anthropic\n"
            "Or:  bash ~/Desktop/REX/install_ocr_deps.command"
        )

    api_key = _load_api_key()
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not found.\n"
            "Add it to ~/Desktop/REX/.env as: ANTHROPIC_API_KEY=sk-ant-..."
        )

    import base64, io

    # Convert PDF pages to JPEG bytes
    page_jpegs = []
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(pdf_path))
        mat = fitz.Matrix(200/72, 200/72)
        for page in doc:
            pix = page.get_pixmap(matrix=mat)
            page_jpegs.append(pix.tobytes("jpeg"))
    except ImportError:
        from pdf2image import convert_from_path
        pages = convert_from_path(str(pdf_path), dpi=200)
        for img in pages:
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=85)
            page_jpegs.append(buf.getvalue())

    if not page_jpegs:
        raise RuntimeError(f"Could not render any pages from {pdf_path}")

    client = anthropic.Anthropic(api_key=api_key)
    results = []

    # Process 2 pages at a time (each GOJ menu form = 2 pages)
    for i in range(0, len(page_jpegs), 2):
        batch = page_jpegs[i:i+2]
        encoded = [base64.standard_b64encode(j).decode('utf-8') for j in batch]

        content = []
        for enc in encoded:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": enc}
            })

        content.append({
            "type": "text",
            "text": """This is a Russian-language weekly menu form from Garden of Joy Adult Day Care in Brooklyn.

Extract the following and return ONLY valid JSON, no other text:

{
  "client_name": "full name as written",
  "date_filled": "date if visible",
  "week_start": "YYYY-MM-DD (Monday of the applicable week)",
  "days": {
    "M":  {"salad": "item or null", "soup": "item or null", "main": "item or null", "side": "item or null"},
    "T":  {"salad": null, "soup": null, "main": null, "side": null},
    "W":  {"salad": null, "soup": null, "main": null, "side": null},
    "TH": {"salad": null, "soup": null, "main": null, "side": null},
    "F":  {"salad": null, "soup": null, "main": null, "side": null},
    "SA": {"salad": null, "soup": null, "main": null, "side": null}
  }
}

САЛАТЫ: Салат из баклажан, Салат весенний, Винегрет, Салат Днестр, Квашеная капуста, Оливье, Свекла, Селедка, Сало
СУПЫ: Борщ зеленый, Борщ красный, Грибной суп, Куриный суп, Овощной суп, Харчо, Гороховый суп
ГЛАВНОЕ БЛЮДО: Баса с помидорами под сыром, Блины с мясом, Блины с творогом, Вареники с картошкой, Голубцы, Гуляш, Дорадо запеченая, Жульен, Котлеты куриные, Куриные крылышки, Курица в терияки соусе, Пельмени, Поперечка, Салмон, Свиная отбивная, Цыпленок табака, Чалахач, Чебуреки, Шницель куриный
ГАРНИР: Тушеная капуста, Картошка по деревенски, Пюре, Гречка, Паста, Рис, Жареная картошка, Без гарнира

Days: Пон/Пн=M, Втор/Вт=T, Ср=W, Четв/Чт=TH, Пят/Пт=F, Суб/Сб=SA
A checkmark (✓,V,v,L,√,+,*,x,х,■) next to an item in a day's column = that item was selected.
Use EXACT Russian names from the lists. Return null if nothing checked.
Return ONLY the JSON object."""
        })

        try:
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1200,
                messages=[{"role": "user", "content": content}]
            )
            text = response.content[0].text.strip()
            if '```' in text:
                text = text.split('```')[1]
                if text.startswith('json'):
                    text = text[4:]
            parsed = json.loads(text)
            parsed['_source'] = 'claude_vision'
            parsed['_confidence'] = 0.95
            parsed['_page_start'] = i + 1
            results.append(parsed)
        except Exception as e:
            print(f"    Vision error pages {i+1}-{i+2}: {e}")
            results.append(None)

    return [r for r in results if r is not None]


# ─────────────────────────────────────────────────────────────────────────────
# Client matching (standalone version)
# ─────────────────────────────────────────────────────────────────────────────

def match_client(name_str: str, db_path: Path) -> tuple[Optional[int], Optional[str], float]:
    """Fuzzy match a name string against active clients in the DB."""
    if not name_str or not db_path.exists():
        return None, None, 0.0
    try:
        import difflib
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT client_id, name FROM clients WHERE active = 1"
        ).fetchall()
        conn.close()
        if not rows:
            return None, None, 0.0

        name_lower = name_str.lower().strip()
        best_score = 0.0
        best_row   = None
        for cid, cname in rows:
            score = difflib.SequenceMatcher(None, name_lower, cname.lower()).ratio()
            if score > best_score:
                best_score = score
                best_row   = (cid, cname)

        if best_row and best_score >= CLIENT_MATCH_MIN:
            return best_row[0], best_row[1], best_score
        return None, None, best_score
    except Exception as e:
        print(f"  Client matching error: {e}")
        return None, None, 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Database save
# ─────────────────────────────────────────────────────────────────────────────

def save_menu_to_db(
    parsed: dict,
    client_id: int,
    client_name: str,
    source_pdf: str,
    db_path: Path,
    dry_run: bool = False,
) -> int:
    """
    Save parsed menu selections to client_menus table.
    Returns number of rows inserted.
    """
    rows_inserted = 0
    if dry_run:
        for day, meals in parsed.get('days', {}).items():
            non_null = {k: v for k, v in meals.items() if v}
            if non_null:
                print(f"    [dry-run] Would insert {day}: {non_null}")
                rows_inserted += 1
        return rows_inserted

    try:
        conn = sqlite3.connect(db_path)
        cur  = conn.cursor()

        # Ensure table exists
        cur.execute("""
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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        week_start = parsed.get('week_start') or datetime.now().strftime('%Y-%m-%d')

        for day in ['M', 'T', 'W', 'TH', 'F', 'SA']:
            meals = parsed.get('days', {}).get(day, {})
            if any(v for v in meals.values()):
                cur.execute("""
                    INSERT INTO client_menus
                    (client_id, client_name, week_start, day,
                     salad, soup, main, side,
                     confidence, source_pdf, ocr_engines)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    client_id, client_name, week_start, day,
                    meals.get('salad'), meals.get('soup'),
                    meals.get('main'),  meals.get('side'),
                    float(parsed.get('_confidence', 0.95)),
                    source_pdf, 'claude_vision',
                ))
                rows_inserted += 1

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"    DB save error: {e}")

    return rows_inserted


# ─────────────────────────────────────────────────────────────────────────────
# Main processor
# ─────────────────────────────────────────────────────────────────────────────

def process_flags(
    dry_run: bool = False,
    limit: int = 0,
    flag_id: Optional[str] = None,
) -> None:
    """Main entry point — process unresolved flags with Claude Vision."""

    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║  REX Vision Flag Processor                          ║")
    print(f"║  {datetime.now().strftime('%Y-%m-%d %H:%M')}  {'DRY RUN' if dry_run else 'LIVE MODE'}             " + " " * (13 - len('DRY RUN' if dry_run else 'LIVE MODE')) + "║")
    print("╚══════════════════════════════════════════════════════╝")
    print()

    # ── Pre-flight ─────────────────────────────────────────────────────────────
    api_key = _load_api_key()
    if not api_key:
        print("❌  ANTHROPIC_API_KEY not found in .env")
        print("    Add it to ~/Desktop/REX/.env and rerun.")
        sys.exit(1)
    print(f"✅  API key: {api_key[:20]}...{api_key[-4:]}")

    paperless_ok = _check_paperless()
    print(f"{'✅' if paperless_ok else '⚠️ '}  Paperless: {'reachable' if paperless_ok else 'NOT reachable (Tailscale off?)'}")
    print(f"{'✅' if DB_PATH.exists() else '⚠️ '}  Database: {DB_PATH}")
    print()

    # ── Load flags ─────────────────────────────────────────────────────────────
    if not FLAGS_PATH.exists():
        print("⚠️  Flag queue not found:", FLAGS_PATH)
        sys.exit(0)

    with open(FLAGS_PATH) as f:
        all_flags = json.load(f)

    unresolved = [fl for fl in all_flags if not fl.get('resolved', False)]
    if flag_id:
        unresolved = [fl for fl in unresolved if str(fl.get('flag_id')) == str(flag_id)]
    if limit:
        unresolved = unresolved[:limit]

    print(f"Flag queue: {len(all_flags)} total | {len([f for f in all_flags if not f.get('resolved')])} unresolved | processing {len(unresolved)}")
    print()

    if not unresolved:
        print("✅  Nothing to process.")
        return

    # ── Classify flags and deduplicate by PDF ─────────────────────────────────
    # Two flag types exist:
    #   1. Paperless flags — have integer doc_id, title from Paperless
    #   2. UUID flags      — have pdf_path (possibly stale sandbox path), no doc_id
    #
    # Deduplicate: if the same PDF was flagged multiple times, process it once
    # and mark all matching flags resolved.

    def _resolve_pdf_path(flag: dict) -> Optional[Path]:
        """
        Return a local Path to this flag's PDF, or None if unavailable.
        Handles stale sandbox paths by rebasing to MENUS_DIR.
        """
        raw = flag.get('pdf_path', '')
        if not raw:
            return None
        p = Path(raw)
        # If it's an old sandbox path (/sessions/*/mnt/...), rebase to Mac menus dir
        if '/sessions/' in raw and '/mnt/' in raw:
            return MENUS_DIR / p.name
        # Otherwise use as-is (may already be a Mac path)
        return p

    # Build a map: canonical_pdf_path → list of flag_ids that reference it
    pdf_to_flag_ids: dict[str, list[str]] = {}
    paperless_flags = []

    for fl in unresolved:
        doc_id = fl.get('doc_id')
        fid    = str(fl.get('flag_id', '?'))

        if doc_id and str(doc_id).isdigit():
            # Paperless flag — process individually
            paperless_flags.append(fl)
        else:
            # UUID / local file flag
            local_path = _resolve_pdf_path(fl)
            if local_path:
                key = str(local_path)
                pdf_to_flag_ids.setdefault(key, []).append(fid)
            else:
                pdf_to_flag_ids.setdefault('__no_path__', []).append(fid)

    unique_local_pdfs = [(Path(k), ids) for k, ids in pdf_to_flag_ids.items()
                         if k != '__no_path__']
    no_path_ids       = pdf_to_flag_ids.get('__no_path__', [])

    print(f"Flag breakdown:")
    print(f"  Paperless flags (download from server): {len(paperless_flags)}")
    print(f"  Local PDF flags (unique files):         {len(unique_local_pdfs)}")
    print(f"  No-path flags (cannot process):         {len(no_path_ids)}")
    if paperless_ok is False and paperless_flags:
        print()
        print("  ⚠️  Paperless not reachable — Paperless flags will be skipped.")
    print()

    stats = {
        'processed': 0, 'saved': 0, 'no_client_match': 0,
        'vision_failed': 0, 'download_failed': 0,
        'file_not_found': 0, 'skipped': len(no_path_ids),
    }
    updated_flags = {str(fl.get('flag_id')): fl for fl in all_flags}

    def _process_pdf_and_save(pdf_path_str: str, source_label: str, flag_ids: list[str],
                               item_num: int, total: int) -> None:
        """Run Vision on a PDF and save results; marks all flag_ids resolved on success."""
        nonlocal stats

        print(f"[{item_num}/{total}] {source_label}")

        # Run Claude Vision
        print("   Running Claude Vision...", end=' ', flush=True)
        try:
            results = run_vision_on_pdf(pdf_path_str)
        except RuntimeError as e:
            print(f"\n   ❌  {e}")
            sys.exit(1)

        if not results:
            print("FAIL — no results returned")
            stats['vision_failed'] += 1
            return

        print(f"OK — {len(results)} client form(s)")
        stats['processed'] += 1

        any_saved = False
        for result_idx, parsed in enumerate(results, 1):
            client_name_raw = parsed.get('client_name') or ''
            print(f"   Form {result_idx}: name={client_name_raw!r}")

            if not client_name_raw:
                print("   ⚠️  No client name extracted — document may not be a menu form")
                stats['no_client_match'] += 1
                continue

            client_id, matched_name, score = match_client(client_name_raw, DB_PATH)
            print(f"   Match: {matched_name!r}  (score={score:.2f})", end=' ')

            if not client_id:
                print("— below threshold, skipping")
                stats['no_client_match'] += 1
                continue

            print("— accepted")

            for day, meals in parsed.get('days', {}).items():
                non_null = {k: v for k, v in meals.items() if v}
                if non_null:
                    print(f"     {day}: {non_null}")

            rows = save_menu_to_db(
                parsed, client_id, matched_name, source_label, DB_PATH, dry_run=dry_run,
            )
            if rows > 0:
                print(f"   {'[dry-run] ' if dry_run else ''}✅  Saved {rows} day row(s)")
                stats['saved'] += rows
                any_saved = True

        # Mark all flags for this PDF as resolved
        if any_saved and not dry_run:
            for fid in flag_ids:
                if fid in updated_flags:
                    updated_flags[fid]['resolved']         = True
                    updated_flags[fid]['resolved_at']      = datetime.now().isoformat()
                    updated_flags[fid]['resolved_by']      = 'claude_vision'

    # ── 1. Process Paperless flags ────────────────────────────────────────────
    if paperless_flags and paperless_ok:
        print("── Paperless flags ─────────────────────────────────────────")
        for idx, flag in enumerate(paperless_flags, 1):
            doc_id = flag.get('doc_id')
            fid    = str(flag.get('flag_id', '?'))
            title  = flag.get('doc_title', f'doc {doc_id}')

            print(f"[{idx}/{len(paperless_flags)}] Flag {fid} — {title}")

            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
                tmp_path = tmp.name
            try:
                print(f"   Downloading doc {doc_id} from Paperless...", end=' ', flush=True)
                ok = download_pdf_from_paperless(doc_id, tmp_path)
                if not ok:
                    print("FAIL")
                    stats['download_failed'] += 1
                    continue
                print(f"OK ({os.path.getsize(tmp_path):,} bytes)")
                _process_pdf_and_save(
                    tmp_path,
                    f"paperless_doc_{doc_id}",
                    [fid],
                    idx, len(paperless_flags),
                )
            finally:
                try: os.unlink(tmp_path)
                except Exception: pass

            if idx < len(paperless_flags):
                time.sleep(1.5)

        print()

    # ── 2. Process local UUID flags (deduplicated) ────────────────────────────
    if unique_local_pdfs:
        print("── Local PDF flags ─────────────────────────────────────────")
        for idx, (pdf_path, flag_ids) in enumerate(unique_local_pdfs, 1):
            dup_note = f" ({len(flag_ids)} flags)" if len(flag_ids) > 1 else ""
            print(f"[{idx}/{len(unique_local_pdfs)}] {pdf_path.name}{dup_note}")

            if not pdf_path.exists():
                print(f"   ⚠️  File not found: {pdf_path}")
                print("   (PDF may have been moved or deleted — marking flags as stale)")
                stats['file_not_found'] += len(flag_ids)
                # Mark stale so we don't retry forever
                if not dry_run:
                    for fid in flag_ids:
                        if fid in updated_flags:
                            updated_flags[fid]['resolved']    = True
                            updated_flags[fid]['resolved_at'] = datetime.now().isoformat()
                            updated_flags[fid]['resolved_by'] = 'stale_path'
                continue

            _process_pdf_and_save(
                str(pdf_path),
                pdf_path.name,
                flag_ids,
                idx, len(unique_local_pdfs),
            )

            if idx < len(unique_local_pdfs):
                time.sleep(1.5)

        print()

    if no_path_ids:
        print(f"── {len(no_path_ids)} flag(s) with no PDF path — skipped ───────────────")

    # ── Save updated flag queue ────────────────────────────────────────────────
    if not dry_run:
        with open(FLAGS_PATH, 'w', encoding='utf-8') as f:
            json.dump(list(updated_flags.values()), f, ensure_ascii=False, indent=2)
        print()
        print("✅  Flag queue updated.")

    # ── Summary ────────────────────────────────────────────────────────────────
    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║  Summary                                            ║")
    print("╚══════════════════════════════════════════════════════╝")
    print(f"  PDFs processed:       {stats['processed']}")
    print(f"  DB rows saved:        {stats['saved']}")
    print(f"  No client match:      {stats['no_client_match']}")
    print(f"  Vision failed:        {stats['vision_failed']}")
    print(f"  Download failed:      {stats['download_failed']}")
    print(f"  Skipped (no doc_id):  {stats['skipped']}")
    if dry_run:
        print()
        print("  DRY RUN — nothing was written. Rerun without --dry-run to commit.")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    ap = argparse.ArgumentParser(
        description="Process OCR flag queue using Claude Vision"
    )
    ap.add_argument('--dry-run', action='store_true',
                    help='Show what would happen without writing to DB')
    ap.add_argument('--limit', type=int, default=0,
                    help='Process at most N flags (0 = all)')
    ap.add_argument('--flag-id', type=str, default=None,
                    help='Process one specific flag by its flag_id')
    args = ap.parse_args()

    process_flags(
        dry_run=args.dry_run,
        limit=args.limit,
        flag_id=args.flag_id,
    )
