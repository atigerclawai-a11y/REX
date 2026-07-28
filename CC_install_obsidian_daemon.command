#!/bin/bash
# CC_install_obsidian_daemon.command
# Installs the Obsidian live daemon as a proper launchd job.
# Kills any existing manual loop, then loads the plist so launchd manages it.
# Double-click to run.

LOG="$HOME/Desktop/REX/logs/install_obsidian_daemon.log"
mkdir -p "$HOME/Desktop/REX/logs"

PLIST_SRC="$HOME/Desktop/REX/com.ghs.obsidian-daemon.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.ghs.obsidian-daemon.plist"
DAEMON="$HOME/Desktop/REX/CC_obsidian_live_daemon.py"
PYTHON="$HOME/debate-chamber/.venv/bin/python3"

{
echo "════════════════════════════════════════════════════════"
echo " GHS Obsidian Daemon — Install"
echo " $(date)"
echo "════════════════════════════════════════════════════════"
echo ""

# ── Verify deps ──────────────────────────────────────────────────────────────
if [ ! -f "$PYTHON" ]; then
    echo "❌ ERROR: Python venv not found at $PYTHON"
    exit 1
fi
echo "✅ Python: OK"

if [ ! -f "$DAEMON" ]; then
    echo "❌ ERROR: Daemon script not found at $DAEMON"
    exit 1
fi
echo "✅ Daemon script: OK"

if [ ! -f "$PLIST_SRC" ]; then
    echo "❌ ERROR: Plist not found at $PLIST_SRC"
    exit 1
fi
echo "✅ Plist source: OK"
echo ""

# ── Kill any existing manual daemon loop ────────────────────────────────────
echo "Stopping any existing daemon processes..."
KILLED=0
while IFS= read -r pid; do
    if [ -n "$pid" ]; then
        echo "  Killing PID $pid (CC_obsidian_live_daemon.py)"
        kill "$pid" 2>/dev/null && KILLED=$((KILLED+1))
    fi
done < <(pgrep -f "CC_obsidian_live_daemon.py" 2>/dev/null)

if [ $KILLED -eq 0 ]; then
    echo "  No existing daemon process found."
else
    echo "  Stopped $KILLED process(es)."
    sleep 2
fi
echo ""

# ── Unload if previously loaded ─────────────────────────────────────────────
launchctl unload "$PLIST_DST" 2>/dev/null

# ── Install plist ──────────────────────────────────────────────────────────
echo "Installing launchd job..."
cp "$PLIST_SRC" "$PLIST_DST"
launchctl load "$PLIST_DST"
LOAD_EXIT=$?

if [ $LOAD_EXIT -eq 0 ]; then
    echo "✅ Installed: com.ghs.obsidian-daemon"
else
    echo "❌ launchctl load failed (exit $LOAD_EXIT)"
    exit 1
fi
echo ""

# ── Run once immediately so vault updates now ────────────────────────────────
echo "Running one pass now to refresh vault files..."
"$PYTHON" "$DAEMON" --once
RUN_EXIT=$?
echo ""

if [ $RUN_EXIT -eq 0 ]; then
    echo "✅ Vault files updated"
else
    echo "⚠️  First run exited $RUN_EXIT — check logs"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " OBSIDIAN DAEMON ACTIVE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo " Runs: every 5 minutes via launchd"
echo " Vault: ~/Desktop/Gold_Health_Systems/BRAIN/GHS Live/"
echo " Log:   ~/Desktop/REX/logs/obsidian_daemon.log"
echo ""
echo " Status check:"
STATUS=$(launchctl list | grep "com.ghs.obsidian-daemon" || echo "NOT FOUND")
echo "   $STATUS"
echo ""
echo "════════════════════════════════════════════════════════"
echo " DONE"
echo "════════════════════════════════════════════════════════"
} 2>&1 | tee "$LOG"

read -n 1 -s -p "Press any key to close."
echo ""
