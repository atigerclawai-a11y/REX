#!/bin/bash
LOG="$HOME/Desktop/REX/logs/goj_dashboard_check.log"
exec > >(tee "$LOG") 2>&1

echo "=== GOJ Dashboard Diagnostic ==="
echo "Time: $(date)"
echo ""

echo "--- Port 8080 status ---"
lsof -i :8080 | head -20
echo ""

echo "--- launchctl com.goj.datarex ---"
launchctl list | grep -E "goj|datarex" || echo "NOT FOUND in launchctl"
echo ""

echo "--- curl health check ---"
curl -s --max-time 5 http://localhost:8080/health && echo "" || echo "FAILED: no response on :8080"
curl -s --max-time 5 http://localhost:8080/ | head -5 && echo "" || echo "FAILED: / not responding"
echo ""

echo "--- datarex app.py location ---"
ls -la ~/.hermes-cloud/home/goj-pipeline/datarex/app.py 2>/dev/null || echo "app.py NOT FOUND at expected path"
ls ~/.hermes-cloud/home/goj-pipeline/datarex/ 2>/dev/null
echo ""

echo "--- Last 30 lines of datarex log ---"
LOGFILE=$(find ~/Library/Logs ~/Desktop/REX/logs -name "*datarex*" -o -name "*goj*dashboard*" 2>/dev/null | head -3)
if [ -n "$LOGFILE" ]; then
  for f in $LOGFILE; do
    echo "=== $f ==="
    tail -30 "$f"
  done
else
  echo "No datarex/goj log found in standard locations"
fi

echo ""
echo "--- launchctl plist status ---"
launchctl list com.goj.datarex 2>&1 || echo "com.goj.datarex not loaded"

echo ""
echo "--- Pipeline data freshness ---"
ls -la ~/.hermes-cloud/home/goj-pipeline/data/*.json 2>/dev/null | tail -10 || echo "No JSON files found"

echo ""
echo "--- Python process check ---"
ps aux | grep -E "datarex|app.py|flask|gunicorn" | grep -v grep || echo "No Flask/datarex process running"

echo ""
echo "=== End Diagnostic ==="
echo "Press Enter to close..."
read
