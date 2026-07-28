#!/bin/bash
# ====================================================================
#  REX — Start FastAPI Backend (Multi-Worker Production Mode)
#  Serves the React dashboard AND all API routes
#  at localhost:8000 (and via Tailscale for staff access)
#
#  This is the correct way to start Rex for multi-user operation.
#  FIX_REXXIE.command starts this automatically — run this only
#  if you need to restart the backend independently.
#
#  After starting: staff access the dashboard at:
#    Local:     http://localhost:8000
#    Tailscale: http://[your-tailscale-ip]:8000
# ====================================================================
set -uo pipefail

REX="$HOME/Desktop/REX"
LOG_DIR="$REX/logs"
TS=$(date +%Y%m%d_%H%M%S)
mkdir -p "$LOG_DIR"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  REX FastAPI Backend — Production Mode              ║"
echo "║  $(date +%Y-%m-%d\ %H:%M)                                ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# Kill any existing backend
pkill -f "uvicorn.*backend.main" 2>/dev/null && echo "  Stopped existing backend" || true
sleep 1

# Python detection
PY=""
for C in "$REX/.venv/bin/python3" "$(command -v python3 2>/dev/null)"; do
    [ -f "$C" ] && PY="$C" && break
done
[ -z "$PY" ] && echo "❌ No Python found." && read -n 1 && exit 1

# Install uvicorn if needed
"$PY" -c "import uvicorn" 2>/dev/null || {
    echo "Installing uvicorn..."
    "$PY" -m pip install "uvicorn[standard]" --quiet
}

# Verify DB exists and has data
DB="$HOME/Documents/goj files/dashboard/auth_tracker.db"
if [ ! -f "$DB" ]; then
    echo "❌ auth_tracker.db not found at: $DB"
    echo "   Cannot start backend without the database."
    read -n 1 && exit 1
fi

CLIENT_COUNT=$("$PY" -c "
import sqlite3
conn = sqlite3.connect('$DB')
n = conn.execute('SELECT COUNT(*) FROM clients WHERE active=1').fetchone()[0]
conn.close()
print(n)
" 2>/dev/null || echo "0")

echo "  Database: $DB"
echo "  Active clients: $CLIENT_COUNT"

if [ "$CLIENT_COUNT" -eq 0 ]; then
    echo "  ⚠️  WARNING: No active clients found — check database"
fi

echo ""
echo "  Starting FastAPI with 4 workers..."
echo "  → Local:     http://localhost:8000"
echo "  → Dashboard: http://localhost:8000/app  (if static files mounted)"
echo "  → API docs:  http://localhost:8000/docs"
echo "  → Tailscale: http://[your-tailscale-ip]:8000"
echo ""
echo "  Press Ctrl+C to stop."
echo ""

cd "$REX"
nohup "$PY" -m uvicorn backend.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4 \
    --log-level info \
    >> "$LOG_DIR/api_server_${TS}.log" 2>&1 &

API_PID=$!
sleep 2

if kill -0 $API_PID 2>/dev/null; then
    echo "  ✅ Backend started (pid $API_PID)"
    echo "  Log: $LOG_DIR/api_server_${TS}.log"
    echo ""
    # Quick health check
    HEALTH=$("$PY" -c "
import urllib.request, json
try:
    r = urllib.request.urlopen('http://localhost:8000/api/health', timeout=5)
    d = json.loads(r.read())
    print('✅ Health: ' + str(d.get('status','ok')))
except Exception as e:
    print('⚠️  Health check failed: ' + str(e))
" 2>/dev/null)
    echo "  $HEALTH"
else
    echo "  ❌ Backend failed to start — check log:"
    tail -20 "$LOG_DIR/api_server_${TS}.log"
fi

echo ""
read -n 1 -p "Press any key to close..."
