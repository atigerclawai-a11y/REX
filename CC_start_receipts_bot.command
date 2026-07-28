#!/usr/bin/env bash
# CC_start_receipts_bot.command — start @GOJReceipts_bot with new token
LOG="$HOME/Desktop/REX/logs/cc_receipts_bot.log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

export TELEGRAM_BOT_TOKEN="8691447155:AAGxIpxCoXz119ajZxISWpevztf9ZmeeJ9U"
BOT_DIR="$HOME/Desktop/receipt_processor"
BOT_SCRIPT="$BOT_DIR/telegram_bot.py"

echo "── @GOJReceipts_bot Startup ──"

if [ ! -f "$BOT_SCRIPT" ]; then
  echo "ERROR: Bot script not found at $BOT_SCRIPT"
  echo "Searching for receipt bot..."
  find "$HOME/Desktop" -name "telegram_bot.py" 2>/dev/null | head -5
  sleep 8
  exit 1
fi

echo "Found: $BOT_SCRIPT"

# Kill any existing instance
pkill -f "receipt_processor/telegram_bot.py" 2>/dev/null && echo "Stopped old instance" || echo "No old instance running"
sleep 1

# Find Python
PYTHON=$(which python3)
if [ -f "$BOT_DIR/.venv/bin/python3" ]; then
  PYTHON="$BOT_DIR/.venv/bin/python3"
elif [ -f "$BOT_DIR/venv/bin/python3" ]; then
  PYTHON="$BOT_DIR/venv/bin/python3"
fi
echo "Python: $PYTHON"

# Start bot
cd "$BOT_DIR"
nohup "$PYTHON" telegram_bot.py >> "$LOG" 2>&1 &
BOT_PID=$!
sleep 3

echo ""
echo "── Status ──"
if kill -0 $BOT_PID 2>/dev/null; then
  echo "✓ @GOJReceipts_bot running — PID $BOT_PID"
else
  echo "✗ Bot failed to start — check log: $LOG"
fi

echo ""
echo "Done. Log: $LOG"
sleep 5
