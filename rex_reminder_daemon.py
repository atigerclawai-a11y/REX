#!/usr/bin/env python3
"""
REX Chairman Reminder Daemon
==============================
Runs every 5 minutes via launchd.
Checks for upcoming personal events with reminders due,
fires Telegram messages to Kato, marks them sent.

All reminders are chairman-only — no other user ever sees them.
"""

import sys
import json
import logging
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

REX_DIR = Path(__file__).parent
LOG_PATH = REX_DIR / "logs" / "reminders.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_PATH), mode="a"),
    ],
)
log = logging.getLogger("rex-reminders")

REX_API  = "http://localhost:8000"
TG_CONFIG = REX_DIR / "rex_rexxie_telegram_config.json"  # uses Rexxie bot — private


def _load_tg():
    if TG_CONFIG.exists():
        try:
            d = json.loads(TG_CONFIG.read_text())
            return d.get("bot_token",""), d.get("owner_chat_id", 0)
        except Exception:
            pass
    return "", 0


def _send_telegram(token: str, chat_id: int, text: str) -> bool:
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()).get("ok", False)
    except Exception as e:
        log.error(f"Telegram send failed: {e}")
        return False


def _api_get(path: str):
    req = urllib.request.Request(f"{REX_API}{path}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        log.error(f"API GET {path} failed: {e}")
        return None


def _api_post(path: str, body: dict = None):
    payload = json.dumps(body or {}).encode()
    req = urllib.request.Request(f"{REX_API}{path}", data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        log.error(f"API POST {path} failed: {e}")
        return None


def check_and_fire():
    log.info("Checking for pending reminders…")

    data = _api_get("/api/chairman/reminders/pending")
    if not data:
        log.warning("REX backend unreachable — skipping")
        return

    reminders = data.get("reminders", [])
    if not reminders:
        log.info("No reminders due")
        return

    token, chat_id = _load_tg()
    log.info(f"Found {len(reminders)} reminder(s) to fire")

    for r in reminders:
        title     = r.get("title", "Reminder")
        notes     = r.get("notes", "")
        date      = r.get("event_date", "")
        time_str  = r.get("event_time", "")
        event_id  = r.get("id")

        # Format time nicely
        time_label = ""
        if time_str:
            try:
                h, m = map(int, time_str.split(":"))
                suffix = "AM" if h < 12 else "PM"
                h12 = h if 1 <= h <= 12 else (12 if h == 0 else h - 12)
                time_label = f" at {h12}:{m:02d} {suffix}"
            except Exception:
                time_label = f" at {time_str}"

        # Build message
        msg = f"🐢 <b>Reminder — {title}</b>\n"
        msg += f"📅 {date}{time_label}\n"
        if notes:
            msg += f"\n{notes}\n"
        msg += f"\n<i>— Rexxie</i>"

        ok = _send_telegram(token, chat_id, msg)
        if ok:
            log.info(f"Reminder fired: {title} ({event_id})")
            _api_post(f"/api/chairman/reminders/{event_id}/mark-sent")
        else:
            log.error(f"Failed to send reminder: {title}")


if __name__ == "__main__":
    check_and_fire()
