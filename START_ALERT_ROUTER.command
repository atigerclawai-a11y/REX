#!/bin/bash
# ====================================================================
#  LUCY CORE — Rex Alert Router
#  Phase 3 | GHS / GOJ Hardening Plan
#
#  Starts the alert bus (Phase 0) then the alert router (Phase 3).
#  Router tails alert_bus.jsonl and routes events:
#    CRITICAL  → immediate Telegram to Kato
#    WARNING   → 15-min digest (or when 10 accumulate)
#    INFO      → local log only
#
#  Double-click to run. Runs in foreground — close window to stop.
#  Use --daemon to fork to background.
# ====================================================================

set -uo pipefail

REX="$HOME/Desktop/REX"
LOG_DIR="$REX/logs"
TS=$(date +%Y%m%d_%H%M%S)
mkdir -p "$LOG_DIR"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Rex Alert Router — Phase 3                         ║"
echo "║  $(date +%Y-%m-%d\ %H:%M:%S)                              ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Python detection ──────────────────────────────────────────────────────────
PY=""
for C in "$REX/.venv/bin/python3" "$(command -v python3 2>/dev/null)"; do
    [ -f "$C" ] && PY="$C" && break
done
[ -z "$PY" ] && echo "❌ No Python found." && read -n 1 && exit 1

# ── Check alert bus ───────────────────────────────────────────────────────────
SOCK="$REX/data/rex_alert.sock"
if [ ! -S "$SOCK" ]; then
    echo "⚡ Alert bus not running — starting it..."
    "$PY" -m core.alert_bus --daemon \
        --socket "$SOCK" \
        --log "$REX/data/alert_bus.jsonl"
    sleep 1
    [ -S "$SOCK" ] && echo "✅  Alert bus started" || echo "⚠️  Alert bus start failed (router will still process log)"
else
    echo "✅  Alert bus already running"
fi
echo ""

# ── Start router ──────────────────────────────────────────────────────────────
echo "🚦  Starting alert router..."
echo "    CRITICAL  → immediate Telegram"
echo "    WARNING   → digest every 15 min (or 10 items)"
echo "    INFO      → local log only"
echo ""
echo "    Log: $LOG_DIR/alert_router_${TS}.log"
echo ""

cd "$REX"
"$PY" -m core.alert_router 2>&1 | tee "$LOG_DIR/alert_router_${TS}.log"

echo ""
read -n 1 -p "Router stopped. Press any key to close..."
