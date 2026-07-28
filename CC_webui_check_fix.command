#!/usr/bin/env bash
# CC_webui_check_fix.command
# Check Open WebUI / Hermes WebUI status and fix
# Double-click to run.

LOG="$HOME/Desktop/REX/logs/cc_webui_check_fix.log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

echo "══════════════════════════════════════════════════"
echo "  Hermes WebUI Check & Fix — $(date '+%Y-%m-%d %H:%M:%S')"
echo "══════════════════════════════════════════════════"

DEST="$HOME/Library/LaunchAgents"

echo ""
echo "── Open WebUI plist ──"
cat "$DEST/ai.openwebui.hermes.plist" 2>/dev/null || echo "  (plist not readable)"

echo ""
echo "── Open WebUI process ──"
pgrep -fl "open.webui\|openwebui\|open_webui" | grep -v grep | head -5 || echo "  (not running)"

echo ""
echo "── Port 8080 check ──"
curl -s --max-time 5 "http://localhost:8080/" | head -c 300
echo ""
curl -s --max-time 5 -o /dev/null -w "  HTTP status: %{http_code}\n" "http://localhost:8080/"

echo ""
echo "── Port 5000 check ──"
curl -s --max-time 5 "http://localhost:5000/" | head -c 300
echo ""
curl -s --max-time 5 -o /dev/null -w "  HTTP status: %{http_code}\n" "http://localhost:5000/"

echo ""
echo "── Hermes WebUI server ──"
pgrep -fl "hermes-webui\|hermes_webui" | grep -v grep | head -5 || echo "  (not running)"
ls "$HOME/hermes-webui/" 2>/dev/null | head -10 || echo "  (~/hermes-webui/ not found)"

echo ""
echo "── Hermes WebUI plist check ──"
ls "$DEST/" | grep -iE "webui|hermes.web|chatui|openwebui" | head -10

echo ""
echo "── Load Open WebUI if stopped ──"
OWUI_RUNNING=$(pgrep -f "open.webui\|openwebui\|open_webui" | head -1)
if [ -z "$OWUI_RUNNING" ]; then
  echo "  Open WebUI not running — trying to start via plist..."
  launchctl unload "$DEST/ai.openwebui.hermes.plist" 2>/dev/null || true
  sleep 1
  launchctl load "$DEST/ai.openwebui.hermes.plist" 2>/dev/null && echo "  ✓ Loaded" || echo "  ✗ Failed"
  sleep 8
  pgrep -fl "open.webui\|openwebui\|open_webui" | grep -v grep | head -3 || echo "  Still not running"
  curl -s --max-time 5 -o /dev/null -w "  Port 8080 status: %{http_code}\n" "http://localhost:8080/"
else
  echo "  ✓ Open WebUI running (PID $OWUI_RUNNING)"
fi

echo ""
echo "── What URL is the Cloudflare tunnel pointing to? ──"
cat "$HOME/.cloudflared/hermestigerclaw.yml" 2>/dev/null | grep -E "hostname|service|url|ingress" | head -20
cat "$HOME/.hermes-cloud/cloudflared.yml" 2>/dev/null | grep -E "hostname|service|url|ingress" | head -20

echo ""
echo "── hermes-webui server.py ──"
cat "$HOME/hermes-webui/server.py" 2>/dev/null | grep -E "port|PORT|host|HOST|app.run|uvicorn" | head -10

echo ""
echo "══ WEBUI FIX COMPLETE ══"
echo "Log: $LOG"
echo ""
sleep 4
