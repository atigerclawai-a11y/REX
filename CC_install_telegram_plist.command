#!/bin/bash
# ====================================================================
#  CC_install_telegram_plist — Install com.rex.telegram-bot.plist
#  Replaces the terminal-tied background process with a proper
#  launchd-managed service that auto-restarts on crash/reboot.
# ====================================================================
LOG="$HOME/Desktop/REX/logs/rex_telegram.log"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Installing @RexOfGold_bot as launchd service        ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# 1. Kill ALL existing instances (including the terminal-tied one)
echo "→ Killing any running rex_telegram_bot.py processes..."
pkill -9 -f rex_telegram_bot.py 2>/dev/null
sleep 3
echo "  Done."

# 2. Copy plist to LaunchAgents
echo "→ Installing plist..."
cp "$HOME/Desktop/REX/launchd/com.rex.telegram-bot.plist" \
   "$HOME/Library/LaunchAgents/com.rex.telegram-bot.plist"
echo "  Copied."

# 3. Load it
echo "→ Loading with launchctl..."
launchctl unload "$HOME/Library/LaunchAgents/com.rex.telegram-bot.plist" 2>/dev/null
sleep 2
launchctl load "$HOME/Library/LaunchAgents/com.rex.telegram-bot.plist"
echo "  Loaded."

# 4. Wait and verify
echo "→ Waiting 20s for clean startup..."
sleep 20

echo ""
echo "→ Last 5 log lines:"
tail -5 "$LOG"
echo ""

# Check result — only look at lines AFTER the most recent startup
STARTUP_LINE=$(grep -n "REX Telegram bot started" "$LOG" | tail -1 | cut -d: -f1)
if [ -n "$STARTUP_LINE" ]; then
    ERRORS_AFTER=$(tail -n +"$STARTUP_LINE" "$LOG" | grep -c "409\|401" || true)
    if [ "$ERRORS_AFTER" -eq 0 ]; then
        echo "✅  @RexOfGold_bot is running cleanly under launchd."
        echo "    It will auto-restart on crash and survive reboots."
    elif grep -q "409" <(tail -n +"$STARTUP_LINE" "$LOG"); then
        echo "⚠️  409 Conflict after startup — another process using same token."
        echo "    Run: launchctl list | grep -i telegram"
        echo "    Run: ps aux | grep -i telegram | grep -v grep"
    else
        echo "⚠️  401 Unauthorized — token in rex_telegram_config.json may be wrong."
    fi
else
    echo "ℹ️  Bot hasn't logged a startup yet. Give it another 10s."
fi

echo ""
read -n 1 -p "Press any key to close..."
