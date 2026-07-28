#!/usr/bin/env python3
"""
rex_scan_watcher_run.py — Standalone one-shot menu scan watcher
===============================================================
Invoked by launchd every 5 minutes via com.rex.menu-scan-watcher.plist.
Runs one IMAP poll pass and exits cleanly.

This makes the scan watcher INDEPENDENT of the REX backend — emails
get downloaded even if the backend is down, crashed, or restarting.
The shared state file (menu_scan_watcher_state.json) prevents double-
processing if the backend's internal watcher also runs.

Auth: ~/.rex_gmail_imap.json (App Password, never OAuth)
"""
import logging
import sys
from pathlib import Path

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_PATH = Path.home() / "Desktop/REX/logs/menu_scan_watcher.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("rex.scan_watcher_run")

# ── Path setup ─────────────────────────────────────────────────────────────────
REX_DIR     = Path(__file__).resolve().parent
BACKEND_DIR = REX_DIR / "backend"
sys.path.insert(0, str(REX_DIR))
sys.path.insert(0, str(BACKEND_DIR))

# ── Run one poll ───────────────────────────────────────────────────────────────
try:
    from rex_menu_scan_watcher import _poll_once, is_configured
    if not is_configured():
        logger.error("IMAP not configured — missing ~/.rex_gmail_imap.json or app_password")
        sys.exit(1)
    logger.info("▶ Starting one-shot IMAP poll")
    _poll_once()
    logger.info("✅ Poll complete")
except Exception as e:
    logger.error(f"❌ Poll failed: {e}", exc_info=True)
    sys.exit(1)
