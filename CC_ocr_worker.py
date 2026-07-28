#!/usr/bin/env python3
"""
CC_ocr_worker.py — Processes pending OCR jobs from the queue.

Usage:
    python3 CC_ocr_worker.py                           # process all pending
    python3 CC_ocr_worker.py --mode local              # enqueue+process local mode
    python3 CC_ocr_worker.py --file path/to.pdf --mode hybrid
    python3 CC_ocr_worker.py --status                  # print queue status and exit
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import date, timedelta
from pathlib import Path

REX_DIR   = Path(__file__).resolve().parent
LOCKS_DIR = REX_DIR / "locks"
LOCKS_DIR.mkdir(parents=True, exist_ok=True)

SYSTEM_LOCK  = LOCKS_DIR / "system.lock"
WORKER_LOCK  = LOCKS_DIR / "ocr_worker.lock"
TELEGRAM_CFG = REX_DIR / "rex_rexxie_telegram_config.json"

sys.path.insert(0, str(REX_DIR))


# ── Week-start locked rule (copied verbatim from goj_menu_ocr.py) ──────────────
import logging
from datetime import datetime

log = logging.getLogger("cc-ocr-worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")


def infer_week_start(week_indicator=None, scan_date=None, force_week_start=None):
    """
    LOCKED RULE: menus scanned this week are ALWAYS for next week.
    week_indicator is stored in notes but never used to determine week_start.
    """
    if force_week_start:
        try:
            d = date.fromisoformat(force_week_start)
            if d.weekday() != 0:
                raise ValueError(f"force_week_start must be a Monday, got {d.strftime('%A')}")
            log.info(f"  week_start OVERRIDE applied: {force_week_start}")
            return d.isoformat()
        except ValueError as e:
            log.error(f"  Invalid force_week_start '{force_week_start}': {e} — falling back to auto")

    today = scan_date or date.today()
    days_ahead = 7 - today.weekday()
    if today.weekday() == 0:
        days_ahead = 7
    next_monday = today + timedelta(days=days_ahead)

    if week_indicator:
        log.debug(f"  week_indicator '{week_indicator}' stored in notes — not used for week_start (locked rule)")

    while next_monday <= today:
        log.warning(f"  infer_week_start: {next_monday} not in future — advancing 7 days")
        next_monday += timedelta(days=7)

    return next_monday.isoformat()


# ── Telegram notification ──────────────────────────────────────────────────────

def _notify_telegram(msg: str) -> None:
    try:
        cfg = json.loads(TELEGRAM_CFG.read_text())
        token   = cfg.get("bot_token") or cfg.get("token")
        chat_id = cfg.get("owner_chat_id") or cfg.get("chairman_chat_id")
        if not token or not chat_id:
            return
        payload = json.dumps({"chat_id": chat_id, "text": msg}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass  # silent fail — notifications are best-effort


# ── Lock helpers ───────────────────────────────────────────────────────────────

def _check_system_lock() -> bool:
    """True if system.lock exists and is < 10 min old."""
    if not SYSTEM_LOCK.exists():
        return False
    age = time.time() - SYSTEM_LOCK.stat().st_mtime
    return age < 600


def _acquire_worker_lock() -> bool:
    """True if we acquired the lock. False if another worker is running."""
    if WORKER_LOCK.exists():
        try:
            pid = int(WORKER_LOCK.read_text().strip())
            # Check if that PID is still alive
            os.kill(pid, 0)
            return False  # process alive — another worker running
        except (ProcessLookupError, ValueError):
            pass  # stale lock — safe to overwrite
    WORKER_LOCK.write_text(str(os.getpid()))
    return True


def _release_worker_lock() -> None:
    try:
        WORKER_LOCK.unlink(missing_ok=True)
    except Exception:
        pass


# ── Main processing loop ───────────────────────────────────────────────────────

def _run_job(job: dict) -> tuple[int, int]:
    """Run one OCR job. Returns (inserted, skipped)."""
    pdf_path = job["file_path"]
    mode     = job["mode"]

    if mode == "local":
        from goj_menu_consensus_ocr import process_pdf_local
        result = process_pdf_local(pdf_path)
    else:
        from goj_menu_ocr import process_menu_pdf
        result = process_menu_pdf(pdf_path)

    if result is None:
        return 0, 0

    inserted = result.get("inserted", 0) if isinstance(result, dict) else 0
    skipped  = result.get("skipped",  0) if isinstance(result, dict) else 0
    return inserted, skipped


def process_queue() -> None:
    from CC_ocr_queue import get_next_pending, mark_done, mark_error, reset_stuck_jobs

    reset_stuck_jobs()

    if _check_system_lock():
        log.info("system.lock active — another agent running, exiting")
        return

    if not _acquire_worker_lock():
        log.info("ocr_worker.lock held by live process — exiting")
        return

    try:
        while True:
            job = get_next_pending()
            if not job:
                log.info("Queue empty — worker done")
                break

            pdf_name = Path(job["file_path"]).name
            log.info(f"Processing job {job['id']}: {pdf_name} [{job['mode']}]")
            try:
                inserted, skipped = _run_job(job)
                mark_done(job["id"], inserted, skipped)

                # Sync new rows into pipeline.db so datarex can display them
                try:
                    from CC_sync_to_pipeline import sync_menus_to_pipeline
                    s, sk = sync_menus_to_pipeline()
                    log.info(f"  Pipeline sync: {s} upserted, {sk} skipped")
                except Exception as se:
                    log.warning(f"  Pipeline sync failed (non-fatal): {se}")

                _notify_telegram(
                    f"✅ OCR done: {pdf_name}\n"
                    f"Mode: {job['mode']} | Inserted: {inserted} | Skipped: {skipped}"
                )
                log.info(f"  Job {job['id']} done — inserted={inserted} skipped={skipped}")
            except Exception as e:
                mark_error(job["id"], str(e))
                _notify_telegram(f"❌ OCR error: {pdf_name}\n{str(e)[:200]}")
                log.error(f"  Job {job['id']} error: {e}")
                # Also send the actual PDF page 1 to Telegram so Kato can
                # manually review the unreadable scan.
                try:
                    import importlib.util as _ilu
                    _spec = _ilu.spec_from_file_location(
                        "ocr_fallback",
                        str(Path.home() / "Desktop" / "REX" / "CC_ocr_telegram_fallback.py"),
                    )
                    _ocr_fb = _ilu.module_from_spec(_spec)
                    _spec.loader.exec_module(_ocr_fb)
                    _ocr_fb.flag_for_review(
                        source="menu_ocr_worker",
                        file_path=Path(job["file_path"]),
                        reason=f"OCR engine crashed: {str(e)[:160]}",
                        partial={"job_id": job["id"], "mode": job["mode"]},
                        bot="rex_of_gold",
                    )
                except Exception as _fbe:
                    log.warning(f"  OCR Telegram fallback failed (non-fatal): {_fbe}")
    finally:
        _release_worker_lock()


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="GOJ OCR queue worker")
    parser.add_argument("--file",   help="Enqueue a specific PDF")
    parser.add_argument("--mode",   default="hybrid", choices=["hybrid", "local"],
                        help="OCR mode (default: hybrid)")
    parser.add_argument("--status", action="store_true", help="Print queue status and exit")
    args = parser.parse_args()

    if args.status:
        from CC_ocr_queue import get_queue_status
        status = get_queue_status()
        print("OCR Queue Status:")
        for state, count in sorted(status.items()):
            print(f"  {state:10s}: {count}")
        if not status:
            print("  (empty)")
        return

    if args.file:
        from CC_ocr_queue import enqueue_scan
        job_id = enqueue_scan(args.file, args.mode)
        if job_id:
            log.info(f"Enqueued {args.file} as job {job_id} [{args.mode}]")
        else:
            log.info(f"Already queued/done: {args.file} [{args.mode}]")

    process_queue()


if __name__ == "__main__":
    main()
