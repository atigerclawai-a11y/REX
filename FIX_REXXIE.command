#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  FIX EVERYTHING — Kill conflicts, restart all REX services clean
#  Double-click to fix Rexxie 409, REX backend, GOJ Dashboard
# ─────────────────────────────────────────────────────────────────

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
REX_DIR="$HOME/Desktop/REX"
GOJ_DIR="$HOME/Documents/goj files/dashboard"
LOGS="$REX_DIR/logs"
mkdir -p "$LOGS"

echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}   🦖  FIX EVERYTHING — REX Full Restart${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

# ── Manifest compliance check (ENFORCED — Red Team fix 2026-04-14) ────────────
MANIFEST="$REX_DIR/ACTIVE_SYSTEM_MANIFEST.json"
VIOLATIONS=0

if [ -f "$MANIFEST" ]; then
  # 1. Kill any quarantined bot that somehow started
  if pgrep -f "private_confidant_gold" > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Quarantined growth loop bot is running — killing it${NC}"
    pkill -f "private_confidant_gold" 2>/dev/null
  fi

  # 2. Check no process is running from inside any QUARANTINE directory
  for QDIR in "$REX_DIR"/QUARANTINE_*/; do
    if [ -d "$QDIR" ]; then
      QNAME=$(basename "$QDIR")
      QRUNNING=$(pgrep -f "$QNAME" 2>/dev/null | wc -l | tr -d ' ')
      if [ "$QRUNNING" -gt 0 ]; then
        echo -e "${RED}🚨 MANIFEST VIOLATION: Process running from $QNAME — stop it first${NC}"
        VIOLATIONS=$((VIOLATIONS+1))
      fi
    fi
  done

  # 3. Warn about forbidden files still in REX root (need QUARANTINE_COMMANDS.command run)
  FORBIDDEN_COUNT=0
  for F in start_rexxie_only.command fix_rexxie_launchd.command restart-backend.command \
           RUN_OCR.command RUN_SIGNIN_INTAKE.command goj_signin_intake_v4_patch.py \
           run_menu_ocr_new.py rex_user_model.db rex_memory.db; do
    [ -f "$REX_DIR/$F" ] && FORBIDDEN_COUNT=$((FORBIDDEN_COUNT+1))
  done
  if [ "$FORBIDDEN_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  $FORBIDDEN_COUNT superseded files still in REX root — run QUARANTINE_COMMANDS.command${NC}"
  fi

  # 4. Hard stop on violations
  if [ "$VIOLATIONS" -gt 0 ]; then
    echo -e "${RED}Cannot restart — resolve $VIOLATIONS manifest violation(s) first.${NC}"
    exit 1
  fi
fi

# ── Step 1: Kill ALL conflicting processes ────────────────────────
echo -e "${YELLOW}[1/4]${NC} Stopping all services..."
for PROC in "rex_telegram_bot.py" "rex_rexxie_telegram_bot.py" "private_confidant_gold.py" "goj_telegram_bot" "uvicorn"; do
    PIDS=$(pgrep -f "$PROC" 2>/dev/null)
    if [ -n "$PIDS" ]; then
        kill -9 $PIDS 2>/dev/null
        echo -e "  ${GREEN}✓${NC} Stopped: $PROC"
    fi
done
# Also free ports if anything is stuck
for PORT in 8000 8080; do
    PID=$(lsof -ti :$PORT 2>/dev/null)
    if [ -n "$PID" ]; then
        kill -9 $PID 2>/dev/null
        echo -e "  ${GREEN}✓${NC} Freed port $PORT"
    fi
done
sleep 2
echo -e "  ${GREEN}✓ All clear${NC}"

# ── Step 2: Start REX backend ─────────────────────────────────────
echo -e "\n${YELLOW}[2/4]${NC} Starting REX backend (port 8000)..."
cd "$REX_DIR"

# Load API keys from .env so Anthropic/OpenAI keys reach the backend process
if [ -f "$REX_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$REX_DIR/.env" 2>/dev/null
    set +a
    echo -e "  ${GREEN}✓ API keys loaded from .env${NC}"
fi

VENV_PYTHON="$REX_DIR/.venv/bin/python"
[ ! -f "$VENV_PYTHON" ] && VENV_PYTHON="$HOME/debate-chamber/.venv/bin/python3"
[ ! -f "$VENV_PYTHON" ] && VENV_PYTHON="python3"
nohup "$VENV_PYTHON" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 >> "$LOGS/rex_backend.log" 2>&1 &
REX_PID=$!
sleep 4
if lsof -i :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "  ${GREEN}✓ REX backend running (PID $REX_PID) → http://localhost:8000${NC}"
else
    echo -e "  ${RED}❌ REX backend failed — check $LOGS/rex_backend.log${NC}"
    tail -8 "$LOGS/rex_backend.log"
fi

# ── Step 3: Start GOJ Dashboard ──────────────────────────────────
echo -e "\n${YELLOW}[3/4]${NC} Starting GOJ Dashboard (port 8080)..."
cd "$GOJ_DIR"

# Find best Python — prefer venvs that already have Flask
DASHBOARD_PYTHON=""
for CANDIDATE in \
    "$GOJ_DIR/.venv/bin/python3" \
    "$GOJ_DIR/.venv/bin/python" \
    "$REX_DIR/.venv/bin/python3" \
    "$REX_DIR/.venv/bin/python" \
    "$HOME/debate-chamber/.venv/bin/python3" \
    "$(which python3)" \
    "$(which python)"; do
    if [ -f "$CANDIDATE" ] && "$CANDIDATE" -c "import flask" 2>/dev/null; then
        DASHBOARD_PYTHON="$CANDIDATE"
        echo -e "  Using Python: $DASHBOARD_PYTHON"
        break
    fi
done

# If no Python with Flask found, install into REX venv and use that
if [ -z "$DASHBOARD_PYTHON" ]; then
    echo -e "  ${YELLOW}⚠  Flask not found — installing into REX venv...${NC}"
    "$REX_DIR/.venv/bin/pip" install flask werkzeug --quiet 2>/dev/null \
        && DASHBOARD_PYTHON="$REX_DIR/.venv/bin/python" \
        || DASHBOARD_PYTHON="python3"
    pip3 install flask werkzeug --break-system-packages --quiet 2>/dev/null || true
    DASHBOARD_PYTHON="$(which python3)"
    echo -e "  Using Python: $DASHBOARD_PYTHON (with freshly installed Flask)"
fi

nohup "$DASHBOARD_PYTHON" app.py >> "$LOGS/dashboard_startup.log" 2>&1 &
DASH_PID=$!
sleep 5
if lsof -i :8080 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "  ${GREEN}✓ GOJ Dashboard running (PID $DASH_PID) → http://localhost:8080${NC}"
else
    echo -e "  ${RED}❌ GOJ Dashboard failed — check $LOGS/dashboard_startup.log${NC}"
    tail -8 "$LOGS/dashboard_startup.log"
fi

# ── Step 4: Start ONE clean Rexxie ───────────────────────────────
echo -e "\n${YELLOW}[4/5]${NC} Starting Rexxie (Telegram)..."
cd "$REX_DIR"
nohup "$VENV_PYTHON" rex_rexxie_telegram_bot.py >> "$LOGS/rexxie_telegram.log" 2>&1 &
REXXIE_PID=$!
sleep 4
if pgrep -f "rex_rexxie_telegram_bot.py" > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓ Rexxie is live (PID $REXXIE_PID)${NC}"
else
    echo -e "  ${RED}❌ Rexxie failed — last 8 lines:${NC}"
    tail -8 "$LOGS/rexxie_telegram.log"
fi

# ── Step 5: REX Telegram Bot ─────────────────────────────────────
echo -e "\n${YELLOW}[5/5]${NC} REX Telegram bot check..."
# NOTE: rex_telegram_bot.py uses the SAME token as Rexxie.
# Running both simultaneously causes 409 Conflict — skip for now.
# To run both, create a separate bot via @BotFather and update rex_telegram_config.json.
REX_TOKEN=$(python3 -c "import json; d=open('$REX_DIR/rex_telegram_config.json').read(); print(json.loads(d).get('bot_token',''))" 2>/dev/null)
REXXIE_TOKEN=$(python3 -c "import json; d=open('$REX_DIR/rex_rexxie_telegram_config.json').read(); print(json.loads(d).get('bot_token',''))" 2>/dev/null)
if [ "$REX_TOKEN" = "$REXXIE_TOKEN" ]; then
    echo -e "  ${YELLOW}⚠️  REX bot shares the same token as Rexxie — skipping to avoid 409.${NC}"
    echo -e "  ${YELLOW}   To run both: create a new bot via @BotFather and update rex_telegram_config.json${NC}"
else
    cd "$REX_DIR"
    nohup "$VENV_PYTHON" rex_telegram_bot.py >> "$LOGS/rex_telegram.log" 2>&1 &
    REX_BOT_PID=$!
    sleep 4
    if pgrep -f "rex_telegram_bot.py" > /dev/null 2>&1; then
        echo -e "  ${GREEN}✓ REX bot is live (PID $REX_BOT_PID)${NC}"
    else
        echo -e "  ${RED}❌ REX bot failed — last 8 lines:${NC}"
        tail -8 "$LOGS/rex_telegram.log"
    fi
fi

# ── Summary ───────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  GOJ Dashboard  → http://localhost:8080${NC}"
echo -e "${GREEN}  REX Backend    → http://localhost:8000${NC}"
echo -e "${GREEN}  Rexxie         → Telegram (personal confidant)${NC}"
if [ "$REX_TOKEN" != "$REXXIE_TOKEN" ]; then
    echo -e "${GREEN}  REX Bot        → Telegram (occupational)${NC}"
else
    echo -e "${YELLOW}  REX Bot        → needs its own token (see @BotFather)${NC}"
fi
echo -e "${GREEN}  Login: KChairman / ghs2026!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
echo "Press Enter to close..."
read
