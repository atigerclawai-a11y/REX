#!/bin/bash
# Download staff medical files from Gmail
VENV="$HOME/debate-chamber/.venv/bin/python3"
SCRIPT="$HOME/Desktop/REX/download_staff_medicals.py"

echo "=========================================="
echo "  GOJ Staff Medical File Downloader"
echo "  $(date)"
echo "=========================================="
echo ""

if [ ! -f "$VENV" ]; then
    echo "❌ venv not found at $VENV"
    exit 1
fi

if [ ! -f "$SCRIPT" ]; then
    echo "❌ Script not found at $SCRIPT"
    exit 1
fi

"$VENV" "$SCRIPT"

echo ""
read -n 1 -p "Press any key to close..."
