#!/usr/bin/env python3
"""
CC_google_token_refresh.py — Autonomous Google OAuth Token Refresher
======================================================================
Checks if the canonical Google OAuth token is near expiry, refreshes it,
and verifies all symlinks are intact. Designed to run as a cron job
every hour — keeps the token alive forever.

Usage:
    python3 CC_google_token_refresh.py           # Normal refresh check
    python3 CC_google_token_refresh.py --test     # Test refresh now
    python3 CC_google_token_refresh.py --force    # Force refresh regardless
    python3 CC_google_token_refresh.py --status   # Print token status only
"""

import json, os, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path(os.path.expanduser("~"))

# ── Config ──────────────────────────────────────────────────────────────
HERMES_SHARED = HOME / ".hermes" / "shared"
CANONICAL_TOKEN = HERMES_SHARED / "google_token.json"
CREDS_PATH = HOME / "Desktop" / "REX" / "google_credentials.json"
LOG_PATH = HOME / "Desktop" / "REX" / "logs" / "google_token_refresh.log"

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
HERMES_SHARED.mkdir(parents=True, exist_ok=True)

# Token symlinks that must point to canonical
TOKEN_SYMLINKS = [
    HOME / ".rex_google_token.json",
    HOME / "Desktop" / "REX" / ".rex_google_token.json",
]

# Refresh when < 1 hour until expiry (Google access tokens live 1 hour)
REFRESH_WINDOW_HOURS = 1

# ── Scopes ──────────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/drive",           # write access for uploads
]

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} | {msg}"
    print(line)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")

def check_status() -> dict:
    """Read token and return status dict."""
    if not CANONICAL_TOKEN.exists():
        return {"error": "no_token_file", "message": f"Canonical token missing: {CANONICAL_TOKEN}"}
    
    try:
        data = json.loads(CANONICAL_TOKEN.read_text())
    except json.JSONDecodeError as e:
        return {"error": "invalid_json", "message": str(e)}
    
    has_refresh = bool(data.get("refresh_token"))
    has_access = bool(data.get("access_token") or data.get("token"))
    expiry_str = data.get("expiry", "")
    
    expiry = None
    if expiry_str:
        try:
            expiry = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass
    
    now = datetime.now(timezone.utc)
    is_expired = expiry is not None and expiry < now
    hours_until = None
    if expiry:
        hours_until = (expiry - now).total_seconds() / 3600
    
    return {
        "has_refresh_token": has_refresh,
        "has_access_token": has_access,
        "expiry": expiry_str,
        "expired": is_expired,
        "hours_until_expiry": round(hours_until, 1) if hours_until is not None else None,
        "needs_refresh": is_expired or (hours_until is not None and hours_until < REFRESH_WINDOW_HOURS),
    }

def do_refresh() -> bool:
    """Attempt to refresh the access token. Returns True on success."""
    if not CREDS_PATH.exists():
        log(f"ERROR: Credentials file missing: {CREDS_PATH}")
        return False
    
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    try:
        creds = Credentials.from_authorized_user_file(str(CANONICAL_TOKEN), SCOPES)
    except Exception as e:
        log(f"ERROR: Failed to load credentials: {e}")
        return False
    
    if not creds.refresh_token:
        log("ERROR: No refresh_token in token file — full re-auth needed")
        return False
    
    try:
        creds.refresh(Request())
        CANONICAL_TOKEN.write_text(creds.to_json())
        log(f"Token refreshed — new expiry: {creds.expiry}")
        return True
    except Exception as e:
        msg = str(e)
        if "invalid_grant" in msg:
            log("REFRESH TOKEN REVOKED — full re-auth required! Run CC_google_reauth.py")
        else:
            log(f"Refresh failed: {e}")
        return False

def fix_symlinks():
    """Ensure all symlinks point to canonical token."""
    for link_path in TOKEN_SYMLINKS:
        try:
            if link_path.is_symlink():
                current_target = link_path.resolve()
                if current_target != CANONICAL_TOKEN:
                    link_path.unlink()
                    link_path.symlink_to(CANONICAL_TOKEN)
                    log(f"Symlink fixed: {link_path}")
            elif link_path.exists():
                link_path.unlink()
                link_path.symlink_to(CANONICAL_TOKEN)
                log(f"Replaced stale file with symlink: {link_path}")
            else:
                link_path.parent.mkdir(parents=True, exist_ok=True)
                link_path.symlink_to(CANONICAL_TOKEN)
                log(f"Symlink created: {link_path}")
        except Exception as e:
            log(f"Symlink check failed for {link_path}: {e}")

# ── Main ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if "--status" in sys.argv:
        status = check_status()
        print(json.dumps(status, indent=2))
        sys.exit(0)
    
    force = "--force" in sys.argv or "--test" in sys.argv
    log("=" * 50)
    mode = "FORCED" if force else "SCHEDULED"
    log(f"Google Token Refresh — {mode}")
    
    fix_symlinks()
    
    status = check_status()
    if "error" in status:
        log(f"ERROR: {status['message']}")
        sys.exit(1)
    
    log(f"  Expiry: {status['expiry']}")
    log(f"  Expired: {status['expired']}")
    log(f"  Hours until: {status['hours_until_expiry']}")
    log(f"  Has refresh: {status['has_refresh_token']}")
    
    if not status["has_refresh_token"]:
        log("No refresh token — full re-auth needed (CC_google_reauth.py)")
        sys.exit(1)
    
    if force or status["needs_refresh"]:
        log("Refreshing token...")
        success = do_refresh()
        if not success:
            sys.exit(1)
    else:
        log(f"Token still valid ({status['hours_until_expiry']}h remaining)")
    
    log("Done.")
