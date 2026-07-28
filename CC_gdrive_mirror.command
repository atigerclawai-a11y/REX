#!/bin/bash
# CC_gdrive_mirror.command — Mirror all GOJ Google Drive folders to local disk
# Double-click to run. Will open a browser tab for Google auth if needed.

LOG_DIR="$HOME/Desktop/REX/logs"
LOG="$LOG_DIR/cc_gdrive_mirror_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$LOG_DIR"
exec > >(tee "$LOG") 2>&1

echo "======================================================"
echo "  GOJ Google Drive Mirror — $(date)"
echo "======================================================"
echo ""

cd "$HOME/Desktop/REX" || { echo "ERROR: ~/Desktop/REX not found"; read -n 1 -p "Press any key..."; exit 1; }

# Use dev venv if available, else system python
if [ -f ~/debate-chamber/.venv/bin/python3 ]; then
    PYTHON=~/debate-chamber/.venv/bin/python3
elif [ -f ~/.rex-venv/bin/python3 ]; then
    PYTHON=~/.rex-venv/bin/python3
else
    PYTHON=python3.11
fi

echo "Using: $PYTHON"
echo ""

$PYTHON CC_gdrive_mirror.py

echo ""
echo "Log saved: $LOG"
read -n 1 -p "Press any key to close..."
