#!/bin/bash
# CC_setup_drive_service_account.command
# One-time setup: create a Google service account for Drive access.
# After this runs, the Drive preflight never needs OAuth again.

LOG="$HOME/Desktop/REX/logs/setup_drive_sa.log"
mkdir -p "$HOME/Desktop/REX/logs"

SA_KEY="$HOME/.rex_drive_service_account.json"
PYTHON="$HOME/.rex-venv/bin/python3"

{
echo "════════════════════════════════════════════════════════"
echo " GOJ Drive — Service Account Setup"
echo " $(date)"
echo "════════════════════════════════════════════════════════"
echo ""

# ── Already installed: test connection ──────────────────────────────────────
if [ -f "$SA_KEY" ]; then
    echo "✅ Service account key found at $SA_KEY"
    echo ""
    echo "Testing connection to Google Sheets API..."
    "$PYTHON" - <<'PYEOF'
import sys
from pathlib import Path

SA_KEY = Path.home() / ".rex_drive_service_account.json"
SIGN_IN_ID = "112lNtvdBCIEQY4aDrjc3tB68CB4oVaJz-E0b0mX4RyU"

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        str(SA_KEY),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    svc = build("sheets", "v4", credentials=creds)
    meta = svc.spreadsheets().get(spreadsheetId=SIGN_IN_ID).execute()
    title = meta.get("properties", {}).get("title", "unknown")
    print(f"  ✅ Connected! Spreadsheet: {title}")
    print(f"  ✅ Service account auth is working — preflight will use it automatically.")
except Exception as e:
    print(f"  ❌ Connection failed: {e}")
    print()
    print("  If you just installed the key, make sure you shared the spreadsheets.")
    print("  See the 3 spreadsheet links in Step 3 below.")
PYEOF
    echo ""

else
    # ── Not installed: print instructions ───────────────────────────────────
    echo "Service account key not found. Follow these steps (~5 minutes):"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo " STEP 1 — Create service account in Google Cloud Console"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "  1. Open: https://console.cloud.google.com"
    echo "  2. Select your project (or create one called 'goj-ops')"
    echo "  3. Go to: IAM & Admin → Service Accounts"
    echo "  4. Click 'Create Service Account'"
    echo "     Name: goj-drive-reader"
    echo "     Click DONE (no roles needed)"
    echo "  5. Click the new account → Keys tab → Add Key → JSON"
    echo "  6. Download the JSON file"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo " STEP 2 — Install the key"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "  Open Terminal and run (replace filename):"
    echo "  mv ~/Downloads/goj-ops-*.json $SA_KEY"
    echo "  chmod 600 $SA_KEY"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo " STEP 3 — Share the GOJ spreadsheets with the service account"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "  After installing the key, run this to get the email:"
    echo "  python3 -c \"import json; d=json.load(open('$SA_KEY')); print(d['client_email'])\""
    echo ""
    echo "  Share these 3 spreadsheets with that email (Viewer role):"
    echo ""
    echo "  Sign-in / Attendance:"
    echo "  https://docs.google.com/spreadsheets/d/112lNtvdBCIEQY4aDrjc3tB68CB4oVaJz-E0b0mX4RyU"
    echo ""
    echo "  Menu Sheet S1:"
    echo "  https://docs.google.com/spreadsheets/d/1IfBJbKleeqA329FI3WeoFQp2xqmKYRJiy_I7RC2ZBcw"
    echo ""
    echo "  Menu Sheet S2:"
    echo "  https://docs.google.com/spreadsheets/d/18rs4xZHmdjt78za9tsh1bse94q-9Vn-pKXcnjID3ER0"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo " STEP 4 — Run this script again to verify"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "  Double-click CC_setup_drive_service_account.command again."
    echo "  It will test the connection and confirm everything works."
    echo ""
    echo "Waiting for key file (drops $SA_KEY to continue)..."
    for i in $(seq 1 120); do
        if [ -f "$SA_KEY" ]; then
            chmod 600 "$SA_KEY"
            echo ""
            echo "✅ Key file detected!"
            SA_EMAIL=$("$PYTHON" -c "import json; d=json.load(open('$SA_KEY')); print(d['client_email'])" 2>/dev/null)
            if [ -n "$SA_EMAIL" ]; then
                echo ""
                echo "Service account email:"
                echo "  $SA_EMAIL"
                echo ""
                echo "Share the 3 spreadsheets above with this email (Viewer),"
                echo "then run this script again to verify."
            fi
            break
        fi
        sleep 2
    done
fi
} 2>&1 | tee "$LOG"

read -n 1 -s -p "Press any key to close."
echo ""
