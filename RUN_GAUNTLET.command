#!/bin/bash
# ====================================================================
#  LUCY CORE — Gauntlet Background Runner V1.5
#  Phase 4 | GHS / GOJ Hardening Plan
#
#  Deterministic adversarial test harness.
#  NEVER touches production data — all runs use isolated temp envs.
#
#  5 categories:
#    policy_attacks    — bypass attempts, secrecy forgery
#    memory_attacks    — overflow, corruption, dedup
#    ocr_poisoning     — injected text, schema bypass
#    tool_abuse        — malformed inputs, boundary violations
#    resource_starvation — write storms, large vault, rapid events
#
#  Double-click to run all categories.
#  Critical failures → CRITICAL alert to Rex alert bus.
# ====================================================================

set -uo pipefail

REX="$HOME/Desktop/REX"
LOG_DIR="$REX/logs"
TS=$(date +%Y%m%d_%H%M%S)
LOG="$LOG_DIR/gauntlet_${TS}.log"
mkdir -p "$LOG_DIR"
exec > >(tee "$LOG") 2>&1

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  LUCY CORE — GAUNTLET V1.5                              ║"
echo "║  Deterministic Adversarial Harness                      ║"
echo "║  $(date +%Y-%m-%d\ %H:%M:%S)                                  ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  ⚠️  This harness NEVER touches production data."
echo "  All runs use isolated temporary environments."
echo ""

PY=""
for C in "$REX/.venv/bin/python3" "$(command -v python3 2>/dev/null)"; do
    [ -f "$C" ] && PY="$C" && break
done
[ -z "$PY" ] && echo "❌ No Python found." && read -n 1 && exit 1

# ── Dependency check ─────────────────────────────────────────────────────────
for pkg in yaml cryptography; do
    "$PY" -c "import $pkg" 2>/dev/null || {
        echo "❌ Missing: $pkg — run: pip3 install pyyaml cryptography"
        read -n 1; exit 1
    }
done

# ── Parse optional args ───────────────────────────────────────────────────────
CATEGORY="${1:-}"
SCENARIO_ID="${2:-}"
EXTRA_ARGS=""
[ -n "$CATEGORY" ]    && EXTRA_ARGS="$EXTRA_ARGS --category $CATEGORY"
[ -n "$SCENARIO_ID" ] && EXTRA_ARGS="$EXTRA_ARGS --id $SCENARIO_ID"

cd "$REX"

echo "Running Gauntlet…"
echo ""
"$PY" -m core.gauntlet.runner $EXTRA_ARGS
EXIT=$?

echo ""
if [ $EXIT -eq 0 ]; then
    echo "✅  Gauntlet complete — all scenarios passed."
else
    echo "❌  Gauntlet complete — FAILURES DETECTED. Check log: $LOG"
fi

echo ""
read -n 1 -p "Press any key to close..."
exit $EXIT
