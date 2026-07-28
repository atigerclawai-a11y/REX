"""
OCR attendance staging + promotion — VERIFIED against a copy of the canonical
auth_tracker.db on 2026-07-02 (registry -> ingest_run -> staged_rows -> review_queue,
and confidence-gated promotion into attendance_log).

Replaces the stale write path in CC_ocr_pipeline.py:write_to_db (which used
non-existent columns). Confidence-gated to satisfy the PHI review gate:
  - row_confidence >= AUTO_FLOOR  -> auto-promote to attendance_log (source='ocr_auto')
  - below the floor               -> held in attendance_review_queue for human approve
"""
import sqlite3, json, hashlib, os
from datetime import datetime, date

import os as _os
# rows at/above this confidence auto-enter attendance_log; below waits for review.
# Set OCR_AUTO_FLOOR=2.0 for a fully-supervised run (nothing auto-promotes; everything
# stages into the review queue for human approval).
AUTO_FLOOR = float(_os.environ.get("OCR_AUTO_FLOOR", "0.85"))


def _sha(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return hashlib.sha256((path or "").encode()).hexdigest()


def stage_attendance(conn, source_file, clients, *, log_date=None, day_key="", shift=0,
                     classification="signin_sheet", doc_confidence=0.0):
    """file registry -> ingest run -> staged rows (+ review queue for low-confidence)."""
    cur = conn.cursor(); now = datetime.now().isoformat()
    log_date = log_date or date.today().isoformat()
    sha = _sha(source_file)
    row = cur.execute("SELECT id FROM goj_file_registry WHERE sha256_hash=?", (sha,)).fetchone()
    if row:
        registry_id = row[0]
    else:
        cur.execute(
            "INSERT INTO goj_file_registry (source_type, original_filename, stored_path, "
            "sha256_hash, classification, confidence, status, created_at, updated_at) "
            "VALUES ('ocr', ?, ?, ?, ?, ?, 'ingested', ?, ?)",
            (os.path.basename(source_file or ""), source_file, sha, classification, doc_confidence, now, now))
        registry_id = cur.lastrowid
    cur.execute(
        "INSERT INTO attendance_ingest_runs (registry_id, source_pdf, source_path, log_date, "
        "day_key, shift, classification, confidence, total_pages, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'staged', ?)",
        (registry_id, os.path.basename(source_file or ""), source_file, log_date, day_key,
         shift, classification, doc_confidence, now))
    run_id = cur.lastrowid
    staged = queued = 0
    for i, c in enumerate(clients):
        name = (c.get("name") or "").strip()
        if not name:
            continue
        conf = float(c.get("confidence", 0.0) or 0.0)
        review = 0 if conf >= AUTO_FLOOR else 1
        rj = json.dumps(c, ensure_ascii=False)
        cur.execute(
            "INSERT INTO attendance_staged_rows (registry_id, run_id, log_date, day_key, shift, "
            "client_name, plan, tr_ntr, time_in, signature_present, row_confidence, review_required, "
            "review_reason, row_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (registry_id, run_id, log_date, day_key, shift, name, c.get("plan", ""), c.get("tr", ""),
             c.get("time_in", ""), c.get("signature", "unknown"), conf, review,
             "" if not review else "low_confidence", rj, now))
        staged += 1
        if review:
            cur.execute(
                "INSERT INTO attendance_review_queue (registry_id, run_id, log_date, day_key, shift, "
                "row_number, client_name, reason, row_confidence, row_json, status, created_at) "
                "VALUES (?,?,?,?,?,?,?,'low_confidence',?,?,'pending',?)",
                (registry_id, run_id, log_date, day_key, shift, i + 1, name, conf, rj, now))
            queued += 1
    return {"registry_id": registry_id, "run_id": run_id, "staged": staged, "review_queued": queued}


def promote_staged(conn, run_id, *, auto_only=True):
    """Promote staged rows into attendance_log (dashboard reads this). Idempotent.
    auto_only=True promotes only confidence-passed rows; approvals call with auto_only=False per row."""
    cur = conn.cursor(); promoted = 0
    q = ("SELECT log_date, day_key, shift, client_name, plan, tr_ntr "
         "FROM attendance_staged_rows WHERE run_id=?" + (" AND review_required=0" if auto_only else ""))
    for ld, dk, sh, name, plan, tr in cur.execute(q, (run_id,)).fetchall():
        cur.execute(
            "INSERT OR IGNORE INTO attendance_log (log_date, day_key, shift, client_name, status, source, note) "
            "VALUES (?, ?, ?, ?, 'present', 'ocr_auto', ?)",
            (ld, dk, sh, name, f"ocr run {run_id} plan={plan} tr={tr}"))
        promoted += cur.rowcount
    return promoted


def stage_menu(conn, source_file, table_data, *, week_start="", day="", doc_confidence=0.0):
    """Log OCR'd menu rows into client_menus (correct schema) + register the doc in menus.
    VERIFIED against a DB copy 2026-07-02. Columns: client_name, week_start, day, salad,
    soup, main, side, confidence, source_pdf, source, created_at."""
    cur = conn.cursor(); now = datetime.now().isoformat()
    cur.execute(
        "INSERT INTO menus (menu_date, week_start, original_filename, file_path, file_type, uploaded_by, uploaded_at, notes) "
        "VALUES (?, ?, ?, ?, 'ocr', 'ocr_pipeline', ?, 'auto-ingested')",
        (day or week_start, week_start, os.path.basename(source_file or ""), source_file, now))
    written = 0
    for table in table_data or []:
        for row in table.get("rows", []):
            name = (row[0] if len(row) > 0 else "").strip()
            if not name:
                continue
            cur.execute(
                "INSERT INTO client_menus (client_name, week_start, day, salad, soup, main, side, "
                "confidence, source_pdf, source, created_at) VALUES (?,?,?,?,?,?,?,?,?, 'ocr', ?)",
                (name, week_start, day,
                 row[1] if len(row) > 1 else "", row[2] if len(row) > 2 else "",
                 row[3] if len(row) > 3 else "", row[4] if len(row) > 4 else "",
                 doc_confidence, os.path.basename(source_file or ""), now))
            written += 1
    return {"menu_rows": written}
