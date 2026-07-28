"""
REX — WebAuthn Passkey Authentication
======================================
Replaces TOTP for REX vault unlock — one Face ID tap from iPhone or Touch ID on Mac.

Flow:
  Registration (one-time):
    1. GET  /api/passkey/register/begin   → challenge options JSON
    2. POST /api/passkey/register/complete → verify + store credential

  Authentication (every unlock):
    1. GET  /api/passkey/auth/begin       → assertion challenge JSON
    2. POST /api/passkey/auth/complete    → verify assertion → return JWT + trigger unlock

Serves /passkey  — a PWA you can add to iPhone home screen.
"""
import json
import secrets
import logging
import time
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import webauthn
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    UserVerificationRequirement,
    ResidentKeyRequirement,
    AttestationConveyancePreference,
)
from webauthn.helpers.exceptions import InvalidCBORData, InvalidAuthenticatorDataStructure

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/passkey", tags=["passkey"])

# ── Storage ────────────────────────────────────────────────────────────────────

PASSKEY_DIR  = Path.home() / ".rex" / "passkeys"
PASSKEY_FILE = PASSKEY_DIR / "credentials.json"
CHALLENGE_FILE = PASSKEY_DIR / "pending_challenge.json"
PASSKEY_DIR.mkdir(parents=True, exist_ok=True)

RP_NAME = "REX Sovereign"

# Allowed origins for WebAuthn — RP ID is always the hostname
ALLOWED_ORIGINS = {
    "localhost":             "http://localhost:8000",
    "127.0.0.1":             "http://127.0.0.1:8000",
    "rex.hermestigerclaw.com": "https://rex.hermestigerclaw.com",
}


def _get_rp_id(request: Request) -> str:
    """Derive RP ID from the request Host header (hostname without port)."""
    host = request.headers.get("host", "localhost")
    return host.split(":")[0]


def _get_origin(rp_id: str) -> str:
    """Return the expected origin string for the given RP ID."""
    return ALLOWED_ORIGINS.get(rp_id, f"https://{rp_id}")


def _load_credentials() -> List[dict]:
    if PASSKEY_FILE.exists():
        try:
            return json.loads(PASSKEY_FILE.read_text())
        except Exception:
            pass
    return []


def _save_credentials(creds: List[dict]):
    PASSKEY_FILE.write_text(json.dumps(creds, indent=2))
    PASSKEY_FILE.chmod(0o600)


def _store_challenge(challenge: bytes, rp_id: str):
    data = {
        "challenge": challenge.hex(),
        "rp_id": rp_id,
        "created_at": time.time(),
    }
    CHALLENGE_FILE.write_text(json.dumps(data))
    CHALLENGE_FILE.chmod(0o600)


def _pop_challenge() -> Optional[dict]:
    """Load and delete the pending challenge (single-use)."""
    if not CHALLENGE_FILE.exists():
        return None
    try:
        data = json.loads(CHALLENGE_FILE.read_text())
        CHALLENGE_FILE.unlink()
        # Expire after 5 minutes
        if time.time() - data.get("created_at", 0) > 300:
            return None
        data["challenge"] = bytes.fromhex(data["challenge"])
        return data
    except Exception:
        return None


# ── Models ─────────────────────────────────────────────────────────────────────

class RegistrationCompleteRequest(BaseModel):
    credential: dict   # PublicKeyCredential JSON from browser


class AuthCompleteRequest(BaseModel):
    credential: dict   # PublicKeyCredential JSON from browser
    trigger_unlock: bool = True


# ── Registration ───────────────────────────────────────────────────────────────

@router.get("/register/begin")
async def register_begin(request: Request):
    """Generate a WebAuthn registration challenge."""
    rp_id = _get_rp_id(request)
    challenge = secrets.token_bytes(32)
    _store_challenge(challenge, rp_id)

    options = webauthn.generate_registration_options(
        rp_id=rp_id,
        rp_name=RP_NAME,
        user_id=b"kato-rex-1",
        user_name="kato",
        user_display_name="Kato — REX",
        challenge=challenge,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        attestation=AttestationConveyancePreference.NONE,
        timeout=60000,
    )
    return json.loads(webauthn.options_to_json(options))


@router.post("/register/complete")
async def register_complete(body: RegistrationCompleteRequest, request: Request):
    """Verify WebAuthn registration and store credential."""
    pending = _pop_challenge()
    if not pending:
        raise HTTPException(status_code=400, detail="No pending registration challenge")

    rp_id = pending["rp_id"]
    origin = _get_origin(rp_id)

    try:
        credential_json = json.dumps(body.credential)
        verification = webauthn.verify_registration_response(
            credential=credential_json,
            expected_challenge=pending["challenge"],
            expected_rp_id=rp_id,
            expected_origin=origin,
            require_user_verification=True,
        )
    except Exception as e:
        logger.error(f"Passkey registration failed: {e}")
        raise HTTPException(status_code=400, detail=f"Registration verification failed: {e}")

    creds = _load_credentials()
    # Remove any existing credential for the same device (re-registration)
    creds = [c for c in creds if c.get("credential_id") != verification.credential_id.hex()]
    creds.append({
        "credential_id": verification.credential_id.hex(),
        "public_key": verification.credential_public_key.hex(),
        "sign_count": verification.sign_count,
        "rp_id": rp_id,
        "registered_at": time.time(),
        "aaguid": str(verification.aaguid) if verification.aaguid else None,
    })
    _save_credentials(creds)

    logger.info(f"✅ Passkey registered: {verification.credential_id.hex()[:16]}...")
    return {"ok": True, "credential_id": verification.credential_id.hex()[:16] + "..."}


# ── Authentication ─────────────────────────────────────────────────────────────

@router.get("/auth/begin")
async def auth_begin(request: Request):
    """Generate a WebAuthn authentication challenge."""
    rp_id = _get_rp_id(request)
    creds = _load_credentials()
    if not creds:
        raise HTTPException(status_code=404, detail="No passkeys registered")

    challenge = secrets.token_bytes(32)
    _store_challenge(challenge, rp_id)

    # Allow any registered credential
    allow_credentials = [
        {"type": "public-key", "id": c["credential_id"]}
        for c in creds
        if c.get("rp_id") == rp_id or not c.get("rp_id")
    ]

    options = webauthn.generate_authentication_options(
        rp_id=rp_id,
        challenge=challenge,
        allow_credentials=allow_credentials,
        user_verification=UserVerificationRequirement.REQUIRED,
        timeout=60000,
    )
    return json.loads(webauthn.options_to_json(options))


@router.post("/auth/complete")
async def auth_complete(body: AuthCompleteRequest, request: Request):
    """Verify WebAuthn assertion and trigger Mac unlock."""
    pending = _pop_challenge()
    if not pending:
        raise HTTPException(status_code=400, detail="No pending authentication challenge")

    rp_id = pending["rp_id"]
    origin = _get_origin(rp_id)

    # Find matching stored credential
    creds = _load_credentials()
    credential_id_hex = body.credential.get("id", "").replace("-", "+").replace("_", "/")
    # Handle URL-safe base64 → hex lookup
    import base64
    try:
        cred_id_bytes = base64.urlsafe_b64decode(credential_id_hex + "==")
        cred_id_hex = cred_id_bytes.hex()
    except Exception:
        cred_id_hex = credential_id_hex

    stored = next((c for c in creds if c["credential_id"] == cred_id_hex), None)
    if not stored:
        # Try prefix match
        stored = next((c for c in creds if c["credential_id"].startswith(cred_id_hex[:16])), None)
    if not stored:
        raise HTTPException(status_code=400, detail="Unknown credential")

    try:
        verification = webauthn.verify_authentication_response(
            credential=json.dumps(body.credential),
            expected_challenge=pending["challenge"],
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=bytes.fromhex(stored["public_key"]),
            credential_current_sign_count=stored["sign_count"],
            require_user_verification=True,
        )
    except Exception as e:
        logger.error(f"Passkey auth failed: {e}")
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")

    # Update sign count (replay attack protection)
    stored["sign_count"] = verification.new_sign_count
    _save_credentials(creds)

    logger.info(f"✅ Passkey authenticated: {cred_id_hex[:16]}...")

    # Trigger Mac unlock
    unlock_result = {"vault_pre_authorized": False}
    if body.trigger_unlock:
        try:
            from .rex_phone_unlock import pre_authorize_vault, wake_display, dismiss_screensaver
            pre_authorize_vault()
            wake_display()
            dismiss_screensaver()
            unlock_result = {"vault_pre_authorized": True, "vault_minutes": 15}
            logger.info("📱 Vault pre-authorized via passkey")
        except Exception as e:
            logger.warning(f"Unlock trigger failed (non-fatal): {e}")

    # Issue a session token
    from .auth import create_jwt
    jwt = create_jwt("passkey-kato", "Kato iPhone Passkey")

    return {
        "ok": True,
        "token": jwt,
        "message": "Authenticated 🦖",
        **unlock_result,
    }


# ── Status ─────────────────────────────────────────────────────────────────────

@router.get("/status")
async def passkey_status():
    creds = _load_credentials()
    return {
        "registered": len(creds) > 0,
        "count": len(creds),
        "credentials": [
            {
                "id": c["credential_id"][:16] + "...",
                "registered_at": c.get("registered_at"),
                "rp_id": c.get("rp_id"),
            }
            for c in creds
        ],
    }


@router.delete("/credentials")
async def revoke_all_passkeys():
    """Remove all registered passkeys (forces re-registration)."""
    PASSKEY_FILE.unlink(missing_ok=True)
    logger.warning("🗑️  All passkeys revoked")
    return {"ok": True}
