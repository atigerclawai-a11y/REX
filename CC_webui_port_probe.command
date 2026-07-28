#!/usr/bin/env bash
# CC_webui_port_probe.command
# Probe all Hermes-relevant ports and read startup scripts

LOG="$HOME/Desktop/REX/logs/cc_webui_port_probe.log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

echo "══════════════════════════════════════════════════"
echo "  Hermes WebUI Port Probe — $(date '+%Y-%m-%d %H:%M:%S')"
echo "══════════════════════════════════════════════════"

for PORT in 3000 3003 3080 8787; do
  STATUS=$(curl -s --max-time 4 -o /dev/null -w "%{http_code}" "http://localhost:$PORT/")
  BODY=$(curl -s --max-time 4 "http://localhost:$PORT/" | head -c 200)
  echo ""
  echo "── Port $PORT (HTTP $STATUS) ──"
  echo "$BODY"
done

echo ""
echo "── Open WebUI startup script ──"
cat "$HOME/.local/bin/start-open-webui-hermes.sh" 2>/dev/null || echo "  (not found)"

echo ""
echo "── Open WebUI error log (last 30 lines) ──"
tail -30 "$HOME/.hermes/logs/openwebui.error.log" 2>/dev/null || echo "  (no log)"

echo ""
echo "── Open WebUI stdout log (last 20 lines) ──"
tail -20 "$HOME/.hermes/logs/openwebui.log" 2>/dev/null || echo "  (no log)"

echo ""
echo "── hermes-webui routes.py port ──"
grep -E "port|PORT|host|HOST|listen|LISTEN|run|bind" "$HOME/hermes-webui/api/routes.py" 2>/dev/null | head -15 || echo "  (not found)"

echo ""
echo "── All processes on relevant ports ──"
lsof -i :3000 -i :3003 -i :3080 -i :8787 -i :3002 2>/dev/null | grep LISTEN | head -20

echo ""
echo "══ PROBE COMPLETE ══"
echo "Log: $LOG"
echo ""
sleep 4
