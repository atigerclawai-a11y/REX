#!/usr/bin/env python3
"""
CC_telegram_attendance_bot.py — GOJ Staff Clock-In/Out via Telegram
=====================================================================

Minimal polling bot. One command: /clockin toggles clock-in/out.
Maps Telegram user IDs → staff MACs. Calls CC_attendance :8101.

Setup:
  1. Create bot with @BotFather → get token
  2. Set GOJ_ATTENDANCE_TOKEN in ~/.hermes-cloud/.env
  3. Staff send /start to register their Telegram ID
  4. Admin maps Telegram IDs → staff MACs in config below

Run:
  python3 CC_telegram_attendance_bot.py             # foreground polling
  python3 CC_telegram_attendance_bot.py --once      # process + exit
"""
from __future__ import annotations

import json, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
REX  = HOME / "Desktop" / "REX"
STATE_FILE = REX / ".attendance_bot_state.json"
LOG_FILE   = REX / "logs" / "attendance_bot.log"
API_BASE   = "http://127.0.0.1:8101"

# ── staff mapping: Telegram user ID → staff MAC ──────────────────────
# Fill in once staff message the bot (their ID shows in log)
STAFF_MAP: dict[int, str] = {
    # 123456789: "vlads_mac",       # Vladimir
    # 987654321: "mykhailo_mac",    # Mykhailo
    # 555555555: "frontdesk_mac",   # Front Desk
    # 111111111: "kato_mac",        # Kato
}

# ── helpers ───────────────────────────────────────────────────────────

def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} | {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

def tg_api(method: str, data: dict | None = None) -> dict:
    token = os.getenv("GOJ_ATTENDANCE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("GOJ_ATTENDANCE_TOKEN not set")
    url = f"https://api.telegram.org/bot{token}/{method}"
    if data:
        req = urllib.request.Request(url, json.dumps(data).encode(),
                                     {"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def send_message(chat_id: int, text: str) -> None:
    try:
        tg_api("sendMessage", {"chat_id": chat_id, "text": text})
    except Exception as e:
        log(f"sendMessage error: {e}")

def clock_toggle(mac: str) -> dict:
    """POST /api/event → toggle clock-in/out. Returns {mac, status, session_id}."""
    data = json.dumps({"mac": mac}).encode()
    req = urllib.request.Request(f"{API_BASE}/api/event", data,
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())

def get_attendance() -> list[dict]:
    """GET /api/attendance/today → list of staff statuses."""
    with urllib.request.urlopen(f"{API_BASE}/api/attendance/today", timeout=5) as r:
        return json.loads(r.read())

def get_staff_list() -> list[dict]:
    with urllib.request.urlopen(f"{API_BASE}/api/staff", timeout=5) as r:
        return json.loads(r.read())

# ── command handlers ──────────────────────────────────────────────────

def handle_clockin(msg: dict) -> None:
    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]
    first = msg["from"].get("first_name", "Staff")

    mac = STAFF_MAP.get(user_id)
    if not mac:
        send_message(chat_id,
            f"❌ {first}, your Telegram ID ({user_id}) is not mapped to a staff MAC.\n"
            f"Ask Kato to add: STAFF_MAP[{user_id}] = \"your_mac\"")
        return

    try:
        result = clock_toggle(mac)
        new_status = result.get("status", result.get("new_status", "?"))
        name = result.get("name", first)
        if new_status == "in":
            send_message(chat_id, f"🟢 {name} clocked IN")
        else:
            sesh = result.get("session_id", "")[:8]
            send_message(chat_id, f"🔴 {name} clocked OUT  [{sesh}]")
    except Exception as e:
        log(f"clockin error for {user_id}: {e}")
        send_message(chat_id, f"⚠️ Clock-in failed — is the attendance server running?")

def handle_status(msg: dict) -> None:
    chat_id = msg["chat"]["id"]
    try:
        entries = get_attendance()
        if not entries:
            send_message(chat_id, "📋 No clock-ins today yet.")
            return
        lines = ["📋 *Today's Attendance*", ""]
        for e in entries:
            name = e.get("name", "?")
            status = e.get("status", "?")
            icon = "🟢" if status == "in" else "🔴"
            lines.append(f"{icon} {name} — {status}")
        send_message(chat_id, "\n".join(lines))
    except Exception as e:
        log(f"status error: {e}")
        send_message(chat_id, "⚠️ Could not fetch attendance.")

def handle_start(msg: dict) -> None:
    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]
    first = msg["from"].get("first_name", "Staff")
    send_message(chat_id,
        f"👋 Hi {first}! Your Telegram ID is `{user_id}`.\n\n"
        f"Commands:\n"
        f"/clockin — toggle clock-in/out\n"
        f"/status  — today's attendance\n"
        f"/help    — this message")

def handle_help(msg: dict) -> None:
    send_message(msg["chat"]["id"],
        "🕐 *GOJ Staff Attendance Bot*\n\n"
        "/clockin — clock in or out (toggle)\n"
        "/status  — who's here today\n"
        "/help    — this message")

# ── main loop ─────────────────────────────────────────────────────────

COMMANDS = {
    "/clockin": handle_clockin,
    "/start":   handle_start,
    "/status":  handle_status,
    "/help":    handle_help,
}

def process_update(update: dict) -> None:
    msg = update.get("message")
    if not msg:
        return
    text = (msg.get("text") or "").strip()
    # Extract command (strip @botname suffix if present)
    cmd = text.split()[0].split("@")[0].lower() if text else ""
    handler = COMMANDS.get(cmd)
    if handler:
        try:
            handler(msg)
        except Exception as e:
            log(f"handler {cmd} error: {e}")
    elif text and text.startswith("/"):
        send_message(msg["chat"]["id"],
            f"Unknown command. Try /clockin, /status, or /help.")

def load_state() -> int:
    try:
        return json.loads(STATE_FILE.read_text()).get("last_update_id", 0)
    except Exception:
        return 0

def save_state(update_id: int) -> None:
    STATE_FILE.write_text(json.dumps({"last_update_id": update_id}))

def run_once() -> None:
    offset = load_state() + 1
    try:
        result = tg_api("getUpdates", {"offset": offset, "timeout": 10})
    except Exception as e:
        log(f"getUpdates error: {e}")
        return

    for update in result.get("result", []):
        process_update(update)
        uid = update.get("update_id", 0)
        if uid >= offset:
            offset = uid + 1
    save_state(offset)

def run_forever() -> None:
    log("Attendance bot polling started")
    while True:
        try:
            run_once()
        except Exception as e:
            log(f"loop error: {e}")
            time.sleep(5)
        time.sleep(2)

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()

    # Load env
    try:
        from dotenv import load_dotenv as _load
        _load(HOME / ".hermes-cloud" / ".env", override=False)
    except Exception:
        pass

    if not os.getenv("GOJ_ATTENDANCE_TOKEN", "").strip():
        print("❌ GOJ_ATTENDANCE_TOKEN not set in ~/.hermes-cloud/.env", file=sys.stderr)
        sys.exit(1)

    REX.joinpath("logs").mkdir(parents=True, exist_ok=True)

    if args.once:
        run_once()
    else:
        run_forever()
