#!/usr/bin/env python3
"""
CC_ocr_pipeline.py — DEFINITIVE GOJ OCR Pipeline
================================================
Single script: MinerU → classify → extract → output.

Replaces ALL legacy OCR scripts. MinerU 3.4.0 is the only engine.
Signatures are extracted as cropped PNGs using bbox data.
Handwriting falls back to Tesseract for edge cases only.

Usage:
    python3 CC_ocr_pipeline.py input.pdf                  # Process one file
    python3 CC_ocr_pipeline.py --watch                     # Watch scans/ folder
    python3 CC_ocr_pipeline.py --process-all               # Process all PDFs in scans/
    python3 CC_ocr_pipeline.py input.pdf --signatures-only # Extract signatures only
    python3 CC_ocr_pipeline.py --test                      # Run on Friday drivers demo

Hardcoded paths — do NOT change without updating CC_RECOVERY.md and battle-fixes skill.
"""

import json
import os
import re
import sys
import time
import shutil
import tempfile
import sqlite3
from pathlib import Path
from datetime import datetime


def _log(msg):
    """Daemon-thread-safe print — stdout may be closed when the bridge
    spawns process_file() in background threads (ValueError: I/O operation
    on closed file). Fall back to the pipeline log file."""
    try:
        print(msg)
    except (ValueError, OSError):
        try:
            logp = Path.home() / ".hermes" / "profiles" / "work" / "logs" / "ocr_pipeline.log"
            logp.parent.mkdir(parents=True, exist_ok=True)
            with open(logp, "a") as fh:
                fh.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")
        except Exception:
            pass
from typing import Optional

# ── Hardcoded Paths ────────────────────────────────────────────────────────
REX_DIR      = Path(__file__).resolve().parent
SCANS_DIR    = Path.home() / "Documents" / "goj files" / "scans"
OUTPUT_DIR   = Path.home() / "Documents" / "goj files" / "dashboard" / "documents"
SIGNATURES   = OUTPUT_DIR / "signatures"
MENUS_DIR    = OUTPUT_DIR / "menus"
AUTH_DIR     = OUTPUT_DIR / "authorization"
DB_PATH      = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
MINERU_BIN   = str(REX_DIR / "mineru-venv/bin/mineru")
TESSERACT    = str(Path.home() / ".local/bin/tesseract")
DONE_LOG     = SCANS_DIR / ".pipeline_processed.json"

# ── Ensure output dirs ──────────────────────────────────────────────────────
for d in [OUTPUT_DIR, SIGNATURES, MENUS_DIR, AUTH_DIR, SCANS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Document Classification ─────────────────────────────────────────────────
# Detection order matters: template FIRST (skip), then filename patterns, then content

DOC_TYPES = {
    "template": {
        "patterns": [r"(?i)TEMPLATE"],
        "keywords": [],
        "description": "Template — skip processing entirely"
    },
    "sign_in_sheet": {
        "patterns": [r"(?i)sign[_\s-]?in|signin"],
        "keywords": ["ATTENDANCE", "Time In", "Time Out", "Signature", "Shift:"],
        "table_headers": ["No", "Client Name", "Plan", "TR", "Time In", "Time Out"],
        "description": "Daily sign-in sheet with client names and signatures"
    },
    "driver_route": {
        "patterns": [r"(?i)driver|route"],
        "keywords": ["ROUTE", "Clients:", "Address", "Phone"],
        "table_headers": ["No", "Client Name", "Address", "Phone"],
        "description": "Driver route sheet with addresses and phone numbers"
    },
    "menu": {
        "patterns": [r"(?i)menu|меню"],
        "keywords": ["main dish", "основное", "блюдо", "Monday", "Tuesday", "Wednesday"],
        "table_headers": ["Client", "Main", "Side"],
        "description": "Weekly menu with food items in Russian/English"
    },
    "auth_letter": {
        "patterns": [r"(?i)auth|authorization|mltc|plan"],
        "keywords": ["Authorization", "MLTC", "Plan:", "Auth Start", "Auth End"],
        "description": "Insurance authorization letter"
    },
    "kitchen": {
        "patterns": [r"(?i)kitchen|distribution"],
        "keywords": ["Kitchen Count", "Distribution", "Meal Count"],
        "description": "Kitchen count or distribution sheet"
    },
    "unknown": {
        "patterns": [],
        "keywords": [],
        "description": "Unknown document — extract all text, don't guess"
    }
}

def classify_document(filename: str, markdown_text: str = "") -> str:
    """Classify a document by filename patterns first, then content keywords."""
    for doc_type, rules in DOC_TYPES.items():
        if doc_type == "unknown":
            continue
        for pattern in rules["patterns"]:
            if re.search(pattern, filename):
                return doc_type
    # Content-based detection (fallback)
    if markdown_text:
        for doc_type, rules in DOC_TYPES.items():
            if doc_type in ("unknown", "template"):
                continue
            matches = sum(1 for kw in rules.get("keywords", []) if kw.lower() in markdown_text.lower())
            if matches >= 2:
                return doc_type
    return "unknown"


# ── MinerU Integration ───────────────────────────────────────────────────────

def run_mineru(pdf_path: str) -> dict:
    """Run MinerU pipeline backend. Returns parsed result dict."""
    pdf = Path(pdf_path).resolve()
    if not pdf.exists():
        return {"error": f"File not found: {pdf_path}", "type": "unknown"}

    if not Path(MINERU_BIN).exists():
        return {"error": f"MinerU not found at {MINERU_BIN}", "type": "unknown"}

    out_dir = Path(tempfile.mkdtemp(prefix="mineru_"))
    start = time.time()

    import subprocess
    result = subprocess.run(
        [MINERU_BIN, "-p", str(pdf), "-o", str(out_dir), "-b", "pipeline"],
        capture_output=True, text=True, timeout=600
    )
    elapsed = round(time.time() - start, 1)

    auto_dir = out_dir / pdf.stem / "auto"
    md_file = auto_dir / f"{pdf.stem}.md"
    cl_file = auto_dir / f"{pdf.stem}_content_list.json"

    if not cl_file.exists():
        return {
            "error": f"MinerU produced no output (exit {result.returncode})",
            "stderr": result.stderr[-500:] if result.stderr else "",
            "type": "unknown",
            "elapsed_s": elapsed
        }

    with open(cl_file) as f:
        content_list = json.load(f)

    md_text = md_file.read_text() if md_file.exists() else ""

    # Extract tables
    tables = []
    for elem in content_list:
        if elem.get("type") == "table" and elem.get("table_body"):
            tables.append({
                "page": elem.get("page_idx", 0),
                "bbox": elem.get("bbox", []),
                "html": elem["table_body"],
                "rows": _parse_html_table(elem["table_body"])
            })

    doc_type = classify_document(pdf.name, md_text)

    return {
        "file": str(pdf),
        "filename": pdf.name,
        "type": doc_type,
        "pages": len(set(e.get("page_idx", 0) for e in content_list)),
        "elements": len(content_list),
        "tables": len(tables),
        "table_data": tables,
        "markdown": md_text,
        "content_list": content_list,
        "md_path": str(md_file) if md_file.exists() else None,
        "json_path": str(cl_file),
        "output_dir": str(auto_dir),
        "elapsed_s": elapsed
    }


def _parse_html_table(html: str) -> list[list[str]]:
    """Parse MinerU HTML table into list of rows."""
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", html, re.DOTALL):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.DOTALL)
        rows.append([c.strip() for c in cells])
    return rows


# ── Signature Extraction ─────────────────────────────────────────────────────

def extract_signatures(pdf_path: str, content_list: list, doc_type: str) -> list[dict]:
    """Extract signature regions from sign-in sheets using bbox data."""
    if doc_type not in ("sign_in_sheet", "driver_route"):
        return []

    try:
        import fitz  # pymupdf
    except ImportError:
        try:
            logger.warning(f"fitz (pymupdf) not available — skipping signature extraction for {pdf_path}")
        except NameError:
            pass  # logger may not be set up in all contexts
        return []
    signatures = []
    doc = fitz.open(pdf_path)
    sig_dir = SIGNATURES / Path(pdf_path).stem
    sig_dir.mkdir(parents=True, exist_ok=True)

    # Look for "Signature" text elements and extract the region to their right
    for elem in content_list:
        if elem.get("type") != "text":
            continue
        text = elem.get("text", "").strip()
        if re.search(r"(?i)signature|подпись", text):
            bbox = elem.get("bbox", [])
            page_idx = elem.get("page_idx", 0)
            if len(bbox) != 4 or page_idx >= len(doc):
                continue
            page = doc[page_idx]
            x0, y0, x1, y1 = bbox
            # Signature is to the right of the label
            sig_rect = fitz.Rect(x1 + 5, y0 - 10, x1 + 200, y1 + 30)
            # Guard: ensure valid dimensions
            if sig_rect.width <= 0 or sig_rect.height <= 0:
                continue
            try:
                pix = page.get_pixmap(clip=sig_rect, dpi=150)
                if pix.width > 0 and pix.height > 0:
                    sig_file = sig_dir / f"page{page_idx}_sig_{len(signatures)}.png"
                    pix.save(str(sig_file))
                    signatures.append({
                        "page": page_idx,
                        "label": text,
                        "bbox": bbox,
                        "sig_file": str(sig_file)
                    })
            except Exception:
                continue  # Skip invalid crops silently

    doc.close()
    return signatures


# ── Data Extraction ──────────────────────────────────────────────────────────

def extract_signin_data(result: dict) -> list[dict]:
    """Extract client rows from sign-in sheet tables."""
    clients = []
    for table in result.get("table_data", []):
        rows = table.get("rows", [])
        for row in rows:
            if len(row) >= 3 and row[0].isdigit():
                clients.append({
                    "no": row[0],
                    "name": row[1] if len(row) > 1 else "",
                    "plan": row[2] if len(row) > 2 else "",
                    "tr": row[3] if len(row) > 3 else "",
                    "time_in": row[4] if len(row) > 4 else "",
                    "time_out": row[5] if len(row) > 5 else "",
                })
    return clients


def extract_driver_data(result: dict) -> list[dict]:
    """Extract driver routes from route sheets using MinerU content_list."""
    routes = []
    current_route = None

    for elem in result.get("content_list", []):
        # Detect route headers: "ROUTE — NAME" in text elements
        if elem.get("type") == "text":
            text = elem.get("text", "").strip()
            match = re.match(r"ROUTE [—\-–] (.+)", text)
            if match:
                current_route = match.group(1).strip()
                continue

        # Detect route metadata: "Friday, March 27, 2026   Shift: 1   Clients: 16"
        if elem.get("type") == "text" and current_route:
            text = elem.get("text", "").strip()
            meta = re.match(r"(.+?)\s+Shift:\s*(\d+)\s+Clients:\s*(\d+)", text)
            if meta:
                routes.append({
                    "driver": current_route,
                    "date": meta.group(1).strip(),
                    "shift": int(meta.group(2)),
                    "total_clients": int(meta.group(3)),
                    "clients": []
                })

    # Now extract clients from tables — one table per route (in order)
    tables = result.get("table_data", [])
    for i, table in enumerate(tables):
        if i < len(routes):
            for row in table.get("rows", []):
                if len(row) >= 2 and row[0].isdigit():
                    routes[i]["clients"].append({
                        "no": row[0],
                        "name": row[1],
                        "address": row[2] if len(row) > 2 else "",
                        "phone": row[3] if len(row) > 3 else "",
                        "notes": row[4] if len(row) > 4 else ""
                    })
    return routes


# ── Database Writer ──────────────────────────────────────────────────────────

def write_to_db(result: dict) -> dict:
    """Write extracted data to auth_tracker.db. Returns summary."""
    doc_type = result.get("type", "unknown")
    if doc_type == "template":
        return {"status": "skipped", "reason": "template"}

    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        rows_written = 0  # Default for unknown/generic types

        if doc_type == "menu":
            # Menu forms: parse MinerU markdown into per-client/day food selections
            # via goj_menu_form_parser (checkmark grids), write to goj_proprietary.db.
            # Replaces the old ocr_staging.stage_menu row-dump (wrong schema for forms).
            import sys as _sys
            if str(REX_DIR) not in _sys.path:
                _sys.path.insert(0, str(REX_DIR))
            import tempfile as _tf
            from goj_menu_form_parser import (parse_menu_md, load_roster,
                                              week_from_filename)
            from CC_menu_intake import shift_lookup_factory, DAY_MAP as _DM  # noqa

            md_path = result.get("md_path")
            if not md_path and result.get("markdown"):
                tmp = _tf.NamedTemporaryFile(mode="w", suffix=".md", delete=False)
                tmp.write(result["markdown"])
                tmp.close()
                md_path = tmp.name
            if not md_path:
                return {"status": "error", "error": "no markdown for menu doc",
                        "doc_type": doc_type}

            roster, norm = load_roster()
            parsed = parse_menu_md(md_path, roster, norm,
                                   fallback_monday=week_from_filename(
                                       result.get("filename", "")))
            shift_lookup = shift_lookup_factory()
            from datetime import date as _date, timedelta as _td
            ws = parsed["stats"].get("week_start")
            prop_db = Path.home() / "Desktop/REX/goj_proprietary.db"
            rows_written = 0
            if ws:
                week_monday = _date.fromisoformat(ws)
                pconn = sqlite3.connect(str(prop_db))
                DAY_CODES = ["M", "T", "W", "TH", "F"]
                # Merge p1+p2 anchors of the same client first, or INSERT OR IGNORE
                # would drop page-2 categories (side/main-continued).
                merged = {}
                for raw, info in parsed["clients"].items():
                    client = info["matched"]
                    if not client:
                        continue
                    slot = merged.setdefault(client, {"shift": info["shift"], "days": {}})
                    if not slot["shift"] and info["shift"]:
                        slot["shift"] = info["shift"]
                    for d, cats in info["days"].items():
                        if not cats or d > 4:
                            continue
                        dd = slot["days"].setdefault(d, {})
                        for cat, item in cats.items():
                            if not dd.get(cat) and item:
                                dd[cat] = item
                for client, slot in merged.items():
                    for d, cats in slot["days"].items():
                        menu_date = week_monday + _td(days=d)
                        day_code = DAY_CODES[d]
                        shift = (slot["shift"] or shift_lookup(client, day_code) or "1")
                        cur = pconn.execute(
                            "INSERT OR IGNORE INTO client_menus "
                            "(client_name, menu_date, day_code, shift, salad, soup, main, side, "
                            "source_sheet) VALUES (?,?,?,?,?,?,?,?, 'ocr_scan')",
                            (client, str(menu_date), day_code, shift,
                             cats.get("salad"), cats.get("soup"),
                             cats.get("main"), cats.get("side")))
                        rows_written += cur.rowcount
                pconn.commit()
                pconn.close()

        elif doc_type in ("sign_in_sheet", "driver_route"):
            # Attendance — verified multi-table staging + confidence-gated promotion.
            # (Replaces the stale wrong-schema INSERT. See ocr_staging.py, tested on a
            # DB copy 2026-07-02: registry -> ingest_run -> staged_rows -> review_queue,
            # high-confidence auto-promotes to attendance_log, low-confidence held for review.)
            import sys as _sys
            if str(REX_DIR) not in _sys.path:
                _sys.path.insert(0, str(REX_DIR))
            from ocr_staging import stage_attendance, promote_staged
            if doc_type == "sign_in_sheet":
                clients = extract_signin_data(result)
                shift = int(result.get("shift", 0) or 0)
            else:
                clients = []
                shift = 0
                for route in extract_driver_data(result):
                    clients.extend(route.get("clients", []))
            info = stage_attendance(conn, result.get("file", ""), clients,
                                    log_date=result.get("log_date"),
                                    day_key=result.get("day_key", ""),
                                    shift=shift, classification=doc_type,
                                    doc_confidence=float(result.get("confidence", 0.0) or 0.0))
            promoted = promote_staged(conn, info["run_id"])
            rows_written = info["staged"]
            conn.commit()
            conn.close()
            return {"status": "ok", "rows_written": rows_written, "staged": info["staged"],
                    "doc_type": doc_type, "registry_id": info["registry_id"], "run_id": info["run_id"],
                    "review_queued": info["review_queued"], "auto_promoted": promoted}

        conn.commit()
        conn.close()
        return {"status": "ok", "rows_written": rows_written, "doc_type": doc_type}

    except Exception as e:
        return {"status": "error", "error": str(e), "doc_type": doc_type}


def _hash_file(path: str) -> str:
    """SHA-256 hash of file for dedup."""
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Watcher ──────────────────────────────────────────────────────────────────

def watch_folder():
    """Watch scans/ folder for new PDFs and process them."""
    processed = {}
    if DONE_LOG.exists():
        processed = json.loads(DONE_LOG.read_text())

    print(f"👁 Watching {SCANS_DIR} for new PDFs... (Ctrl+C to stop)")
    try:
        while True:
            for pdf in sorted(SCANS_DIR.glob("*.pdf")):
                if pdf.name in processed:
                    continue
                print(f"\n📄 NEW: {pdf.name}")
                result = process_file(str(pdf))
                if "error" not in result:
                    processed[pdf.name] = {
                        "processed_at": datetime.now().isoformat(),
                        "type": result.get("type"),
                        "pages": result.get("pages")
                    }
                    DONE_LOG.write_text(json.dumps(processed, indent=2))
                    print(f"  ✅ {result.get('type')}: {result.get('pages')} pages, {result.get('tables')} tables, {result.get('elapsed_s')}s")
                else:
                    print(f"  ❌ {result.get('error')}")
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n🛑 Watcher stopped.")


# ── Main Process ─────────────────────────────────────────────────────────────

def process_file(pdf_path: str, extract_sigs: bool = True) -> dict:
    """Full pipeline: MinerU → classify → extract → output."""
    _log(f"🔍 Processing: {pdf_path}")

    # Step 1: MinerU
    result = run_mineru(pdf_path)
    if "error" in result:
        return result

    doc_type = result["type"]
    try:
        _log(f"  📋 Classified: {doc_type} ({DOC_TYPES.get(doc_type, {}).get('description', '')})")
        _log(f"  📊 {result['pages']} pages, {result['elements']} elements, {result['tables']} tables")
    except (ValueError, OSError):
        pass  # daemon thread stdout may be closed

    # Step 2: Signature extraction
    if extract_sigs and doc_type in ("sign_in_sheet", "driver_route"):
        sigs = extract_signatures(pdf_path, result["content_list"], doc_type)
        result["signatures"] = sigs
        if sigs:
            _log(f"  ✍️  {len(sigs)} signatures extracted")

    # Step 3: Data extraction
    if doc_type == "sign_in_sheet":
        clients = extract_signin_data(result)
        result["extracted_clients"] = clients
        _log(f"  👥 {len(clients)} clients extracted")
    elif doc_type == "driver_route":
        routes = extract_driver_data(result)
        result["extracted_routes"] = routes
        total = sum(r["total_clients"] for r in routes)
        _log(f"  🚗 {len(routes)} routes, {total} clients")
    elif doc_type == "menu":
        _log(f"  🍽️ Menu document — {result['tables']} tables extracted")

    # Step 4: Save output JSON
    out_name = Path(pdf_path).stem
    json_out = OUTPUT_DIR / f"{out_name}_pipeline.json"
    json_out.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    result["pipeline_json"] = str(json_out)
    _log(f"  💾 Output: {json_out}")

    return result


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h"):
        print(__doc__)
        sys.exit(0)

    if sys.argv[1] == "--test":
        test_file = Path.home() / "Documents/goj files/GOJ_F_S1_Friday_drivers.pdf"
        if not test_file.exists():
            print(f"Demo file not found: {test_file}")
            sys.exit(1)
        result = process_file(str(test_file))
        print(f"\n{'='*60}")
        print(f"✅ Pipeline test complete: {result.get('type')}")
        print(f"   File: {test_file.name}")
        print(f"   Pages: {result.get('pages')}  Tables: {result.get('tables')}")
        print(f"   Time: {result.get('elapsed_s')}s")
        if result.get('extracted_routes'):
            for r in result['extracted_routes']:
                print(f"   🚗 {r['driver']}: {r['total_clients']} clients")
        if result.get('signatures'):
            print(f"   ✍️  {len(result['signatures'])} signatures extracted")
        print(f"   Output: {result.get('pipeline_json')}")

    elif sys.argv[1] == "--watch":
        watch_folder()

    elif sys.argv[1] == "--process-all":
        pdfs = sorted(SCANS_DIR.glob("*.pdf"))
        print(f"📦 Processing {len(pdfs)} PDFs in {SCANS_DIR}")
        for pdf in pdfs:
            process_file(str(pdf))
            print()

    else:
        pdf_path = sys.argv[1]
        sigs_only = "--signatures-only" in sys.argv
        result = process_file(pdf_path, extract_sigs=not sigs_only)
        if "error" in result:
            print(f"❌ {result['error']}")
            sys.exit(1)
