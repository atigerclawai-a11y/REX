#!/bin/bash
# CC_install_stats_api.command — Install CC_stats_api as a permanent LaunchAgent
# Makes hermestigerclaw.com/progress and hermestigerclaw.com/live work 24/7
# Run once; survives reboots.
exec > >(tee "$HOME/Desktop/REX/logs/install_stats_api_$(date +%Y%m%d_%H%M%S).log") 2>&1

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
pass(){ echo -e "${GREEN}✅  $1${NC}"; }
fail(){ echo -e "${RED}❌  $1${NC}"; }
info(){ echo -e "${CYAN}ℹ️   $1${NC}"; }
warn(){ echo -e "${YELLOW}⚠️   $1${NC}"; }

echo -e "${BOLD}=== GHS STATS API INSTALLER ===${NC}"
echo "Time: $(date)"
echo "Purpose: CC_stats_api.py → port 8001 → hermestigerclaw.com/progress"
echo ""

REX_DIR="$HOME/Desktop/REX"
VENV="$HOME/.rex-venv"
DEV_VENV="$HOME/debate-chamber/.venv"
LOG_DIR="$REX_DIR/logs"
PLIST="$HOME/Library/LaunchAgents/com.ghs.stats-api.plist"

mkdir -p "$LOG_DIR"

# ─── 1. Find the right uvicorn ────────────────────────────────────────────────
echo -e "${BOLD}[1/4] Finding Python environment...${NC}"

UVICORN=""
if [ -f "$VENV/bin/uvicorn" ]; then
    UVICORN="$VENV/bin/uvicorn"
    pass "Using ~/.rex-venv/bin/uvicorn"
elif [ -f "$DEV_VENV/bin/uvicorn" ]; then
    UVICORN="$DEV_VENV/bin/uvicorn"
    warn "~/.rex-venv not found — using debate-chamber venv"
    warn "Note: launchd may have TCC restrictions on Desktop access"
    warn "If /progress shows 404 on the API data, run CC_rex_venv_sync.command"
else
    fail "No uvicorn found in ~/.rex-venv or ~/debate-chamber/.venv"
    echo "  Install: source ~/debate-chamber/.venv/bin/activate && pip install uvicorn fastapi"
    read -p "Press Enter to exit..."; exit 1
fi

# ─── 2. Test the API locally ──────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[2/4] Testing CC_stats_api.py...${NC}"
info "Quick syntax check..."
"$UVICORN" --version > /dev/null 2>&1 && pass "uvicorn OK" || fail "uvicorn error"

if [ -f "$REX_DIR/CC_stats_api.py" ]; then
    pass "CC_stats_api.py found"
else
    fail "CC_stats_api.py not found at $REX_DIR"
    read -p "Press Enter to exit..."; exit 1
fi

if [ -f "$REX_DIR/CC_live_progress_v2.html" ]; then
    pass "CC_live_progress_v2.html found (served at /progress)"
else
    warn "CC_live_progress_v2.html not found — /progress endpoint will 404"
fi

# ─── 3. Unload any old instance ───────────────────────────────────────────────
echo ""
echo -e "${BOLD}[3/4] Removing old Stats API service...${NC}"
launchctl unload "$PLIST" 2>/dev/null && info "Unloaded old plist" || info "No old plist to unload"
# Kill any existing process on 8001
lsof -ti:8001 | xargs kill -9 2>/dev/null && info "Killed existing :8001 process" || true
sleep 1

# ─── 4. Install LaunchAgent ───────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[4/4] Installing LaunchAgent...${NC}"

cat > "$PLIST" << ENDPLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ghs.stats-api</string>
    <key>ProgramArguments</key>
    <array>
        <string>$UVICORN</string>
        <string>CC_stats_api:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>8001</string>
        <string>--log-level</string>
        <string>warning</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$REX_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/stats_api.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/stats_api_err.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>
ENDPLIST

launchctl load "$PLIST"
sleep 3

# ─── Verify ───────────────────────────────────────────────────────────────────
echo ""
if launchctl list | grep -q "com.ghs.stats-api"; then
    STATUS=$(launchctl list | grep "com.ghs.stats-api" | awk '{print $2}')
    if [ "$STATUS" = "0" ] || [ "$STATUS" = "-" ]; then
        pass "com.ghs.stats-api LOADED and running"
    else
        warn "com.ghs.stats-api loaded but exit code: $STATUS (check logs below)"
    fi
else
    fail "LaunchAgent did not load"
fi

echo ""
info "Testing :8001/health..."
HEALTH=$(curl -s --max-time 5 http://localhost:8001/health 2>/dev/null)
if echo "$HEALTH" | grep -q '"status"'; then
    pass "Stats API responding at :8001"
else
    warn ":8001 not responding yet (may still be starting — wait 10s and retry)"
    echo "  Manual test: curl http://localhost:8001/health"
fi

info "Testing /progress page..."
CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:8001/progress 2>/dev/null)
if [ "$CODE" = "200" ]; then
    pass "/progress serving CC_live_progress_v2.html (HTTP 200)"
else
    warn "/progress returned HTTP $CODE"
fi

echo ""
echo -e "${BOLD}=== STATS API INSTALLED ===${NC}"
echo ""
echo "  Local:   http://localhost:8001/progress"
echo "  Domain:  https://hermestigerclaw.com/progress  (via Cloudflare tunnel)"
echo ""
echo "  Note: hermestigerclaw.com/progress requires the Cloudflare tunnel"
echo "  to route /progress to localhost:8001. Run CC_gateway_audit.command"
echo "  to verify tunnel routing is correct."
echo ""
echo "  Logs:    $LOG_DIR/stats_api.log"
echo "  Control: launchctl {load|unload} $PLIST"
echo ""
read -p "Press Enter to close..."
