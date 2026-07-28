#!/bin/bash
# CC_test_port_resolution.command
# Test EXACTLY what port the APIServerAdapter would use given the current env
# AND instrument the gateway log to capture what port is actually used at startup

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG=~/Desktop/REX/logs/cc_test_port_resolution_${TIMESTAMP}.log
VENV=~/.hermes/hermes-agent/venv
PYTHON="$VENV/bin/python"

exec > >(tee "$LOG") 2>&1

echo "══════════════════════════════════════════════════════"
echo "  CC_test_port_resolution — $(date)"
echo "══════════════════════════════════════════════════════"
echo ""

# ── 1: Direct test with current process env ───────────────────
echo "── 1: Direct APIServerAdapter test (current env) ────"
export HERMES_HOME="$HOME/.hermes/profiles/default"
export API_SERVER_PORT=65001
"$PYTHON" -c "
import sys, os
sys.path.insert(0, '$HOME/.hermes/hermes-agent')
from gateway.config import PlatformConfig
from gateway.platforms.api_server import APIServerAdapter, DEFAULT_PORT

# Simulate what the gateway does
cfg = PlatformConfig(enabled=True)
print('PlatformConfig.extra:', cfg.extra)
print('extra.get(port):', cfg.extra.get('port'))
print('os.getenv(API_SERVER_PORT):', os.getenv('API_SERVER_PORT'))
print('DEFAULT_PORT:', DEFAULT_PORT)

adapter = APIServerAdapter(cfg)
print('adapter._port:', adapter._port)
" 2>&1
echo ""

# ── 2: Test WITHOUT API_SERVER_PORT env ───────────────────────
echo "── 2: Test WITHOUT API_SERVER_PORT (should be 8642) ─"
unset API_SERVER_PORT
"$PYTHON" -c "
import sys, os
sys.path.insert(0, '$HOME/.hermes/hermes-agent')
from gateway.config import PlatformConfig
from gateway.platforms.api_server import APIServerAdapter

cfg = PlatformConfig(enabled=True)
adapter = APIServerAdapter(cfg)
print('Without env var, adapter._port:', adapter._port)
" 2>&1
echo ""

# ── 3: What does the gateway do with the api_server platform? ─
echo "── 3: How gateway.py actually creates the api_server adapter ─"
"$PYTHON" -c "
import sys, os
sys.path.insert(0, '$HOME/.hermes/hermes-agent')
import inspect, hermes_cli.gateway as gw_mod

src = inspect.getsource(gw_mod)
lines = src.split('\n')

# Find any PlatformConfig creation or api_server setup
matches = []
for i, line in enumerate(lines):
    if 'API_SERVER' in line or ('api_server' in line.lower() and ('platform' in line.lower() or 'config' in line.lower() or 'port' in line.lower())):
        matches.append(f'Line {i+1}: {line}')

for m in matches[:30]:
    print(m)
" 2>&1
echo ""

# ── 4: How is the api_server activated in gateway_run? ────────
echo "── 4: gateway_run function — what starts the api_server ─"
grep -n "api_server\|APIServer\|_api_server\|start_api\|Platform\." \
  ~/.hermes/hermes-agent/hermes_cli/gateway.py 2>/dev/null | head -30
echo ""

# ── 5: What is the RUNNING process's api_server._port? ────────
echo "── 5: Current gateway — actually verify port via lsof ──"
GW_PID=$(launchctl list | grep "ai.hermes.gateway$" | awk '{print $1}')
echo "Gateway PID: ${GW_PID:-'not running'}"
echo ""
echo "All TCP ports for gateway PID:"
lsof -p "$GW_PID" -iTCP -sTCP:LISTEN 2>/dev/null || echo "(none)"
echo ""
echo "HTTP test on 8642:"
curl -s --max-time 3 http://127.0.0.1:8642/health 2>/dev/null || echo "(no response)"
echo ""
echo "HTTP test on 65001:"
curl -s --max-time 3 http://127.0.0.1:65001/health 2>/dev/null || echo "(no response)"
echo ""

# ── 6: Last few lines of gateway profile log ─────────────────
echo "── 6: Profile gateway log (last 20) ─────────────────"
tail -20 ~/.hermes/profiles/default/logs/gateway.log 2>/dev/null || echo "(missing)"
echo ""

echo "══════════════════════════════════════════════════════"
echo "  Test complete — $(date)"
echo "  Log: $LOG"
echo "══════════════════════════════════════════════════════"
echo ""
read -p "Press any key to close..."
