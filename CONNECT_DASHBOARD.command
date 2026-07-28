#!/bin/bash
# ====================================================================
#  CONNECT DASHBOARD — Wire your Railway frontend to your Mac's data
#  
#  What this does:
#    1. Detects your Mac's Tailscale IP
#    2. Confirms FastAPI is listening on 0.0.0.0:8000 (all interfaces)
#    3. Tests that your local DB is reachable through FastAPI
#    4. Tests that the API is reachable via Tailscale
#    5. Outputs the EXACT text to paste into Railway's env vars
#
#  After running this, you copy 2 values into Railway and you're done.
# ====================================================================
set -uo pipefail
REX="$HOME/Desktop/REX"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Connect Dashboard to Real Data                         ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── Step 1: Check Tailscale ─────────────────────────────────────
echo "▶ Step 1/5 — Tailscale"
if ! command -v tailscale &>/dev/null; then
    echo "  ❌ Tailscale CLI not found. Install from https://tailscale.com/download"
    read -n 1 -p "Press any key to close..."; exit 1
fi

TS_STATUS=$(tailscale status --json 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('BackendState','unknown'))" 2>/dev/null)
if [ "$TS_STATUS" != "Running" ]; then
    echo "  ❌ Tailscale is not running. Open the Tailscale app → Connect."
    read -n 1 -p "Press any key to close..."; exit 1
fi

TS_IP=$(tailscale ip -4 2>/dev/null | head -1)
if [ -z "$TS_IP" ]; then
    echo "  ❌ Could not get Tailscale IP"; read -n 1; exit 1
fi
echo "  ✅ Tailscale running — your Mac's Tailscale IP: $TS_IP"

# ── Step 2: Confirm FastAPI is running on 0.0.0.0 ───────────────
echo ""
echo "▶ Step 2/5 — FastAPI backend"
if ! pgrep -f "uvicorn.*backend.main" > /dev/null; then
    echo "  ⚠️  FastAPI not running. Starting it..."
    cd "$REX"
    nohup .venv/bin/python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4 \
        >> "$REX/logs/api_connect.log" 2>&1 &
    sleep 3
fi

# Verify it's listening on 0.0.0.0 (not just 127.0.0.1)
LISTEN_ALL=$(lsof -iTCP:8000 -sTCP:LISTEN 2>/dev/null | grep -c "\*:8000")
if [ "$LISTEN_ALL" -eq 0 ]; then
    echo "  ⚠️  FastAPI is only on localhost. Restarting with --host 0.0.0.0..."
    pkill -f "uvicorn.*backend.main" 2>/dev/null; sleep 2
    cd "$REX"
    nohup .venv/bin/python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4 \
        >> "$REX/logs/api_connect.log" 2>&1 &
    sleep 3
fi
echo "  ✅ FastAPI listening on 0.0.0.0:8000 (all interfaces)"

# ── Step 3: Test local data access ──────────────────────────────
echo ""
echo "▶ Step 3/5 — Local data test"
SUMMARY=$(curl -s "http://localhost:8000/api/dashboard/summary" 2>/dev/null)
CLIENT_COUNT=$(echo "$SUMMARY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('clients',{}).get('total_active','?'))" 2>/dev/null)
echo "  ✅ Clients visible via API: $CLIENT_COUNT"

# ── Step 4: Test Tailscale access ───────────────────────────────
echo ""
echo "▶ Step 4/5 — Tailscale access test"
TS_TEST=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://$TS_IP:8000/api/health" 2>/dev/null)
if [ "$TS_TEST" = "200" ]; then
    echo "  ✅ API reachable via Tailscale IP: http://$TS_IP:8000"
else
    echo "  ⚠️  Tailscale test returned HTTP $TS_TEST — check firewall or MagicDNS"
    echo "     You may still be able to access it via Tailscale from another device"
fi

# ── Step 5: Output Railway env vars ─────────────────────────────
echo ""
echo "▶ Step 5/5 — Railway configuration"
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  COPY THESE VALUES INTO RAILWAY                         ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  1. Open https://railway.app → your GOJ dashboard project"
echo "  2. Click Variables tab"
echo "  3. Add or update these two variables:"
echo ""
echo "  ┌──────────────────────────────────────────────────────┐"
echo "  │  Name:   NEXT_PUBLIC_API_URL                         │"
echo "  │  Value:  http://$TS_IP:8000                          │"
echo "  └──────────────────────────────────────────────────────┘"
echo ""
echo "  ┌──────────────────────────────────────────────────────┐"
echo "  │  Name:   DATABASE_URL                                │"
echo "  │  Value:  (DELETE this variable entirely)             │"
echo "  └──────────────────────────────────────────────────────┘"
echo ""
echo "  4. Click Deploy. Railway rebuilds with the new config (~1 minute)."
echo "  5. Refresh goldhealthsys.com — it now reads from your Mac via Tailscale."
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Alternative (simplest): Skip Railway entirely."
echo "  Your React dashboard is already served by FastAPI."
echo "  Staff can access it right now at:  http://$TS_IP:8000"
echo "  Bookmark that URL on every staff device. Done."
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Log:     $REX/logs/api_connect.log"
echo "  FastAPI status: $(pgrep -f "uvicorn.*backend.main" | wc -l | tr -d ' ') worker(s) running"
echo ""
read -n 1 -p "Press any key to close..."
