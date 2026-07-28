#!/bin/bash
# Reruns the HYBRID OCR pipeline on all unprocessed menu PDFs
cd ~/Desktop/REX
echo "=== GOJ Menu OCR — HYBRID Stack ==="
echo "Started: $(date)"
echo ""

PYTHON=""
if [ -f ~/Desktop/REX/.venv/bin/python3 ]; then
    PYTHON=~/Desktop/REX/.venv/bin/python3
elif command -v ~/.pyenv/shims/python3 &>/dev/null; then
    PYTHON=~/.pyenv/shims/python3
else
    PYTHON=python3
fi

echo "Python: $PYTHON"
echo ""

$PYTHON ~/Desktop/REX/goj_menu_ocr.py --batch ~/Documents/goj\ files/dashboard/documents/menus/ 2>&1

echo ""
echo "=== Done: $(date) — You can close this window. ==="
