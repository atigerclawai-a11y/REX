#!/usr/bin/env bash
# CC_bots_webui_check_and_start.command
# Check and start: Rexxie bot, HermieChatt (Hermes cloud), hermes-webui
# Double-click to run.

LOG="$HOME/Desktop/REX/logs/cc_bots_webui.log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

echo "══════════════════════════════════════════════════"
echo "  Bots + WebUI Check & Start — $(date '+%Y-%m-%d %H:%M:%S')"
echo "══════════════════════════════════════════════════"

REXXIE_TOKEN="8657319466:AAGVYz_o7j1ZMpoqiHa8I1ZjS6VYGiWZS8k"
HERMIE_TOKEN="8702536335:AAHlGlEpLVuq9RAaqNq4kugv1MqJRg4IJQY"

# ── 1. Rexxie Telegram Bot ────────────────────────────
echo ""
echo "── 1. Rexxie bot status ──"
REXXIE_PIDS=$(pgrep -f "rex_rexxie_telegram_bot" 2>/dev/null)
if [ -n "$REXXIE_PIDS" ]; then
  echo "  ✓ Running (PIDs: $REXXIE_PIDS)"
else
  echo "  ✗ Not running — starting via launchd..."
  launchctl unload "$HOME/Library/LaunchAgents/com.rex.rexxie-bot.plist" 2>/dev/null || true
  sleep 1
  launchctl load "$HOME/Library/LaunchAgents/com.rex.rexxie-bot.plist" 2>/dev/null && echo "  ✓ Loaded plist" || echo "  ✗ Failed to load plist"
  sleep 3
  REXXIE_PIDS=$(pgrep -f "rex_rexxie_telegram_bot" 2>/dev/null)
  [ -n "$REXXIE_PIDS" ] && echo "  ✓ Now running (PIDs: $REXXIE_PIDS)" || echo "  ✗ Still not running"
fi
echo "  Token check:"
curl -s --max-time 6 "https://api.telegram.org/bot$REXXIE_TOKEN/getMe" | python3 -c "import sys,json; d=json.load(sys.stdin); print('  ✓ @'+d['result']['username'],'—',d['result']['first_name'])" 2>/dev/null || echo "  ✗ Token check failed"

# ── 2. HermieChatt (Hermes cloud Telegram) ────────────
echo ""
echo "── 2. HermieChatt / Hermes cloud Telegram ──"
HERMIE_RUNNING=$(pgrep -fl "hermes_cli.main --profile cloud" 2>/dev/null | head -2)
if [ -n "$HERMIE_RUNNING" ]; then
  echo "  ✓ Cloud gateway running:"
  echo "  $HERMIE_RUNNING"
else
  echo "  ✗ Cloud gateway not running — reloading..."
  launchctl unload "$HOME/Library/LaunchAgents/ai.hermes.gateway-cloud.plist" 2>/dev/null || true
  sleep 1
  launchctl load "$HOME/Library/LaunchAgents/ai.hermes.gateway-cloud.plist" 2>/dev/null && echo "  ✓ Loaded" || echo "  ✗ Failed"
  sleep 4
fi
echo "  Token check:"
curl -s --max-time 6 "https://api.telegram.org/bot$HERMIE_TOKEN/getMe" | python3 -c "import sys,json; d=json.load(sys.stdin); print('  ✓ @'+d['result']['username'],'—',d['result']['first_name'])" 2>/dev/null || echo "  ✗ Token check failed"

# ── 3. Hermes WebUI ────────────────────────────────────
echo ""
echo "── 3. Hermes WebUI ──"
WEBUI_PIDS=$(pgrep -fl "hermes-webui/server.py\|hermes.webui" 2>/dev/null | grep -v grep | head -3)
if [ -n "$WEBUI_PIDS" ]; then
  echo "  ✓ Running:"
  echo "$WEBUI_PIDS" | sed 's/^/    /'
else
  echo "  ✗ Not running"
fi

# Check port 9090 / 8080 / 8765 common webui ports
for PORT in 8765 9090 8080 3030 5000; do
  RESP=$(curl -s --max-time 3 "http://localhost:$PORT/" 2>/dev/null | head -c 100)
  if [ -n "$RESP" ]; then
    echo "  ✓ Something responding on port $PORT"
  fi
done

# Check if there's a launchd plist for webui
echo "  WebUI launchd plists:"
ls "$HOME/Library/LaunchAgents/" 2>/dev/null | grep -iE "webui|openwebui|hermes.web|chatui" | head -5 || echo "    (none found)"

# Check for open-webui process
OWUI=$(pgrep -fl "open-webui\|openwebui\|open_webui" 2>/dev/null | grep -v grep | head -3)
if [ -n "$OWUI" ]; then
  echo "  ✓ Open-WebUI running:"
  echo "$OWUI" | sed 's/^/    /'
fi

# ── 4. Cloudflare tunnel ────────────────────────────────
echo ""
echo "── 4. Cloudflare tunnel ──"
CF_PID=$(pgrep -f "cloudflared" | head -1)
if [ -n "$CF_PID" ]; then
  echo "  ✓ cloudflared running (PID $CF_PID)"
else
  echo "  ✗ cloudflared not running"
fi

# ── 5. Cloud gateway health ────────────────────────────
echo ""
echo "── 5. Cloud gateway health (port 3002) ──"
curl -s --max-time 5 "http://localhost:3002/health" | python3 -m json.tool 2>/dev/null | grep -E "status|uptime|sessions" || echo "  (not responding)"

echo ""
echo "── 6. Telegram platform status (Hermes cloud gateway) ──"
curl -s --max-time 5 "http://localhost:3002/platforms" 2>/dev/null | python3 -m json.tool 2>/dev/null | head -20 || \
curl -s --max-time 5 "http://localhost:3002/api/platforms" 2>/dev/null | python3 -m json.tool 2>/dev/null | head -20 || \
echo "  (no platforms endpoint)"

echo ""
echo "══ CHECK COMPLETE ══"
echo "Log: $LOG"
echo ""
sleep 4
