#!/bin/bash
# CC_read_api_server_source.command
# Read the api_server platform source to find the port config key

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG=~/Desktop/REX/logs/cc_read_api_server_source_${TIMESTAMP}.log
HERMES_SRC=~/.hermes/hermes-agent

exec > >(tee "$LOG") 2>&1

echo "══════════════════════════════════════════════════════"
echo "  CC_read_api_server_source — $(date)"
echo "══════════════════════════════════════════════════════"
echo ""

# ── 1: config.py around line 3087 (port description) ─────
echo "── 1: config.py lines 3075-3130 ─────────────────────"
sed -n '3075,3130p' "$HERMES_SRC/hermes_cli/config.py" 2>/dev/null || echo "[missing]"
echo ""

# ── 2: api_server platform source ─────────────────────────
echo "── 2: gateway/platforms/api_server.py (first 150 lines) ──"
cat "$HERMES_SRC/gateway/platforms/api_server.py" 2>/dev/null | head -150 || echo "[missing]"
echo ""

# ── 3: How port is determined in api_server ────────────────
echo "── 3: port-related lines in api_server.py ────────────"
grep -n "port\|_port\|extra\|config\|host" "$HERMES_SRC/gateway/platforms/api_server.py" 2>/dev/null | head -60
echo ""

# ── 4: Profile config resolution — how profiles load ──────
echo "── 4: Profile loading in hermes_cli ─────────────────"
grep -rn "profile\|HERMES_HOME\|config_path\|load_config" \
  "$HERMES_SRC/hermes_cli" --include="*.py" 2>/dev/null | \
  grep -v "test\|#.*profile\|__pycache__" | grep -i "config.*path\|load.*config\|hermes_home\|profile.*dir" | head -20
echo ""

# ── 5: The actual config key path for api_server port ─────
echo "── 5: Config schema — what key is 'api_server port' under ──"
grep -n -B5 -A5 "Port for the API server" "$HERMES_SRC/hermes_cli/config.py" 2>/dev/null
echo ""

# ── 6: Test file — how port is set in tests ───────────────
echo "── 6: test_api_server.py lines around port 8642 ─────"
grep -n -B5 -A5 "_port == 8642\|port.*8642\|8642.*port" \
  "$HERMES_SRC/tests/gateway/test_api_server.py" 2>/dev/null | head -60
echo ""

echo "══════════════════════════════════════════════════════"
echo "  Source read complete — $(date)"
echo "  Log: $LOG"
echo "══════════════════════════════════════════════════════"
echo ""
read -p "Press any key to close..."
