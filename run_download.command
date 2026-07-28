#!/bin/bash
cd "$(dirname "$0")"
python3 download_menus.py
echo ""
echo "Press any key to close..."
read -n 1
