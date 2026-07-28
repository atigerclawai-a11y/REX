#!/bin/bash
# GOJ Master Scanner Downloader — downloads all Gmail attachment PDFs
VENV="$HOME/debate-chamber/.venv/bin/python3"
SCRIPT="$HOME/Desktop/REX/DOWNLOAD_ALL_SCANS.py"
echo "==========================================="
echo "  GOJ Master Scanner Downloader"
echo "  $(date)"
echo "==========================================="
"$VENV" "$SCRIPT"
echo ""
read -n 1 -p "Press any key to close..."
