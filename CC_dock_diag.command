#!/bin/bash
# CC_dock_diag.command — find why Dock keeps crashing, then fix it
LOG=~/Desktop/REX/logs/dock_diag_$(date +%Y%m%d_%H%M%S).log
mkdir -p ~/Desktop/REX/logs
exec > >(tee "$LOG") 2>&1

echo "=== Dock Crash Diagnostics ==="
echo "$(date)"
echo ""

echo "--- Recent Dock crash reports ---"
ls -t ~/Library/Logs/DiagnosticReports/Dock_*.crash 2>/dev/null | head -5
echo ""

echo "--- Last Dock crash (last 60 lines) ---"
LAST_CRASH=$(ls -t ~/Library/Logs/DiagnosticReports/Dock_*.crash 2>/dev/null | head -1)
if [ -n "$LAST_CRASH" ]; then
    echo "File: $LAST_CRASH"
    tail -60 "$LAST_CRASH"
    # Copy it to REX logs
    cp "$LAST_CRASH" ~/Desktop/REX/logs/dock_last_crash.txt
    echo ""
    echo "--- Exception / crash reason ---"
    grep -E "Exception|Reason|Application Specific|Crashed Thread|Thread.*Crashed" "$LAST_CRASH" | head -20
else
    echo "No crash files found in DiagnosticReports."
fi
echo ""

echo "--- Current Dock plist (what's in the dock) ---"
defaults read com.apple.dock persistent-apps 2>/dev/null | grep -E "file-label|_CFURLString" | head -40
echo ""

echo "--- Check for broken aliases in Dock ---"
defaults read com.apple.dock persistent-apps 2>/dev/null | grep "_CFURLString" | sed 's/.*= "//;s/";//' | while read app_path; do
    # Decode URL if needed
    clean=$(python3 -c "import urllib.parse; print(urllib.parse.unquote('$app_path'))" 2>/dev/null || echo "$app_path")
    if [ ! -e "$clean" ]; then
        echo "  MISSING: $clean"
    fi
done
echo ""

echo "--- Is Dock running now? ---"
pgrep -x Dock && echo "Dock IS running" || echo "Dock NOT running"
echo ""

echo "--- Nuke dock prefs and restart with empty dock ---"
defaults delete com.apple.dock 2>/dev/null
# Remove persistent apps and other-apps so nothing bad auto-loads
defaults write com.apple.dock persistent-apps -array
defaults write com.apple.dock persistent-others -array
killall Dock 2>/dev/null
sleep 3
pgrep -x Dock && echo "Dock restarted OK" || echo "Dock STILL not running"
echo ""

echo "=== Done ==="
echo "Check above for MISSING app paths — those cause dock crashes."
read -p "Press Enter to close..."
