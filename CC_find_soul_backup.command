#!/bin/bash
# CC_find_soul_backup.command — Find original SOUL.md backup

echo "=== Finding SOUL.md Backup $(date) ==="

echo ""
echo "--- External drive /Volumes/cartoons/ ---"
find /Volumes/cartoons/ -name "SOUL.md" 2>/dev/null
find /Volumes/cartoons/ -name "*soul*" -o -name "*hermes*backup*" 2>/dev/null | grep -v ".DS_Store" | head -30

echo ""
echo "--- Hermes critical backup ~/Desktop/hermes_critical_backup/ ---"
find ~/Desktop/hermes_critical_backup/ -name "SOUL.md" 2>/dev/null
ls ~/Desktop/hermes_critical_backup/ 2>/dev/null | head -20

echo ""
echo "--- ~/.hermes/backups/ ---"
ls ~/.hermes/backups/ 2>/dev/null
find ~/.hermes/backups/ -name "SOUL.md" 2>/dev/null

echo ""
echo "--- Hermes Backups in Google Drive (if synced) ---"
find ~/Library/CloudStorage/ -name "SOUL.md" 2>/dev/null | head -5
find ~/Google\ Drive/ -name "SOUL.md" 2>/dev/null | head -5

echo ""
echo "--- Any SOUL.md anywhere on disk (excluding node_modules/venv) ---"
find ~ -name "SOUL.md" 2>/dev/null | grep -v "node_modules" | grep -v "/venv/" | grep -v "/.Trash/"

echo ""
echo "Press any key to close..."
read -n 1
