"""
CC_auth_router.py — GHS Unified Login Auth
Single-user (Chairman/Kato) password setup + JWT issuance.
No PHI anywhere in this module.

GET  /api/auth/status  — {configured: bool}
POST /api/auth/setup   — first-time password setup → {token}
POST /api/auth/login   — verify password → {token}

Desktop mode (127.0.0.1 / localhost): same flow, no bypass —
login still required for browser-facing auth even from local.
JWT secret and password hash stored in ~/.rex/config.json.
"""
import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from pathlib import Path

import bcrypt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_CONFIG_FILE = Path.home() / ".rex" / "config.json"
_HASH_KEY    = "ghs_password_hash"
_SECRET_KEY  = "ghs_jwt_secret"
_TOKEN_TTL   = 24 * 3600          # 24 hours

router = APIRouter()


# ── Config helpers ────────────────────────────────────────────────────────────

def _load_cfg() -> dict:
    try:
        return json.loads(_CONFIG_FILE.read_text()) if _CONFIG_FILE.exists() else {}
    except Exception:
        return {}


def _save_cfg(data: dict) -> None:
    _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(json.dumps(data, indent=2))


# ── JWT (stdlib HS256 — matches auth.py pattern, no external library) ─────────

def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _mint_jwt(secret: str) -> str:
    key  = secret.encode()
    hdr  = _b64u(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    now  = int(time.time())
    pay  = _b64u(json.dumps({"sub": "chairman", "iat": now, "exp": now + _TOKEN_TTL}).encode())
    sig  = _b64u(hmac.new(key, f"{hdr}.{pay}".encode(), hashlib.sha256).digest())
    return f"{hdr}.{pay}.{sig}"


def _get_or_create_secret() -> str:
    cfg = _load_cfg()
    if not cfg.get(_SECRET_KEY):
        cfg[_SECRET_KEY] = secrets.token_hex(32)
        _save_cfg(cfg)
    return cfg[_SECRET_KEY]


# ── Models ────────────────────────────────────────────────────────────────────

class PasswordBody(BaseModel):
    password: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/api/auth/status", include_in_schema=False)
async def auth_status():
    cfg = _load_cfg()
    return {"configured": bool(cfg.get(_HASH_KEY))}


@router.post("/api/auth/setup", include_in_schema=False)
async def auth_setup(body: PasswordBody):
    cfg = _load_cfg()
    if cfg.get(_HASH_KEY):
        raise HTTPException(status_code=409, detail="Already configured — use /api/auth/login.")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")
    pw_hash = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    cfg[_HASH_KEY] = pw_hash
    _save_cfg(cfg)
    logger.info("✅ GHS Chairman password configured")
    return {"token": _mint_jwt(_get_or_create_secret())}


@router.post("/api/auth/login", include_in_schema=False)
async def auth_login(body: PasswordBody, request: Request):
    cfg    = _load_cfg()
    stored = cfg.get(_HASH_KEY, "")
    if not stored:
        raise HTTPException(status_code=404, detail="Not configured — use /api/auth/setup first.")
    try:
        ok = bcrypt.checkpw(body.password.encode("utf-8"), stored.encode("utf-8"))
    except Exception:
        ok = False
    if not ok:
        client = request.client.host if request.client else "unknown"
        logger.warning("⚠️ GHS login failed from %s", client)
        raise HTTPException(status_code=401, detail="Access denied.")
    logger.info("✅ GHS Chairman login successful")
    return {"token": _mint_jwt(_get_or_create_secret())}
