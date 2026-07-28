#!/bin/bash
# ====================================================================
#  CC_install_pdf_watcher_plist — Install com.rex.email-pdf-watcher
#  Uses KeepAlive+ThrottleInterval (same pattern as telegram bot)
#  so it bootstraps reliably on modern macOS.
# ====================================================================
LOG_DIR="$HOME/Desktop/REX/logs"
PLIST_SRC="$HOME/Desktop/REX/launchd/com.rex.email-pdf-watcher.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.rex.email-pdf-watcher.plist"
LABEL="com.rex.email-pdf-watcher"
DOMAIN="gui/$(id -u)"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Installing pdf_watcher as launchd service           ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# 1. Copy updated plist
echo "→ Copying updated plist (KeepAlive mode)..."
cp "$PLIST_SRC" "$PLIST_DST"
echo "  Done."

# 2. Remove old registration
echo "→ Removing old registration..."
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null && echo "  Booted out." || echo "  (none to remove)"
launchctl unload "$PLIST_DST" 2>/dev/null
sleep 2

# 3. Bootstrap (modern API first, fallback to legacy)
echo "→ Registering with launchd..."
if launchctl bootstrap "$DOMAIN" "$PLIST_DST" 2>/dev/null; then
    echo "  Bootstrapped (modern API)."
elif launchctl load -w "$PLIST_DST" 2>/dev/null; then
    echo "  Loaded (legacy API)."
else
    echo "  ⚠️  Both APIs failed. Trying kickstart..."
    launchctl enable "$DOMAIN/$LABEL" 2>/dev/null
    launchctl kickstart -k "$DOMAIN/$LABEL" 2>/dev/null && echo "  Kickstarted." || echo "  ❌ All methods failed — try rebooting."
fi

sleep 5

# 4. Verify
echo ""
echo "→ Service status:"
RESULT=$(launchctl list | grep "$LABEL")
if [ -n "$RESULT" ]; then
    echo "  ✅  $RESULT"
else
    echo "  ⚠️  Not in launchctl list"
fi

echo ""
echo "→ Last 3 log lines (if any):"
tail -3 "$LOG_DIR/pdf_watcher.log" 2>/dev/null || echo "  (no log yet)"

echo ""
read -n 1 -p "Press any key to close..."
