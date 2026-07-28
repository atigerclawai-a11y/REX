#!/bin/bash
PLIST="$HOME/Library/LaunchAgents/com.rex.email-pdf-watcher.plist"
SRC="$HOME/Desktop/REX/launchd/com.rex.email-pdf-watcher.plist"

# Copy updated plist to LaunchAgents
cp "$SRC" "$PLIST"

# Unload if already loaded (ignore errors)
launchctl unload "$PLIST" 2>/dev/null

# Load with updated config
launchctl load "$PLIST"

echo "Watcher reloaded. Checking status..."
launchctl list | grep email-pdf-watcher

echo ""
echo "Done. Press any key to close."
read -n 1
