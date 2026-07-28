#!/usr/bin/env python3
"""
CC_google_reauth.py — One-Time Google OAuth Reauthorization
=============================================================
Run ONCE to get a fresh refresh_token. Saves to canonical location.
All symlinked consumers (rex_gmail.py, himalaya, TransitionAgent, OCR watcher)
will pick it up automatically.

This MUST be run interactively — it opens a browser for Google sign-in.

Usage:
    python3 CC_google_reauth.py              # Interactive (opens browser)
    python3 CC_google_reauth.py --headless    # Print URL, paste code
"""

import json
import shutil
import sys
from pathlib import Path

HOME = Path.home()

# ── Paths ──────────────────────────────────────────────────────────────
CREDS_PATH = HOME / "Desktop" / "REX" / "google_credentials.json"
CANONICAL_TOKEN = HOME / ".hermes" / "shared" / "google_token.json"
TOKEN_SYMLINKS = [
    HOME / ".rex_google_token.json",
    HOME / "Desktop" / "REX" / ".rex_google_token.json",
]

# ── Scopes ─────────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/drive",           # write access for uploads
]

HEADLESS = "--headless" in sys.argv

# ── Check credentials ──────────────────────────────────────────────────
if not CREDS_PATH.exists():
    raise SystemExit(f"ERROR: Credentials not found at {CREDS_PATH}\n"
                      "Download from Google Cloud Console → APIs & Services → Credentials")

creds_data = json.loads(CREDS_PATH.read_text())
if "installed" not in creds_data:
    raise SystemExit("ERROR: Credentials file is not in 'installed app' format")

print(f"📋 Client ID: {creds_data['installed']['client_id'][:40]}...")
print(f"🔑 Scopes: {len(SCOPES)} (Gmail read/modify + Drive read)")
print()

# ── Run OAuth flow ────────────────────────────────────────────────────
from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_secrets_file(
    str(CREDS_PATH),
    SCOPES,
    # Force refresh_token every time — NEVER skip
    autogenerate_code_verifier=True,
)

# CRITICAL: These two params ensure we ALWAYS get a refresh_token
extra_params = {
    "access_type": "offline",   # ← forces refresh_token
    "prompt": "consent",        # ← forces re-consent every time (guarantees fresh token)
}

if HEADLESS:
    # For headless: use out-of-band redirect
    flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
    auth_url, _ = flow.authorization_url(**extra_params)
    print("🔗 Open this URL in your browser:\n")
    print(f"    {auth_url}\n")
    code = input("Paste the authorization code: ").strip()
    flow.fetch_token(code=code)
else:
    # Opens browser automatically — run_local_server handles redirect internally
    creds = flow.run_local_server(
        port=0,
        authorization_prompt_message="",
        success_message="✅ Authorized! You may close this window.",
        open_browser=True,
        **extra_params,
    )
    print(f"\n✅ Token obtained from Google")

# ── Verify we got a refresh_token ─────────────────────────────────────
if not hasattr(flow, 'credentials') and 'creds' not in dir():
    # fetch_token was used in headless mode
    creds = flow.credentials

if not creds.refresh_token:
    raise SystemExit(
        "❌ ERROR: Google did NOT return a refresh_token!\n"
        "   This happens when you've already authorized this app recently.\n"
        "   Fix: Go to https://myaccount.google.com/permissions\n"
        "   → Remove 'solid-idiom-489906-g7' (or similar)\n"
        "   → Then re-run this script."
    )

print(f"   Refresh token: ✅ present ({creds.refresh_token[:20]}...)")
print(f"   Expiry: {creds.expiry}")

# ── Save to canonical location ───────────────────────────────────────
CANONICAL_TOKEN.parent.mkdir(parents=True, exist_ok=True)

# Backup old token
if CANONICAL_TOKEN.exists():
    backup = CANONICAL_TOKEN.with_suffix(".json.bak")
    shutil.copy2(CANONICAL_TOKEN, backup)
    print(f"\n📦 Old token backed up to: {backup}")

# Write new token
CANONICAL_TOKEN.write_text(creds.to_json())
print(f"💾 Token saved to: {CANONICAL_TOKEN}")

# ── Verify symlinks ───────────────────────────────────────────────────
print()
for link_path in TOKEN_SYMLINKS:
    if link_path.exists() or link_path.is_symlink():
        if link_path.is_symlink() and link_path.resolve() == CANONICAL_TOKEN:
            print(f"✅ Symlink OK: {link_path}")
        else:
            # Broken or wrong target — recreate
            link_path.unlink(missing_ok=True)
            link_path.symlink_to(CANONICAL_TOKEN)
            print(f"🔧 Symlink fixed: {link_path} → {CANONICAL_TOKEN}")
    else:
        link_path.parent.mkdir(parents=True, exist_ok=True)
        link_path.symlink_to(CANONICAL_TOKEN)
        print(f"🔧 Symlink created: {link_path} → {CANONICAL_TOKEN}")

print()
print("=" * 60)
print("✅ Google OAuth reauthorization complete.")
print()
print("   Next: Run the auto-refresh test to verify:")
print(f"   python3 CC_google_token_refresh.py --test")
print()
print("   Auto-refresh cron job should be installed separately.")
print("=" * 60)
