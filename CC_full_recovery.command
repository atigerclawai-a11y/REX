#!/usr/bin/env bash
# CC_full_recovery.command
# Three-step recovery: Ollama → launchd fix → verify
# Double-click to run.

LOG="$HOME/Desktop/REX/logs/cc_full_recovery.log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee -a "$LOG") 2>&1

echo "══════════════════════════════════════════════════"
echo "  REX Full Recovery — Ollama + launchd + Clause"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "══════════════════════════════════════════════════"

SRC="$HOME/Desktop/REX/launchd"
DEST="$HOME/Library/LaunchAgents"
REX_VENV="$HOME/Desktop/REX/.venv"
OLD_VENV="/Users/mainsobhelper/debate-chamber/.venv"
REXXIE_TOKEN="8657319466:AAGVYz_o7j1ZMpoqiHa8I1ZjS6VYGiWZS8k"

# ═══════════════════════════════════════════════════
# STEP 1 — Start Ollama
# ═══════════════════════════════════════════════════
echo ""
echo "── STEP 1: Ollama ──"

# Check if already running
if curl -s --max-time 3 "http://localhost:11434/api/tags" >/dev/null 2>&1; then
  echo "  ✓ Ollama already running at localhost:11434"
else
  echo "  Ollama not running — searching..."

  # Try brew service
  if command -v ollama &>/dev/null; then
    echo "  Found: $(which ollama)"
    ollama serve &>/dev/null &
    echo "  Started via: ollama serve"
    sleep 4
  # Try /Applications/Ollama.app
  elif [ -d "/Applications/Ollama.app" ]; then
    echo "  Found: /Applications/Ollama.app"
    open -a Ollama
    sleep 5
  # Try Homebrew locations
  elif [ -f "/opt/homebrew/bin/ollama" ]; then
    echo "  Found: /opt/homebrew/bin/ollama"
    /opt/homebrew/bin/ollama serve &>/dev/null &
    sleep 4
  elif [ -f "/usr/local/bin/ollama" ]; then
    echo "  Found: /usr/local/bin/ollama"
    /usr/local/bin/ollama serve &>/dev/null &
    sleep 4
  else
    echo "  ⚠ Ollama not found in standard locations"
    echo "  Locations checked:"
    echo "    - which ollama"
    echo "    - /Applications/Ollama.app"
    echo "    - /opt/homebrew/bin/ollama"
    echo "    - /usr/local/bin/ollama"
    echo "  → Install: https://ollama.com/download"
    echo "    or: brew install ollama && brew services start ollama"
  fi

  # Verify
  sleep 2
  if curl -s --max-time 5 "http://localhost:11434/api/tags" >/dev/null 2>&1; then
    echo "  ✓ Ollama is UP at localhost:11434"
  else
    echo "  ✗ Ollama still not responding — continuing with other fixes"
  fi
fi

# ═══════════════════════════════════════════════════
# STEP 2 — Kill Telegram conflicts + fix launchd
# ═══════════════════════════════════════════════════
echo ""
echo "── STEP 2A: Kill conflicting Telegram processes ──"
KILLED=0
for pid in $(pgrep -f "rex_rexxie_telegram_bot\|$REXXIE_TOKEN\|8657319466" 2>/dev/null); do
  echo "  kill $pid"
  kill -9 "$pid" 2>/dev/null && KILLED=$((KILLED+1)) || true
done
echo "  Killed: $KILLED process(es)"

echo ""
echo "── STEP 2B: Unload all affected plists ──"
for label in com.rex.rexxie-bot com.rex.reminders com.rex.nextday-preview \
             com.goj.rexxiedaily com.rex.backend com.rex.queue-processor \
             com.rex.evening-report com.rex.encrypted-backup com.rex.email-pdf-watcher \
             com.rex.daily-backup com.goj.scheduler.morning_report \
             com.goj.scheduler.nightly_rundown com.goj.scheduler.kitchen_sheets \
             com.goj.scheduler.signin_driver_sheets com.goj.scheduler.weekly_email_fri \
             com.goj.scanprocessor com.goj.menuaudit com.goj.rexcurriculum; do
  launchctl unload "$DEST/$label.plist" 2>/dev/null && echo "  unloaded: $label" || true
done

echo ""
echo "── STEP 2C: Fix and install all plists ──"
if [ ! -d "$SRC" ]; then
  echo "  ⚠ No launchd/ folder at $SRC — skipping plist fix"
else
  for src_plist in "$SRC"/*.plist; do
    [ -f "$src_plist" ] || continue
    name=$(basename "$src_plist")
    dst="$DEST/$name"
    sed "s|PLACEHOLDER_HOME|$HOME|g; s|$OLD_VENV|$REX_VENV|g" "$src_plist" > "$dst"
    echo "  ✓ $name"
  done
fi

echo ""
echo "── STEP 2D: Verify venv ──"
if [ -f "$REX_VENV/bin/python" ]; then
  echo "  ✓ $REX_VENV/bin/python"
else
  echo "  Creating venv at $REX_VENV ..."
  python3 -m venv "$REX_VENV"
  "$REX_VENV/bin/pip" install python-telegram-bot requests --quiet
  echo "  ✓ Created"
fi

echo ""
echo "── STEP 2E: Reload all plists ──"
LOADED=0
for dst_plist in "$DEST"/com.rex.*.plist "$DEST"/com.goj.*.plist; do
  [ -f "$dst_plist" ] || continue
  launchctl load "$dst_plist" 2>/dev/null && LOADED=$((LOADED+1)) || true
done
echo "  Loaded: $LOADED plists"

# ═══════════════════════════════════════════════════
# STEP 3 — Verify everything
# ═══════════════════════════════════════════════════
sleep 5
echo ""
echo "── STEP 3: Verification ──"

echo ""
echo "  Ollama:"
if curl -s --max-time 5 "http://localhost:11434/api/tags" >/dev/null 2>&1; then
  echo "  ✓ localhost:11434 responding"
  curl -s --max-time 5 "http://localhost:11434/api/tags" | python3 -m json.tool 2>/dev/null | grep '"name"' | head -5 || true
else
  echo "  ✗ localhost:11434 not responding"
fi

echo ""
echo "  Rexxie Telegram API:"
TG=$(curl -s --max-time 8 "https://api.telegram.org/bot$REXXIE_TOKEN/getMe" 2>/dev/null)
echo "$TG" | python3 -m json.tool 2>/dev/null | grep -E '"ok"|"username"|"first_name"' || echo "  $TG"

echo ""
echo "  Bot processes:"
pgrep -fl "rex_rexxie_telegram_bot" | head -5 || echo "  (none yet — check in 15s as launchd starts it)"

echo ""
echo "  Clause status:"
if pgrep -f "rex_rexxie_telegram_bot" >/dev/null 2>&1; then
  echo "  ✓ Bot running → UnifiedEnforcer (Clause) active"
else
  echo "  Waiting for bot to start (launchd will start it shortly)"
fi

echo ""
echo "══ RECOVERY COMPLETE ══"
echo "Log saved: $LOG"
echo ""
sleep 5
