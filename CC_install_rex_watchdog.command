#!/bin/bash
# CC_install_rex_watchdog.command
# Installs a LaunchAgent that auto-chmod +x's any .command file
# dropped into ~/Desktop/REX — permanently fixes the execute-bit problem.
# Run with: bash ~/Desktop/REX/CC_install_rex_watchdog.command

LOG="$HOME/Desktop/REX/logs/CC_install_rex_watchdog_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✅  $1${NC}"; }
fail() { echo -e "${RED}❌  $1${NC}"; echo ""; echo "Log: $LOG"; echo "Press any key..."; read -n 1; exit 1; }
warn() { echo -e "${YELLOW}⚠️   $1${NC}"; }
info() { echo -e "${CYAN}ℹ️   $1${NC}"; }

echo -e "${BOLD}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   REX Watchdog — Auto chmod +x for .command files  ║${NC}"
echo -e "${BOLD}╚════════════════════════════════════════════════════╝${NC}"
echo ""

PLIST_LABEL="com.rex.command-watcher"
PLIST="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
WATCH_DIR="$HOME/Desktop/REX"
SCRIPT="$HOME/Desktop/REX/scripts/rex_command_watcher.sh"

# ── STEP 1: Create watcher script ─────────────────────────────────────────────
info "Creating watcher script..."
mkdir -p "$HOME/Desktop/REX/scripts"
cat > "$SCRIPT" << 'SCRIPTEOF'
#!/bin/bash
# rex_command_watcher.sh — called by launchd when ~/Desktop/REX changes
# chmod +x on all .command files in the REX folder tree
find "$HOME/Desktop/REX" -name "*.command" ! -perm -u+x -exec chmod +x {} \;
SCRIPTEOF
chmod +x "$SCRIPT"
ok "Watcher script created: $SCRIPT"

# ── STEP 2: Unload existing plist if present ──────────────────────────────────
if launchctl list "$PLIST_LABEL" &>/dev/null 2>&1; then
    info "Unloading existing watchdog..."
    launchctl unload "$PLIST" 2>/dev/null
    ok "Old watchdog unloaded"
fi

# ── STEP 3: Write LaunchAgent plist ───────────────────────────────────────────
info "Writing LaunchAgent plist..."
cat > "$PLIST" << PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${SCRIPT}</string>
    </array>
    <key>WatchPaths</key>
    <array>
        <string>${WATCH_DIR}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>${HOME}/Desktop/REX/logs/rex_command_watcher.log</string>
    <key>StandardOutPath</key>
    <string>${HOME}/Desktop/REX/logs/rex_command_watcher.log</string>
</dict>
</plist>
PLISTEOF
ok "Plist written: $PLIST"

# ── STEP 4: Load the LaunchAgent ──────────────────────────────────────────────
info "Loading LaunchAgent..."
launchctl load "$PLIST"
[ $? -eq 0 ] || fail "launchctl load failed"
ok "Watchdog loaded and active"

# ── STEP 5: Run immediately to fix any existing .command files ────────────────
info "Fixing existing .command files now..."
find "$WATCH_DIR" -name "*.command" -exec chmod +x {} \;
COUNT=$(find "$WATCH_DIR" -name "*.command" | wc -l | tr -d ' ')
ok "chmod +x applied to $COUNT .command files"

echo ""
echo -e "${BOLD}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   REX Watchdog — Active ✅                         ║${NC}"
echo -e "${BOLD}╚════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Watches:  ${CYAN}$WATCH_DIR${NC}"
echo -e "  Trigger:  any file change in REX folder"
echo -e "  Action:   chmod +x on all .command files"
echo -e "  Plist:    $PLIST"
echo ""
echo "  Every new .command file I deliver will be auto-executable."
echo "  No more 'access privileges' errors."
echo ""
echo "Log: $LOG"
echo ""; echo "Press any key..."; read -n 1
