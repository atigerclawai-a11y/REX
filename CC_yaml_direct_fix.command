#!/usr/bin/env bash
# CC_yaml_direct_fix.command — direct fix for line 18 of Hermes cloud config.yaml
LOG="$HOME/Desktop/REX/logs/cc_yaml_direct_fix.log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

YAML="$HOME/.hermes/profiles/cloud/config.yaml"

echo "── Direct YAML fix for line 18 ──"
echo "File: $YAML"
echo ""

if [ ! -f "$YAML" ]; then
  echo "ERROR: File not found at $YAML"
  sleep 8; exit 1
fi

echo "Lines 15-22 before fix:"
awk 'NR>=15 && NR<=22 {printf "%3d: %s\n", NR, $0}' "$YAML"

echo ""
echo "Creating backup..."
cp "$YAML" "${YAML}.bak_$(date +%Y%m%d_%H%M%S)" && echo "Backup OK"

echo ""
echo "Fixing line 18 (fallback_ → fallback_providers:)..."
python3 - "$YAML" <<'EOF'
import sys
path = sys.argv[1]
lines = open(path).readlines()
idx = 17  # line 18
print(f"Before: {repr(lines[idx].rstrip())}")
lines[idx] = "fallback_providers:\n"
print(f"After:  {repr(lines[idx].rstrip())}")
open(path, 'w').writelines(lines)
print("Saved.")
EOF

echo ""
echo "Validating YAML..."
python3 - "$YAML" <<'EOF'
import sys, yaml
try:
    yaml.safe_load(open(sys.argv[1]))
    print("✅ YAML is valid")
except yaml.YAMLError as e:
    print(f"❌ Still invalid: {e}")
    sys.exit(1)
EOF

if [ $? -ne 0 ]; then
  sleep 8; exit 1
fi

echo ""
echo "Restarting cloud gateway..."
PLIST="$HOME/Library/LaunchAgents/ai.hermes.gateway-cloud.plist"
launchctl unload "$PLIST" 2>/dev/null && echo "Unloaded old instance"
sleep 5
launchctl load "$PLIST" && echo "Loaded fresh instance"
sleep 6

echo ""
echo "Gateway status:"
launchctl list | grep "ai.hermes.gateway-cloud"

echo ""
echo "Recent log (last 20 lines):"
tail -20 "$HOME/.hermes/profiles/cloud/logs/gateway.log" 2>/dev/null

echo ""
echo "✅ Done."
sleep 8
