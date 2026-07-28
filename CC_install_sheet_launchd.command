#!/bin/bash
# CC_install_sheet_launchd.command
# Installs the daily GOJ sheet generator to run automatically at 3:15 PM every day.
# Run this ONCE. After that, sheets generate automatically — no manual intervention needed.

LOG="$HOME/Desktop/REX/logs/install_sheet_launchd.log"
mkdir -p "$HOME/Desktop/REX/logs"

PLIST_SRC="$HOME/Desktop/REX/com.goj.daily_sheets.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.goj.daily_sheets.plist"
PYTHON="$HOME/.rex-venv/bin/python3"
SCRIPT="$HOME/Documents/goj files/dashboard/generate_tomorrow.py"

{
echo "════════════════════════════════════════════════════════"
echo " GOJ Daily Sheet Automation — Install"
echo " $(date)"
echo "════════════════════════════════════════════════════════"
echo ""

# ── Verify dependencies ─────────────────────────────────────────────────────
if [ ! -f "$PYTHON" ]; then
    echo "❌ ERROR: Python venv not found at $PYTHON"
    exit 1
fi
echo "✅ Python venv: OK"

if [ ! -f "$SCRIPT" ]; then
    echo "❌ ERROR: generate_tomorrow.py not found at $SCRIPT"
    exit 1
fi
echo "✅ Generator script: OK"

if [ ! -f "$PLIST_SRC" ]; then
    echo "❌ ERROR: plist not found at $PLIST_SRC"
    echo "   Make sure com.goj.daily_sheets.plist is in ~/Desktop/REX/"
    exit 1
fi
echo "✅ Plist source: OK"
echo ""

# ── Install plist ──────────────────────────────────────────────────────────
echo "Installing launchd job..."
cp "$PLIST_SRC" "$PLIST_DST"

# Unload if already running
launchctl unload "$PLIST_DST" 2>/dev/null

# Load fresh
launchctl load "$PLIST_DST"
LOAD_EXIT=$?

if [ $LOAD_EXIT -eq 0 ]; then
    echo "✅ Installed: com.goj.daily_sheets"
else
    echo "❌ launchctl load failed (exit $LOAD_EXIT)"
    exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " AUTOMATION ACTIVE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo " Runs: every day at 3:15 PM"
echo " Generates: tomorrow's signin + drivers + kitchen + distribution"
echo " Sends: all PDFs to Telegram automatically"
echo " Log: ~/Desktop/REX/logs/daily_sheets.log"
echo ""
echo " Coverage:"
echo "   Mon–Fri 3:15 PM → next day's sheets (Tue–Sat)"
echo "   Sat 3:15 PM     → Sunday sheets"
echo "   Sun 3:15 PM     → Monday sheets"
echo ""
echo " ⚠️  IMPORTANT: Mac must be ON and logged in at 3:15 PM"
echo "     If it's asleep, sheets won't generate for that day."
echo "     For missed days, use CC_run_sheets_now.command"
echo ""

# ── Verify it's loaded ─────────────────────────────────────────────────────
STATUS=$(launchctl list | grep "com.goj.daily_sheets" || echo "NOT FOUND")
echo "launchctl status: $STATUS"
echo ""
echo "════════════════════════════════════════════════════════"
echo " DONE — sheets will auto-generate at 3:15 PM daily"
echo "════════════════════════════════════════════════════════"
} 2>&1 | tee "$LOG"

read -n 1 -s -p "Press any key to close."
echo ""
