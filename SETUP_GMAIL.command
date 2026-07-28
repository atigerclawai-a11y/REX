#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  SETUP_GMAIL.command — One-time Gmail authorization for REX
#  Double-click this file. A browser window will open — just click Allow.
#  After that, Rexxie will automatically monitor your Gmail for PDFs.
# ─────────────────────────────────────────────────────────────────────────────

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'

REX_DIR="$HOME/Desktop/REX"
cd "$REX_DIR"

echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}   📧  REX Gmail Setup${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

# ── Check google_credentials.json ────────────────────────────────────────────
if [ ! -f "$REX_DIR/google_credentials.json" ]; then
  echo -e "${RED}❌  Missing: google_credentials.json${NC}"
  echo ""
  echo "  To fix:"
  echo "  1. Go to: https://console.cloud.google.com/apis/credentials"
  echo "  2. Find your OAuth 2.0 Client ID (Desktop app type)"
  echo "  3. Click the download ↓ icon → save as google_credentials.json"
  echo "  4. Move it to: ~/Desktop/REX/google_credentials.json"
  echo "  5. Double-click SETUP_GMAIL.command again"
  echo ""
  echo "Press Enter to close..."
  read
  exit 1
fi

echo -e "${GREEN}✓ google_credentials.json found${NC}"

# ── Install Google API libraries ──────────────────────────────────────────────
echo -e "\n[1/2] Checking Google API libraries..."

VENV_PYTHON="$REX_DIR/.venv/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then VENV_PYTHON="python3"; fi

"$VENV_PYTHON" -c "import google.auth" 2>/dev/null
if [ $? -ne 0 ]; then
  echo -e "  Installing google-auth libraries..."
  "$VENV_PYTHON" -m pip install \
    google-auth \
    google-auth-oauthlib \
    google-auth-httplib2 \
    google-api-python-client \
    --quiet --break-system-packages
  if [ $? -eq 0 ]; then
    echo -e "  ${GREEN}✓ Libraries installed${NC}"
  else
    echo -e "  ${RED}❌ Install failed — check internet connection${NC}"
    echo ""
    echo "Press Enter to close..."
    read
    exit 1
  fi
else
  echo -e "  ${GREEN}✓ Libraries already installed${NC}"
fi

# ── Run auth script ────────────────────────────────────────────────────────────
echo -e "\n[2/2] Opening Gmail authorization in browser..."
echo -e "  ${YELLOW}A browser window will open. Click 'Allow' to grant REX read-only Gmail access.${NC}"
echo ""

"$VENV_PYTHON" rex_gmail_auth.py

if [ $? -eq 0 ]; then
  echo ""
  echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${GREEN}  ✅  Gmail connected!${NC}"
  echo -e "${GREEN}  Rexxie will now notify you when PDFs arrive in your inbox.${NC}"
  echo -e "${GREEN}  The watcher runs every 10 minutes automatically.${NC}"
  echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

  # ── Install launchd plist so watcher runs every 10 minutes ───────────────
  PLIST_DIR="$HOME/Library/LaunchAgents"
  PLIST_PATH="$PLIST_DIR/com.rex.pdf-watcher.plist"
  mkdir -p "$PLIST_DIR"

  cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.rex.pdf-watcher</string>
    <key>ProgramArguments</key>
    <array>
        <string>$VENV_PYTHON</string>
        <string>$REX_DIR/rex_email_pdf_watcher.py</string>
    </array>
    <key>StartInterval</key>
    <integer>600</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$REX_DIR/logs/pdf_watcher.log</string>
    <key>StandardErrorPath</key>
    <string>$REX_DIR/logs/pdf_watcher_err.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>$HOME</string>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
    <key>WorkingDirectory</key>
    <string>$REX_DIR</string>
</dict>
</plist>
PLIST

  # Load it
  launchctl unload "$PLIST_PATH" 2>/dev/null
  launchctl load "$PLIST_PATH" 2>/dev/null

  if launchctl list | grep -q "com.rex.pdf-watcher"; then
    echo -e "  ${GREEN}✓ PDF watcher scheduled (every 10 minutes, auto-starts on login)${NC}"
  else
    echo -e "  ${YELLOW}⚠  Watcher plist written but may need manual load:${NC}"
    echo -e "  launchctl load $PLIST_PATH"
  fi

else
  echo ""
  echo -e "${RED}❌  Gmail auth was not completed.${NC}"
  echo "   Try running this again and make sure to click Allow in the browser."
fi

echo ""
echo "Press Enter to close..."
read
