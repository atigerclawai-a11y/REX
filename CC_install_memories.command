#!/bin/bash
# CC_install_memories.command — Push SOUL.md + MEMORY.md + MASTER.md into Hermes cloud profile
# Run after any BRAIN/MASTER.md update or when Hermes has lost memory
# Double-click to run

LOG="$HOME/Desktop/REX/logs/CC_install_memories_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
pass(){ echo -e "${GREEN}✅  $1${NC}"; }
fail(){ echo -e "${RED}❌  $1${NC}"; }
info(){ echo -e "${CYAN}ℹ️   $1${NC}"; }

BRAIN="$HOME/Desktop/Gold_Health_Systems/BRAIN"
MEMORIES="$HOME/.hermes/profiles/cloud/memories"

echo -e "${BOLD}=== Hermes Memory Install $(date) ===${NC}"
echo ""

# ── 1. Verify source files exist
echo -e "${BOLD}── 1. Checking source files ────────────────${NC}"
[ -f "$BRAIN/SOUL.md" ]   && pass "SOUL.md found"   || { fail "SOUL.md not found at $BRAIN/SOUL.md"; exit 1; }
[ -f "$BRAIN/MEMORY.md" ] && pass "MEMORY.md found" || { fail "MEMORY.md not found at $BRAIN/MEMORY.md"; exit 1; }
[ -f "$BRAIN/MASTER.md" ] && pass "MASTER.md found" || { fail "MASTER.md not found at $BRAIN/MASTER.md"; exit 1; }
echo ""

# ── 2. Install SOUL.md
echo -e "${BOLD}── 2. Installing SOUL.md ───────────────────${NC}"
chflags nouchg "$MEMORIES/SOUL.md" 2>/dev/null && info "Unlocked existing SOUL.md"
cp "$BRAIN/SOUL.md" "$MEMORIES/SOUL.md"
chflags uchg "$MEMORIES/SOUL.md"
pass "SOUL.md installed and locked"
echo ""

# ── 3. Install MEMORY.md
echo -e "${BOLD}── 3. Installing MEMORY.md ─────────────────${NC}"
chflags nouchg "$MEMORIES/MEMORY.md" 2>/dev/null && info "Unlocked existing MEMORY.md"
cp "$BRAIN/MEMORY.md" "$MEMORIES/MEMORY.md"
chflags uchg "$MEMORIES/MEMORY.md"
MEMSIZE=$(wc -c < "$MEMORIES/MEMORY.md")
pass "MEMORY.md installed and locked (${MEMSIZE} chars / 2800 limit)"
echo ""

# ── 4. Install MASTER.md (full source of truth — for deep reference)
echo -e "${BOLD}── 4. Installing MASTER.md ─────────────────${NC}"
chflags nouchg "$MEMORIES/MASTER.md" 2>/dev/null && info "Unlocked existing MASTER.md"
cp "$BRAIN/MASTER.md" "$MEMORIES/MASTER.md"
chflags uchg "$MEMORIES/MASTER.md"
pass "MASTER.md installed and locked"
echo ""

# ── 5. Restart Hermes CLOUD gateway only
echo -e "${BOLD}── 5. Restarting Hermes cloud gateway ──────${NC}"
PLIST="$HOME/Library/LaunchAgents/ai.hermes.gateway-cloud.plist"
launchctl unload "$PLIST" 2>/dev/null && info "Unloaded cloud gateway"
pkill -f "hermes_cli.main.*gateway.*cloud" 2>/dev/null && info "Killed old cloud process"
sleep 8
launchctl load "$PLIST" 2>/dev/null
sleep 3
PID=$(launchctl list | grep "ai.hermes.gateway-cloud" | awk '{print $1}')
if [[ "$PID" =~ ^[0-9]+$ ]]; then
  pass "Hermes cloud gateway running — PID $PID"
else
  fail "Gateway not running — check log: tail -f ~/.hermes/profiles/cloud/logs/gateway.log"
fi
echo ""

# ── 6. Quick health check
echo -e "${BOLD}── 6. Verifying Hermes cloud (:3002) ───────${NC}"
sleep 3
CODE=$(curl -s --max-time 8 -o /dev/null -w "%{http_code}" http://localhost:3002/health 2>/dev/null)
if [ "$CODE" = "200" ]; then
  pass "Hermes :3002 → HTTP 200 ✓"
else
  info "Hermes :3002 → $CODE (may still be starting — check gateway.log)"
fi
echo ""

echo -e "${BOLD}=== Done $(date) ===${NC}"
echo "  Source:    $BRAIN"
echo "  Installed: $MEMORIES"
echo "  Files:     SOUL.md · MEMORY.md · MASTER.md"
echo "  Log: $LOG"
echo ""
echo "Test: message @Hermes_Cloud_May_bot → 'who are you?'"
echo ""
echo "Press any key to close..."
read -n 1
