#!/bin/bash
# Runs DB cleanup + syntax check for the OCR pipeline bug fixes
cd ~/Desktop/REX
echo "=== DB Cleanup + Syntax Check ==="
~/.pyenv/shims/python3 ~/Desktop/REX/CC_DB_CLEANUP_AND_SYNTAXCHECK.py 2>&1 || \
~/Desktop/REX/.venv/bin/python3 ~/Desktop/REX/CC_DB_CLEANUP_AND_SYNTAXCHECK.py 2>&1 || \
python3 ~/Desktop/REX/CC_DB_CLEANUP_AND_SYNTAXCHECK.py 2>&1
echo ""
echo "=== Done. You can close this window. ==="
