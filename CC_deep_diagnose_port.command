#!/bin/bash
# CC_deep_diagnose_port.command
# Find WHY api_server.py gets port=8642 despite API_SERVER_PORT=65001
# Two angles: (1) global config structure, (2) live process environment

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG=~/Desktop/REX/logs/cc_deep_diagnose_port_${TIMESTAMP}.log
GLOBAL_CFG=~/.hermes/config.yaml
PLIST=~/Library/LaunchAgents/ai.hermes.gateway.plist
HERMES_SRC=~/.hermes/hermes-agent

exec > >(tee "$LOG") 2>&1

echo "══════════════════════════════════════════════════════"
echo "  CC_deep_diagnose_port — $(date)"
echo "══════════════════════════════════════════════════════"
echo ""

# ── 1: Global config — lines 210-280 (around line 233) ────────
echo "── 1: Global config lines 210-280 ──────────────────"
sed -n '210,280p' "$GLOBAL_CFG"
echo ""

# ── 2: Full global config — all port/api_server lines ─────────
echo "── 2: All api_server + port lines in global config ─"
grep -n "api_server\|port\|extra\|enabled\|platforms" "$GLOBAL_CFG" | head -60
echo ""

# ── 3: Profile config — full dump ─────────────────────────────
echo "── 3: Profile config (full) ─────────────────────────"
cat ~/.hermes/profiles/default/config.yaml 2>/dev/null || echo "[MISSING]"
echo ""

# ── 4: Live process environment — does the gateway actually see API_SERVER_PORT? ──
echo "── 4: Live gateway process env ──────────────────────"
GW_PID=$(launchctl list | grep "ai.hermes.gateway$" | awk '{print $1}')
echo "Gateway PID: ${GW_PID:-'not running'}"
echo ""

if [ -n "$GW_PID" ] && [ "$GW_PID" != "-" ]; then
  echo "All env vars of PID $GW_PID containing PORT or API:"
  ps ewww -p "$GW_PID" 2>/dev/null | tr ' ' '\n' | grep -i "port\|api_server\|hermes" | sort
fi
echo ""

# ── 5: Read api_server.__init__ — the EXACT port resolution code ──
echo "── 5: APIServerAdapter.__init__ (lines 685-720) ─────"
sed -n '685,720p' "$HERMES_SRC/gateway/platforms/api_server.py" 2>/dev/null || echo "[missing]"
echo ""

# ── 6: How PlatformConfig is built from the config.yaml ───────
echo "── 6: PlatformConfig source (gateway/config.py) ─────"
grep -n "class PlatformConfig\|extra\|from_dict\|from_config\|api_server" \
  "$HERMES_SRC/gateway/config.py" 2>/dev/null | head -40
echo ""

# ── 7: How platforms are loaded from config ────────────────────
echo "── 7: Platform loading in gateway/run.py or __main__ ─"
grep -rn "PlatformConfig\|load_platform\|api_server\|get_platform" \
  "$HERMES_SRC/hermes_cli" --include="*.py" 2>/dev/null | \
  grep -v "test\|__pycache__" | head -30
echo ""

# ── 8: gateway.json in profile if it exists ───────────────────
echo "── 8: gateway.json ───────────────────────────────────"
cat ~/.hermes/profiles/default/gateway.json 2>/dev/null || echo "[MISSING]"
echo ""

# ── 9: Any file with port 8642 in hermes home ────────────────
echo "── 9: Files in ~/.hermes containing '8642' ──────────"
grep -rl "8642" ~/.hermes 2>/dev/null | \
  grep -v "hermes-agent\|venv\|__pycache__\|logs\|response_store\|bak_" | head -20
echo ""

echo "══════════════════════════════════════════════════════"
echo "  Deep diagnose complete — $(date)"
echo "  Log: $LOG"
echo "══════════════════════════════════════════════════════"
echo ""
read -p "Press any key to close..."
