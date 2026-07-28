#!/usr/bin/env bash
# CC_upgrade_fallback_to_sonnet.command — swap Claude Haiku for Sonnet in fallback
LOG="$HOME/Desktop/REX/logs/cc_upgrade_fallback_to_sonnet.log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

YAML="$HOME/.hermes/profiles/cloud/config.yaml"

echo "Upgrading Claude fallback: haiku → sonnet"
echo ""

cp "$YAML" "${YAML}.bak_$(date +%Y%m%d_%H%M%S)"

python3 - "$YAML" <<'EOF'
import sys, yaml

path = sys.argv[1]
cfg = yaml.safe_load(open(path)) or {}

fallbacks = cfg.get("fallback_providers") or []
for fb in fallbacks:
    if fb.get("provider") == "anthropic":
        fb["model"] = "claude-sonnet-4-6"
        print("✅ Updated: anthropic → claude-sonnet-4-6")

cfg["fallback_providers"] = fallbacks
with open(path, "w") as f:
    yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
EOF

echo ""
python3 -c "import yaml; yaml.safe_load(open('$YAML')); print('✅ YAML valid')"

PLIST="$HOME/Library/LaunchAgents/ai.hermes.gateway-cloud.plist"
launchctl unload "$PLIST" 2>/dev/null && echo "Unloaded"
pkill -f "hermes_cli.main.*gateway" 2>/dev/null && echo "Killed stale gateway" || echo "(none)"
sleep 8
launchctl load "$PLIST" && echo "Loaded"
sleep 6

echo ""
launchctl list | grep "ai.hermes.gateway-cloud"
echo ""
tail -8 "$HOME/.hermes/profiles/cloud/logs/gateway.log" 2>/dev/null
echo ""
echo "Done."
sleep 6
