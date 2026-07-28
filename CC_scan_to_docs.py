#!/usr/bin/env python3
"""
CC_scan_to_docs.py — GOJ Unified Scan-to-Documents Pipeline
============================================================
Accepts scanned PDFs (menus, sign-in sheets, auth docs, receipts),
auto-classifies them, runs OCR, writes to auth_tracker.db,
and generates kitchen/distribution/sign-in PDFs.

Replaces the Google Drive manual-entry workflow with OCR-first automation.

Usage:
    # Full pipeline for a date (OCR → DB → PDFs)
    python3 CC_scan_to_docs.py --pipeline --date 2026-06-17
    
    # Process a specific scanned PDF
    python3 CC_scan_to_docs.py --input scan.pdf --type menu --week 2026-06-15 --day W
    python3 CC_scan_to_docs.py --input scan.pdf --type signin --date 2026-06-17 --shift 1
    
    # Drive-sync mode (still works, uses Drive as source)
    python3 CC_scan_to_docs.py --drive-sync --date 2026-06-17
    
    # Generate PDFs only (DB already populated)
    python3 CC_scan_to_docs.py --generate-only --date 2026-06-17
    
    # Scan watch mode (monitors a directory for new scans)
    python3 CC_scan_to_docs.py --watch ~/Documents/goj\\ files/scans/
"""

import sys, json, sqlite3, subprocess, time, logging
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Optional

# ── Paths ───────────────────────────────────────────────────────────
HOME      = Path.home()
REX_DIR   = HOME / "Desktop" / "REX"
DB_PATH   = HOME / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
OUTPUT_DIR = HOME / "Documents" / "goj files" / "output_docs"
LOG_DIR   = REX_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(REX_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "scan_to_docs.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("scan_to_docs")

# ── Day mapping ─────────────────────────────────────────────────────
DAY_NAMES = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"}
DAY_CODES = {0: "M", 1: "T", 2: "W", 3: "TH", 4: "F", 5: "Sa", 6: "Su"}
DAY_COLUMNS = {0: "day_M_actual", 1: "day_T_actual", 2: "day_W_actual", 3: "day_TH_actual", 4: "day_F_actual", 5: "day_Sa_actual", 6: "day_Su_actual"}

# ── Document Classification ─────────────────────────────────────────

SIGNIN_KEYWORDS = [
    "sign-in sheet", "sign in sheet", "attendance report",
    "garden of joy adult day care center", "staff signature",
    "member's daily attendance", "total present",
]
MENU_KEYWORDS = [
    "салаты", "супы", "главное", "гарнир", "menu for the date",
    "борщ", "котлета", "salad", "soup", "main dish",
]
NON_FOOD_KEYWORDS = [
    "authorization", "prior approval", "carecenta", "medicaid",
    "receipt", "invoice", "квитанция",
]

def classify_document(pdf_path: Path) -> tuple[str, float]:
    """
    Returns (document_type, confidence).
    Types: 'menu_form', 'signin_sheet', 'auth_document', 'receipt', 'unknown'
    """
    try:
        import fitz
    except ImportError:
        return ('unknown', 0.0)
    
    doc = fitz.open(str(pdf_path))
    page_count = len(doc)
    first_text = ""
    all_text = ""
    for i, page in enumerate(doc):
        text = page.get_text().lower()
        all_text += text
        if i < 3:
            first_text += text
    doc.close()
    
    # Menu form: 40+ pages, food keywords
    if page_count >= 30:
        food_hits = sum(1 for kw in MENU_KEYWORDS if kw in all_text)
        if food_hits >= 2:
            return ('menu_form', 0.95)
    
    # Menu form: even small ones with menu keywords
    food_hits_first = sum(1 for kw in MENU_KEYWORDS if kw in first_text)
    if food_hits_first >= 2:
        return ('menu_form', 0.88)
    
    # Sign-in sheet: 1-4 pages, sign-in keywords
    signin_hits = sum(1 for kw in SIGNIN_KEYWORDS if kw in first_text)
    if signin_hits >= 2 and page_count <= 5:
        return ('signin_sheet', 0.93)
    
    # Auth document
    if 'authorization' in first_text or 'prior approval' in first_text:
        return ('auth_document', 0.85)
    
    # Receipt
    if page_count == 1 and ('receipt' in first_text or '$' in first_text):
        return ('receipt', 0.80)
    
    # Fallback: check filename
    fname = pdf_path.name.lower()
    if 'sign' in fname or 'attend' in fname:
        return ('signin_sheet', 0.60)
    if 'menu' in fname:
        return ('menu_form', 0.60)
    
    return ('unknown', 0.0)

# ── Day utilities ───────────────────────────────────────────────────

def get_day_info(date_str: str) -> dict:
    d = date.fromisoformat(date_str)
    wd = d.weekday()
    return {
        "date": date_str,
        "weekday": wd,
        "day_name": DAY_NAMES[wd],
        "day_code": DAY_CODES[wd],
        "day_column": DAY_COLUMNS[wd],
    }

def get_week_start(date_str: str) -> str:
    d = date.fromisoformat(date_str)
    monday = d - timedelta(days=d.weekday())
    return monday.isoformat()

# ── Drive sync (preflight) ──────────────────────────────────────────

def sync_from_drive(date_str: str) -> dict:
    """
    Pull attendance + menus from Google Drive via CC_drive_preflight.
    Preflight handles all syncing: attendance, menus, client mirror, fill/flag.
    """
    try:
        from CC_drive_preflight import preflight
        pf = preflight(date_str)
        s1_count = len(pf['attendance'].get(1, []))
        s2_count = len(pf['attendance'].get(2, []))
        s1_menu_count = len(pf['menus'].get(1, {}))
        s2_menu_count = len(pf['menus'].get(2, {}))
        log.info(f"Drive preflight: S1={s1_count} clients, S2={s2_count} clients")
        log.info(f"  Menus: S1={s1_menu_count}, S2={s2_menu_count}")
        if pf.get("no_menu"):
            log.warning(f"  No menu: {len(pf['no_menu'])} clients")

        return {
            "status": "ok",
            "s1_count": s1_count,
            "s2_count": s2_count,
            "s1_menus": s1_menu_count,
            "s2_menus": s2_menu_count,
            "no_menu": len(pf.get("no_menu", [])),
        }
    except Exception as e:
        log.error(f"Drive sync (preflight) failed: {e}")
        return {"status": "error", "error": str(e)}

# ── PDF Generation ──────────────────────────────────────────────────

def generate_pdfs(date_str: str) -> dict:
    """Generate all daily PDFs: sign-in S1/S2, kitchen S1/S2, distribution S1/S2.
    Sunday: combined shift 1 only, skip shift 2."""
    day = get_day_info(date_str)
    is_sunday = (day['weekday'] == 6)
    shifts = ["1"] if is_sunday else ["1", "2"]
    log.info(f"Generating PDFs for {day['day_name']} {date_str} (shifts: {shifts})")

    venv = str(HOME / ".rex-venv/bin/python3")
    generated = []

    # Sign-in sheets (generate_tomorrow.py)
    r = subprocess.run(
        [venv, str(HOME / "Documents/goj files/dashboard/generate_tomorrow.py"),
         "--day", day['day_name'], "--mode", "signin"],
        cwd=str(HOME / "Documents/goj files/dashboard"),
        capture_output=True, text=True, timeout=60
    )
    for line in r.stdout.splitlines():
        if 'signin.pdf' in line.lower():
            generated.append(line.strip())

    # Kitchen + Distribution
    for script, label in [
        ("goj_kitchen_paired.py", "Kitchen"),
        ("goj_distribution.py", "Distribution"),
    ]:
        for shift in shifts:
            r = subprocess.run(
                [venv, str(REX_DIR / script), "--date", date_str, "--shift", shift],
                cwd=str(REX_DIR),
                capture_output=True, text=True, timeout=60
            )
            for line in r.stdout.splitlines():
                if 'Generated' in line:
                    generated.append(line.strip())

    return {"generated": generated, "count": len(generated)}

# ── Main Pipeline ───────────────────────────────────────────────────

def pipeline(date_str: str, input_dir: Path = None, use_drive: bool = False):
    """
    Full pipeline:
    1. If use_drive: sync from Google Drive
    2. If input_dir: scan for new PDFs, classify, OCR
    3. Generate all PDFs
    """
    results = {
        "date": date_str,
        "pipeline_start": datetime.now().isoformat(),
        "sync": None,
        "ocr": None,
        "generation": None,
    }
    
    # Step 1: Sync attendance (from Drive or OCR)
    if use_drive:
        results["sync"] = sync_from_drive(date_str)
    
    # Step 2: Scan input dir for new PDFs (OCR pathway)
    if input_dir and input_dir.exists():
        log.info(f"Scanning {input_dir} for new PDFs...")
        ocr_results = []
        for pdf in sorted(input_dir.glob("*.pdf")):
            doc_type, conf = classify_document(pdf)
            log.info(f"  {pdf.name}: {doc_type} (confidence: {conf:.0%})")
            ocr_results.append({
                "file": str(pdf),
                "type": doc_type,
                "confidence": conf
            })
        results["ocr"] = {"scanned": len(ocr_results), "details": ocr_results}
    
    # Step 3: Generate PDFs
    results["generation"] = generate_pdfs(date_str)
    
    # Save report
    report_path = LOG_DIR / f"pipeline_{date_str}.json"
    report_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    
    log.info(f"Pipeline complete: {results['generation']['count']} PDFs generated")
    log.info(f"Report: {report_path}")
    
    return results

def watch_mode(watch_dir: Path, interval: int = 60):
    """Monitor a directory for new scans and process them."""
    log.info(f"Watching {watch_dir} every {interval}s...")
    seen = set()
    
    while True:
        try:
            for pdf in sorted(watch_dir.glob("*.pdf")):
                if pdf.name in seen:
                    continue
                doc_type, conf = classify_document(pdf)
                log.info(f"New scan: {pdf.name} → {doc_type} ({conf:.0%})")
                seen.add(pdf.name)
            time.sleep(interval)
        except KeyboardInterrupt:
            log.info("Watch stopped.")
            break

# ── CLI ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="GOJ Unified Scan-to-Documents Pipeline")
    p.add_argument("--pipeline", action="store_true", help="Run full pipeline")
    p.add_argument("--date", help="Date (YYYY-MM-DD), default: today")
    p.add_argument("--drive-sync", action="store_true", help="Use Google Drive as source")
    p.add_argument("--generate-only", action="store_true", help="Only generate PDFs")
    p.add_argument("--input", help="Path to scanned PDF or directory")
    p.add_argument("--type", choices=["menu", "signin", "auth", "receipt"], help="Document type override")
    p.add_argument("--week", help="Week start date for menu forms (YYYY-MM-DD)")
    p.add_argument("--day", help="Day code for menu forms (M/T/W/TH/F/Su)")
    p.add_argument("--shift", type=int, choices=[1, 2], help="Shift for sign-in sheets")
    p.add_argument("--watch", help="Watch directory for new scans")
    args = p.parse_args()
    
    target_date = args.date or date.today().isoformat()
    
    if args.watch:
        watch_mode(Path(args.watch))
    elif args.generate_only:
        result = generate_pdfs(target_date)
        print(json.dumps(result, indent=2))
    elif args.pipeline:
        result = pipeline(target_date, 
                         input_dir=Path(args.input) if args.input else None,
                         use_drive=args.drive_sync)
        print(json.dumps(result, indent=2))
    elif args.input:
        pdf_path = Path(args.input)
        if pdf_path.is_file():
            doc_type, conf = classify_document(pdf_path)
            print(f"Classified: {doc_type} (confidence: {conf:.0%})")
            print("Individual document OCR not yet implemented — use --pipeline for batch processing")
        elif pdf_path.is_dir():
            result = pipeline(target_date, input_dir=pdf_path, use_drive=args.drive_sync)
            print(json.dumps(result, indent=2))
    else:
        p.print_help()
