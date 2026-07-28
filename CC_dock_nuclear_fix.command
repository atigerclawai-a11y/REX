#!/bin/bash
# CC_dock_nuclear_fix.command — GHS Dock Nuclear Fix
# Destroys dock preferences, rebuilds from scratch, installs persistent enforcer
# Run ONCE after logging in. The LaunchAgent handles every restart after.
exec > >(tee "$HOME/Desktop/REX/logs/dock_nuclear_$(date +%Y%m%d_%H%M%S).log") 2>&1

echo "=== GHS DOCK NUCLEAR FIX ==="
echo "Time: $(date)"
echo ""

# 1. Kill everything related to Dock
echo "[1/7] Killing Dock processes..."
killall -9 Dock 2>/dev/null
sleep 1

# 2. Delete the dock plist entirely (macOS will recreate it)
echo "[2/7] Deleting dock preferences..."
rm -f "$HOME/Library/Preferences/com.apple.dock.plist"
defaults delete com.apple.dock 2>/dev/null
sleep 1

# 3. Apply fresh settings
echo "[3/7] Applying dock settings..."
defaults write com.apple.dock autohide           -bool  false
defaults write com.apple.dock autohide-delay     -float 0
defaults write com.apple.dock autohide-time-modifier -float 0.3
defaults write com.apple.dock show-recents       -bool  false
defaults write com.apple.dock launchanim         -bool  false
defaults write com.apple.dock expose-animation-duration -float 0.15
defaults write com.apple.dock "expose-group-apps" -bool true
# Prevent dock from hiding when going fullscreen
defaults write com.apple.dock "mismatch-fullscreen-option" -bool false

# 4. Screensaver → Lock screen: require password immediately
echo "[4/7] Wiring screensaver to lock screen..."
defaults write com.apple.screensaver askForPassword      -int 1
defaults write com.apple.screensaver askForPasswordDelay -int 0

# 5. Restart Dock with fresh settings
echo "[5/7] Restarting Dock..."
killall Dock
sleep 2

# 6. Install persistent LaunchAgent enforcer (runs every 60 seconds)
echo "[6/7] Installing persistent LaunchAgent..."
PLIST="$HOME/Library/LaunchAgents/com.ghs.dock-enforcer.plist"
cat > "$PLIST" << 'PLIST_EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ghs.dock-enforcer</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/sh</string>
        <string>-c</string>
        <string>
CURRENT=$(defaults read com.apple.dock autohide 2>/dev/null)
if [ "$CURRENT" != "0" ]; then
    defaults write com.apple.dock autohide -bool false
    defaults write com.apple.dock autohide-delay -float 0
    defaults write com.apple.dock show-recents -bool false
    killall Dock 2>/dev/null
    echo "$(date): Dock settings enforced (was autohide=$CURRENT)" >> ~/Desktop/REX/logs/dock_enforcer.log
fi
if ! pgrep -x Dock > /dev/null; then
    open -a Dock 2>/dev/null || /System/Library/CoreServices/Dock.app/Contents/MacOS/Dock &
    echo "$(date): Dock restarted (was dead)" >> ~/Desktop/REX/logs/dock_enforcer.log
fi
        </string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StartInterval</key>
    <integer>60</integer>
    <key>StandardOutPath</key>
    <string>/tmp/dock-enforcer.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/dock-enforcer-err.log</string>
</dict>
</plist>
PLIST_EOF

launchctl unload "$PLIST" 2>/dev/null
launchctl load   "$PLIST"

# 7. Verify
echo "[7/7] Verifying..."
sleep 2
if pgrep -x Dock > /dev/null; then
    echo "✅ Dock is running."
else
    echo "⚠️  Dock not found — trying to launch..."
    open -a Dock 2>/dev/null
fi
AUTOHIDE=$(defaults read com.apple.dock autohide 2>/dev/null)
echo "   autohide = $AUTOHIDE (should be 0)"

echo ""
echo "✅ DONE. Dock is fixed and LaunchAgent enforces it every 60 seconds."
echo "   Log: ~/Desktop/REX/logs/dock_enforcer.log"
echo ""
echo "NOTE: If dock still appears during screensaver, that is normal macOS behavior"
echo "      when the dock position is 'Bottom' and autohide is OFF."
echo "      The screensaver now requires password immediately (lock screen mode)."
echo ""
echo "Press Enter to close..."
read
