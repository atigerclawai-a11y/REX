#!/bin/bash
# CC_instrument2.command
# Fixed debug print (Python 3.11 compatible) + investigate run.py

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG=~/Desktop/REX/logs/cc_instrument2_${TIMESTAMP}.log
API_SERVER_PY=~/.hermes/hermes-agent/gateway/platforms/api_server.py
RUN_PY=~/.hermes/hermes-agent/gateway/run.py
PLIST=~/Library/LaunchAgents/ai.hermes.gateway.plist
VENV=~/.hermes/hermes-agent/venv
PYTHON="$VENV/bin/python"

exec > >(tee "$LOG") 2>&1

echo "══════════════════════════════════════════════════════"
echo "  CC_instrument2 — $(date)"
echo "══════════════════════════════════════════════════════"
echo ""

# ── Step 1: run.py around _create_adapter (line 4195) ────────
echo "── Step 1: run.py lines 4185-4215 ───────────────────"
sed -n '4185,4215p' "$RUN_PY" 2>/dev/null
echo ""

# ── Step 2: run.py _create_adapter function ──────────────────
echo "── Step 2: run.py _create_adapter (line 6490-6530) ──"
sed -n '6490,6530p' "$RUN_PY" 2>/dev/null
echo ""

# ── Step 3: How platform configs are loaded ───────────────────
echo "── Step 3: run.py api_server/platform_config lines ──"
grep -n "api_server\|Platform\.API\|platform_config\|PlatformConfig" "$RUN_PY" 2>/dev/null | \
  grep -iv "test\|#" | head -30
echo ""

# ── Step 4: run.py start_gateway context ─────────────────────
echo "── Step 4: run.py start_gateway (18920-18950) ────────"
sed -n '18920,18950p' "$RUN_PY" 2>/dev/null
echo ""

# ── Step 5: Inject debug print (Python 3.11 compatible) ──────
echo "── Step 5: Inject debug print ────────────────────────"
PORT_LINE=$(grep -n "self\._port: int = _coerce_port" "$API_SERVER_PY" | head -1 | cut -d: -f1)
echo "Port assignment at line: $PORT_LINE"

cp "$API_SERVER_PY" "${API_SERVER_PY}.bak_${TIMESTAMP}"

"$PYTHON" - << 'PYEOF'
import os
path = os.path.expanduser('~/.hermes/hermes-agent/gateway/platforms/api_server.py')
with open(path, 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'self._port: int = _coerce_port' in line:
        indent = len(line) - len(line.lstrip())
        # Python 3.11 compatible — no double quotes inside f-string
        debug = (' ' * indent +
            "import sys as __sys; "
            "__sys.stderr.write('[DEBUG_PORT] extra=' + repr(extra) + "
            "' raw=' + repr(raw_port) + ' port=' + repr(self._port) + "
            "' env=' + repr(__import__('os').getenv('API_SERVER_PORT')) + '\\n'); "
            "__sys.stderr.flush()\n"
        )
        lines.insert(i + 1, debug)
        print(f'Injected at line {i+2}')
        break

with open(path, 'w') as f:
    f.writelines(lines)
print('[OK] Debug line written')
PYEOF

# Verify syntax
echo "Syntax check:"
"$PYTHON" -m py_compile "$API_SERVER_PY" && echo "[OK]" || echo "[SYNTAX ERROR]"
echo ""

# ── Step 6: Restart gateway ───────────────────────────────────
echo "── Step 6: Restart gateway ───────────────────────────"
launchctl unload "$PLIST" 2>&1 || echo "(not loaded)"
pkill -9 -f "hermes_cli.main.*gateway" 2>&1 && echo "[OK] Killed" || echo "[INFO] Not running"
sleep 8
launchctl load "$PLIST"
echo "Waiting 25s..."
sleep 25
echo ""

# ── Step 7: Read debug output ─────────────────────────────────
echo "── Step 7: Debug output ──────────────────────────────"
ERR_LOG=~/.hermes/profiles/default/logs/gateway.error.log
GW_PID=$(launchctl list | grep "ai.hermes.gateway$" | awk '{print $1}')
echo "Gateway PID: ${GW_PID:-not running}"
echo ""
echo "Port 65001: $(lsof -i :65001 2>/dev/null | grep LISTEN || echo 'nothing')"
echo "Port 8642:  $(lsof -i :8642  2>/dev/null | grep LISTEN || echo 'nothing')"
echo ""
echo "DEBUG_PORT output:"
[ -f "$ERR_LOG" ] && grep "DEBUG_PORT" "$ERR_LOG" | tail -5 || echo "(none)"
echo ""
echo "Last 10 error log lines:"
[ -f "$ERR_LOG" ] && tail -10 "$ERR_LOG" | grep -v "fireflies\|rejected" || echo "(missing)"
echo ""

# ── Step 8: Process env check ─────────────────────────────────
echo "── Step 8: API_SERVER_PORT in process env ────────────"
if [ -n "$GW_PID" ] && [ "$GW_PID" != "-" ]; then
  ps eww -p "$GW_PID" 2>/dev/null | tr ' ' '\n' | grep "API_SERVER_PORT\|HERMES_HOME" | head -5
else
  echo "Gateway not running — checking plist"
  /usr/libexec/PlistBuddy -c "Print :EnvironmentVariables:API_SERVER_PORT" "$PLIST" 2>/dev/null
fi
echo ""

# ── Step 9: Restore ───────────────────────────────────────────
echo "── Step 9: Restore api_server.py ─────────────────────"
cp "${API_SERVER_PY}.bak_${TIMESTAMP}" "$API_SERVER_PY"
echo "[OK] Restored"
echo ""

echo "══════════════════════════════════════════════════════"
echo "  Done — $(date)"
echo "  Log: $LOG"
echo "══════════════════════════════════════════════════════"
echo ""
read -p "Press any key to close..."
