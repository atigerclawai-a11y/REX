#!/bin/bash
# CC_dock_lock.command — Permanently prevent dock from auto-hiding
# More aggressive than CC_dock_nuclear_fix — LaunchAgent runs every 30s
# Run this once; it installs itself and survives reboots.
exec > >(tee "$HOME/Desktop/REX/logs/dock_lock_$(date +%Y%m%d_%H%M%S).log") 2>&1

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
pass(){ echo -e "${GREEN}✅  $1${NC}"; }
fail(){ echo -e "${RED}❌  $1${NC}"; }
info(){ echo -e "${CYAN}ℹ️   $1${NC}"; }

echo -e "${BOLD}=== GHS DOCK LOCK (PERMANENT) ===${NC}"
echo "Time: $(date)"
echo ""

# ─── 1. Remove ALL old dock enforcers ────────────────────────────────────────
echo -e "${BOLD}[1/5] Removing all old dock enforcers...${NC}"
for label in com.ghs.dock-enforcer com.ghs.dock-lock com.ghs.dock-fix; do
    plist="$HOME/Library/LaunchAgents/${label}.plist"
    launchctl unload "$plist" 2>/dev/null
    rm -f "$plist"
done
pass "Old enforcers cleared"

# ─── 2. Fix dock RIGHT NOW ────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[2/5] Applying dock settings now...${NC}"
defaults write com.apple.dock autohide           -bool  false
defaults write com.apple.dock autohide-delay     -float 0
defaults delete com.apple.dock autohide-time-modifier 2>/dev/null || true
defaults write com.apple.dock show-process-indicators -bool true
defaults write com.apple.dock launchanim          -bool  true
defaults write com.apple.dock tilesize            -int   60
killall Dock
sleep 2
pass "Dock restarted with autohide OFF"

# ─── 3. Create the watcher script ────────────────────────────────────────────
echo ""
echo -e "${BOLD}[3/5] Creating watcher script...${NC}"
WATCHER="$HOME/Library/Scripts/GHS/dock_guard.sh"
mkdir -p "$HOME/Library/Scripts/GHS"
cat > "$WATCHER" << 'ENDSCRIPT'
#!/bin/bash
# GHS Dock Guard — runs every 30 seconds via LaunchAgent
val=$(defaults read com.apple.dock autohide 2>/dev/null)
if [ "$val" != "0" ]; then
    defaults write com.apple.dock autohide -bool false
    killall Dock
fi
ENDSCRIPT
chmod +x "$WATCHER"
pass "Watcher created: $WATCHER"

# ─── 4. Install LaunchAgent ───────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[4/5] Installing LaunchAgent (every 30s)...${NC}"
PLIST="$HOME/Library/LaunchAgents/com.ghs.dock-lock.plist"
cat > "$PLIST" << ENDPLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ghs.dock-lock</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$WATCHER</string>
    </array>
    <key>StartInterval</key>
    <integer>30</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>/tmp/dock-lock.log</string>
</dict>
</plist>
ENDPLIST
pass "Plist written: $PLIST"

# ─── 5. Load it ───────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[5/5] Loading LaunchAgent...${NC}"
launchctl load "$PLIST"
sleep 1

if launchctl list | grep -q "com.ghs.dock-lock"; then
    pass "com.ghs.dock-lock is LOADED and active"
else
    fail "LaunchAgent did not load — check /tmp/dock-lock.log"
fi

# ─── Also fix screensaver: require password immediately ──────────────────────
echo ""
info "Configuring screensaver (require password on wake)..."
defaults write com.apple.screensaver askForPassword      -int 1
defaults write com.apple.screensaver askForPasswordDelay -int 0
pass "Screen now locks immediately on sleep / screensaver start"

# ─── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}=== DOCK LOCK INSTALLED ===${NC}"
echo ""
echo "  Dock autohide:   DISABLED (permanent)"
echo "  Check interval:  every 30 seconds"
echo "  LaunchAgent:     com.ghs.dock-lock"
echo "  Screensaver:     requires password immediately"
echo ""
echo "  To verify:     launchctl list | grep dock-lock"
echo "  To uninstall:  launchctl unload $PLIST && rm $PLIST"
echo ""
echo "  The dock will stay visible even after macOS updates reset prefs."
echo "  If it ever hides, it will reappear within 30 seconds automatically."
echo ""
read -p "Press Enter to close..."
