#!/usr/bin/env bash
# CC_update_hermes_cloud_token.command — update @Hermes_Cloud_May_bot token in config and restart
LOG="$HOME/Desktop/REX/logs/cc_hermes_cloud_token.log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

NEW_TOKEN="8648749431:AAGladZuVkdK0mOKXFR2c1rKzQUqn4-Cq9U"
CONFIG="$HOME/.hermes-cloud/config.yaml"

echo "── Hermes Cloud Token Update ──"
echo "Config: $CONFIG"

if [ ! -f "$CONFIG" ]; then
  echo "ERROR: Config file not found at $CONFIG"
  echo "Searching for hermes cloud config..."
  find "$HOME" -name "config.yaml" -path "*hermes*" 2>/dev/null | head -5
  sleep 8
  exit 1
fi

echo ""
echo "── Current token line ──"
grep -i "token\|bot_token\|telegram" "$CONFIG" | head -5

echo ""
echo "── Updating token ──"
# Try common YAML key patterns
if grep -q "telegram_token:" "$CONFIG"; then
  sed -i.bak "s|telegram_token:.*|telegram_token: \"$NEW_TOKEN\"|" "$CONFIG"
  echo "Updated 'telegram_token' key"
elif grep -q "bot_token:" "$CONFIG"; then
  sed -i.bak "s|bot_token:.*|bot_token: \"$NEW_TOKEN\"|" "$CONFIG"
  echo "Updated 'bot_token' key"
elif grep -q "token:" "$CONFIG"; then
  sed -i.bak "s|token:.*|token: \"$NEW_TOKEN\"|" "$CONFIG"
  echo "Updated 'token' key"
else
  echo "WARNING: No token key found in config. Adding it..."
  echo "telegram_token: \"$NEW_TOKEN\"" >> "$CONFIG"
fi

echo ""
echo "── Verifying update ──"
grep -i "token" "$CONFIG"

echo ""
echo "── Restarting Hermes Cloud Gateway ──"
PLIST="$HOME/Library/LaunchAgents/ai.hermes.gateway-cloud.plist"
if [ -f "$PLIST" ]; then
  launchctl unload "$PLIST" 2>/dev/null
  sleep 2
  launchctl load "$PLIST"
  sleep 3
  echo "── Status ──"
  launchctl list | grep hermes || echo "(hermes not in launchctl list)"
else
  echo "WARNING: Plist not found at $PLIST"
  echo "Looking for hermes plists..."
  ls -la "$HOME/Library/LaunchAgents/" | grep -i hermes
fi

echo ""
echo "Done."
sleep 5
