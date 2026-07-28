#!/bin/bash
# CC_setup_gmail_imap.command
# One-time setup: save Gmail App Password so the scan watcher never expires.
# Run once. Takes 2 minutes. Done forever.

LOG="$HOME/Desktop/REX/logs/CC_setup_gmail_imap_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✅  $1${NC}"; }
fail() { echo -e "${RED}❌  $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️   $1${NC}"; }
info() { echo -e "${CYAN}ℹ️   $1${NC}"; }

echo -e "${BOLD}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   Gmail IMAP Setup — One Time, Done Forever      ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════╝${NC}"
echo ""

IMAP_CFG="$HOME/.rex_gmail_imap.json"
VENV="$HOME/debate-chamber/.venv"
EMAIL="atigerclawai@gmail.com"

# ── Step 1: Get the App Password ──────────────────────────────────────────────
echo -e "${BOLD}Step 1: Get your Gmail App Password${NC}"
echo ""
echo "  1. Open this link in Chrome (copy/paste):"
echo -e "     ${CYAN}https://myaccount.google.com/apppasswords${NC}"
echo ""
echo "  2. Sign in as $EMAIL if asked"
echo "  3. In 'App name' type:  REX Scanner"
echo "  4. Click 'Create'"
echo "  5. Google shows a 16-character password — copy it"
echo ""
echo -e "${YELLOW}NOTE: You need 2-Step Verification enabled on your Google account.${NC}"
echo -e "${YELLOW}      If prompted, enable it first at: https://myaccount.google.com/security${NC}"
echo ""

# Check if already configured
if [ -f "$IMAP_CFG" ]; then
    EXISTING=$(python3 -c "import json; d=json.load(open('$IMAP_CFG')); print(d.get('app_password','')[:4])" 2>/dev/null)
    if [ -n "$EXISTING" ]; then
        warn "App Password already saved (starts with: ${EXISTING}****)"
        echo ""
        read -r -p "Enter new password to replace it, or press Enter to keep existing: " NEW_PW
        if [ -z "$NEW_PW" ]; then
            info "Keeping existing password — running connection test..."
        else
            APP_PW=$(echo "$NEW_PW" | tr -d ' ')
        fi
    fi
fi

if [ -z "$APP_PW" ] && ! [ -f "$IMAP_CFG" ]; then
    echo ""
    read -r -s -p "Paste your 16-character App Password (input hidden): " APP_PW
    echo ""
    APP_PW=$(echo "$APP_PW" | tr -d ' ')
fi

# ── Step 2: Save the config ───────────────────────────────────────────────────
if [ -n "$APP_PW" ]; then
    python3 -c "
import json
cfg = {'email': '$EMAIL', 'app_password': '$APP_PW', 'imap_host': 'imap.gmail.com', 'imap_port': 993}
with open('$IMAP_CFG', 'w') as f:
    json.dump(cfg, f, indent=2)
print('saved')
"
    chmod 600 "$IMAP_CFG"
    ok "App Password saved to $IMAP_CFG (mode 600 — private)"
fi

# ── Step 3: Test the connection ───────────────────────────────────────────────
echo ""
info "Testing IMAP connection to Gmail..."

python3 - <<PYEOF
import json, imaplib, sys
try:
    with open("$IMAP_CFG") as f:
        cfg = json.load(f)
    pw = cfg.get("app_password", "")
    if not pw:
        print("❌  No app password in config")
        sys.exit(1)
    mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    mail.login("$EMAIL", pw)
    status, data = mail.select("INBOX")
    count = data[0].decode() if data and data[0] else "?"
    mail.logout()
    print(f"✅  Connected to Gmail as $EMAIL")
    print(f"   INBOX: {count} messages")
    sys.exit(0)
except imaplib.IMAP4.error as e:
    print(f"❌  IMAP login failed: {e}")
    print("   Double-check the App Password is correct and 2FA is enabled")
    sys.exit(1)
except Exception as e:
    print(f"❌  Connection error: {e}")
    sys.exit(1)
PYEOF

RESULT=$?

if [ $RESULT -eq 0 ]; then
    echo ""
    ok "Gmail IMAP is working — scan watcher will never expire again"

    # Reload REX backend to pick up the new config
    PLIST="$HOME/Library/LaunchAgents/com.rex.backend.plist"
    if [ -f "$PLIST" ]; then
        info "Reloading REX backend..."
        launchctl unload "$PLIST" 2>/dev/null
        sleep 3
        launchctl load "$PLIST" 2>/dev/null
        sleep 2
        # Quick health check
        HTTP=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 http://localhost:8000/api/health 2>/dev/null)
        if [[ "$HTTP" =~ ^[23] ]]; then
            ok "REX backend reloaded and healthy (HTTP $HTTP)"
        else
            warn "REX backend reloaded — health check returned $HTTP (may still be starting)"
        fi
    fi
else
    echo ""
    fail "Connection test failed — check the App Password and try again"
fi

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   Setup complete — scan watcher is permanent     ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo "Config: $IMAP_CFG"
echo "Log:    $LOG"
echo ""; read -n 1 -p "Press any key..."
