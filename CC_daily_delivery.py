#!/usr/bin/env python3
"""
CC_daily_delivery.py — GOJ Daily PDF Delivery Orchestrator
══════════════════════════════════════════════════════════
Runs the Drive sync then calls generate_tomorrow.py at the right times.

Usage (via launchd or manually):
  python3 CC_daily_delivery.py --time morning      # 7:30 AM: sync + signin sheets
  python3 CC_daily_delivery.py --time sheets       # 10:30 AM: sync + kitchen/distribution
  python3 CC_daily_delivery.py --time signin       # 3:15 PM: signin sheets (no sync)
  python3 CC_daily_delivery.py --time evening      # 9:00 PM: text summary to Telegram

Log: ~/Desktop/REX/logs/daily_delivery.log
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
HOME        = Path.home()
REX_DIR     = HOME / "Desktop" / "REX"
LOG_DIR     = REX_DIR / "logs"
GOJ_DIR     = HOME / "Documents" / "goj files"
DB_PATH     = GOJ_DIR / "dashboard" / "auth_tracker.db"

# generate_tomorrow.py lives here
GENERATE_SCRIPT = GOJ_DIR / "dashboard" / "generate_tomorrow.py"

# Python venv for production (launchd can't use ~/Desktop due to TCC)
VENV_PYTHON = HOME / ".rex-venv" / "bin" / "python3"

# Telegram
TG_CHAT_ID  = 5587703834

LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "daily_delivery.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("daily_delivery")


# ── Token loader ───────────────────────────────────────────────────────────────

def _load_token() -> str:
    """Load REXXIE_BOT_TOKEN from env or .env file."""
    # 1. Environment variable
    tok = os.environ.get("REXXIE_BOT_TOKEN", "")
    if tok:
        return tok
    # 2. ~/Documents/goj files/.env
    env_path = GOJ_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("REXXIE_BOT_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                tok = line.split("=", 1)[1].strip().strip('"').strip("'")
    return tok


def _tg_send(text: str, token: str) -> bool:
    """Send a Telegram message to Chairman."""
    if not token:
        log.warning("No Telegram token — message not sent")
        return False
    try:
        url  = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": TG_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }).encode()
        with urllib.request.urlopen(
            urllib.request.Request(url, data=data), timeout=15
        ) as r:
            return r.status == 200
    except Exception as e:
        log.warning(f"Telegram send failed: {e}")
        return False


# ── Drive sync ─────────────────────────────────────────────────────────────────

def run_sync() -> bool:
    """Drive data sync DISABLED (Kato law 2026-08-05).

    Google Drive is OUTPUT-ONLY — never a source of truth. Attendance truth
    = LIVE Carecenta, menus = OCR pipeline. This function no longer runs
    CC_drive_sync_data.py and returns True (no-op success) so downstream
    delivery steps continue unaffected.
    """
    log.warning("Drive sync SKIPPED (Kato law 2026-08-05 — Drive is output-only, not a source of truth)")
    return True


# ── PDF generation ─────────────────────────────────────────────────────────────

def run_generate(day: str, mode: str) -> bool:
    """
    Run generate_tomorrow.py with --day, --mode, and --send.
    Returns True on success. Sends Telegram alert on failure.
    """
    if not GENERATE_SCRIPT.exists():
        log.error(f"generate_tomorrow.py not found at {GENERATE_SCRIPT}")
        return False

    cmd = [
        str(VENV_PYTHON),
        str(GENERATE_SCRIPT),
        "--day", day,
        "--mode", mode,
        "--send",
    ]
    log.info(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=600,
            cwd=str(GENERATE_SCRIPT.parent),
        )
        if result.stdout:
            log.info(f"[generate stdout] {result.stdout.strip()[:1000]}")
        if result.stderr:
            log.warning(f"[generate stderr] {result.stderr.strip()[:1000]}")

        if result.returncode != 0:
            log.error(f"generate_tomorrow.py exited {result.returncode}")
            token = _load_token()
            _tg_send(
                f"⚠️ <b>GOJ PDF generation FAILED</b>\n"
                f"Mode: {mode} | Day: {day}\n"
                f"Exit code: {result.returncode}\n"
                f"<code>{result.stderr.strip()[-300:]}</code>",
                token,
            )
            return False

        log.info("PDF generation complete")
        return True
    except subprocess.TimeoutExpired:
        log.error("generate_tomorrow.py timed out after 10 minutes")
        token = _load_token()
        _tg_send(
            f"⚠️ <b>GOJ PDF generation TIMED OUT</b>\nMode: {mode} | Day: {day}",
            token,
        )
        return False
    except Exception as e:
        log.error(f"generate_tomorrow.py error: {e}")
        token = _load_token()
        _tg_send(
            f"⚠️ <b>GOJ PDF generation ERROR</b>\nMode: {mode} | Day: {day}\n{e}",
            token,
        )
        return False


# ── Evening summary ────────────────────────────────────────────────────────────

def send_evening_summary() -> bool:
    """
    Send a brief text summary of today's attendance count to Telegram.
    Reads from auth_tracker.db. No PDF generated.
    """
    import sqlite3

    today = date.today()
    day_codes = ["M", "T", "W", "TH", "F", "Sa", "Su"]
    day_col_map = {
        "M": "day_M_actual", "T": "day_T_actual", "W": "day_W_actual",
        "TH": "day_TH_actual", "F": "day_F_actual", "Sa": "day_Su_actual",
        "Su": "day_Su_actual",
    }
    day_code = day_codes[today.weekday()]
    col = day_col_map.get(day_code)

    s1_count, s2_count = 0, 0
    if col and DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            s1_count = conn.execute(
                f"SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=1"
            ).fetchone()[0]
            s2_count = conn.execute(
                f"SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=2"
            ).fetchone()[0]
            conn.close()
        except Exception as e:
            log.warning(f"DB query for evening summary failed: {e}")

    day_name = today.strftime("%A")
    date_str = today.strftime("%B %d, %Y")
    total = s1_count + s2_count
    msg = (
        f"📋 <b>GOJ Evening Rundown — {day_name}, {date_str}</b>\n"
        f"Shift 1: {s1_count} clients\n"
        f"Shift 2: {s2_count} clients\n"
        f"Total today: {total}\n"
        f"No decisions necessary."
    )

    token = _load_token()
    ok = _tg_send(msg, token)
    if ok:
        log.info(f"Evening summary sent: S1={s1_count} S2={s2_count}")
    else:
        log.error("Evening summary failed to send")
    return ok


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="GOJ Daily PDF Delivery")
    parser.add_argument(
        "--time",
        required=True,
        choices=["morning", "sheets", "signin", "evening"],
        help=(
            "morning=7:30AM signin sheets for tomorrow | "
            "sheets=10:30AM kitchen+dist for tomorrow | "
            "signin=3:15PM kitchen+dist for tomorrow (afternoon refresh) | "
            "evening=9PM text summary"
        ),
    )
    args = parser.parse_args()

    log.info("=" * 60)
    log.info(f"CC_daily_delivery.py --time {args.time} starting at {datetime.now().isoformat()}")

    if args.time == "morning":
        # 7:30 AM: sync Drive, then generate sign-in sheets for tomorrow
        ok = run_sync()
        if not ok:
            log.warning("Drive sync failed — attempting generation with existing data")
        run_generate(day="tomorrow", mode="signin")

    elif args.time == "sheets":
        # 10:30 AM: sync Drive, then generate kitchen+distribution for tomorrow
        ok = run_sync()
        if not ok:
            log.warning("Drive sync failed — attempting generation with existing data")
        run_generate(day="tomorrow", mode="distribution")

    elif args.time == "signin":
        # 3:15 PM: sync Drive, then re-send kitchen+distribution for tomorrow (afternoon refresh)
        # catches any day changes made after the 10:30 AM run
        ok = run_sync()
        if not ok:
            log.warning("Drive sync failed — attempting generation with existing data")
        run_generate(day="tomorrow", mode="distribution")

    elif args.time == "evening":
        # 9:00 PM: text summary to Telegram, no PDFs
        send_evening_summary()

    log.info(f"CC_daily_delivery.py --time {args.time} finished")
    sys.exit(0)


if __name__ == "__main__":
    main()
