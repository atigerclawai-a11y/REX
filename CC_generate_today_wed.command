#!/bin/bash
# CC_generate_today_wed.command
# Generates today (Wed Jul 8) sign-in + driver sheets
# AND tomorrow (Thu Jul 9) distribution + kitchen sheets
# Source of truth: Google Drive attendance + menu spreadsheets via CC_drive_preflight

LOG="$HOME/Desktop/REX/logs/CC_generate_wed_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

VENV="$HOME/Desktop/REX/.venv/bin/python3"
DASHBOARD="$HOME/Documents/goj files/dashboard"

echo "============================================="
echo "  GOJ DAILY GENERATOR — $(date)"
echo "============================================="
echo ""

echo ">>> STEP 1: TODAY (Wednesday Jul 8) — sign-in + driver sheets"
echo "--------------------------------------------------------------"
cd "$DASHBOARD"
"$VENV" generate_tomorrow.py --day today --mode signin
echo ""
"$VENV" generate_tomorrow.py --day today --mode drivers
echo ""

echo ">>> STEP 2: TOMORROW (Thursday Jul 9) — distribution + kitchen"
echo "--------------------------------------------------------------"
"$VENV" generate_tomorrow.py --day tomorrow --mode distribution
echo ""

echo "============================================="
echo "  DONE — $(date)"
echo "  Output: $HOME/Documents/goj\ files/output_docs/"
echo "============================================="
echo ""
echo "Press any key to close..."
read -n 1
