#!/bin/bash
# ─────────────────────────────────────────────────────────────
# GHS Command Center — Launcher
# Gold Health Systems · Phase 1
# Opens CC_command_center.html in Chrome kiosk/fullscreen mode
# Usage: double-click this file, or: bash CC_command_center_launcher.command
# ─────────────────────────────────────────────────────────────

set -euo pipefail

LOG_DIR="$HOME/Desktop/REX/logs"
LOG="$LOG_DIR/CC_launcher_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$LOG_DIR"
exec > >(tee "$LOG") 2>&1

echo "═══════════════════════════════════════════════════"
echo "  GHS Command Center Launcher"
echo "  $(date)"
echo "═══════════════════════════════════════════════════"

CC_FILE="$HOME/Desktop/REX/CC_command_center.html"

if [[ ! -f "$CC_FILE" ]]; then
  echo "ERROR: CC_command_center.html not found at:"
  echo "  $CC_FILE"
  echo "Run the build script first."
  exit 1
fi

echo "File: $CC_FILE"
echo "Size: $(wc -c < "$CC_FILE") bytes"
echo ""

# Detect Chrome path (macOS)
CHROME_PATHS=(
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
  "/Applications/Chromium.app/Contents/MacOS/Chromium"
  "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
)

CHROME=""
for p in "${CHROME_PATHS[@]}"; do
  if [[ -x "$p" ]]; then
    CHROME="$p"
    break
  fi
done

FILE_URL="file://$CC_FILE"

if [[ -n "$CHROME" ]]; then
  echo "Launching with: $CHROME"
  echo "Mode: Kiosk / Fullscreen"
  echo "URL: $FILE_URL"
  echo ""

  # Launch in kiosk mode (true fullscreen, no UI chrome)
  "$CHROME" \
    --kiosk \
    --disable-translate \
    --disable-extensions \
    --disable-sync \
    --no-default-browser-check \
    --disable-infobars \
    --allow-file-access-from-files \
    --autoplay-policy=no-user-gesture-required \
    "$FILE_URL" &

  echo "✓ Chrome kiosk launched (PID: $!)"
  echo ""
  echo "To exit kiosk mode: Cmd+W or Alt+F4"
  echo "To reopen normally: open -a 'Google Chrome' \"$FILE_URL\""
else
  echo "Chrome not found — trying macOS default browser..."
  open "$FILE_URL"
  echo "✓ Opened in default browser"
  echo ""
  echo "For best experience: open in Chrome and press Cmd+Shift+F for fullscreen"
fi

echo ""
echo "═══════════════════════════════════════════════════"
echo "  Launcher complete · $(date)"
echo "═══════════════════════════════════════════════════"
