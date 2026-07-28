#!/usr/bin/env bash
# Start REX Telegram bot (occupational assistant)
REX_DIR="$HOME/Desktop/REX"
LOGS="$REX_DIR/logs"
VENV_PYTHON="$HOME/debate-chamber/.venv/bin/python3"
[ ! -f "$VENV_PYTHON" ] && VENV_PYTHON="python3"

echo "Starting REX Telegram bot..."
pkill -f "rex_telegram_bot.py" 2>/dev/null; sleep 2
cd "$REX_DIR"
nohup "$VENV_PYTHON" rex_telegram_bot.py >> "$LOGS/rex_telegram.log" 2>&1 &
sleep 4
if pgrep -f "rex_telegram_bot.py" > /dev/null; then
    echo "✅ REX bot is live — message him on Telegram now"
else
    echo "❌ Failed — last log:"
    tail -10 "$LOGS/rex_telegram.log"
fi
echo "Press Enter to close..."; read
