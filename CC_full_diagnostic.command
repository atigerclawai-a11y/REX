#!/bin/bash
# CC_full_diagnostic.command — full system diagnostic
# Covers: Hermes gateway, Hermes Desktop, dock, Jarvis, Instagram hint
LOG=~/Desktop/REX/logs/full_diag_$(date +%Y%m%d_%H%M%S).log
mkdir -p ~/Desktop/REX/logs
exec > >(tee "$LOG") 2>&1

echo "╔══════════════════════════════════════════╗"
echo "║     FULL SYSTEM DIAGNOSTIC               ║"
echo "║     $(date)          ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. HERMES GATEWAY ────────────────────────────────────────────────────────
echo "━━━ [1/6] HERMES CLOUD GATEWAY ━━━"
launchctl list | grep "hermes.gateway"
echo ""
HEALTH=$(curl -s --max-time 6 http://localhost:3002/health 2>/dev/null)
echo "Health: $HEALTH"
echo ""
echo "Last 10 gateway.log lines:"
tail -10 ~/.hermes/profiles/cloud/logs/gateway.log 2>/dev/null
echo ""
echo "Telegram conflict check (last 5 lines):"
tail -5 ~/.hermes/profiles/cloud/logs/gateway.log 2>/dev/null | grep -i "telegram\|conflict\|error" || echo "  No recent Telegram errors"
echo ""

# ── 2. HERMES DESKTOP ────────────────────────────────────────────────────────
echo "━━━ [2/6] HERMES DESKTOP ━━━"
HERMES_APP=~/.hermes/hermes-agent/apps/desktop/release/mac-arm64/Hermes.app
if [ -d "$HERMES_APP" ]; then
    echo "✅ Hermes Desktop app exists at: $HERMES_APP"
    # Check version
    cat "$HERMES_APP/Contents/Info.plist" 2>/dev/null | grep -A1 "CFBundleShortVersionString\|CFBundleVersion" | head -6
else
    echo "❌ Hermes Desktop app NOT found"
fi
echo ""
pgrep -f "Hermes.app" && echo "✅ Hermes Desktop process running" || echo "⚠️  Hermes Desktop not running"
echo ""

# ── 3. DOCK ───────────────────────────────────────────────────────────────────
echo "━━━ [3/6] DOCK ━━━"
pgrep -x Dock && echo "✅ Dock IS running (PID: $(pgrep -x Dock))" || echo "❌ Dock NOT running"
echo ""
echo "Dock autohide setting:"
defaults read com.apple.dock autohide 2>/dev/null && echo "(1=hidden, 0=visible)" || echo "  autohide key not set (= visible/default)"
echo ""
echo "Recent Dock crashes:"
ls -t ~/Library/Logs/DiagnosticReports/Dock_*.crash 2>/dev/null | head -3 || echo "  None found"
echo ""

# ── 4. DOCK WATCHDOG LAUNCHAGENT ─────────────────────────────────────────────
echo "━━━ [4/6] INSTALLING DOCK WATCHDOG LAUNCHAGENT ━━━"
PLIST=~/Library/LaunchAgents/com.kato.dock-watchdog.plist
WATCH_SCRIPT=~/Desktop/REX/dock_watchdog.sh

# Write the watchdog shell script
cat > "$WATCH_SCRIPT" << 'WATCHDOG'
#!/bin/bash
# Dock keepalive — auto-restarts Dock if it dies (e.g. after Jarvis screensaver)
while true; do
    if ! pgrep -x Dock > /dev/null; then
        defaults delete com.apple.dock autohide 2>/dev/null
        open /System/Library/CoreServices/Dock.app
        echo "$(date): Dock restarted" >> ~/Desktop/REX/logs/dock_watchdog.log
    fi
    sleep 8
done
WATCHDOG
chmod +x "$WATCH_SCRIPT"

# Write the LaunchAgent plist
cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.kato.dock-watchdog</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$WATCH_SCRIPT</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$HOME/Desktop/REX/logs/dock_watchdog.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/Desktop/REX/logs/dock_watchdog_err.log</string>
</dict>
</plist>
EOF

# Unload if already running, reload fresh
launchctl unload "$PLIST" 2>/dev/null
launchctl load "$PLIST"
echo "Watchdog LaunchAgent status:"
launchctl list | grep "dock-watchdog" || echo "  (not yet visible — may take a moment)"
echo ""

# ── 5. JARVIS SCREENSAVER ────────────────────────────────────────────────────
echo "━━━ [5/6] JARVIS SCREENSAVER ━━━"
echo "Jarvis runs as browser-based HTML at ~/hermes-hub/www/screensaver.html"
echo "Root cause of dock issue: Chrome fullscreen mode hides dock;"
echo "when window closes, macOS sometimes fails to restore dock."
echo "Fix: dock watchdog above will catch this and restore dock within 8 seconds."
echo ""
echo "Hermes Hub server (port 9000):"
curl -s --max-time 4 http://localhost:9000/health 2>/dev/null || echo "  Not responding on 9000"
echo ""
HERMES_HUB_PID=$(pgrep -f "hermes-hub/server.py\|tigerclaw\|port.*9000" 2>/dev/null | head -1)
[ -n "$HERMES_HUB_PID" ] && echo "Hub process: PID $HERMES_HUB_PID" || echo "Hub process: not detected"
echo ""

# ── 6. SERVICES OVERVIEW ─────────────────────────────────────────────────────
echo "━━━ [6/6] SERVICES OVERVIEW ━━━"
echo "launchctl services:"
launchctl list | grep -E "hermes|rex|goj|tigerclaw|n8n|openwebui|claus|rexxie|dock" 2>/dev/null
echo ""
echo "Port checks:"
for port in 3002 8000 8080 9000 65001 27226 3000 3080; do
    RESP=$(curl -s --max-time 3 http://localhost:$port/health 2>/dev/null | head -c 60)
    [ -n "$RESP" ] && echo "  ✅ :$port → $RESP" || echo "  ⚠️  :$port → not responding"
done
echo ""

echo "━━━ NOTES ━━━"
echo "Instagram: browser-based issue (cookies/session). Not diagnosable from terminal."
echo "  Fix: clear Instagram cookies in Chrome, log back in."
echo ""
echo "Hermes on Chrome: Chrome extension — check chrome://extensions for status."
echo "  If gateway health shows ok above, extension just needs to reconnect."
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     DIAGNOSTIC COMPLETE                  ║"
echo "╚══════════════════════════════════════════╝"
read -p "Press Enter to close..."
