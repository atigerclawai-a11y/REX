#!/usr/bin/env bash
# CC_show_error_log.command — show gateway error log + model config
LOG="$HOME/Desktop/REX/logs/cc_show_error_log.log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

HERMES_HOME="$HOME/.hermes/profiles/cloud"
GATEWAY_CONFIG="$HERMES_HOME/config.yaml"

echo "══════════════════════════════════"
echo "  Gateway Error Log + Model Config"
echo "══════════════════════════════════"
echo ""

echo "── gateway.error.log (last 60 lines) ──"
tail -60 "$HERMES_HOME/logs/gateway.error.log" 2>/dev/null || echo "(not found)"

echo ""
echo "── gateway.log — model/provider lines ──"
grep -iE "deepseek|model|provider|llm|api.*key|key.*api|error|failed|timeout" \
  "$HERMES_HOME/logs/gateway.log" 2>/dev/null | tail -40

echo ""
echo "── config.yaml — provider/model section ──"
python3 - "$GATEWAY_CONFIG" <<'EOF'
import sys, yaml
path = sys.argv[1]
try:
    cfg = yaml.safe_load(open(path)) or {}
except Exception as e:
    print(f"Cannot parse: {e}")
    sys.exit(0)

# Show top-level keys
print("Top-level keys:", list(cfg.keys()))
print()

# Show model/provider/llm sections
for key in ["model", "provider", "llm", "deepseek", "fallback_providers", "agent"]:
    if key in cfg:
        print(f"{key}: {cfg[key]}")
EOF

echo ""
echo "── .env file (current) ──"
cat "$HERMES_HOME/.env" 2>/dev/null | grep -v "SECRET\|TOKEN\|KEY\|PASSWORD" || echo "(empty or not found)"
echo "(sensitive keys hidden — checking for DEEPSEEK specifically)"
grep -i "deepseek\|model\|provider" "$HERMES_HOME/.env" 2>/dev/null || echo "(none found)"

echo ""
echo "Done."
sleep 8
