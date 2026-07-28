"""
REX — Telegram Bot (Natural Conversation Mode)
===============================================
Talk to REX exactly like you talk to Claude — no slash commands,
no special syntax. Just send a message and REX replies.

Features:
  • Natural language — any message goes straight to REX as a chat
  • Chairman detection — Kato's chat_id gets full chairman access
  • Rexxie mode — say "hey rexxie" and switch to personal confidant
  • No commands required — REX understands context naturally
  • Fast replies — responses streamed back as soon as they arrive
  • Long messages — auto-split into Telegram's 4096-char limit
  • Status ping — "rex status" shows system health at a glance

Setup (one-time):
  1. python rex_telegram_bot.py --setup
     → Enter your Bot Token (from @BotFather)
     → Send /start to your bot to register your Chat ID as Chairman
  2. python rex_telegram_bot.py
     → Bot starts. Message it from Telegram — it just works.

Chairman auto-detection:
  The FIRST person to send /start after --setup is registered as Chairman.
  This locks Kato's Telegram chat_id to the chairman role permanently.
  Any other chat_id is treated as staff.

Config: ~/Desktop/REX/rex_telegram_config.json
Requires: python-telegram-bot v20+  OR  httpx + custom polling loop
Uses: requests (no extra deps beyond what REX already has)
"""

import json
import logging
import os
import time
import threading
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Set

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")

# ── Config ─────────────────────────────────────────────────────────────────────
CONFIG_PATH = Path.home() / "Desktop" / "REX" / "rex_telegram_config.json"
REX_BASE_URL  = "http://localhost:8000"   # LOCAL ONLY — REX never leaves this machine
POLL_INTERVAL = 1          # seconds between Telegram polls
MAX_MSG_LEN   = 4096       # Telegram hard limit per message
CHAIRMAN_CHAT_ID_KEY = "chairman_chat_id"

# ── RBAC allow-list (security gap C5) ────────────────────────────────────────────
# Closes C5: previously ANY Telegram user who messaged this bot got staff-level
# REX access (and thus GOJ/sensitive data). Now only chat_ids in the allow-list
# may reach REX. The allow-list is the union of:
#   1. env TELEGRAM_ALLOWED_USERS (comma-separated chat_ids), and
#   2. the registered chairman_chat_id (so Kato is never locked out).
# Loaded fresh on each check so .env edits take effect without a restart.
#
# TODO(per-tier-scoping): this phase is binary — ALLOWED (full) vs everyone-else
# (denied). A future phase should map chat_ids to roles (e.g. read-only staff,
# ops, chairman) and scope REX capabilities per tier instead of all-or-nothing.
ALLOWED_USERS_ENV = "TELEGRAM_ALLOWED_USERS"
HERMES_CLOUD_ENV_PATH = Path.home() / ".hermes-cloud" / ".env"
ACCESS_DENIED_LOG = Path.home() / "Desktop" / "REX" / "logs" / "rex_telegram_denied.log"


def _read_env_value(key: str) -> Optional[str]:
    """Read a key from the process env, falling back to ~/.hermes-cloud/.env."""
    val = os.environ.get(key)
    if val:
        return val
    try:
        if HERMES_CLOUD_ENV_PATH.exists():
            for line in HERMES_CLOUD_ENV_PATH.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() == key:
                    return v.strip().strip('"').strip("'")
    except Exception as e:
        logger.error(f"Could not read {key} from {HERMES_CLOUD_ENV_PATH}: {e}")
    return None


def _load_allowed_users() -> Set[int]:
    """Parse TELEGRAM_ALLOWED_USERS (comma-separated chat_ids) into an int set."""
    raw = _read_env_value(ALLOWED_USERS_ENV) or ""
    allowed: Set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            allowed.add(int(part))
        except ValueError:
            logger.warning(f"Ignoring non-numeric entry in {ALLOWED_USERS_ENV}: {part!r}")
    return allowed


def _log_denied_attempt(chat_id: int, username: str):
    """Append a denied access attempt (id, ts) to a local audit log."""
    try:
        ACCESS_DENIED_LOG.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat()
        with ACCESS_DENIED_LOG.open("a") as fh:
            fh.write(f"{ts}\tchat_id={chat_id}\tusername={username}\n")
    except Exception as e:
        logger.error(f"Could not write denied-attempt log: {e}")

# ── Typing indicators & personality ────────────────────────────────────────────
THINKING_EMOJI = "🦖"


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}


def _save_config(cfg: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    CONFIG_PATH.chmod(0o600)


def _tg_api(token: str, method: str, payload: dict = None) -> Optional[dict]:
    """Call Telegram Bot API. Returns response JSON or None on error."""
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload or {}).encode()
    req  = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # Long-poll timeout: getUpdates asks Telegram to hold for 30s, so socket
    # timeout must be longer (35s) — otherwise urllib closes first and errors.
    # All other API calls are fast so 35s is a safe ceiling for both.
    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            return json.loads(resp.read())
    except Exception as e:
        logger.error(f"Telegram API error ({method}): {e}")
        return None


def _send_typing(token: str, chat_id: int):
    _tg_api(token, "sendChatAction", {"chat_id": chat_id, "action": "typing"})


def _send_message(token: str, chat_id: int, text: str, parse_mode: str = "Markdown"):
    """Send message, auto-splitting if over Telegram's 4096 char limit."""
    if not text.strip():
        text = "_(no response)_"

    # Split into chunks without breaking words/lines
    chunks = []
    while len(text) > MAX_MSG_LEN:
        # Find last newline before limit
        split_at = text.rfind("\n", 0, MAX_MSG_LEN)
        if split_at < MAX_MSG_LEN // 2:
            split_at = MAX_MSG_LEN
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    chunks.append(text)

    for i, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
        payload = {
            "chat_id":    chat_id,
            "text":       chunk,
            "parse_mode": parse_mode,
        }
        result = _tg_api(token, "sendMessage", payload)
        if not result or not result.get("ok"):
            # Retry without markdown if parse failed
            payload["parse_mode"] = None
            _tg_api(token, "sendMessage", payload)
        if i < len(chunks) - 1:
            time.sleep(0.3)  # brief pause between chunks


def _call_rex(
    message: str,
    user_name: str = "kato",
    user_role: str = "chairman",
    session_id: str = None,
) -> str:
    """Send message to REX REST endpoint, return reply text."""
    payload = {
        "message":       message,
        "user_name":     user_name,
        "user_role":     user_role,
        "dashboard_mode": False,
    }
    if session_id:
        payload["session_id"] = session_id

    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        f"{REX_BASE_URL}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            return result.get("reply", "_(REX returned no reply)_")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.error(f"REX HTTP error {e.code}: {body[:200]}")
        return f"⚠️ REX error {e.code}: {body[:150]}"
    except Exception as e:
        logger.error(f"REX connection error: {e}")
        # REX is LOCAL ONLY — no cloud fallback, ever.
        return "⚠️ REX is offline. Start REX on your Mac to continue."


class TelegramBot:
    """
    Long-polling Telegram bot that bridges to REX naturally.
    Every text message → REX → reply. No commands required.
    """

    def __init__(self):
        cfg = _load_config()
        self.token: str = cfg.get("bot_token", "")
        self.chairman_chat_id: Optional[int] = cfg.get(CHAIRMAN_CHAT_ID_KEY)
        self._offset: int = 0
        self._sessions: dict = {}   # chat_id → session_id (per conversation)
        self._setup_pending = not self.chairman_chat_id

    def _is_chairman(self, chat_id: int) -> bool:
        return self.chairman_chat_id and chat_id == self.chairman_chat_id

    def _get_session(self, chat_id: int) -> str:
        if chat_id not in self._sessions:
            import uuid
            self._sessions[chat_id] = str(uuid.uuid4())
        return self._sessions[chat_id]

    def _determine_role(self, chat_id: int) -> str:
        # HermieChatt_bot routes ALL traffic through local gateway (:65001).
        # Kato's directive 2026-06-15: "This should be local."
        return "chairman"

    def _handle_update(self, update: dict):
        """Process a single Telegram update."""
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return

        chat_id   = msg["chat"]["id"]
        text      = (msg.get("text") or "").strip()
        user_info = msg.get("from", {})
        username  = user_info.get("username") or user_info.get("first_name") or "user"

        if not text:
            return  # ignore photos, stickers, etc. for now

        # ── RBAC allow-list gate (security gap C5) ──────────────────────────
        # Only allow-listed chat_ids may reach REX. The chairman is always
        # allowed. Exception: while setup is pending (no chairman registered),
        # let the first /start through so the owner can claim the bot.
        allowed_users = _load_allowed_users()
        if self.chairman_chat_id:
            allowed_users.add(self.chairman_chat_id)
        is_allowed = chat_id in allowed_users
        if not is_allowed and not (self._setup_pending and text == "/start"):
            _log_denied_attempt(chat_id, username)
            logger.warning(
                f"🚫 Access denied: chat_id={chat_id} (@{username}) not in allow-list"
            )
            _send_message(self.token, chat_id, "Access denied.")
            return

        # ── Chairman registration (first /start after setup) ────────────────
        if text == "/start":
            if self._setup_pending:
                self.chairman_chat_id = chat_id
                self._setup_pending   = False
                cfg = _load_config()
                cfg[CHAIRMAN_CHAT_ID_KEY] = chat_id
                _save_config(cfg)
                _send_message(
                    self.token, chat_id,
                    f"🦖 *REX is ready, Kato.*\n\n"
                    f"Your Telegram identity is now locked as Chairman.\n"
                    f"Just talk to me naturally — no commands needed.\n\n"
                    f"Try: _\"What's on my schedule today?\"_ or _\"hey rexxie\"_",
                )
                logger.info(f"✅ Chairman registered: chat_id={chat_id} (@{username})")
            else:
                role = self._determine_role(chat_id)
                _send_message(
                    self.token, chat_id,
                    f"🦖 *REX here.* You're connected as *{role}*.\n"
                    f"Just talk to me normally — no commands needed.",
                )
            return

        # ── Status shortcut (convenience — REX also understands natural language) ──
        if text.lower() in ("rex status", "/status", "status"):
            try:
                req = urllib.request.Request(f"{REX_BASE_URL}/api/health", method="GET")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    h = json.loads(resp.read())
                enc_level = h.get("encryption_level", "standard")
                training  = h.get("training_trainer", "none")
                mem_count = h.get("memory_count", "?")
                status_text = (
                    f"🦖 *REX Status*\n"
                    f"• Encryption: `{enc_level}`\n"
                    f"• Memory: `{mem_count}` entries\n"
                    f"• Training: `{training}`\n"
                    f"• Secure mode: `{h.get('secure_mode', False)}`\n"
                    f"• Version: `{h.get('version', '?')}`"
                )
            except Exception:
                status_text = "⚠️ REX backend not reachable — is it running?"
            _send_message(self.token, chat_id, status_text)
            return

        # ── All other messages — forward to REX naturally ───────────────────
        role       = self._determine_role(chat_id)
        session_id = self._get_session(chat_id)
        tg_user    = "kato" if self._is_chairman(chat_id) else username.lower()

        # Show typing indicator while REX thinks
        _send_typing(self.token, chat_id)

        # Call REX
        rex_reply = _call_rex(
            message=text,
            user_name=tg_user,
            user_role=role,
            session_id=session_id,
        )

        # Send reply back to Telegram
        _send_message(self.token, chat_id, rex_reply)
        logger.info(f"Chat [{chat_id}] ({role}): {text[:60]}... → {rex_reply[:60]}...")

    def poll_once(self):
        """Fetch and process pending updates."""
        result = _tg_api(self.token, "getUpdates", {
            "offset":          self._offset,
            "timeout":         30,
            "allowed_updates": ["message", "edited_message"],
        })
        if not result or not result.get("ok"):
            return

        for update in result.get("result", []):
            try:
                self._handle_update(update)
            except Exception as e:
                logger.error(f"Error handling update: {e}", exc_info=True)
            finally:
                self._offset = update["update_id"] + 1

    def run(self):
        """Start the polling loop."""
        if not self.token:
            logger.error("No bot token configured. Run: python rex_telegram_bot.py --setup")
            return

        logger.info(f"🦖 REX Telegram bot started (chairman_chat_id={self.chairman_chat_id})")
        if self._setup_pending:
            logger.info("⚠️  Chairman not yet registered — send /start to your bot to lock in your identity.")

        while True:
            try:
                self.poll_once()
            except KeyboardInterrupt:
                logger.info("Bot stopped.")
                break
            except Exception as e:
                logger.error(f"Poll error: {e}")
                time.sleep(5)
            time.sleep(POLL_INTERVAL)


# ── Setup Wizard ───────────────────────────────────────────────────────────────

def setup_wizard():
    print("\n" + "="*60)
    print("  REX Telegram Bot — Setup")
    print("="*60)
    print()
    print("Step 1 — Get a Bot Token:")
    print("  1. Open Telegram and search for @BotFather")
    print("  2. Send: /newbot")
    print("  3. Choose a name (e.g., 'REX Assistant')")
    print("  4. Copy the token it gives you")
    print()
    token = input("  Paste your Bot Token: ").strip()
    if not token:
        print("❌ No token entered.")
        return

    # Test the token
    result = _tg_api(token, "getMe", {})
    if not result or not result.get("ok"):
        print("❌ Token test failed — double-check the token.")
        return

    bot_name = result["result"].get("username", "your-bot")
    print(f"\n  ✅ Connected! Bot username: @{bot_name}")

    cfg = _load_config()
    cfg["bot_token"] = token
    # Clear chairman so the next /start registers it fresh
    cfg.pop(CHAIRMAN_CHAT_ID_KEY, None)
    _save_config(cfg)

    print()
    print("Step 2 — Register as Chairman:")
    print(f"  1. Open Telegram and find @{bot_name}")
    print(f"  2. Send:  /start")
    print(f"  That locks your Telegram identity as Chairman permanently.")
    print()
    print("Step 3 — Start the bot:")
    print(f"  python rex_telegram_bot.py")
    print()
    print("Then just talk to REX naturally. No commands needed.")
    print("="*60 + "\n")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="REX Telegram Bot")
    parser.add_argument("--setup",  action="store_true", help="Run setup wizard")
    parser.add_argument("--status", action="store_true", help="Show config and test token")
    args = parser.parse_args()

    if args.setup:
        setup_wizard()
    elif args.status:
        cfg = _load_config()
        token = cfg.get("bot_token", "")
        cid   = cfg.get(CHAIRMAN_CHAT_ID_KEY)
        print(f"\n🦖 REX Telegram Bot Status")
        print(f"   Token configured: {'✅' if token else '❌'}")
        print(f"   Chairman chat_id: {cid or '⚠️  Not registered yet (send /start to bot)'}")
        if token:
            r = _tg_api(token, "getMe", {})
            if r and r.get("ok"):
                print(f"   Bot username:     @{r['result'].get('username', '?')}")
                print(f"   Token valid:      ✅")
            else:
                print(f"   Token valid:      ❌")
        print()
    else:
        bot = TelegramBot()
        bot.run()
