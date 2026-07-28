#!/bin/bash
# CC_find_api_server_config.command
# Find where extra.port=8642 comes from in global config
# AND find where API_SERVER_PORT is overridden in run.py

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG=~/Desktop/REX/logs/cc_find_api_server_config_${TIMESTAMP}.log
VENV=~/.hermes/hermes-agent/venv
PYTHON="$VENV/bin/python"
GLOBAL_CFG=~/.hermes/config.yaml
RUN_PY=~/.hermes/hermes-agent/gateway/run.py

exec > >(tee "$LOG") 2>&1

echo "══════════════════════════════════════════════════════"
echo "  CC_find_api_server_config — $(date)"
echo "══════════════════════════════════════════════════════"
echo ""

# ── 1: Search global config for port: 8642 ───────────────────
echo "── 1: Global config — all 'port:' lines ─────────────"
grep -n "port:" "$GLOBAL_CFG"
echo ""

# ── 2: Search global config for model_name / Hermes Agent ────
echo "── 2: Global config — model_name / group_sessions ───"
grep -n "model_name\|group_sessions\|f22503\|key:" "$GLOBAL_CFG" | head -20
echo ""

# ── 3: Global config — api_server section ────────────────────
echo "── 3: Global config — all 'api_server' lines ────────"
grep -n "api_server" "$GLOBAL_CFG"
echo ""

# ── 4: run.py — where API_SERVER_PORT is SET ─────────────────
echo "── 4: run.py — API_SERVER_PORT assignments ──────────"
grep -n "API_SERVER_PORT" "$RUN_PY" | head -20
echo ""

# ── 5: How GatewayConfig builds from merged config ───────────
echo "── 5: Load merged config and show api_server platform ─"
export HERMES_HOME="$HOME/.hermes/profiles/default"
"$PYTHON" - << 'PYEOF'
import sys, os
os.environ['HERMES_HOME'] = os.path.expanduser('~/.hermes/profiles/default')
sys.path.insert(0, os.path.expanduser('~/.hermes/hermes-agent'))
from hermes_cli.config import read_raw_config, load_config
from gateway.config import GatewayConfig, Platform

# Check both configs
raw = read_raw_config()
print('=== read_raw_config platforms ===')
print(type(raw.get('platforms')), raw.get('platforms'))
print()
print('=== read_raw_config api_server ===')
print(raw.get('api_server'))
print()

# Try to build GatewayConfig
try:
    gw = GatewayConfig.from_dict(raw)
    print('=== GatewayConfig.platforms ===')
    for p, cfg in gw.platforms.items():
        print(f'  {p.value}: enabled={cfg.enabled} extra={cfg.extra}')
except Exception as e:
    print(f'GatewayConfig error: {e}')
PYEOF
echo ""

# ── 6: How does the gateway actually read its full config? ────
echo "── 6: run.py — _platform_config_key function ────────"
sed -n '1395,1420p' "$RUN_PY" 2>/dev/null
echo ""

# ── 7: Global config full platforms/api_server section ───────
echo "── 7: Global config lines 200-260 ───────────────────"
sed -n '200,260p' "$GLOBAL_CFG"
echo ""

# ── 8: Global config — where does 'key:' with hex appear? ────
echo "── 8: Global config — lines around api_server ────────"
# Find all sections that look like platform config with key+port
"$PYTHON" - << 'PYEOF'
import yaml, os
path = os.path.expanduser('~/.hermes/config.yaml')
with open(path) as f:
    data = yaml.safe_load(f)

def find_key(obj, target='port', path='', depth=0):
    if depth > 10:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_path = f'{path}.{k}' if path else k
            if k == target:
                print(f'{new_path} = {v!r}')
            find_key(v, target, new_path, depth+1)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            find_key(v, target, f'{path}[{i}]', depth+1)

print('All port: values in global config:')
find_key(data, 'port')
print()
print('All key: values (first 50 chars):')
def find_key2(obj, target='key', path='', depth=0):
    if depth > 10:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_path = f'{path}.{k}' if path else k
            if k == target:
                print(f'{new_path} = {str(v)[:60]!r}')
            find_key2(v, target, new_path, depth+1)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            find_key2(v, target, f'{path}[{i}]', depth+1)
find_key2(data, 'key')
PYEOF
echo ""

echo "══════════════════════════════════════════════════════"
echo "  Find complete — $(date)"
echo "  Log: $LOG"
echo "══════════════════════════════════════════════════════"
echo ""
read -p "Press any key to close..."
