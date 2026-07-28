#!/bin/bash
# CC_reset_dock.command — reset dock prefs and restart
echo "=== Dock Reset ==="
echo "Deleting dock preferences..."
defaults delete com.apple.dock 2>/dev/null
echo "Killing Dock..."
killall Dock
echo "Done — Dock should reappear in a few seconds."
sleep 3
echo "If dock is still missing, run: rm ~/Library/Preferences/com.apple.dock.plist && killall Dock"
read -p "Press Enter to close..."
