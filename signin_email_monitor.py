#!/usr/bin/env python3
"""signin_email_monitor.py — 'did the email-forwarded scans keep coming?' watchdog.

REPLACES the Drive-folder signin_monitor (Kato 2026-08-05: the sign-in monitor
must use the scanned PDFs Kato forwards through email daily, NOT Drive).

Watches ~/Desktop/REX/signin_intake/ (populated by email_intake_poller every 3m
from forwarded sign-in scan emails). Alerts ONLY when stale — no new scan for
--max-lag operating days. Silent on a healthy day.

Exit 0 = healthy (silent), 1 = alert, 2 = error.
PHI-safe: counts/dates only.
"""
import json
import os
import re
import sys
import datetime as dt
from pathlib import Path

SIGNIN_DIR = Path.home() / "Desktop" / "REX" / "signin_intake"
LOG = Path.home() / "Desktop" / "REX" / "logs" / "signin_email_monitor.log"
LOG.parent.mkdir(parents=True, exist_ok=True)


def arg(flag, default):
    return int(sys.argv[sys.argv.index(flag) + 1]) if flag in sys.argv else default


def is_operating(d):
    return d.weekday() != 5  # GOJ closed Saturdays


def scandate(name):
    m = re.search(r'doc\d{6}(\d{14})', name or "")
    return m.group(1)[:8] if m else None


def logline(msg):
    with open(LOG, "a") as f:
        f.write(f"{dt.datetime.now().isoformat(timespec='seconds')}  {msg}\n")


def telegram(text):
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        return
    import urllib.request
    import urllib.parse
    url = f"https://api.telegram.org/bot{tok}/sendMessage"
    req = urllib.request.Request(
        url, data=urllib.parse.urlencode({"chat_id": chat, "text": text}).encode())
    try:
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        logline(f"telegram failed: {e}")


def main():
    max_lag = arg("--max-lag", 3)
    window = arg("--window", 14)

    if not SIGNIN_DIR.exists():
        logline(f"ERROR: {SIGNIN_DIR} missing")
        print("ERROR: signin_intake dir missing")
        return 2

    pdfs = sorted(SIGNIN_DIR.glob("*.pdf"))
    if not pdfs:
        logline("ALERT: no sign-in scans at all in signin_intake")
        telegram("⚠️ GOJ: no scanned sign-in sheets in email intake — is the forward chain working?")
        print("ALERT: zero sign-in scans in intake")
        return 1

    # newest scan date from doc id (scan timestamp embedded)
    newest = None
    for p in pdfs:
        sd = scandate(p.name)
        if sd and (newest is None or sd > newest):
            newest = sd

    if newest is None:
        # fallback: file mtime
        newest_mt = max(os.path.getmtime(p) for p in pdfs)
        newest = dt.datetime.fromtimestamp(newest_mt).strftime("%Y%m%d")

    newest_d = dt.datetime.strptime(newest, "%Y%m%d").date()
    today = dt.date.today()
    lag_days = 0
    probe = today
    while lag_days <= max_lag + window and probe > newest_d:
        if is_operating(probe):
            lag_days += 1
        probe -= dt.timedelta(days=1)

    logline(f"newest scan {newest} ({len(pdfs)} pdfs), lag {lag_days} operating days")
    if lag_days > max_lag:
        telegram(f"⚠️ GOJ sign-in scans STALE: newest {newest}, {lag_days} operating days without a forwarded scan")
        print(f"ALERT: newest scan {newest}, {lag_days} operating days stale")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
