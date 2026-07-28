"""
CC_cowork_relay.py — Cowork → Telegram relay endpoint
======================================================
Lets a Cowork/Claude session (which can't reach localhost) send
Telegram messages to Kato's bots via hermestigerclaw.com tunnel.

POST /api/cowork-relay

Auth: X-Relay-Token header required for external requests.
      localhost (Desktop Mode) bypasses the token check.

Token stored at: ~/.rex/config.json → cowork_relay_token
Bot tokens resolved: config.json → env vars → macOS Keychain
"""

import json
import logging
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Constants ─────────────────────────────────────────────────────────────────

CHAT_ID = 5587703834  # Kato's Telegram chat ID

# bot key → {config.json key, env var, keychain service name}
_BOT_CONFIG: dict[str, dict] = {
    "hermes": {
        "token_key": "telegram_hermes_token",
        "env_key":   "TELEGRAM_HERMES_TOKEN",
        "keychain":  "hermes-telegram-bot",
    },
    "rexxie": {
        "token_key": "telegram_rexxie_token",
        "env_key":   "TELEGRAM_REXXIE_TOKEN",
        "keychain":  "rexxie-telegram-bot",
    },
    "goj": {
        "token_key": "telegram_goj_token",
        "env_key":   "TELEGRAM_GOJ_TOKEN",
        "keychain":  "rex-goj-telegram-bot",
    },
    "rex": {
        "token_key": "telegram_hermes_token",   # default to hermes bot
        "env_key":   "TELEGRAM_HERMES_TOKEN",
        "keychain":  "hermes-telegram-bot",
    },
}

_CONFIG_PATH = Path.home() / ".rex" / "config.json"

# ── Config helpers ────────────────────────────────────────────────────────────

def _load_config() -> dict:
    if _CONFIG_PATH.exists():
        try:
            return json.loads(_CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}


def _save_config(cfg: dict) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


# ── Relay token (generated once, persisted) ───────────────────────────────────

def _get_relay_token() -> str:
    """Return existing relay token or generate and persist a new one."""
    cfg = _load_config()
    token = cfg.get("cowork_relay_token")
    if not token:
        token = secrets.token_urlsafe(32)
        cfg["cowork_relay_token"] = token
        _save_config(cfg)
        logger.info(f"🔑 New cowork_relay_token generated → saved to {_CONFIG_PATH}")
    return token


# Evaluate at import time so the token appears in startup logs.
_RELAY_TOKEN: str = _get_relay_token()
logger.info(f"🔑 COWORK RELAY TOKEN (copy this): {_RELAY_TOKEN}")


# ── Bot token resolution ──────────────────────────────────────────────────────

def _resolve_bot_token(bot: str) -> Optional[str]:
    """Resolve the Telegram bot token for `bot`.

    Priority: config.json → environment variable → macOS Keychain.
    """
    spec = _BOT_CONFIG[bot]

    # 1. config.json
    cfg = _load_config()
    token = cfg.get(spec["token_key"])
    if token:
        return token

    # 2. Environment variable
    token = os.getenv(spec["env_key"])
    if token:
        return token

    # 3. macOS Keychain via keyring
    try:
        import keyring  # type: ignore
        token = keyring.get_password(spec["keychain"], "bot_token")
        if token:
            return token
    except Exception as e:
        logger.debug(f"Keyring lookup failed for {spec['keychain']!r}: {e}")

    return None


# ── Pydantic models ───────────────────────────────────────────────────────────

class RelayRequest(BaseModel):
    message: str
    bot: Literal["hermes", "rexxie", "goj", "rex"] = "hermes"
    priority: Literal["normal", "urgent"] = "normal"
    source: str = "cowork"


class RelayResponse(BaseModel):
    ok: bool
    telegram_message_id: Optional[int] = None
    bot_used: str
    chat_id: int
    error: Optional[str] = None


# ── Auth helper ───────────────────────────────────────────────────────────────

def _is_localhost(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in ("127.0.0.1", "::1", "localhost")


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/api/cowork-relay", response_model=RelayResponse)
async def cowork_relay(
    payload: RelayRequest,
    request: Request,
    x_relay_token: Optional[str] = Header(default=None),
) -> RelayResponse:
    """Relay a message from a Cowork session to one of Kato's Telegram bots."""

    # Auth — localhost (Desktop Mode) always trusted, same as rest of REX
    if not _is_localhost(request):
        if x_relay_token != _RELAY_TOKEN:
            raise HTTPException(status_code=401, detail="Invalid or missing X-Relay-Token")

    # Resolve bot token
    bot_token = _resolve_bot_token(payload.bot)
    if not bot_token:
        raise HTTPException(
            status_code=503,
            detail=(
                f"No Telegram token found for bot '{payload.bot}'. "
                f"Set '{_BOT_CONFIG[payload.bot]['token_key']}' in ~/.rex/config.json, "
                f"'{_BOT_CONFIG[payload.bot]['env_key']}' env var, "
                f"or Keychain service '{_BOT_CONFIG[payload.bot]['keychain']}'."
            ),
        )

    # Format message
    if payload.priority == "urgent":
        text = f"\U0001f6a8 [COWORK URGENT] {payload.message}"
    else:
        text = f"[COWORK] {payload.message}"

    # Log every relay call
    preview = payload.message[:60] + ("..." if len(payload.message) > 60 else "")
    logger.info(
        f"[cowork-relay] {datetime.utcnow().isoformat()}Z | "
        f"bot={payload.bot} priority={payload.priority} "
        f"source={payload.source!r} | {preview!r}"
    )

    # Send to Telegram
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    tg_body = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(url, json=tg_body)
            result = resp.json()
        except Exception as exc:
            logger.error(f"[cowork-relay] HTTP error: {exc}")
            return RelayResponse(ok=False, bot_used=payload.bot, chat_id=CHAT_ID, error=str(exc))

    if not result.get("ok"):
        err = result.get("description", "Unknown Telegram error")
        logger.error(f"[cowork-relay] Telegram API error: {err}")
        return RelayResponse(ok=False, bot_used=payload.bot, chat_id=CHAT_ID, error=err)

    msg_id: Optional[int] = result.get("result", {}).get("message_id")
    logger.info(f"[cowork-relay] ✅ Delivered → message_id={msg_id}")
    return RelayResponse(
        ok=True,
        telegram_message_id=msg_id,
        bot_used=payload.bot,
        chat_id=CHAT_ID,
    )
