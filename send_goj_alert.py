#!/usr/bin/env python3
"""
Send the GOJ 10 AM handoff alert to the Rexxie Telegram chat.

Run this from your Mac (where api.telegram.org is reachable):
    python3 ~/Desktop/REX/send_goj_alert.py

It was generated because the 10 AM scheduled task on 2026-05-21 could not
reach api.telegram.org from its sandbox. See GOJ_10AM_run_2026-05-21.md.
"""
import json, os, urllib.request, urllib.parse, sys

CFG = os.path.expanduser("~/Desktop/REX/rex_rexxie_telegram_config.json")
cfg = json.load(open(CFG))
token = cfg["bot_token"]
chat_id = cfg["owner_chat_id"]

msg = """\U0001F37D <b>GOJ Kitchen &amp; Distribution — Friday, May 22, 2026</b>

⚠️ <b>Kitchen &amp; distribution sheets could NOT be generated.</b>

Clients expected Friday: 206 (Shift 1: 100 | Shift 2: 106)
Menu orders on file for May 22: <b>0</b>

generate_tomorrow.py ran without error, but kitchen/distribution sheets are built from menu-order data and there is none for the week of May 18–25. The latest menu data in the database is the week of May 4.

<b>Why:</b> The filled-out menus for May 18–25 were scanned and emailed (goj3152.scans → Allen, May 15, e.g. doc00410720260515113734.pdf), forwarded to you May 19, but not yet ingested into the database — GOJ_Menu_Orders.json is still empty.

<b>Action needed:</b> Run the menu-ingestion pipeline on the May 18-25 menu scans, then re-run generate_tomorrow.py for kitchen + distribution.

✅ Sign-in &amp; driver sheets for Friday generated fine — they go out at 3 PM as scheduled.

ℹ️ dietary_notes check: 0 of 206 filled (column unused system-wide; menu data lives in client_menus)."""

data = urllib.parse.urlencode({
    "chat_id": chat_id,
    "text": msg,
    "parse_mode": "HTML",
    "disable_web_page_preview": "true",
}).encode()

url = f"https://api.telegram.org/bot{token}/sendMessage"
try:
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=30) as r:
        print("HTTP", r.status)
        print(r.read().decode("utf-8", "replace")[:600])
except urllib.error.HTTPError as e:
    print("HTTPError", e.code, e.read().decode("utf-8", "replace")[:600])
    sys.exit(1)
except Exception as e:
    print("ERROR", repr(e))
    sys.exit(1)
