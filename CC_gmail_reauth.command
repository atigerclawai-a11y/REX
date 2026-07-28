#!/bin/bash
# CC_gmail_reauth.command — One-click Gmail + Drive re-auth
# Double-click to run. Browser will open automatically.
# Run this ONCE. After that, the token auto-refreshes forever.

set -e

LOG="$HOME/Desktop/REX/logs/gmail_reauth_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

echo "================================================"
echo " Gmail OAuth Re-auth — Gold Health Systems"
echo " $(date)"
echo "================================================"
echo ""

source ~/debate-chamber/.venv/bin/activate
cd ~/Desktop/REX

echo "🔐 Deleting stale token(s)..."
rm -f ~/.rex_google_token.json ~/.rex_gdrive_token.json ~/.hermes/shared/google_token.json
echo "   Done."
echo ""

echo "🌐 Opening Google auth in browser..."
echo "   → Sign in as: atigerclawai@gmail.com"
echo "   → Grant ALL requested permissions (Gmail + Drive)"
echo "   → You should see a success page in the browser"
echo ""
# CC_google_reauth.py requests the FULL scope set (Gmail read+modify, Drive read+metadata),
# uses access_type=offline + prompt=consent to GUARANTEE a fresh refresh_token,
# and writes the canonical token to ~/.hermes/shared/google_token.json with symlinks.
# This is what unblocks the live Drive → TransitionAgent → dashboard pipeline.
python CC_google_reauth.py

echo ""
echo "🧪 Testing Gmail + Drive connection..."
python - <<'PYEOF'
import sys, json, os
sys.path.insert(0, 'backend')

# 1. Gmail
from rex_gmail import _get_service
try:
    svc = _get_service()
    profile = svc.users().getProfile(userId='me').execute()
    print(f"✅ Gmail connected as: {profile['emailAddress']}")
    print(f"   Total messages: {profile.get('messagesTotal', '?')}")
except Exception as e:
    print(f"❌ Gmail connection test failed: {e}")
    exit(1)

# 2. Drive — verify the new Drive scopes actually work
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
tok_path = os.path.expanduser("~/.rex_google_token.json")
tok = json.load(open(tok_path))
print(f"   Scopes on token: {len(tok.get('scopes', []))} → {tok.get('scopes')}")
try:
    creds = Credentials.from_authorized_user_file(tok_path)
    drive = build('drive', 'v3', credentials=creds)
    about = drive.about().get(fields="user(emailAddress)").execute()
    print(f"✅ Drive connected as: {about['user']['emailAddress']}")
except Exception as e:
    print(f"❌ Drive connection test failed: {e}")
    exit(1)
PYEOF

echo ""
echo "✅ Re-auth complete."
echo "   Token saved (canonical): ~/.hermes/shared/google_token.json"
echo "   Symlinks: ~/.rex_google_token.json + ~/Desktop/REX/.rex_google_token.json"
echo "   The OCR watcher will pick up missed menus on its next poll (within 5 min)."
echo "   The Drive watcher (com.goj.drive-watcher) will resume downloads next cycle."
echo "   The TransitionAgent live feed is now back online."
echo ""
echo "   Log saved to: $LOG"
echo ""
echo "Press any key to close..."
read -n 1
