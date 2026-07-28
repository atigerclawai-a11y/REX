#!/bin/bash
# CC_find_real_api_server.command
# Find what api_server.py Python is ACTUALLY running from — source vs site-packages
# Also read the actual __init__ that runs, and check how GatewayConfig loads platforms

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG=~/Desktop/REX/logs/cc_find_real_api_server_${TIMESTAMP}.log
VENV=~/.hermes/hermes-agent/venv
PYTHON="$VENV/bin/python"

exec > >(tee "$LOG") 2>&1

echo "══════════════════════════════════════════════════════"
echo "  CC_find_real_api_server — $(date)"
echo "══════════════════════════════════════════════════════"
echo ""

# ── 1: Where does Python find gateway.platforms.api_server? ───
echo "── 1: Python import path for api_server ─────────────"
"$PYTHON" -c "
import sys
sys.path.insert(0, '$HOME/.hermes/hermes-agent')
import gateway.platforms.api_server as m
print('File:', m.__file__)
import inspect
src = inspect.getsource(m.APIServerAdapter.__init__)
print('--- __init__ source ---')
print(src[:2000])
" 2>&1
echo ""

# ── 2: Check site-packages for gateway ───────────────────────
echo "── 2: site-packages gateway path ────────────────────"
"$PYTHON" -c "
import sys
for p in sys.path:
    print(p)
" 2>&1
echo ""
find "$VENV/lib" -name "api_server.py" -path "*/gateway/platforms/*" 2>/dev/null | head -5
echo ""

# ── 3: How does GatewayConfig build platform configs? ─────────
echo "── 3: GatewayConfig.from_dict (gateway/config.py) ───"
"$PYTHON" -c "
import sys
sys.path.insert(0, '$HOME/.hermes/hermes-agent')
import gateway.config as m
import inspect
src = inspect.getsource(m.GatewayConfig)
# Find from_dict specifically
lines = src.split('\n')
start = next((i for i,l in enumerate(lines) if 'from_dict' in l and 'def ' in l), 0)
print('\n'.join(lines[max(0,start-2):start+60]))
" 2>&1
echo ""

# ── 4: How is the api_server platform config loaded in gateway startup? ──
echo "── 4: Gateway startup — how api_server gets its config ─"
"$PYTHON" -c "
import sys
sys.path.insert(0, '$HOME/.hermes/hermes-agent')
import hermes_cli.gateway as m
import inspect
src = inspect.getsource(m)
# Find api_server config loading
lines = src.split('\n')
for i, line in enumerate(lines):
    if 'api_server' in line.lower() and ('platform' in line.lower() or 'config' in line.lower() or 'port' in line.lower()):
        print(f'Line {i}: {line}')
" 2>&1 | head -30
echo ""

# ── 5: Read the actual config that the gateway loads for platforms ──
echo "── 5: What config does load_config() return for platforms? ─"
"$PYTHON" -c "
import sys, os
os.environ['HERMES_HOME'] = os.path.expanduser('~/.hermes/profiles/default')
sys.path.insert(0, '$HOME/.hermes/hermes-agent')
from hermes_cli.config import load_config
cfg = load_config()
print(type(cfg))
# Find platforms config
if hasattr(cfg, 'platforms'):
    print('cfg.platforms:', cfg.platforms)
elif isinstance(cfg, dict):
    print('platforms key:', cfg.get('platforms'))
    print('api_server key:', cfg.get('api_server'))
" 2>&1
echo ""

# ── 6: Check gateway/config.py load_platforms_config function ─
echo "── 6: How GatewayConfig is actually loaded in gateway startup ─"
HERMES_SRC=~/.hermes/hermes-agent
grep -n "api_server\|GatewayConfig\|load_gateway\|get_platform_config\|platforms_config\|display.*platform" \
  "$HERMES_SRC/hermes_cli/gateway.py" 2>/dev/null | grep -v "test\|#" | head -30
echo ""

echo "══════════════════════════════════════════════════════"
echo "  Find complete — $(date)"
echo "  Log: $LOG"
echo "══════════════════════════════════════════════════════"
echo ""
read -p "Press any key to close..."
