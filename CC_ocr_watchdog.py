#!/usr/bin/env python3
"""
CC_ocr_watchdog.py — GHS OCR Engine Health Monitor
Engine 2: Gmail IMAP (pulls sign-in PDFs for Drive OCR pipeline)
Engine 3: Paperless-NGX (office Mac Docker container)
Auto-heals what it can. Notifies Kato via Telegram on unrecoverable failure.
Silent on healthy state or successful auto-heal.

Usage:
  python3 CC_ocr_watchdog.py          # check + auto-heal + alert if broken
  python3 CC_ocr_watchdog.py --status # print status without sending any alert
"""

import subprocess, json, sys, logging, imaplib, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN  = "8980921667:AAFhwsVvYAXG8hO4Z6Xl--n4gmo9VZDaPu4"  # @goldhealth_rexxie_bot (was @RexOfGold_bot placeholder)
CHAT_ID    = "5587703834"   # Kato
IMAP_CONFIG = Path.home() / ".rex_gmail_imap.json"
PAPERLESS_TOKEN = "51420bd5c9d61208b331d09a528019d50a70520b"
PAPERLESS_URL   = "http://localhost:8010/api/"
LOG_PATH   = Path.home() / "Desktop/REX/logs/ocr_watchdog.log"

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("ocr_watchdog")


# ── Telegram ──────────────────────────────────────────────────────────────────
def notify(msg: str):
    try:
        data = json.dumps({"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data=data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            if r.status != 200:
                log.warning(f"Telegram returned {r.status}")
    except Exception as e:
        log.error(f"Telegram notify failed: {e}")


# ── Engine 2: Gmail IMAP (Drive OCR pipeline) ────────────────────────────────
def check_drive_ocr() -> tuple:
    """Check Gmail IMAP — used by OCR pipeline to fetch sign-in PDFs."""
    if not IMAP_CONFIG.exists():
        return False, "IMAP config missing (~/.rex_gmail_imap.json)", False
    try:
        cfg = json.loads(IMAP_CONFIG.read_text())
        imap = imaplib.IMAP4_SSL(cfg['imap_host'], cfg['imap_port'], timeout=10)
        imap.login(cfg['email'], cfg['app_password'])
        status, data = imap.select('INBOX')
        if status != 'OK':
            imap.logout()
            return False, "IMAP INBOX select failed", False
        imap.logout()
        return True, "IMAP connected — ready for OCR pipeline", False
    except Exception as e:
        return False, f"IMAP failed: {str(e)[:80]}", False


# ── Engine 3: Paperless-NGX (office Mac) ─────────────────────────────────────
def check_paperless() -> tuple:
    """Check Paperless-NGX on office Mac Docker."""
    try:
        req = urllib.request.Request(
            PAPERLESS_URL,
            headers={"Authorization": f"Token {PAPERLESS_TOKEN}"}
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            return True, "Paperless responding OK", False
    except urllib.error.HTTPError as e:
        if e.code in (302, 301):
            return True, "Paperless up (redirect)", False
        return False, f"Paperless HTTP {e.code}", False
    except urllib.error.URLError as e:
        return False, f"Paperless unreachable: {str(e.reason)[:60]}", False
    except OSError as e:
        return False, f"Paperless connection error: {str(e)[:60]}", False


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    status_only = "--status" in sys.argv
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    results = {}

    # Engine 3: Paperless — DEAD (Docker not on office Mac, service killed)
    # Skipping check to avoid false alerts. Re-enable if Paperless is reinstated.
    results["paperless"] = {"ok": True, "msg": "SKIPPED (service decommissioned)", "fixed": False}
    log.info("Engine 3 SKIPPED: Paperless decommissioned — Docker not on office Mac")

    # Engine 2: Drive OCR (IMAP)
    d_ok, d_msg, d_fixed = check_drive_ocr()
    results["drive_ocr"] = {"ok": d_ok or d_fixed, "msg": d_msg, "fixed": d_fixed}
    if d_fixed:
        log.info(f"Engine 2 auto-healed: {d_msg}")
    elif d_ok:
        log.info(f"Engine 2 OK: {d_msg}")
    else:
        log.warning(f"Engine 2 BROKEN: {d_msg}")

    issues = []
    healed = []
    # Engine 3 (Paperless) skipped — service decommissioned
    if d_fixed:
        healed.append(f"Engine 2 (Drive OCR): {d_msg}")
    elif not d_ok:
        issues.append(f"Engine 2 (Drive OCR): {d_msg}")

    if status_only:
        print(json.dumps(results, indent=2))
        sys.exit(0 if not issues else 1)

    if issues:
        lines = [f"⚠️ *OCR Watchdog* `{ts}`", "", "*Needs manual fix:*"]
        for i in issues:
            lines.append(f"• {i}")
        if healed:
            lines += ["", "*Auto-healed this run:*"]
            for h in healed:
                lines.append(f"✅ {h}")
        notify("\n".join(lines))
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
