#!/bin/bash
# CC_run_sheets_now.command
# Runs Sunday sign-in + all Monday sheets and sends to Telegram.
# Double-click to run.

LOG="$HOME/Desktop/REX/logs/run_sheets_now.log"
mkdir -p "$HOME/Desktop/REX/logs"

PYTHON="$HOME/.rex-venv/bin/python3"
SCRIPT="$HOME/Documents/goj files/dashboard/generate_tomorrow.py"

{
echo "════════════════════════════════════════════════════════"
echo " GOJ — Sunday Signin + All Monday Sheets"
echo " $(date)"
echo "════════════════════════════════════════════════════════"
echo ""

if [ ! -f "$PYTHON" ]; then
    echo "ERROR: Python venv not found at $PYTHON"
    exit 1
fi
if [ ! -f "$SCRIPT" ]; then
    echo "ERROR: generate_tomorrow.py not found at $SCRIPT"
    exit 1
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " STEP 1 of 2 — Sunday sign-in sheet"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
"$PYTHON" "$SCRIPT" --day Sunday --mode signin --send
SUNDAY_EXIT=$?
echo ""

if [ $SUNDAY_EXIT -eq 0 ]; then
    echo "✅ Sunday signin sent to Telegram"
else
    echo "❌ Sunday signin FAILED (exit $SUNDAY_EXIT)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " STEP 2 of 2 — Monday all sheets (signin + drivers + kitchen + distribution)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
"$PYTHON" "$SCRIPT" --day Monday --mode all --send
MONDAY_EXIT=$?
echo ""

if [ $MONDAY_EXIT -eq 0 ]; then
    echo "✅ Monday sheets sent to Telegram"
else
    echo "❌ Monday sheets FAILED (exit $MONDAY_EXIT)"
fi

echo ""
echo "════════════════════════════════════════════════════════"
if [ $SUNDAY_EXIT -eq 0 ] && [ $MONDAY_EXIT -eq 0 ]; then
    echo " ALL DONE — check Telegram for the PDFs"
else
    echo " FINISHED WITH ERRORS — scroll up for details"
fi
echo "════════════════════════════════════════════════════════"
} 2>&1 | tee "$LOG"

read -n 1 -s -p "Press any key to close."
echo ""
