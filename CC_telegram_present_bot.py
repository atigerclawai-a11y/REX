#!/usr/bin/env python3
"""
CC_telegram_present_bot.py — Telegram → present-mark bridge
============================================================

Listens for /present and /absent commands on @GojAttendance_bot (or whichever
Telegram bot is configured) and writes the result to attendance_log via the
unified /goj-live/present-mark endpoint. This is T2.1 Option B in Kato's
"all four" present-mark strategy.

Commands the bot understands (case-insensitive, accepts shift 1 or 2):

    /present Adyan Ludmila          → mark present, shift 1, today
    /present Adyan Ludmila 2        → shift 2
    /absent Brodskaya Lidiya sick   → mark absent with reason "sick"
    /list                            → today's present list
    /help                            → short usage

Fuzzy match: if no exact name match in `clients`, try case-insensitive +
substring + last-name match. Returns "did you mean X?" with up to 3
suggestions when ambiguous.

Auth: only chat IDs in TELEGRAM_ALLOWED_USERS (comma-separated) may use the
bot. Everyone else gets a polite refusal.

Run:
    python3 CC_telegram_present_bot.py            # foreground polling loop
    python3 CC_telegram_present_bot.py --once     # process pending updates and exit

State: ~/Desktop/REX/.telegram_present_bot_state.json (last seen update_id)
Log:   ~/Desktop/REX/logs/telegram_present_bot.log
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Load tokens from hermes-cloud env
try:
    from dotenv import load_dotenv as _load
    _load(os.path.expanduser("~/.hermes-cloud/.env"), override=False)
except Exception:
    pass

HOME = Path.home()
REX  = HOME / "Desktop" / "REX"
LOG_DIR = REX / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = REX / ".telegram_present_bot_state.json"
DB_PATH    = HOME / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
PRESENT_URL = "http://127.0.0.1:8000/goj-live/present-mark"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "telegram_present_bot.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("present_bot")

# ── Config ────────────────────────────────────────────────────────────────────

def _bot_token() -> Optional[str]:
    # Prefer the attendance-specific bot if its env var exists; fall back to the
    # general TELEGRAM_BOT_TOKEN. Either bot can receive /present commands —
    # the routing is configured per chat.
    for key in ("GOJ_ATTENDANCE_TOKEN", "TELEGRAM_BOT_TOKEN"):
        v = os.getenv(key)
        if v:
            return v.strip()
    return None


def _allowed_users() -> List[str]:
    """Return the list of chat IDs allowed to issue commands. Defaults to
    Kato's chat if env is missing — DO NOT silently allow everyone."""
    raw = os.getenv("TELEGRAM_ALLOWED_USERS", "").strip()
    if not raw:
        return ["5587703834"]  # Kato per CLAUDE.md
    return [s.strip() for s in raw.split(",") if s.strip()]


# ── State persistence ────────────────────────────────────────────────────────

def _load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"last_update_id": 0}


def _save_state(state: Dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── Telegram API ─────────────────────────────────────────────────────────────

def _tg_call(method: str, params: Dict[str, Any], timeout: int = 30) -> Dict[str, Any]:
    token = _bot_token()
    if not token:
        return {"ok": False, "error": "no bot token in env"}
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}", data=data,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e else ""
        return {"ok": False, "error": f"HTTP {e.code}: {body[:200]}"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def reply(chat_id: int, text: str) -> None:
    _tg_call("sendMessage", {
        "chat_id": chat_id,
        "text":    text,
    })


# ── Client name resolution ───────────────────────────────────────────────────

def resolve_client(input_name: str) -> Tuple[Optional[str], List[str]]:
    """Try to resolve a typed name to the canonical client name.
    Returns (matched_name, suggestions). matched_name is None when ambiguous."""
    raw = " ".join(input_name.strip().split())
    if not raw:
        return None, []

    with sqlite3.connect(str(DB_PATH)) as conn:
        # 1. Exact case-insensitive
        row = conn.execute(
            "SELECT name FROM clients WHERE LOWER(name) = LOWER(?) LIMIT 1",
            (raw,),
        ).fetchone()
        if row:
            return row[0], []

        # 2. Substring match — typed "Adyan" or "Ludmila" should find "Adyan Ludmila"
        sub_rows = conn.execute(
            "SELECT name FROM clients WHERE LOWER(name) LIKE LOWER(?) LIMIT 5",
            (f"%{raw}%",),
        ).fetchall()
        if len(sub_rows) == 1:
            return sub_rows[0][0], []
        if len(sub_rows) > 1:
            return None, [r[0] for r in sub_rows]

        # 3. Last-name match — "/present Ludmila" should suggest Adyan Ludmila
        words = raw.split()
        if len(words) == 1:
            last_rows = conn.execute(
                "SELECT name FROM clients WHERE LOWER(name) LIKE LOWER(?) OR LOWER(name) LIKE LOWER(?) LIMIT 5",
                (f"% {raw}", f"{raw} %"),
            ).fetchall()
            if len(last_rows) == 1:
                return last_rows[0][0], []
            if len(last_rows) > 1:
                return None, [r[0] for r in last_rows]

    return None, []


# ── Command handlers ────────────────────────────────────────────────────────

def handle_present(chat_id: int, args: str, *, status: str = "present") -> None:
    """Parse `/present Name [shift] [reason]` and post to the API."""
    parts = args.strip().split()
    if not parts:
        reply(chat_id, f"Usage: /{status} <Client Name> [shift 1 or 2] [reason]")
        return

    # Pull shift if last token is "1" or "2"
    shift = 1
    if parts[-1] in ("1", "2"):
        shift = int(parts.pop())

    # Heuristic: name is the first 1-3 tokens (most GHS clients are "First Last")
    # Anything after that is reason. Try increasing token counts until match.
    name_candidates = [
        " ".join(parts[:n]) for n in range(1, min(4, len(parts)) + 1)
    ]
    matched, suggestions = None, []
    name_tokens_used = 0
    for n, candidate in enumerate(name_candidates, 1):
        m, s = resolve_client(candidate)
        if m:
            matched = m
            name_tokens_used = n
            suggestions = []
            break
        if s and not suggestions:
            suggestions = s

    if not matched:
        if suggestions:
            sug = "\n".join(f"  • {s}" for s in suggestions[:5])
            reply(chat_id, f"❓ Multiple matches for '{' '.join(parts)}':\n{sug}\nReply with the full name.")
        else:
            reply(chat_id, f"❌ No client matches '{' '.join(parts)}'. Try a partial last name.")
        return

    reason = " ".join(parts[name_tokens_used:]).strip() if name_tokens_used < len(parts) else None

    payload = {
        "client_name": matched,
        "shift":       shift,
        "source":      "telegram",
        "marker_id":   f"tg:{chat_id}",
        "reason":      reason,
    }
    # The unified endpoint only writes status='present'; for /absent we have to
    # write to the DB directly with status='absent' (no separate API for that yet).
    if status == "present":
        try:
            req = urllib.request.Request(
                PRESENT_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                resp = json.loads(r.read().decode("utf-8"))
            if resp.get("ok"):
                msg = f"✓ {matched} marked present (shift {shift})"
                if reason:
                    msg += f" · {reason}"
                reply(chat_id, msg)
            else:
                reply(chat_id, f"⚠ API said no: {resp}")
        except Exception as e:
            reply(chat_id, f"❌ POST failed: {e}")
    else:
        # /absent — write directly to attendance_log
        today = datetime.now().strftime("%Y-%m-%d")
        note = f"source=telegram · by=tg:{chat_id}" + (f" · note={reason}" if reason else "")
        with sqlite3.connect(str(DB_PATH)) as conn:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(attendance_log)")}
            base_cols = ["log_date", "shift", "client_name", "status"]
            base_vals = [today, shift, matched, "absent"]
            if "reason" in cols:
                base_cols.append("reason"); base_vals.append(note)
            if "source" in cols:
                base_cols.append("source"); base_vals.append("telegram")
            if "day_key" in cols:
                base_cols.append("day_key"); base_vals.append(datetime.now().strftime("%a")[:3].lower())
            ph = ",".join("?" * len(base_cols))
            conn.execute(
                f"INSERT INTO attendance_log ({','.join(base_cols)}) VALUES ({ph})",
                base_vals,
            )
            conn.commit()
        msg = f"✓ {matched} marked absent (shift {shift})"
        if reason:
            msg += f" · {reason}"
        reply(chat_id, msg)


def handle_list(chat_id: int) -> None:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/goj-live/present-mark/today", timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        reply(chat_id, f"❌ couldn't fetch list: {e}")
        return
    out = [f"📋 Present today ({data.get('total', 0)})"]
    for s in ("1", "2"):
        names = [e["name"] for e in data.get("by_shift", {}).get(s, [])]
        out.append(f"  Shift {s}: {len(names)}")
        for n in names[:20]:
            out.append(f"    • {n}")
        if len(names) > 20:
            out.append(f"    …+{len(names)-20} more")
    reply(chat_id, "\n".join(out))


def handle_help(chat_id: int) -> None:
    reply(chat_id, (
        "GOJ present-mark bot · commands:\n"
        "  /present Name [shift] [reason] — mark present\n"
        "  /absent  Name [shift] [reason] — mark absent\n"
        "  /list                          — today's present roster\n"
        "  /help                          — this message\n"
        "\nTip: partial name works. /present Adyan → matches Adyan Ludmila."
    ))


# ── Polling loop ─────────────────────────────────────────────────────────────

def process_update(upd: Dict[str, Any]) -> None:
    msg = upd.get("message") or upd.get("channel_post") or {}
    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    text = (msg.get("text") or "").strip()
    if not chat_id or not text:
        return
    if str(chat_id) not in _allowed_users():
        log.warning(f"refused chat_id={chat_id} text={text[:40]!r}")
        reply(chat_id, "⛔ Not authorized.")
        return

    log.info(f"chat={chat_id} cmd={text[:60]!r}")
    parts = text.split(maxsplit=1)
    cmd = parts[0].lower().lstrip("/").split("@")[0]
    args = parts[1] if len(parts) > 1 else ""

    if cmd in ("present", "p"):
        handle_present(chat_id, args, status="present")
    elif cmd in ("absent", "a"):
        handle_present(chat_id, args, status="absent")
    elif cmd in ("list", "today", "l"):
        handle_list(chat_id)
    elif cmd in ("help", "start"):
        handle_help(chat_id)
    else:
        reply(chat_id, "Unknown command. /help for usage.")


def poll_loop(once: bool = False) -> None:
    state = _load_state()
    last_id = state.get("last_update_id", 0)
    log.info(f"present-bot polling, resuming from update_id={last_id}")

    while True:
        params = {
            "timeout": 25,
            "offset":  last_id + 1,
        }
        result = _tg_call("getUpdates", params, timeout=30)
        if not result.get("ok"):
            log.error(f"getUpdates error: {result}")
            if once:
                return
            time.sleep(5)
            continue
        updates = result.get("result", [])
        for upd in updates:
            try:
                process_update(upd)
            except Exception:
                log.exception(f"crash on update_id={upd.get('update_id')}")
            last_id = max(last_id, upd.get("update_id", last_id))
        state["last_update_id"] = last_id
        _save_state(state)
        if once:
            log.info(f"processed {len(updates)} updates; exit (--once)")
            return


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--once", action="store_true",
                   help="process pending updates and exit")
    p.add_argument("--test", action="store_true",
                   help="send a test ping to Kato and exit")
    args = p.parse_args()

    if not _bot_token():
        print("❌ no TELEGRAM_BOT_TOKEN / GOJ_ATTENDANCE_TOKEN in env", file=sys.stderr)
        return 1

    if args.test:
        chat = _allowed_users()[0]
        r = _tg_call("sendMessage", {
            "chat_id": chat,
            "text":    f"🤖 Present-mark bot test\n{datetime.now(timezone.utc).isoformat()}\nUse /help to see commands.",
        })
        print(json.dumps(r, indent=2))
        return 0 if r.get("ok") else 1

    poll_loop(once=args.once)
    return 0


if __name__ == "__main__":
    sys.exit(main())
