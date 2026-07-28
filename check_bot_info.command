#!/usr/bin/env bash
# Quick check — shows Telegram usernames for both bots
REX_DIR="$HOME/Desktop/REX"
REXXIE_TOKEN=$(python3 -c "import json; print(json.load(open('$REX_DIR/rex_rexxie_telegram_config.json'))['bot_token'])" 2>/dev/null)
REX_TOKEN=$(python3 -c "import json; print(json.load(open('$REX_DIR/rex_telegram_config.json'))['bot_token'])" 2>/dev/null)

echo ""
echo "━━ BOT IDENTITIES ━━━━━━━━━━━━━━━━━━━━━━━━━━━"
REXXIE_INFO=$(curl -s "https://api.telegram.org/bot${REXXIE_TOKEN}/getMe")
REXXIE_USER=$(echo "$REXXIE_INFO" | python3 -c "import sys,json; d=json.load(sys.stdin); print('@' + d['result']['username'])" 2>/dev/null)
REXXIE_NAME=$(echo "$REXXIE_INFO" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['result']['first_name'])" 2>/dev/null)

REX_INFO=$(curl -s "https://api.telegram.org/bot${REX_TOKEN}/getMe")
REX_USER=$(echo "$REX_INFO" | python3 -c "import sys,json; d=json.load(sys.stdin); print('@' + d['result']['username'])" 2>/dev/null)
REX_NAME=$(echo "$REX_INFO" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['result']['first_name'])" 2>/dev/null)

echo "  🐢 Rexxie (personal):     $REXXIE_NAME  →  $REXXIE_USER"
echo "  🦖 REX (occupational):    $REX_NAME  →  $REX_USER"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Open Telegram and search for $REX_USER to message REX."
echo ""
echo "Press Enter to close..."
read
