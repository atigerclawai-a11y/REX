#!/bin/bash
# CC_check_hermes_gateway.command
# Diagnoses why Hermes gateway (port 3002) won't start
# Double-click to run

LOG="$HOME/Desktop/REX/logs/hermes_gateway_check_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

echo "========================================"
echo " Hermes Gateway Diagnostic"
echo " $(date)"
echo "========================================"
echo ""

echo "--- Port 3002 status ---"
lsof -i :3002 2>/dev/null || echo "Nothing on port 3002"
echo ""

echo "--- LaunchAgent status ---"
launchctl list | grep -E "hermes|gateway" || echo "No hermes launchd entries found"
echo ""

echo "--- Last 50 lines of gateway.log ---"
GLOG="$HOME/.hermes/profiles/cloud/logs/gateway.log"
if [ -f "$GLOG" ]; then
    tail -50 "$GLOG"
else
    echo "Gateway log not found at: $GLOG"
fi
echo ""

echo "--- config.yaml provider check ---"
CONFIG="$HOME/.hermes/profiles/cloud/config.yaml"
if [ -f "$CONFIG" ]; then
    grep -A2 -i "provider\|deepseek\|base_url\|api_key" "$CONFIG" | head -30
else
    echo "Config not found at: $CONFIG"
fi
echo ""

echo "--- DeepSeek connectivity test ---"
API_KEY=$(grep -i "deepseek\|api_key" "$HOME/.hermes/profiles/cloud/.env" 2>/dev/null | head -1 | cut -d'=' -f2 | tr -d '"' | tr -d "'")
if [ -n "$API_KEY" ]; then
    echo "Testing api.deepseek.com/v1 ..."
    curl -s -o /dev/null -w "HTTP status: %{http_code}\n" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        "https://api.deepseek.com/v1/models" --max-time 10
else
    echo "Could not find DeepSeek API key in .env"
fi
echo ""

echo "========================================"
echo " Log saved to: $LOG"
echo "========================================"
read -p "Press Enter to close..."
