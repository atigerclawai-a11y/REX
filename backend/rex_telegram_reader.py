"""
rex_telegram_reader.py — Telegram Channel Reader for REX

Reads messages from a public or private Telegram channel/group so that
REX and Rexxie can answer questions about schedules, announcements, etc.

Two modes:
  1. Bot mode  — uses an existing REX Telegram bot token + channel username
                 Works for PUBLIC channels where the bot is added as admin.
  2. User mode — uses Telethon (MTProto) with your personal account.
                 Required for private channels/groups.

Config stored in: ~/Desktop/REX/rex_telegram_reader_config.json

Usage:
  python backend/rex_telegram_reader.py --setup   # interactive config
  python backend/rex_telegram_reader.py --fetch   # one-time fetch
  python backend/rex_telegram_reader.py --watch   # continuous polling
"""

import json
import asyncio
import logging
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger("rex.telegram_reader")

REX_DIR     = Path(__file__).resolve().parent.parent
CONFIG_PATH = REX_DIR / "rex_telegram_reader_config.json"
CACHE_PATH  = REX_DIR / ".telegram_channel_cache.json"


# ── Default config ─────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "mode":            "bot",           # "bot" or "user"
    "channel":         "",              # e.g. "@goj_ops" or "-100123456789"
    "bot_token":       "",              # REX bot token (for bot mode)
    "api_id":          "",              # Telegram API ID (for user mode)
    "api_hash":        "",              # Telegram API hash (for user mode)
    "phone":           "",              # Your phone number (for user mode)
    "poll_interval":   300,             # seconds between fetches (5 min)
    "max_messages":    50,              # messages to fetch each poll
    "keywords":        [],              # if set, only save messages containing these
    "channels":        [],              # can watch multiple channels
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return {**DEFAULT_CONFIG, **json.loads(CONFIG_PATH.read_text())}
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text())
        except Exception:
            pass
    return {}


def save_cache(cache: dict) -> None:
    CACHE_PATH.write_text(json.dumps(cache, indent=2))


# ── Bot mode (uses requests, no extra deps) ────────────────────────────

def _bot_get_updates(bot_token: str, offset: int = 0, limit: int = 100) -> list:
    """Fetch bot updates via long-polling."""
    import urllib.request
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates?offset={offset}&limit={limit}&timeout=10"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read())
            return data.get("result", [])
    except Exception as e:
        logger.warning(f"Bot getUpdates failed: {e}")
        return []


def _bot_get_channel_messages(bot_token: str, channel: str, limit: int = 50) -> List[dict]:
    """
    Fetch recent messages from a channel via bot API.
    Note: Bots can only see new messages after they're added.
    For historical messages, user mode (Telethon) is needed.
    """
    import urllib.request
    import urllib.parse

    messages = []
    # Use forwardMessage trick: get chat info first
    url = f"https://api.telegram.org/bot{bot_token}/getChat?chat_id={urllib.parse.quote(str(channel))}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            chat_data = json.loads(r.read())
            if not chat_data.get("ok"):
                logger.warning(f"getChat failed: {chat_data.get('description','')}")
    except Exception as e:
        logger.warning(f"getChat error: {e}")

    return messages


def fetch_channel_bot_mode(config: dict, limit: int = 50) -> Dict[str, Any]:
    """
    Fetch messages using bot mode. Relies on forwarded updates stored in cache.
    For channels, the bot must be an admin of the channel.
    """
    token   = config.get("bot_token", "")
    channel = config.get("channel", "")

    if not token or not channel:
        return {"ok": False, "error": "Bot token or channel not configured.", "messages": []}

    cache = load_cache()
    offset = cache.get(f"offset_{channel}", 0)

    updates = _bot_get_updates(token, offset=offset, limit=100)
    new_messages = []

    for upd in updates:
        upd_id = upd.get("update_id", 0)
        offset = max(offset, upd_id + 1)

        # Check channel_post
        post = upd.get("channel_post") or upd.get("message")
        if not post:
            continue

        chat = post.get("chat", {})
        chat_id       = str(chat.get("id", ""))
        chat_username = chat.get("username", "")

        # Match by channel username or ID
        if channel.lstrip("@") not in (chat_username, chat_id):
            continue

        text = post.get("text") or post.get("caption") or ""
        kws  = config.get("keywords", [])
        if kws and not any(kw.lower() in text.lower() for kw in kws):
            continue

        new_messages.append({
            "id":        post.get("message_id"),
            "date":      datetime.fromtimestamp(post.get("date", 0), tz=timezone.utc).isoformat(),
            "text":      text,
            "from":      chat.get("title", channel),
            "channel":   channel,
        })

    # Persist offset and messages
    cache[f"offset_{channel}"] = offset
    all_msgs = cache.get(f"messages_{channel}", [])
    all_msgs.extend(new_messages)
    all_msgs = all_msgs[-500:]  # keep last 500
    cache[f"messages_{channel}"] = all_msgs
    save_cache(cache)

    return {
        "ok":          True,
        "new":         len(new_messages),
        "total_cached": len(all_msgs),
        "messages":    new_messages,
    }


# ── User mode (Telethon — reads private channels) ──────────────────────

async def _telethon_fetch(config: dict, limit: int = 50) -> Dict[str, Any]:
    """Fetch messages using Telethon user client (handles private channels)."""
    try:
        from telethon import TelegramClient
        from telethon.tl.types import Channel, Chat
    except ImportError:
        return {
            "ok": False,
            "error": "Telethon not installed. Run: pip install telethon --break-system-packages",
            "messages": [],
        }

    api_id   = config.get("api_id")
    api_hash = config.get("api_hash")
    phone    = config.get("phone")
    channel  = config.get("channel")
    channels = config.get("channels") or ([channel] if channel else [])

    if not api_id or not api_hash:
        return {"ok": False, "error": "api_id and api_hash not configured.", "messages": []}

    session_path = str(REX_DIR / "rex_telegram_session")
    client = TelegramClient(session_path, int(api_id), api_hash)

    all_messages = []
    try:
        await client.start(phone=phone)
        for ch in channels:
            try:
                entity = await client.get_entity(ch)
                async for msg in client.iter_messages(entity, limit=limit):
                    text = msg.message or ""
                    kws  = config.get("keywords", [])
                    if kws and not any(kw.lower() in text.lower() for kw in kws):
                        continue
                    all_messages.append({
                        "id":      msg.id,
                        "date":    msg.date.isoformat(),
                        "text":    text,
                        "from":    getattr(entity, "title", str(ch)),
                        "channel": str(ch),
                        "views":   getattr(msg, "views", None),
                    })
            except Exception as e:
                logger.warning(f"Could not read channel {ch}: {e}")
    finally:
        await client.disconnect()

    # Cache results
    cache = load_cache()
    for ch in channels:
        ch_msgs = [m for m in all_messages if m["channel"] == str(ch)]
        existing = cache.get(f"messages_{ch}", [])
        existing_ids = {m["id"] for m in existing}
        new = [m for m in ch_msgs if m["id"] not in existing_ids]
        combined = (existing + new)[-500:]
        cache[f"messages_{ch}"] = combined
    cache["last_fetch"] = datetime.now(tz=timezone.utc).isoformat()
    save_cache(cache)

    return {
        "ok": True,
        "new": len(all_messages),
        "messages": all_messages,
    }


def fetch_channel(config: Optional[dict] = None) -> Dict[str, Any]:
    """Fetch channel messages. Auto-selects bot vs user mode."""
    cfg = config or load_config()
    if cfg.get("mode") == "user":
        return asyncio.run(_telethon_fetch(cfg))
    else:
        return fetch_channel_bot_mode(cfg)


def get_cached_messages(channel: Optional[str] = None, limit: int = 20) -> List[dict]:
    """Return cached messages for a channel (or all channels)."""
    cache = load_cache()
    if channel:
        return cache.get(f"messages_{channel}", [])[-limit:]

    # Merge all channel caches
    all_msgs = []
    for key, val in cache.items():
        if key.startswith("messages_") and isinstance(val, list):
            all_msgs.extend(val)

    # Sort by date descending
    try:
        all_msgs.sort(key=lambda m: m.get("date", ""), reverse=True)
    except Exception:
        pass
    return all_msgs[:limit]


def get_schedule_summary(days: int = 7) -> str:
    """
    Filter cached messages for schedule-related content.
    Returns a formatted summary string for REX/Rexxie to use.
    """
    msgs = get_cached_messages(limit=100)
    schedule_kws = ["schedule", "roster", "shift", "meeting", "event", "date", "time", "appointment"]

    relevant = []
    for m in msgs:
        text_lower = m.get("text", "").lower()
        if any(kw in text_lower for kw in schedule_kws):
            relevant.append(m)

    if not relevant:
        return "No schedule-related messages found in the GOJ channel cache. Fetch may be needed."

    lines = [f"📅 **GOJ Schedule Updates** (last {len(relevant)} relevant messages):\n"]
    for m in relevant[:10]:
        lines.append(f"**{m.get('from', 'GOJ')}** — {m.get('date', '')[:10]}")
        lines.append(f"{m.get('text', '')[:300]}\n")

    return "\n".join(lines)


# ── CLI ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if "--setup" in sys.argv:
        print("\n🤖 REX Telegram Channel Reader — Setup\n")
        cfg = load_config()

        print("Mode: 'bot' = public channels (easier), 'user' = private channels (requires Telethon)")
        mode = input(f"Mode [bot/user] (current: {cfg['mode']}): ").strip() or cfg["mode"]
        cfg["mode"] = mode

        channel = input(f"Channel username or ID (e.g. @goj_ops) (current: {cfg['channel']}): ").strip()
        if channel:
            cfg["channel"] = channel

        if mode == "bot":
            token = input(f"Bot token (current: {'set' if cfg['bot_token'] else 'NOT SET'}): ").strip()
            if token:
                cfg["bot_token"] = token
            print("\n⚠️  Make sure the bot is an ADMIN of the channel to receive channel posts.")
        else:
            api_id = input(f"Telegram API ID (from my.telegram.org): ").strip()
            api_hash = input(f"Telegram API hash: ").strip()
            phone = input(f"Your phone number (e.g. +1876...): ").strip()
            if api_id:   cfg["api_id"]   = api_id
            if api_hash: cfg["api_hash"] = api_hash
            if phone:    cfg["phone"]    = phone

        kw = input("Filter keywords (comma-separated, or blank for all): ").strip()
        if kw:
            cfg["keywords"] = [k.strip() for k in kw.split(",") if k.strip()]

        save_config(cfg)
        print(f"\n✅ Config saved to {CONFIG_PATH}")

    elif "--fetch" in sys.argv:
        result = fetch_channel()
        if result["ok"]:
            print(f"✅ Fetched {result['new']} new message(s)")
            for m in result["messages"][:5]:
                print(f"  [{m['date'][:16]}] {m['text'][:100]}")
        else:
            print(f"❌ {result['error']}")

    elif "--schedule" in sys.argv:
        print(get_schedule_summary())

    elif "--cached" in sys.argv:
        msgs = get_cached_messages(limit=10)
        if msgs:
            for m in msgs:
                print(f"[{m['date'][:16]}] {m.get('from','?')}: {m['text'][:120]}")
        else:
            print("No cached messages. Run --fetch first.")

    else:
        print("Usage:")
        print("  --setup     Configure channel and auth")
        print("  --fetch     Fetch latest messages")
        print("  --schedule  Show schedule-related messages")
        print("  --cached    Show last 10 cached messages")
