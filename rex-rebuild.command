#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
#  REX — One-Click Rebuild + Restart
#  Double-click in Finder to rebuild and restart everything.
#
#  FIRST TIME: Right-click → Open (to allow macOS to run it)
# ─────────────────────────────────────────────────────────────────────

cd "$(dirname "$0")"
REX_DIR="$(pwd)"

BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}   🦖  REX Rebuild + Restart${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

# ── 1. Stop existing backend ──────────────────────────────────────────
echo -e "${YELLOW}[1/4]${NC} Stopping existing REX processes..."
pkill -f "uvicorn.*backend.main" 2>/dev/null
pkill -f "rex_telegram_bot"      2>/dev/null
pkill -f "rex_rexxie_telegram"   2>/dev/null
sleep 1
echo -e "  ${GREEN}✓ Stopped${NC}"

# ── 2. Rebuild frontend ───────────────────────────────────────────────
echo -e "\n${YELLOW}[2/4]${NC} Rebuilding frontend (~15 seconds)..."
cd "$REX_DIR/frontend"

if [ ! -d "node_modules" ]; then
  echo -e "  Installing packages first (one-time, ~60 seconds)..."
  npm install --silent
fi

# Capture build output and exit code correctly
BUILD_OUTPUT=$(npm run build 2>&1)
BUILD_EXIT=${PIPESTATUS[0]:-$?}

if echo "$BUILD_OUTPUT" | grep -qi "error"; then
  echo -e "  ${RED}✗ Build error:${NC}"
  echo "$BUILD_OUTPUT" | grep -i "error" | head -5
  echo ""
  echo "Press Enter to close..."
  read
  exit 1
fi

echo -e "  ${GREEN}✓ Frontend rebuilt successfully${NC}"
cd "$REX_DIR"

# ── 3. Ensure logs directory exists ───────────────────────────────────
mkdir -p "$REX_DIR/logs"

# ── 4. Start REX backend ──────────────────────────────────────────────
echo -e "\n${YELLOW}[3/4]${NC} Starting REX backend on port 8000..."

if [ -d ".venv" ]; then
  PYTHON="$REX_DIR/.venv/bin/python"
else
  PYTHON="python3"
fi

nohup "$PYTHON" -m uvicorn backend.main:app \
  --host 0.0.0.0 --port 8000 --log-level warning \
  > "$REX_DIR/logs/backend.log" 2>&1 &

# Wait and verify
for i in 1 2 3 4 5; do
  sleep 1
  if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓ Backend running${NC}"
    break
  fi
  if [ $i -eq 5 ]; then
    echo -e "  ${YELLOW}⚠ Backend slow to start — check logs/backend.log if issues persist${NC}"
  fi
done

# ── 5. Start Telegram bots ────────────────────────────────────────────
echo -e "\n${YELLOW}[4/4]${NC} Restarting Telegram bots..."

REX_TOKEN=$(python3 -c "import json; d=json.load(open('rex_telegram_config.json')); print(d.get('bot_token',''))" 2>/dev/null)
REXXIE_TOKEN=$(python3 -c "import json; d=json.load(open('rex_rexxie_telegram_config.json')); print(d.get('bot_token',''))" 2>/dev/null)

if [ -n "$REX_TOKEN" ] && [ "$REX_TOKEN" != "YOUR_BOT_TOKEN_HERE" ]; then
  nohup "$PYTHON" rex_telegram_bot.py > logs/rex_bot.log 2>&1 &
  echo -e "  ${GREEN}✓ REX Telegram bot started${NC}"
fi

if [ -n "$REXXIE_TOKEN" ] && [ "$REXXIE_TOKEN" != "YOUR_BOT_TOKEN_HERE" ]; then
  nohup "$PYTHON" rex_rexxie_telegram_bot.py > logs/rexxie_bot.log 2>&1 &
  echo -e "  ${GREEN}✓ Rexxie Telegram bot started${NC}"
fi

# ── Done ──────────────────────────────────────────────────────────────
MAC_IP=$(ipconfig getifaddr en0 2>/dev/null || echo "YOUR-MAC-IP")
echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✅  Done! REX is live.${NC}"
echo -e "${GREEN}${NC}"
echo -e "${GREEN}  Mac browser:  http://localhost:8000${NC}"
echo -e "${GREEN}  iPhone (WiFi): http://${MAC_IP}:8000${NC}"
echo -e "${GREEN}${NC}"
echo -e "${GREEN}  ⚠  Press Cmd+Shift+R in Chrome to force${NC}"
echo -e "${GREEN}     a full reload and see latest changes.${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

open http://localhost:8000

echo "Press Enter to close this window..."
read
