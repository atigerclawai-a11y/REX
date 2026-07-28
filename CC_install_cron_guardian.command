#!/bin/bash
# CC_install_cron_guardian.command — Install the GHS Cron Guardian
# Self-healing agent: monitors cron jobs, auto-fixes, sends one 9pm digest
exec > >(tee "$HOME/Desktop/REX/logs/cron_guardian_install_$(date +%Y%m%d_%H%M%S).log") 2>&1

echo "=== GHS CRON GUARDIAN INSTALL ==="
echo "Time: $(date)"
echo ""

# Activate venv
if [ -f "$HOME/.rex-venv/bin/activate" ]; then
    source "$HOME/.rex-venv/bin/activate"
elif [ -f "$HOME/debate-chamber/.venv/bin/activate" ]; then
    source "$HOME/debate-chamber/.venv/bin/activate"
else
    echo "⚠️  No venv found — using system Python"
fi

echo "[1/2] Installing LaunchAgent..."
python "$HOME/Desktop/REX/CC_cron_guardian.py" install

echo ""
echo "[2/2] Verifying..."
sleep 2
launchctl list | grep cron-guardian && echo "✅ Guardian is running" || echo "⚠️  Check launchctl manually"

echo ""
echo "✅ DONE. Cron Guardian runs every 2 minutes."
echo "   9pm digest → Telegram (chat_id 5587703834)"
echo "   Log: ~/Desktop/REX/logs/cron_guardian.log"
echo "   Digest buffer: ~/Desktop/REX/CC_cron_digest.json"
echo ""
echo "Commands:"
echo "  python CC_cron_guardian.py status   — see today's buffer"
echo "  python CC_cron_guardian.py digest   — preview tonight's message"
echo "  python CC_cron_guardian.py digest --send  — force-send now"
echo ""
read -p "Press Enter to close..."
