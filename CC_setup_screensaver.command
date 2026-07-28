#!/bin/bash
# CC_setup_screensaver.command — Set hermestigerclaw.com/cc as macOS screensaver
# Uses macOS Web View Saver (built into Sonoma+) to display the Command Center
# When Mac idles → Command Center loads → shows live GOJ/BBG + screensaver animation
exec > >(tee "$HOME/Desktop/REX/logs/setup_screensaver_$(date +%Y%m%d_%H%M%S).log") 2>&1

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; BOLD='\033[1m'; YELLOW='\033[1;33m'; NC='\033[0m'
pass(){ echo -e "${GREEN}✅  $1${NC}"; }
fail(){ echo -e "${RED}❌  $1${NC}"; }
info(){ echo -e "${CYAN}ℹ️   $1${NC}"; }
warn(){ echo -e "${YELLOW}⚠️   $1${NC}"; }

echo -e "${BOLD}=== GHS TIGER CLAW SCREENSAVER SETUP ===${NC}"
echo "Target: hermestigerclaw.com/cc as macOS screensaver / lock screen"
echo ""

# Check macOS version
MACOS=$(sw_vers -productVersion)
MAJOR=$(echo "$MACOS" | cut -d. -f1)
info "macOS version: $MACOS"

# Method 1: Try Web View Saver (macOS Sonoma+)
WEB_SAVER="/System/Library/Screen Savers/Web View Saver.saver"
if [ -f "$WEB_SAVER" ]; then
    pass "Web View Saver found at $WEB_SAVER"

    defaults -currentHost write com.apple.screensaver \
        moduleDict -dict \
        moduleName "Web View Saver" \
        path "$WEB_SAVER" \
        type 0

    defaults -currentHost write com.apple.screensaver \
        idleTime 300

    # Set the URL for Web View Saver
    defaults -currentHost write com.apple.screensaverWebViewSaver URL "https://hermestigerclaw.com/cc"

    pass "Screensaver set: Web View Saver → hermestigerclaw.com/cc"
    pass "Idle time: 5 minutes"

    # Kill ScreenSaverEngine to force reload
    killall ScreenSaverEngine 2>/dev/null || true

else
    warn "Web View Saver not found — using iframe approach"

    # Method 2: Create a local screensaver wrapper HTML served by stats API
    info "Command Center screensaver is built into CC_command_center.html"
    info "It activates after ~5 minutes of idle in the browser"
fi

# Check if Command Center is accessible
CC_LOCAL=$(curl -s --max-time 5 http://localhost:8001/cc 2>/dev/null | head -c 100)
if echo "$CC_LOCAL" | grep -qi "GHS\|command\|hermes"; then
    pass "http://localhost:8001/cc is responding ✔"
else
    warn "localhost:8001/cc not responding — stats API may need restart"
    info "Run CC_fix_stats_api_final.command if needed"
fi

echo ""
echo -e "${BOLD}=== MANUAL STEPS IF AUTO-SETUP DIDN'T WORK ===${NC}"
echo ""
echo "1. Open: System Settings → Screen Saver"
echo "2. Select 'Web View Saver' (or 'Aerial' with URL support)"
echo "3. Set URL to: https://hermestigerclaw.com/cc"
echo "4. Set Start After: 5 minutes"
echo "5. Check: Require password after screen saver begins"
echo ""
echo "OR: Use 'Web View Saver' in Screen Saver settings:"
echo "   defaults write com.apple.screensaverWebViewSaver URL https://hermestigerclaw.com/cc"
echo ""
echo "The Command Center screensaver animation activates automatically"
echo "after the page has been idle — no extra setup needed in the browser."
echo ""
read -p "Press Enter to close..."
