#!/bin/bash
# CC_open_builds.command — Open all June 4 build files in Chrome

LOG="$HOME/Desktop/REX/logs/CC_open_builds_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

echo "=== Opening June 4 Build Files $(date) ==="
echo ""

echo "[1] Command Center (all 10 tabs)..."
open -a "Google Chrome" "file://$HOME/Desktop/REX/CC_command_center.html"
sleep 1

echo "[2] Web Rack (D3.js screensaver)..."
open -a "Google Chrome" "file://$HOME/Desktop/REX/CC_web_rack.html"
sleep 1

echo "[3] Bill Dashboard..."
open -a "Google Chrome" "file://$HOME/Desktop/REX/CC_rex_bill_dashboard.html"
sleep 1

echo "[4] GOJ Dashboard (already open, refreshing)..."
open -a "Google Chrome" "http://localhost:8080"
sleep 1

echo "[5] GOJ Admin Dashboard..."
open -a "Google Chrome" "http://localhost:8080/dashboard"
sleep 1

echo ""
echo "=== All files opened $(date) ==="
echo ""
echo "Open files:"
echo "  • file://$HOME/Desktop/REX/CC_command_center.html"
echo "  • file://$HOME/Desktop/REX/CC_web_rack.html"
echo "  • file://$HOME/Desktop/REX/CC_rex_bill_dashboard.html"
echo "  • http://localhost:8080  (Employee Portal)"
echo "  • http://localhost:8080/dashboard  (Admin Dashboard)"
echo ""
echo "OCR data status:"
sqlite3 "$HOME/Documents/goj files/dashboard/auth_tracker.db" \
    "SELECT 'Last OCR: ' || MAX(created_at) || ' | Total records: ' || COUNT(*) FROM client_menus;" 2>/dev/null \
    || echo "  (could not query auth_tracker.db)"
echo ""
echo "Press any key to close..."
read -n 1
