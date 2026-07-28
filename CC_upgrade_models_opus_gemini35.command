#!/usr/bin/env bash
# CC_upgrade_models_opus_gemini35.command — Claude Opus 4.7 + Gemini 3.5
LOG="$HOME/Desktop/REX/logs/cc_upgrade_models_opus_gemini35.log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

YAML="$HOME/.hermes/profiles/cloud/config.yaml"

echo "Upgrading fallback models: Opus 4.7 + Gemini 3.5"
echo ""

cp "$YAML" "${YAML}.bak_$(date +%Y%m%d_%H%M%S)"

python3 - "$YAML" <<'EOF'
import sys, yaml

path = sys.argv[1]
cfg = yaml.safe_load(open(path)) or {}

fallbacks = cfg.get("fallback_providers") or []
for fb in fallbacks:
    if fb.get("provider") == "anthropic":
        fb["model"] = "claude-opus-4-7"
        print("✅ Claude → claude-opus-4-7")
    if fb.get("provider") == "google":
        fb["model"] = "gemini-3.5-flash"
        print("✅ Gemini → gemini-3.5-flash")

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
tail -6 "$HOME/.hermes/profiles/cloud/logs/gateway.log" 2>/dev/null
echo ""
echo "Done."
sleep 6
