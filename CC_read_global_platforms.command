#!/bin/bash
# CC_read_global_platforms.command
# Read the top-level api_server + platforms keys in global config
# AND what read_raw_config() returns vs load_config()

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG=~/Desktop/REX/logs/cc_read_global_platforms_${TIMESTAMP}.log
VENV=~/.hermes/hermes-agent/venv
PYTHON="$VENV/bin/python"
GLOBAL_CFG=~/.hermes/config.yaml

exec > >(tee "$LOG") 2>&1

echo "══════════════════════════════════════════════════════"
echo "  CC_read_global_platforms — $(date)"
echo "══════════════════════════════════════════════════════"
echo ""

# ── 1: All top-level keys in global config (no head limit) ────
echo "── 1: ALL top-level keys in global config ────────────"
grep -n "^[a-zA-Z_]" "$GLOBAL_CFG"
echo ""

# ── 2: Global config — lines 324-566 (bottom half) ────────────
echo "── 2: Global config lines 324-420 ───────────────────"
sed -n '324,420p' "$GLOBAL_CFG"
echo ""
echo "── 2b: Global config lines 420-566 ──────────────────"
sed -n '420,566p' "$GLOBAL_CFG"
echo ""

# ── 3: read_raw_config() output ───────────────────────────────
echo "── 3: read_raw_config() — global config raw ─────────"
export HERMES_HOME="$HOME/.hermes/profiles/default"
"$PYTHON" -c "
import sys, os
os.environ['HERMES_HOME'] = os.path.expanduser('~/.hermes/profiles/default')
sys.path.insert(0, os.path.expanduser('~/.hermes/hermes-agent'))
from hermes_cli.config import read_raw_config
raw = read_raw_config()
print('Type:', type(raw))
if isinstance(raw, dict):
    print('Top-level keys:', list(raw.keys()))
    print()
    if 'platforms' in raw:
        print('platforms:', raw['platforms'])
    if 'api_server' in raw:
        print('api_server:', raw['api_server'])
" 2>&1
echo ""

# ── 4: load_config() for profile vs global ────────────────────
echo "── 4: load_config() — merged config ─────────────────"
"$PYTHON" -c "
import sys, os
os.environ['HERMES_HOME'] = os.path.expanduser('~/.hermes/profiles/default')
sys.path.insert(0, os.path.expanduser('~/.hermes/hermes-agent'))
from hermes_cli.config import load_config
cfg = load_config()
if isinstance(cfg, dict):
    print('platforms:', cfg.get('platforms'))
    print('api_server:', cfg.get('api_server'))
" 2>&1
echo ""

# ── 5: What the gateway actually uses at line 2452 ────────────
echo "── 5: gateway.py line 2445-2460 (read_raw_config) ───"
sed -n '2445,2470p' ~/.hermes/hermes-agent/hermes_cli/gateway.py 2>/dev/null
echo ""

# ── 6: Build GatewayConfig the way the gateway actually does ──
echo "── 6: GatewayConfig from read_raw_config ─────────────"
"$PYTHON" -c "
import sys, os
os.environ['HERMES_HOME'] = os.path.expanduser('~/.hermes/profiles/default')
sys.path.insert(0, os.path.expanduser('~/.hermes/hermes-agent'))
from hermes_cli.config import read_raw_config
from gateway.config import GatewayConfig, Platform
raw = read_raw_config()
try:
    gw = GatewayConfig.from_dict(raw)
    print('GatewayConfig platforms:', list(gw.platforms.keys()))
    if Platform.API_SERVER in gw.platforms:
        cfg = gw.platforms[Platform.API_SERVER]
        print('api_server extra:', cfg.extra)
        print('api_server port from extra:', cfg.extra.get(\"port\"))
    else:
        print('api_server NOT in platforms')
except Exception as e:
    print('Error:', e)
" 2>&1
echo ""

echo "══════════════════════════════════════════════════════"
echo "  Read complete — $(date)"
echo "  Log: $LOG"
echo "══════════════════════════════════════════════════════"
echo ""
read -p "Press any key to close..."
