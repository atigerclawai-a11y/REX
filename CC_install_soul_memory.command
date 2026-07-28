#!/bin/bash
# CC_install_soul_memory.command
# Install SOUL.md v6.0 (short identity) and MEMORY.md into the Hermes cloud gateway profile
# Then restart the cloud gateway to activate both files

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG=~/Desktop/REX/logs/cc_install_soul_memory_${TIMESTAMP}.log
mkdir -p ~/Desktop/REX/logs
exec > >(tee "$LOG") 2>&1

SOUL_SRC=~/Desktop/REX/CC_SOUL_FINAL_SHORT.md
MEMORY_SRC=~/Desktop/REX/CC_MEMORY_FINAL.md
MEMORIES_DIR=~/.hermes/profiles/cloud/memories
SOUL_DEST="$MEMORIES_DIR/SOUL.md"
MEMORY_DEST="$MEMORIES_DIR/MEMORY.md"
PLIST=~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist
KEY=$(grep "API_SERVER_KEY\|API_KEY" ~/.hermes/profiles/cloud/.env 2>/dev/null | grep -v "DEEPSEEK\|ANTHROPIC\|GOOGLE" | head -1 | cut -d= -f2 | tr -d '[:space:]')

echo "══════════════════════════════════════════════════════"
echo "  CC_install_soul_memory — $(date)"
echo "══════════════════════════════════════════════════════"
echo ""

# ── 0: PIN check — unlock if memory files are protected ──
STORED_PIN=$(security find-generic-password -a mainsobhelper -s hermes-memory-pin -w 2>/dev/null)
if [ -n "$STORED_PIN" ]; then
  echo "── 0: Memory PIN protection active ─────────────────"
  read -s -p "  Enter Hermes memory PIN to continue: " INPUT_PIN
  echo ""
  if [ "$INPUT_PIN" != "$STORED_PIN" ]; then
    echo "  ❌ Incorrect PIN. Aborting."
    read -p "Press any key to close..."
    exit 1
  fi
  echo "  ✅ PIN verified — unlocking memory files"
  chflags nouchg "$SOUL_DEST" 2>/dev/null || true
  chflags nouchg "$MEMORY_DEST" 2>/dev/null || true
  echo ""
fi

# ── 1: Verify source files exist ──────────────────────
echo "── 1: Source files ─────────────────────────────────"
[ -f "$SOUL_SRC" ] && echo "  ✅ SOUL.md v6.0:  $SOUL_SRC ($(wc -c < "$SOUL_SRC") bytes)" || { echo "  ❌ SOUL source missing: $SOUL_SRC"; exit 1; }
[ -f "$MEMORY_SRC" ] && echo "  ✅ MEMORY.md:     $MEMORY_SRC ($(wc -c < "$MEMORY_SRC") bytes)" || { echo "  ❌ MEMORY source missing: $MEMORY_SRC"; exit 1; }

MEMORY_CHARS=$(wc -c < "$MEMORY_SRC")
if [ "$MEMORY_CHARS" -gt 2800 ]; then
  echo "  ❌ MEMORY.md exceeds 2800 char limit ($MEMORY_CHARS chars) — aborting"
  exit 1
fi
echo "  ✅ MEMORY.md char count: $MEMORY_CHARS / 2800 limit"
echo ""

# ── 2: Verify destination directory ───────────────────
echo "── 2: Memories directory ────────────────────────────"
if [ ! -d "$MEMORIES_DIR" ]; then
  echo "  Creating $MEMORIES_DIR ..."
  mkdir -p "$MEMORIES_DIR"
fi
echo "  ✅ $MEMORIES_DIR"
ls "$MEMORIES_DIR" | head -10
echo ""

# ── 3: Back up existing files ─────────────────────────
echo "── 3: Backup existing files ─────────────────────────"
[ -f "$SOUL_DEST" ] && cp "$SOUL_DEST" "${SOUL_DEST}.bak_${TIMESTAMP}" && echo "  Backed up: ${SOUL_DEST}.bak_${TIMESTAMP}" || echo "  (no existing SOUL.md to back up)"
[ -f "$MEMORY_DEST" ] && cp "$MEMORY_DEST" "${MEMORY_DEST}.bak_${TIMESTAMP}" && echo "  Backed up: ${MEMORY_DEST}.bak_${TIMESTAMP}" || echo "  (no existing MEMORY.md to back up)"
echo ""

# ── 4: Install SOUL.md ────────────────────────────────
echo "── 4: Install SOUL.md v6.0 ─────────────────────────"
cp "$SOUL_SRC" "$SOUL_DEST"
if [ $? -eq 0 ]; then
  echo "  ✅ Installed: $SOUL_DEST"
  echo "  Size: $(wc -c < "$SOUL_DEST") bytes / $(wc -l < "$SOUL_DEST") lines"
else
  echo "  ❌ Copy failed"
  exit 1
fi
echo ""

# ── 5: Install MEMORY.md ──────────────────────────────
echo "── 5: Install MEMORY.md ────────────────────────────"
cp "$MEMORY_SRC" "$MEMORY_DEST"
if [ $? -eq 0 ]; then
  echo "  ✅ Installed: $MEMORY_DEST"
  echo "  Size: $(wc -c < "$MEMORY_DEST") bytes"
  echo ""
  echo "  MEMORY.md preview:"
  head -5 "$MEMORY_DEST"
else
  echo "  ❌ Copy failed"
  exit 1
fi
echo ""

# ── 6: Restart cloud gateway ──────────────────────────
echo "── 6: Restart cloud gateway ─────────────────────────"
launchctl unload "$PLIST" 2>/dev/null || true
sleep 2
pkill -f "hermes_cli.main.*gateway" 2>/dev/null || true
sleep 8
launchctl load "$PLIST"
echo "  Waiting 20s for gateway init..."
sleep 20
echo ""

# ── 7: Verify gateway is up ───────────────────────────
echo "── 7: Verify cloud gateway (port 3002) ─────────────"
GW_PID=$(pgrep -f "hermes_cli.main.*cloud" | head -1)
LISTENER=$(lsof -i :3002 -P -n 2>/dev/null | grep LISTEN)

[ -n "$GW_PID" ] && echo "  ✅ Gateway process: PID $GW_PID" || echo "  ❌ Gateway not running"
[ -n "$LISTENER" ] && echo "  ✅ Port 3002 listening" || echo "  ❌ Port 3002 not listening"

# Check log for SOUL.md loaded
echo ""
echo "  Recent gateway log (SOUL/MEMORY mentions):"
GW_LOG=$(find ~/.hermes/profiles/cloud/logs -name "gateway.log" 2>/dev/null | head -1)
if [ -f "$GW_LOG" ]; then
  tail -30 "$GW_LOG" | grep -i "soul\|memory\|identity\|started\|loaded\|error\|fail" | head -10
  [ $? -ne 0 ] && tail -15 "$GW_LOG"
else
  echo "  (no gateway log found — check ~/.hermes/profiles/cloud/logs/)"
fi
echo ""

# ── 8: Re-lock memory files if PIN is configured ─────
STORED_PIN=$(security find-generic-password -a mainsobhelper -s hermes-memory-pin -w 2>/dev/null)
if [ -n "$STORED_PIN" ]; then
  echo "── 8: Re-locking memory files ───────────────────────"
  chflags uchg "$SOUL_DEST" && echo "  🔒 Locked: SOUL.md" || echo "  ⚠️  Could not lock SOUL.md"
  chflags uchg "$MEMORY_DEST" && echo "  🔒 Locked: MEMORY.md" || echo "  ⚠️  Could not lock MEMORY.md"
  echo ""
fi

echo "══════════════════════════════════════════════════════"
echo "  Done — $(date)"
echo "  SOUL.md v6.0 installed at: $SOUL_DEST"
echo "  MEMORY.md installed at:    $MEMORY_DEST"
echo "  Cloud gateway restarted"
[ -n "$STORED_PIN" ] && echo "  Memory files: 🔒 LOCKED"
echo "  Log: $LOG"
echo "══════════════════════════════════════════════════════"
echo ""
read -p "Press any key to close..."
