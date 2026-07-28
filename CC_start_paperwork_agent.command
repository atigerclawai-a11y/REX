#!/bin/bash
LOG="$HOME/Desktop/REX/logs/paperwork_agent.log"
exec > >(tee "$LOG") 2>&1

echo "=== CC Paperwork Agent ==="
echo "Time: $(date)"

echo "--- Stopping any existing instance ---"
pkill -f "CC_paperwork_agent" 2>/dev/null && echo "Stopped old process." || echo "None running."
sleep 2

echo "--- Starting Paperwork Agent on port 8003 ---"
source ~/.rex-venv/bin/activate 2>/dev/null || source ~/debate-chamber/.venv/bin/activate
cd "$HOME/Desktop/REX"

nohup python CC_paperwork_agent.py --port 8003 >> "$LOG" 2>&1 &
PID=$!
sleep 3

if kill -0 $PID 2>/dev/null; then
    echo "Paperwork Agent started. PID: $PID"
    echo "API: http://localhost:8003"
    echo "Forms: http://localhost:8003/api/forms"
    echo "Profile: http://localhost:8003/api/profile"
else
    echo "FAILED to start. Check $LOG"
fi

echo ""
echo "Press Enter to close..."
read
