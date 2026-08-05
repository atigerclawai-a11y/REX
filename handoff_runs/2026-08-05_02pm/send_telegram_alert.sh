#!/bin/bash
# Send GOJ handoff Telegram alert
# Usage: bash send_telegram_alert.sh
TOKEN=$(python3 -c "import json; print(json.load(open('/Users/mainsobhelper/Desktop/REX/rex_rexxie_telegram_config.json'))['telegram_token'])" 2>/dev/null || echo "")
CHAT_ID="5587703834"
MSG=$(cat "$(dirname "$0")/telegram_message.txt")
curl -s -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
  -d chat_id="$CHAT_ID" \
  -d parse_mode="HTML" \
  --data-urlencode text="$MSG"
echo ""
echo "Sent."
