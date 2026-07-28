#!/usr/bin/env python3
"""
CC_daily_ocr_loop.py — Daily OCR pipeline with perpetual memory and self-improvement.

Run: source ~/debate-chamber/.venv/bin/activate && python ~/Desktop/REX/CC_daily_ocr_loop.py

Each day:
  1. Fetch new sign-in PDFs from Gmail (skips already-seen IMAP UIDs)
  2. Run OCR pipeline — /tmp fix applied; temp TIFFs go to SAMPLES_DIR
  3. Match names against auth_tracker.db (fuzzy, tunable threshold)
  4. Update CC_ocr_memory.json — corrections, near-matches, unknowns, stats
  5. Self-improve — promote repeated matches, auto-tune threshold
  6. Append structured entry to CC_ocr_log.jsonl
"""

import json, os, sys, imaplib, email, sqlite3, subprocess, tempfile
import datetime
from pathlib import Path
from difflib import SequenceMatcher

try:
    import cv2
    import numpy as np
    from pdf2image import convert_from_path
except ImportError as e:
    sys.exit(f"[FATAL] Missing dependency: {e}\n"
             f"Run: source ~/debate-chamber/.venv/bin/activate")

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR    = Path.home() / "Desktop" / "REX"
SAMPLES_DIR = BASE_DIR / "signin_samples"
MEMORY_PATH = BASE_DIR / "CC_ocr_memory.json"
LOG_PATH    = BASE_DIR / "CC_ocr_log.jsonl"
CREDS_PATH  = Path.home() / ".rex_gmail_imap.json"
DB_PATH     = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
TIFF_DIR    = SAMPLES_DIR   # MUST NOT be /tmp — macOS Leptonica security blocks it

SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

# ── Detection config ───────────────────────────────────────────────────────
DPI              = 150
NAME_COL_START   = 0.0
NAME_COL_END     = 0.40
SIG_COL_START    = 0.72
SIG_COL_END      = 1.0
SIGNED_THRESHOLD = 50
MIN_ROW_H        = 50
MAX_ROW_H        = 120

# ── Learning config ────────────────────────────────────────────────────────
PROMOTION_COUNT  = 3      # fuzzy matches must repeat this many times → correction dict
PROMO_MIN_CONF   = 0.70   # minimum confidence to count toward promotion
THRESHOLD_MIN    = 0.45
THRESHOLD_MAX    = 0.65

# ── Gmail search config ────────────────────────────────────────────────────
SIGNIN_TERMS     = {"sign in", "signin", "sign-in", "sign_in", "attendance"}
EXCLUDE_TERMS    = {"menu", "меню"}
LOOKBACK_DAYS    = 14   # search window for new PDFs

# ══════════════════════════════════════════════════════════════════════════
#  MEMORY
# ══════════════════════════════════════════════════════════════════════════

def _default_memory() -> dict:
    today = str(datetime.date.today())
    return {
        "version": 2,
        "created": today,
        "last_run": None,
        "seen_uids": [],          # IMAP UIDs already inspected (processed or skipped)
        "processed_pdfs": [],     # {filename, uid, date, match_rate}
        "run_history": [],        # per-run stats
        "ocr_corrections": {},    # ocr_text → {client_id, canonical, count, conf_sum, promoted}
        "near_matches": {},       # low-conf matches pending promotion
        "unknown_candidates": {}, # unmatched ocr_text → {count, first_seen, last_seen}
        "fuzzy_threshold": 0.55,
        "threshold_history": [{"date": today, "value": 0.55, "reason": "initial"}],
        "format_anomalies": ["800_doc00474320260601105724.pdf"],
        "totals": {"pdfs": 0, "rows": 0, "matches": 0}
    }


def load_memory() -> dict:
    if MEMORY_PATH.exists():
        with open(MEMORY_PATH) as f:
            mem = json.load(f)
        # Migrate v1 → v2
        if mem.get("version", 1) < 2:
            mem.setdefault("seen_uids", [])
            mem.setdefault("near_matches", {})
            mem.setdefault("totals", {"pdfs": 0, "rows": 0, "matches": 0})
            mem["version"] = 2
        return mem
    print("[MEMORY] No memory file found — starting fresh")
    return _default_memory()


def save_memory(mem: dict):
    mem["last_run"] = str(datetime.date.today())
    MEMORY_PATH.write_text(json.dumps(mem, indent=2, ensure_ascii=False))
    print(f"[MEMORY] Saved → {MEMORY_PATH}")


# ══════════════════════════════════════════════════════════════════════════
#  GMAIL FETCH
# ══════════════════════════════════════════════════════════════════════════

def is_signin_subject(subject: str) -> bool:
    sl = subject.lower()
    return (any(t in sl for t in SIGNIN_TERMS) and
            not any(t in sl for t in EXCLUDE_TERMS))


def fetch_new_pdfs(mem: dict) -> list:
    """Search Gmail for sign-in PDFs not yet in seen_uids. Returns list of dicts."""
    creds = json.loads(CREDS_PATH.read_text())
    seen  = set(str(u) for u in mem["seen_uids"])

    M = imaplib.IMAP4_SSL(creds["imap_host"], creds["imap_port"])
    M.login(creds["email"], creds["app_password"])
    M.select("INBOX")

    since = (datetime.date.today() - datetime.timedelta(days=LOOKBACK_DAYS)
             ).strftime("%d-%b-%Y")

    uid_set = set()
    # Search FROM the GOJ sender — more reliable than SUBJECT search
    for from_addr in ["allen@gardenofjoybrooklyn.com", "gardenofjoybrooklyn.com"]:
        try:
            _, data = M.uid("search", None, f'(FROM "{from_addr}" SINCE "{since}")')
            if data[0]:
                uid_set.update(data[0].split())
        except:
            pass  # Gmail sometimes rejects combined FROM+SINCE, fall through
    
    # Fallback: search by subject terms if FROM+SINCE failed
    if not uid_set:
        for term in ["sign in", "sign-in", "attendance"]:
            _, data = M.uid("search", None, f'(SINCE "{since}" SUBJECT "{term}")')
            if data[0]:
                uid_set.update(data[0].split())

    new_uids = [u for u in sorted(uid_set) if u.decode() not in seen]
    print(f"[FETCH] {len(uid_set)} UIDs in last {LOOKBACK_DAYS}d | "
          f"{len(seen)} already seen | {len(new_uids)} to inspect")

    new_files = []
    for uid_b in new_uids:
        uid = uid_b.decode()
        _, msg_data = M.uid("fetch", uid, "(RFC822)")
        if not msg_data or not msg_data[0]:
            mem["seen_uids"].append(uid)
            continue

        msg     = email.message_from_bytes(msg_data[0][1])
        subject = msg.get("Subject", "")

        # Process ALL PDFs from GOJ sender — menus, rosters, sign-ins, everything
        for part in msg.walk():
            if part.get_content_type() != "application/pdf":
                continue
            fname    = part.get_filename() or f"uid{uid}_attachment.pdf"
            out_path = SAMPLES_DIR / f"{uid}_{fname}"
            if not out_path.exists():
                out_path.write_bytes(part.get_payload(decode=True))
                print(f"  [DL] {out_path.name} ({out_path.stat().st_size // 1024} KB)")
            else:
                print(f"  [EXIST] {out_path.name}")
            new_files.append({"path": out_path, "uid": uid, "subject": subject,
                               "filename": out_path.name})

        mem["seen_uids"].append(uid)

    M.logout()
    print(f"[FETCH] {len(new_files)} new PDF(s) queued for OCR")
    return new_files


# ══════════════════════════════════════════════════════════════════════════
#  PDF → IMAGE PIPELINE
# ══════════════════════════════════════════════════════════════════════════

def pdf_to_rotated_images(pdf_path: Path) -> list:
    """Convert PDF to list of BGR numpy arrays, rotated 90° CCW (portrait→landscape)."""
    pil_pages = convert_from_path(str(pdf_path), dpi=DPI)
    imgs = []
    for pil in pil_pages:
        arr = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        rot = cv2.rotate(arr, cv2.ROTATE_90_COUNTERCLOCKWISE)
        imgs.append(rot)
    return imgs


def detect_rows(img: np.ndarray) -> list:
    """Return list of (top_y, bot_y) row bands from horizontal line detection."""
    gray   = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, bw  = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY_INV)
    w      = img.shape[1]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (w // 2, 1))
    hlines = cv2.morphologyEx(bw, cv2.MORPH_OPEN, kernel)
    ys     = np.where(hlines.sum(axis=1) > w // 3)[0]
    if not len(ys):
        return []

    lines, prev = [], int(ys[0])
    for y in ys[1:]:
        if int(y) - prev > 3:
            lines.append(prev)
        prev = int(y)
    lines.append(prev)

    bands = []
    for i in range(len(lines) - 1):
        h = lines[i+1] - lines[i]
        if MIN_ROW_H <= h <= MAX_ROW_H:
            bands.append((lines[i], lines[i+1]))
    return bands


def best_page(images: list) -> tuple:
    """Return (page_index, image, bands) for the page with the most detected rows."""
    best_idx, best_img, best_bands = 0, images[0], []
    for i, img in enumerate(images):
        bands = detect_rows(img)
        if len(bands) > len(best_bands):
            best_idx, best_img, best_bands = i, img, bands
    return best_idx, best_img, best_bands


def ocr_name(crop_bgr: np.ndarray) -> str:
    """
    Run Tesseract on a BGR crop. Temp TIFF is written to TIFF_DIR — NOT /tmp.
    macOS Leptonica cannot read from /tmp when invoked via subprocess.
    """
    with tempfile.NamedTemporaryFile(suffix=".tiff", delete=False,
                                     dir=str(TIFF_DIR)) as f:
        tiff_path = f.name
    try:
        cv2.imwrite(tiff_path, crop_bgr)
        r = subprocess.run(
            ["tesseract", tiff_path, "stdout", "-l", "rus+eng", "--psm", "6"],
            capture_output=True, text=True
        )
        return r.stdout.strip()
    finally:
        if os.path.exists(tiff_path):
            os.unlink(tiff_path)


def is_signed(img: np.ndarray, top: int, bot: int) -> bool:
    w   = img.shape[1]
    x0  = int(w * SIG_COL_START)
    x1  = int(w * SIG_COL_END)
    roi = img[top:bot, x0:x1]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
    kernel = np.ones((2, 2), np.uint8)
    eroded = cv2.erode(bw, kernel)
    return int(eroded.sum() / 255) > SIGNED_THRESHOLD


# ══════════════════════════════════════════════════════════════════════════
#  DATABASE + FUZZY MATCHING
# ══════════════════════════════════════════════════════════════════════════

def load_clients() -> list:
    """Return [(client_id, full_name), ...] from auth_tracker.db."""
    if not DB_PATH.exists():
        print(f"[WARN] DB not found at {DB_PATH} — matching disabled")
        return []
    conn = sqlite3.connect(str(DB_PATH))
    cur  = conn.cursor()
    try:
        # Inspect schema to find the right columns
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        table  = next((t for t in tables if "client" in t.lower()), tables[0])
        cur.execute(f"PRAGMA table_info({table})")
        cols     = [r[1] for r in cur.fetchall()]
        id_col   = next((c for c in cols if c.lower() in ("id", "client_id")),   cols[0])
        name_col = next((c for c in cols if "name" in c.lower()),                 cols[1])
        cur.execute(f"SELECT {id_col}, {name_col} FROM {table} WHERE {name_col} IS NOT NULL")
        rows = cur.fetchall()
    except Exception as e:
        print(f"[WARN] DB query failed: {e}")
        rows = []
    finally:
        conn.close()
    clients = [(int(r[0]), str(r[1])) for r in rows if r[1]]
    print(f"[DB] {len(clients)} clients loaded from {DB_PATH.name}")
    return clients


def fuzzy_match(ocr_text: str, clients: list, threshold: float) -> tuple:
    """
    Returns (client_id, canonical_name, confidence) or (None, None, best_score).
    Pre-cleans OCR text by stripping row-number prefixes and pipe chars.
    """
    cleaned = ocr_text.strip().lstrip("'|0123456789 ").strip()
    best_id, best_name, best_score = None, None, 0.0
    for cid, cname in clients:
        score = SequenceMatcher(None, cleaned.lower(), cname.lower()).ratio()
        if score > best_score:
            best_score, best_id, best_name = score, cid, cname
    if best_score >= threshold:
        return best_id, best_name, best_score
    return None, None, best_score


# ══════════════════════════════════════════════════════════════════════════
#  LEARNING ENGINE
# ══════════════════════════════════════════════════════════════════════════

def record_match(mem: dict, ocr_text: str, client_id: int,
                 canonical: str, confidence: float):
    """Record a successful fuzzy match into corrections or near_matches."""
    bucket_key = "ocr_corrections" if confidence >= PROMO_MIN_CONF else "near_matches"
    bucket     = mem[bucket_key]
    entry      = bucket.get(ocr_text)
    if entry and entry.get("client_id") == client_id:
        entry["count"]    += 1
        entry["conf_sum"] += confidence
    else:
        bucket[ocr_text] = {
            "client_id": client_id,
            "canonical": canonical,
            "count":     1,
            "conf_sum":  round(confidence, 4),
            "promoted":  False
        }


def record_unknown(mem: dict, ocr_text: str):
    """Track OCR text that had no DB match — potential new/unknown client."""
    today = str(datetime.date.today())
    entry = mem["unknown_candidates"].get(ocr_text)
    if entry:
        entry["count"]    += 1
        entry["last_seen"] = today
    else:
        mem["unknown_candidates"][ocr_text] = {
            "count": 1, "first_seen": today, "last_seen": today
        }


def promote_near_matches(mem: dict) -> list:
    """
    Near-matches seen PROMOTION_COUNT+ times get promoted to ocr_corrections.
    This is the core learning mechanism: repeated low-confidence matches
    eventually become direct lookups, improving speed and accuracy.
    """
    promoted = []
    for ocr_text, entry in list(mem["near_matches"].items()):
        if entry["count"] >= PROMOTION_COUNT:
            avg_conf = entry["conf_sum"] / entry["count"]
            mem["ocr_corrections"][ocr_text] = {
                **entry,
                "promoted":       True,
                "promoted_from":  "near_matches",
                "avg_confidence": round(avg_conf, 4)
            }
            del mem["near_matches"][ocr_text]
            promoted.append(ocr_text)
            print(f"  [PROMOTE] '{ocr_text}' → {entry['canonical']} "
                  f"(seen {entry['count']}×, avg conf {avg_conf:.2f})")
    if not promoted:
        print("  [PROMOTE] Nothing ready for promotion yet")
    return promoted


def auto_tune_threshold(mem: dict):
    """
    Adjust fuzzy threshold based on rolling 7-run match rate.
    < 68% → lower by 0.02 (down to THRESHOLD_MIN)
    > 91% for 14+ runs → raise by 0.01 (up to THRESHOLD_MAX)
    """
    history = mem["run_history"]
    if len(history) < 3:
        return

    recent  = history[-7:]
    rows    = sum(r.get("rows", 0)    for r in recent)
    matches = sum(r.get("matches", 0) for r in recent)
    if rows < 20:
        return

    rate    = matches / rows
    current = mem["fuzzy_threshold"]
    today   = str(datetime.date.today())

    if rate < 0.68 and current > THRESHOLD_MIN:
        new_val = round(current - 0.02, 3)
        mem["fuzzy_threshold"] = new_val
        mem["threshold_history"].append({
            "date": today, "value": new_val,
            "reason": f"match rate {rate:.1%} < 68% over {len(recent)} runs"
        })
        print(f"[TUNE] ↓ Threshold {current} → {new_val}  (match rate {rate:.1%})")

    elif rate > 0.91 and current < THRESHOLD_MAX and len(history) >= 14:
        long_rows    = sum(r.get("rows", 0)    for r in history[-14:])
        long_matches = sum(r.get("matches", 0) for r in history[-14:])
        if long_rows > 0 and long_matches / long_rows > 0.91:
            new_val = round(current + 0.01, 3)
            mem["fuzzy_threshold"] = new_val
            mem["threshold_history"].append({
                "date": today, "value": new_val,
                "reason": f"match rate {rate:.1%} > 91% for 14+ runs"
            })
            print(f"[TUNE] ↑ Threshold {current} → {new_val}  (match rate {rate:.1%})")


# ══════════════════════════════════════════════════════════════════════════
#  PER-PDF PROCESSOR
# ══════════════════════════════════════════════════════════════════════════

def process_pdf(pdf_path: Path, mem: dict, clients: list) -> dict:
    """Run full OCR pipeline on one PDF. Returns stats dict."""
    print(f"\n[PDF] {pdf_path.name}")

    # Skip known anomalous formats
    if pdf_path.name in mem.get("format_anomalies", []):
        print("  [SKIP] Known format anomaly")
        return {"filename": pdf_path.name, "skipped": True, "reason": "format_anomaly"}

    # Convert pages
    try:
        images = pdf_to_rotated_images(pdf_path)
    except Exception as e:
        print(f"  [ERROR] PDF conversion: {e}")
        return {"filename": pdf_path.name, "skipped": True, "reason": str(e)}

    page_idx, img, bands = best_page(images)
    print(f"  Page {page_idx+1}/{len(images)} — {len(bands)} rows "
          f"({img.shape[1]}×{img.shape[0]})")

    # Guard against anomalous format (too few / too many wildly-sized rows)
    if len(bands) < 3:
        print("  [WARN] < 3 rows detected — flagging as format anomaly")
        mem.setdefault("format_anomalies", []).append(pdf_path.name)
        return {"filename": pdf_path.name, "skipped": True, "reason": "too_few_rows"}

    threshold   = mem["fuzzy_threshold"]
    corrections = mem["ocr_corrections"]
    rows_seen = matches = corr_hits = unknowns = 0
    row_log = []

    for top, bot in bands:
        rows_seen += 1
        w         = img.shape[1]
        crop      = img[top:bot, int(w * NAME_COL_START):int(w * NAME_COL_END)]
        ocr_raw   = ocr_name(crop)
        signed    = is_signed(img, top, bot)

        if not ocr_raw:
            row_log.append({"ocr": "", "method": "empty", "signed": signed})
            continue

        # ── 1. Correction dict (direct lookup — no fuzzy needed) ──────────
        if ocr_raw in corrections:
            entry     = corrections[ocr_raw]
            client_id = entry["client_id"]
            canonical = entry["canonical"]
            avg_conf  = entry["conf_sum"] / max(entry["count"], 1)
            entry["count"] += 1                # bump hit counter
            corr_hits += 1
            matches   += 1
            print(f"  [COR] '{ocr_raw}' → {canonical} (direct)")
            row_log.append({"ocr": ocr_raw, "client_id": client_id,
                             "canonical": canonical, "method": "correction",
                             "confidence": round(avg_conf, 3), "signed": signed})
            continue

        # ── 2. Fuzzy match ─────────────────────────────────────────────────
        client_id, canonical, confidence = fuzzy_match(ocr_raw, clients, threshold)

        if client_id is not None:
            matches += 1
            record_match(mem, ocr_raw, client_id, canonical, confidence)
            tag = "HI" if confidence >= PROMO_MIN_CONF else "LO"
            print(f"  [{tag}] '{ocr_raw}' → {canonical} ({confidence:.2f})")
            row_log.append({"ocr": ocr_raw, "client_id": client_id,
                             "canonical": canonical, "method": f"fuzzy_{tag.lower()}",
                             "confidence": round(confidence, 3), "signed": signed})
        else:
            unknowns += 1
            record_unknown(mem, ocr_raw)
            print(f"  [???] '{ocr_raw}'  best={confidence:.2f}")
            row_log.append({"ocr": ocr_raw, "client_id": None,
                             "method": "unknown",
                             "confidence": round(confidence, 3), "signed": signed})

    match_rate = round(matches / rows_seen, 3) if rows_seen else 0.0
    print(f"  → {matches}/{rows_seen} matched ({match_rate:.0%}) | "
          f"{corr_hits} direct | {unknowns} unknown")
    return {
        "filename":   pdf_path.name,
        "pages":      len(images),
        "best_page":  page_idx + 1,
        "rows":       rows_seen,
        "matches":    matches,
        "corr_hits":  corr_hits,
        "unknowns":   unknowns,
        "match_rate": match_rate,
        "row_log":    row_log,
    }


# ══════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════

def main():
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'='*62}")
    print(f"  CC daily OCR loop — {stamp}")
    print(f"{'='*62}")

    mem     = load_memory()
    clients = load_clients()

    # ── 1. Fetch new PDFs from Gmail ──────────────────────────────────────
    new_files = fetch_new_pdfs(mem)

    # ── 2. Process each new PDF ───────────────────────────────────────────
    run_rows = run_matches = run_pdfs = 0
    pdf_results = []

    for finfo in new_files:
        result = process_pdf(Path(finfo["path"]), mem, clients)
        pdf_results.append(result)
        if not result.get("skipped"):
            run_rows    += result.get("rows", 0)
            run_matches += result.get("matches", 0)
            run_pdfs    += 1
            mem["processed_pdfs"].append({
                "filename":   result["filename"],
                "uid":        finfo["uid"],
                "subject":    finfo["subject"],
                "date":       str(datetime.date.today()),
                "match_rate": result.get("match_rate", 0)
            })

    # ── 3. Learning tasks (run even when no new PDFs) ─────────────────────
    print("\n[LEARN] Running learning tasks...")
    promoted = promote_near_matches(mem)
    auto_tune_threshold(mem)

    # ── 4. Update run history & totals ────────────────────────────────────
    today          = str(datetime.date.today())
    run_match_rate = round(run_matches / run_rows, 3) if run_rows else 0.0
    mem["run_history"].append({
        "date":       today,
        "pdfs":       run_pdfs,
        "rows":       run_rows,
        "matches":    run_matches,
        "match_rate": run_match_rate,
        "promoted":   len(promoted),
        "threshold":  mem["fuzzy_threshold"]
    })
    t = mem["totals"]
    t["pdfs"]    += run_pdfs
    t["rows"]    += run_rows
    t["matches"] += run_matches

    save_memory(mem)

    # ── 5. Append to log ──────────────────────────────────────────────────
    log_entry = {
        "ts":          datetime.datetime.now().isoformat(),
        "pdfs":        run_pdfs,
        "rows":        run_rows,
        "matches":     run_matches,
        "match_rate":  run_match_rate,
        "promoted":    len(promoted),
        "threshold":   mem["fuzzy_threshold"],
        "dict_size":   len(mem["ocr_corrections"]),
        "unknowns":    len(mem["unknown_candidates"]),
        "results":     [{k: v for k, v in r.items() if k != "row_log"}
                        for r in pdf_results]
    }
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    # ── 6. Summary ────────────────────────────────────────────────────────
    print(f"\n{'─'*62}")
    print(f"  DONE  {run_pdfs} PDF(s) | {run_matches}/{run_rows} rows ({run_match_rate:.0%})")
    print(f"  Promoted: {len(promoted)} | Threshold: {mem['fuzzy_threshold']}")
    print(f"  Dict: {len(mem['ocr_corrections'])} entries | "
          f"Near: {len(mem['near_matches'])} | "
          f"Unknown: {len(mem['unknown_candidates'])}")
    print(f"  Totals all-time: {t['pdfs']} PDFs | {t['rows']} rows | {t['matches']} matches")
    print(f"{'─'*62}\n")


if __name__ == "__main__":
    main()
