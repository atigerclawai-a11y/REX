#!/usr/bin/env python3
"""
CC_ocr_live_watcher.py — Live OCR Pipeline Watcher
====================================================
Monitors ~/Documents/goj files/dashboard/documents/menus/ for new PDFs,
runs OCR extraction, updates auth_tracker.db, and pushes live updates
to the Tiger Claw Hub via WebSocket.

Designed to run as a cron job every 5 minutes.

Usage:
    python3 CC_ocr_live_watcher.py              # process up to 10 new PDFs
    python3 CC_ocr_live_watcher.py --all         # process ALL unprocessed
    python3 CC_ocr_live_watcher.py --dry-run     # show what would happen
    python3 CC_ocr_live_watcher.py --pdf FILE    # process a specific PDF
"""

import json
import os
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, date, timedelta
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────
HOME      = Path.home()
DB_PATH   = HOME / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
MENUS_DIR = HOME / "Documents" / "goj files" / "dashboard" / "documents" / "menus"
LOG_PATH  = HOME / "Desktop" / "REX" / "logs" / "ocr_watcher.log"
STATE_PATH = HOME / "Desktop" / "REX" / "logs" / "ocr_watcher_state.json"

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── Hub WebSocket push ─────────────────────────────────────────────────
HUB_WS_URL = "http://127.0.0.1:9000/api/ocr/ingest-result"

# ── Config ─────────────────────────────────────────────────────────────
MAX_PDFS_PER_RUN = 10  # limit per cron tick
DRY_RUN = "--dry-run" in sys.argv
PROCESS_ALL = "--all" in sys.argv
SPECIFIC_PDF = None
if "--pdf" in sys.argv:
    idx = sys.argv.index("--pdf")
    if idx + 1 < len(sys.argv):
        SPECIFIC_PDF = sys.argv[idx + 1]

# ── Logging ────────────────────────────────────────────────────────────
def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} | {msg}"
    print(line)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")

# ── State ──────────────────────────────────────────────────────────────
def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"last_pdf_mtime": 0, "processed": [], "total_processed": 0}

def save_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2))

# ── PDF text extraction (pymupdf) ─────────────────────────────────────
def extract_pdf_text(pdf_path: Path) -> list[dict]:
    """Extract text and image info from each page."""
    try:
        import fitz
    except ImportError:
        log("ERROR: pymupdf (fitz) not installed")
        return []
    pages = []
    doc = fitz.open(str(pdf_path))
    for i, page in enumerate(doc):
        text = page.get_text().strip()
        images = page.get_images()
        pages.append({
            "page": i + 1,
            "text_chars": len(text),
            "text": text[:2000] if text else "",
            "image_count": len(images),
            "has_text": len(text) > 50,
        })
    doc.close()
    return pages

# ── OCR via tesseract on extracted images ──────────────────────────────
def ocr_page_with_tesseract(pdf_path: Path, page_num: int) -> str:
    """Extract a single page as image and run tesseract OCR."""
    import subprocess, tempfile
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        page = doc[page_num]
        # Render page to image
        pix = page.get_pixmap(dpi=200)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(pix.tobytes("png"))
            tmp_path = tmp.name
        doc.close()
        # Run tesseract
        result = subprocess.run(
            ["tesseract", tmp_path, "stdout", "-l", "rus+eng", "--psm", "6"],
            capture_output=True, text=True, timeout=30
        )
        os.unlink(tmp_path)
        return result.stdout.strip()
    except Exception as e:
        return f"[OCR ERROR: {e}]"

# ── Simple menu parsing from OCR text ─────────────────────────────────
def parse_menu_from_text(ocr_text: str, pdf_name: str) -> list[dict]:
    """
    Parse OCR'd Russian text to extract client name + menu selections.
    Returns list of {client_name, day, salad, soup, main, side, confidence}.
    """
    import re
    results = []
    if not ocr_text or len(ocr_text) < 20:
        return results
    
    lines = ocr_text.split("\n")
    
    # Try to find client name — look for "Имя:" or "Name:" patterns
    client_name = None
    for line in lines[:15]:
        for pattern in [r"Имя[:\s]+(.+)", r"Name[:\s]+(.+)", r"ИМЯ[:\s]+(.+)"]:
            m = re.search(pattern, line, re.IGNORECASE)
            if m:
                client_name = m.group(1).strip().strip("_").strip(".")
                break
    
    if not client_name:
        # Try first non-empty line as name — skip facility headers and menu section headers
        _HEADER_TOKENS = ("GARDEN", "ADULT DAYCARE", "ГЛАВНОЕ БЛЮДО", "ПРОДОЛЖЕНИЕ")
        for line in lines[:10]:
            line = line.strip()
            if (line and len(line) > 3
                    and not line.startswith(("САЛАТ", "СУП", "ГЛАВН", "НЕДЕЛ", "ПН", "ВТ", "СР", "ЧТ", "ПТ"))
                    and not any(tok in line.upper() for tok in _HEADER_TOKENS)):
                client_name = line[:60]
                break
    
    if not client_name:
        client_name = f"UNKNOWN_{pdf_name[:20]}"
    
    # Detect week start from filename or text
    week_match = re.search(r"(\d{4})(\d{2})(\d{2})", pdf_name)
    if week_match:
        try:
            week_start = date(int(week_match.group(1)), int(week_match.group(2)), int(week_match.group(3)))
            # Adjust to Monday
            week_start = week_start - timedelta(days=week_start.weekday())
        except ValueError:
            week_start = date.today() - timedelta(days=date.today().weekday())
    else:
        week_start = date.today() - timedelta(days=date.today().weekday())
    
    # Look for menu items in text
    # Simple heuristic: find known Russian food words
    KNOWN_ITEMS = {
        "salad": ["винегрет", "оливье", "сельдь", "шуба", "крабовый", "цезарь", "греческий", 
                  "морковь", "свекла", "капуста", "помидор", "огурец", "витаминный"],
        "soup": ["борщ", "щи", "солянка", "рассольник", "уха", "куриный", "гороховый", 
                 "вермишелевый", "харчо", "лапша", "фасолевый"],
        "main": ["котлета", "курица", "рыба", "пюре", "макароны", "рис", "гречка", 
                 "гуляш", "тефтели", "бефстроганов", "пельмени", "голубцы", "плов",
                 "шницель", "бифштекс", "омлет", "запеканка", "сосиска"],
        "side": ["картофель", "овощи", "капуста", "фасоль", "горошек"],
    }
    
    days_map = {"ПН": "M", "ВТ": "T", "СР": "W", "ЧТ": "TH", "ПТ": "F", "СБ": "SA"}
    
    found_items = {cat: [] for cat in KNOWN_ITEMS}
    for cat, terms in KNOWN_ITEMS.items():
        for term in terms:
            if term.lower() in ocr_text.lower():
                found_items[cat].append(term)
    
    # If we found items, create a minimal entry
    if any(found_items.values()):
        entry = {
            "client_name": client_name,
            "week_start": week_start.isoformat(),
            "day": "M",  # default, would need better day detection
            "salad": found_items["salad"][0] if found_items["salad"] else None,
            "soup": found_items["soup"][0] if found_items["soup"] else None,
            "main": found_items["main"][0] if found_items["main"] else None,
            "side": found_items["side"][0] if found_items["side"] else None,
            "confidence": 0.4,  # tesseract-based = lower confidence
            "source_pdf": pdf_name,
            "source": "ocr_watcher_tesseract",
        }
        results.append(entry)
    
    return results

# ── Write to DB ───────────────────────────────────────────────────────
def write_to_db(entries: list[dict]) -> int:
    """Write parsed menu entries to auth_tracker.db. Returns count written."""
    written = 0
    con = sqlite3.connect(str(DB_PATH))
    cur = con.cursor()
    _FACILITY_TOKENS = ("GARDEN", "ADULT DAYCARE", "ГЛАВНОЕ БЛЮДО", "ПРОДОЛЖЕНИЕ")
    for e in entries:
        # Guard: skip facility-header rows — not a real client name
        _cn_upper = (e.get("client_name") or "").upper()
        if any(tok in _cn_upper for tok in _FACILITY_TOKENS):
            log(f"  SKIP facility header: '{e.get('client_name', '')[:40]}'")
            continue
        try:
            cur.execute("""
                INSERT INTO client_menus
                (client_name, week_start, day, salad, soup, main, side,
                 confidence, source_pdf, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                e.get("client_name", "UNKNOWN"),
                e.get("week_start"),
                e.get("day", "M"),
                e.get("salad"),
                e.get("soup"),
                e.get("main"),
                e.get("side"),
                e.get("confidence", 0.3),
                e.get("source_pdf", ""),
                e.get("source", "ocr_watcher"),
                datetime.now().isoformat(),
            ))
            written += 1
        except Exception as ex:
            log(f"  DB write error: {ex}")
    con.commit()
    con.close()
    return written

# ── Push to Hub WebSocket ─────────────────────────────────────────────
def push_to_hub(event_type: str, data: dict):
    """Notify the Hub dashboard of OCR activity."""
    payload = json.dumps({
        "event": event_type,
        "timestamp": datetime.now().isoformat(),
        "data": data,
    }).encode()
    try:
        req = urllib.request.Request(
            HUB_WS_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read())
    except Exception as e:
        log(f"  Hub push failed: {e}")
        return None

# ── Main ───────────────────────────────────────────────────────────────
def main():
    log("=" * 60)
    log("OCR Live Watcher — START")
    
    state = load_state()
    last_mtime = state.get("last_pdf_mtime", 0)
    
    # Find PDFs
    all_pdfs = sorted(MENUS_DIR.glob("*.pdf"), key=lambda p: p.stat().st_mtime)
    
    if SPECIFIC_PDF:
        target = MENUS_DIR / SPECIFIC_PDF
        if target.exists():
            all_pdfs = [target]
        else:
            log(f"ERROR: PDF not found: {SPECIFIC_PDF}")
            return
    
    # Filter: new since last run
    if not PROCESS_ALL and not SPECIFIC_PDF:
        new_pdfs = [p for p in all_pdfs if p.stat().st_mtime > last_mtime]
    else:
        new_pdfs = all_pdfs
    
    # Check which are already processed
    con = sqlite3.connect(str(DB_PATH))
    cur = con.cursor()
    cur.execute("SELECT DISTINCT source_pdf FROM client_menus WHERE source_pdf IS NOT NULL")
    processed_names = set(row[0] for row in cur.fetchall())
    con.close()
    
    unprocessed = [p for p in new_pdfs if p.name not in processed_names]
    
    log(f"Total PDFs: {len(all_pdfs)} | New since last: {len(new_pdfs)} | Unprocessed: {len(unprocessed)}")
    
    if not unprocessed:
        log("Nothing to process.")
        state["last_pdf_mtime"] = max((p.stat().st_mtime for p in all_pdfs), default=0)
        save_state(state)
        return
    
    # Limit per run
    batch = unprocessed[:MAX_PDFS_PER_RUN]
    if not PROCESS_ALL and not SPECIFIC_PDF:
        log(f"Processing up to {MAX_PDFS_PER_RUN} of {len(unprocessed)} unprocessed PDFs")
    
    total_entries = 0
    for pdf_path in batch:
        log(f"  Processing: {pdf_path.name}")
        
        if DRY_RUN:
            pages = extract_pdf_text(pdf_path)
            log(f"    DRY RUN: {len(pages)} pages, would process")
            continue
        
        # Extract pages
        pages = extract_pdf_text(pdf_path)
        log(f"    {len(pages)} pages")
        
        # If image-only PDF, run tesseract on each page
        all_entries = []
        for page_info in pages:
            if not page_info["has_text"] and page_info["image_count"] > 0:
                ocr_text = ocr_page_with_tesseract(pdf_path, page_info["page"] - 1)
                if ocr_text:
                    entries = parse_menu_from_text(ocr_text, pdf_path.name)
                    all_entries.extend(entries)
            elif page_info["has_text"]:
                entries = parse_menu_from_text(page_info["text"], pdf_path.name)
                all_entries.extend(entries)
        
        # Write to DB
        if all_entries:
            n = write_to_db(all_entries)
            total_entries += n
            log(f"    → Wrote {n} entries to DB")
        else:
            log(f"    → No menu data extracted (image-only PDF needs Claude Vision)")
        
        # Small delay between PDFs
        time.sleep(0.5)
    
    # Update state
    state["last_pdf_mtime"] = max((p.stat().st_mtime for p in all_pdfs), default=0)
    state["total_processed"] = state.get("total_processed", 0) + total_entries
    save_state(state)
    
    # Push to Hub
    result_data = {
        "pdfs_scanned": len(batch),
        "entries_written": total_entries,
        "remaining_unprocessed": len(unprocessed) - len(batch),
        "total_unprocessed": len(unprocessed),
    }
    push_to_hub("ocr_batch_complete", result_data)
    
    log(f"DONE: {total_entries} entries from {len(batch)} PDFs | {len(unprocessed) - len(batch)} remaining")
    log("=" * 60)

if __name__ == "__main__":
    main()
