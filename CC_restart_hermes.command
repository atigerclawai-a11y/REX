#!/bin/bash
# CC_restart_hermes.command
# Restarts Hermes cloud gateway (port 3002)
exec > >(tee "$HOME/Desktop/REX/logs/hermes_restart_$(date +%Y%m%d_%H%M%S).log") 2>&1

echo "=== HERMES GATEWAY RESTART ==="
echo "$(date)"
echo ""

echo "Unloading plist..."
launchctl unload ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist 2>/dev/null
echo "Killing any lingering processes..."
pkill -f "hermes_cli.main.*gateway" 2>/dev/null
echo "Waiting 8 seconds..."
sleep 8
echo "Loading plist..."
launchctl load ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist
echo ""
echo "Waiting 5 seconds for startup..."
sleep 5
echo ""
echo "Checking port 3002..."
curl -s http://localhost:3002/health && echo "" || echo "Port 3002 not responding yet — check logs"
echo ""
echo "=== DONE ==="
read -p "Press Enter to close..."
