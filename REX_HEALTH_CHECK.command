#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
#  REX SYSTEM HEALTH CHECK — Full A-Z Diagnostic
#  Double-click to run. Safe to run anytime — read-only, no restarts.
#  If everything is GREEN you're good. RED items need attention.
# ═══════════════════════════════════════════════════════════════════

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

REX_DIR="$HOME/Desktop/REX"
GOJ_DIR="$HOME/Documents/goj files/dashboard"
LOGS="$REX_DIR/logs"
DB="$GOJ_DIR/auth_tracker.db"

PASS=0; WARN=0; FAIL=0

ok()   { echo -e "  ${GREEN}✅ $1${NC}"; ((PASS++)); }
warn() { echo -e "  ${YELLOW}⚠️  $1${NC}"; ((WARN++)); }
fail() { echo -e "  ${RED}❌ $1${NC}"; ((FAIL++)); }
hdr()  { echo -e "\n${BLUE}${BOLD}━━ $1 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

clear
echo -e "${CYAN}${BOLD}"
echo "  ██████╗ ███████╗██╗  ██╗"
echo "  ██╔══██╗██╔════╝╚██╗██╔╝"
echo "  ██████╔╝█████╗   ╚███╔╝ "
echo "  ██╔══██╗██╔══╝   ██╔██╗ "
echo "  ██║  ██║███████╗██╔╝ ██╗"
echo "  ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝"
echo -e "${NC}"
echo -e "${BOLD}  System Health Check — $(date '+%A %b %d, %Y at %I:%M %p')${NC}"
echo -e "${BLUE}  ════════════════════════════════════════════════════${NC}"


# ──────────────────────────────────────────────────────────────────
hdr "A  PYTHON ENVIRONMENT"
# ──────────────────────────────────────────────────────────────────

VENV_PYTHON="$REX_DIR/.venv/bin/python"
DEBATE_PYTHON="$HOME/debate-chamber/.venv/bin/python3"

if [ -f "$DEBATE_PYTHON" ]; then
    PY_VER=$("$DEBATE_PYTHON" --version 2>&1)
    ok "debate-chamber venv: $PY_VER"
else
    fail "debate-chamber venv missing: $DEBATE_PYTHON"
fi

if [ -f "$VENV_PYTHON" ]; then
    PY_VER=$("$VENV_PYTHON" --version 2>&1)
    ok "REX .venv: $PY_VER"
else
    warn "REX .venv not found (fallback will use debate-chamber)"
fi

# Pick best python
BEST_PYTHON="$DEBATE_PYTHON"
[ ! -f "$BEST_PYTHON" ] && BEST_PYTHON="$VENV_PYTHON"
[ ! -f "$BEST_PYTHON" ] && BEST_PYTHON="$(which python3)"

# Check key packages
for PKG in anthropic telegram flask uvicorn; do
    if "$BEST_PYTHON" -c "import $PKG" 2>/dev/null; then
        VER=$("$BEST_PYTHON" -c "import $PKG; print(getattr($PKG,'__version__','ok'))" 2>/dev/null)
        ok "Package $PKG ($VER)"
    else
        fail "Package $PKG NOT INSTALLED in $BEST_PYTHON"
    fi
done


# ──────────────────────────────────────────────────────────────────
hdr "B  CORE FILES"
# ──────────────────────────────────────────────────────────────────

FILES=(
    "$REX_DIR/rex_rexxie_telegram_bot.py:Rexxie Telegram bot"
    "$REX_DIR/rex_telegram_bot.py:REX Telegram bot"
    "$REX_DIR/goj_daily_scheduler.py:GOJ daily scheduler"
    "$REX_DIR/rex_telegram_config.json:REX bot config"
    "$REX_DIR/rex_rexxie_telegram_config.json:Rexxie config"
    "$REX_DIR/.env:Environment / API keys"
    "$REX_DIR/backend/main.py:REX backend (main.py)"
    "$GOJ_DIR/app.py:GOJ Dashboard (app.py)"
)

for ENTRY in "${FILES[@]}"; do
    FPATH="${ENTRY%%:*}"
    FLABEL="${ENTRY##*:}"
    if [ -f "$FPATH" ]; then
        SIZE=$(du -sh "$FPATH" 2>/dev/null | cut -f1)
        ok "$FLABEL  ($SIZE)"
    else
        fail "$FLABEL MISSING: $FPATH"
    fi
done


# ──────────────────────────────────────────────────────────────────
hdr "C  API KEYS (.env)"
# ──────────────────────────────────────────────────────────────────

if [ -f "$REX_DIR/.env" ]; then
    ANTHROPIC_KEY=$(grep "ANTHROPIC_API_KEY" "$REX_DIR/.env" | cut -d= -f2 | tr -d '"' | tr -d "'" | tr -d ' ')
    OPENAI_KEY=$(grep "OPENAI_API_KEY" "$REX_DIR/.env" | cut -d= -f2 | tr -d '"' | tr -d "'" | tr -d ' ')

    if [ -n "$ANTHROPIC_KEY" ] && [ "${#ANTHROPIC_KEY}" -gt 10 ]; then
        ok "ANTHROPIC_API_KEY present (${ANTHROPIC_KEY:0:8}...)"
    else
        fail "ANTHROPIC_API_KEY missing or blank in .env"
    fi

    if [ -n "$OPENAI_KEY" ] && [ "${#OPENAI_KEY}" -gt 10 ]; then
        ok "OPENAI_API_KEY present (${OPENAI_KEY:0:8}...)"
    else
        warn "OPENAI_API_KEY missing or blank (may not be required)"
    fi
else
    fail ".env file not found — API keys will NOT load"
fi


# ──────────────────────────────────────────────────────────────────
hdr "D  LAUNCHD AGENTS (conflict check)"
# ──────────────────────────────────────────────────────────────────

REXXIE_PLIST="$HOME/Library/LaunchAgents/com.rex.rexxie-bot.plist"
if [ -f "$REXXIE_PLIST" ]; then
    fail "com.rex.rexxie-bot.plist IS INSTALLED in LaunchAgents — this causes 409 conflicts!"
    echo -e "     ${RED}→ Double-click fix_rexxie_launchd.command to remove it${NC}"
else
    ok "com.rex.rexxie-bot NOT in LaunchAgents (no auto-respawn conflict)"
fi

# Check for any other suspicious launchd agents
OTHER=$(launchctl list 2>/dev/null | grep -i "rex\|rexxie\|goj\|telegram" | grep -v "^-")
if [ -n "$OTHER" ]; then
    warn "Other REX-related launchd jobs found:"
    echo "$OTHER" | while read -r line; do echo "     $line"; done
else
    ok "No other REX launchd jobs active"
fi


# ──────────────────────────────────────────────────────────────────
hdr "E  RUNNING PROCESSES"
# ──────────────────────────────────────────────────────────────────

# REX backend (uvicorn)
UVICORN_COUNT=$(pgrep -fc "uvicorn" 2>/dev/null || echo 0)
if lsof -i :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
    ok "REX Backend (uvicorn) → port 8000 LISTENING"
else
    fail "REX Backend NOT running on port 8000"
fi

# GOJ Dashboard (Flask)
if lsof -i :8080 -sTCP:LISTEN -t >/dev/null 2>&1; then
    ok "GOJ Dashboard (Flask) → port 8080 LISTENING"
else
    fail "GOJ Dashboard NOT running on port 8080"
fi

# Helper: check log freshness (returns seconds since last write, or 9999)
log_age_seconds() {
    local logfile="$1"
    if [ -f "$logfile" ]; then
        local mod
        mod=$(stat -f "%m" "$logfile" 2>/dev/null || echo 0)
        local now
        now=$(date +%s)
        echo $((now - mod))
    else
        echo 9999
    fi
}

# Rexxie bot — use ps aux (more reliable than pgrep -fc on macOS)
REXXIE_PIDS=$(ps aux | grep -v grep | grep "rex_rexxie_telegram_bot" | awk '{print $2}')
REXXIE_COUNT=$(echo "$REXXIE_PIDS" | grep -c '[0-9]' 2>/dev/null || echo 0)
REXXIE_LOG_AGE=$(log_age_seconds "$LOGS/rexxie_telegram.log")
if [ "$REXXIE_COUNT" -eq 1 ]; then
    ok "Rexxie bot running — 1 instance (PID $REXXIE_PIDS)"
elif [ "$REXXIE_COUNT" -gt 1 ]; then
    fail "Rexxie bot has $REXXIE_COUNT instances — Telegram 409 conflict!"
    echo -e "     ${RED}→ Double-click fix_rexxie_launchd.command to fix${NC}"
else
    # Check if log was written recently — bot may have just restarted
    if [ "$REXXIE_LOG_AGE" -lt 120 ]; then
        warn "Rexxie bot not detected by ps — but log active ${REXXIE_LOG_AGE}s ago (may be restarting)"
        echo -e "     ${YELLOW}→ Wait 30s then re-run health check${NC}"
    else
        fail "Rexxie bot NOT running (log last active ${REXXIE_LOG_AGE}s ago)"
        echo -e "     ${YELLOW}→ Double-click FIX_REXXIE.command to restart${NC}"
    fi
fi

# REX Telegram bot — exclude rexxie matches with word-boundary grep
REX_PIDS=$(ps aux | grep -v grep | grep "rex_telegram_bot" | grep -v "rex_rexxie_telegram_bot" | awk '{print $2}')
REX_BOT_COUNT=$(echo "$REX_PIDS" | grep -c '[0-9]' 2>/dev/null || echo 0)
REX_LOG_AGE=$(log_age_seconds "$LOGS/rex_telegram.log")
if [ "$REX_BOT_COUNT" -ge 1 ]; then
    ok "REX Telegram bot running (PID $REX_PIDS)"
else
    if [ "$REX_LOG_AGE" -lt 120 ]; then
        warn "REX bot not detected by ps — but log active ${REX_LOG_AGE}s ago (may be restarting)"
        echo -e "     ${YELLOW}→ Wait 30s then re-run health check${NC}"
    else
        fail "REX Telegram bot NOT running (log last active ${REX_LOG_AGE}s ago)"
        echo -e "     ${YELLOW}→ Double-click FIX_REXXIE.command to restart${NC}"
    fi
fi

# GOJ Scheduler
SCHED_COUNT=$(pgrep -fc "goj_daily_scheduler" 2>/dev/null || echo 0)
if [ "$SCHED_COUNT" -ge 1 ]; then
    SCHED_PID=$(pgrep -f "goj_daily_scheduler" 2>/dev/null | head -1)
    ok "GOJ Scheduler running (PID $SCHED_PID)"
else
    warn "GOJ Scheduler NOT running (may be OK if not needed 24/7)"
fi


# ──────────────────────────────────────────────────────────────────
hdr "F  HTTP ENDPOINTS"
# ──────────────────────────────────────────────────────────────────

check_endpoint() {
    local URL="$1"; local LABEL="$2"
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 4 "$URL" 2>/dev/null)
    if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "307" ] || [ "$HTTP_CODE" = "302" ]; then
        ok "$LABEL → HTTP $HTTP_CODE"
    elif [ "$HTTP_CODE" = "000" ]; then
        fail "$LABEL → No response (service down?)"
    else
        warn "$LABEL → HTTP $HTTP_CODE (may need auth)"
    fi
}

check_endpoint "http://localhost:8000/"        "REX Backend /"
check_endpoint "http://localhost:8000/docs"   "REX Backend /docs (Swagger)"
check_endpoint "http://localhost:8080/"        "GOJ Dashboard /"
check_endpoint "http://localhost:8080/login"   "GOJ Dashboard /login"


# ──────────────────────────────────────────────────────────────────
hdr "G  DATABASE"
# ──────────────────────────────────────────────────────────────────

if [ -f "$DB" ]; then
    DB_SIZE=$(du -sh "$DB" | cut -f1)
    ok "auth_tracker.db found ($DB_SIZE)"

    # Check tables exist
    TABLES=$(sqlite3 "$DB" ".tables" 2>/dev/null)
    for TBL in users sessions pending_schedule_changes; do
        if echo "$TABLES" | grep -qw "$TBL"; then
            COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM $TBL;" 2>/dev/null)
            ok "Table: $TBL ($COUNT rows)"
        else
            warn "Table $TBL not found in DB"
        fi
    done

    # Check pending_schedule_changes columns
    COLS=$(sqlite3 "$DB" "PRAGMA table_info(pending_schedule_changes);" 2>/dev/null | awk -F'|' '{print $2}' | tr '\n' ' ')
    NEEDED_COLS=("created_at" "day_key" "old_value" "new_value" "note" "field_changed")
    ALL_COLS_OK=true
    for COL in "${NEEDED_COLS[@]}"; do
        if echo "$COLS" | grep -qw "$COL"; then
            : # ok
        else
            fail "pending_schedule_changes missing column: $COL"
            ALL_COLS_OK=false
        fi
    done
    [ "$ALL_COLS_OK" = true ] && ok "pending_schedule_changes schema up to date"
else
    fail "auth_tracker.db NOT FOUND at: $DB"
fi


# ──────────────────────────────────────────────────────────────────
hdr "H  RECENT LOG ERRORS"
# ──────────────────────────────────────────────────────────────────

check_log() {
    local LOGFILE="$1"; local LABEL="$2"
    if [ ! -f "$LOGFILE" ]; then
        warn "$LABEL — log file not found"
        return
    fi

    # Log size check
    SIZE_BYTES=$(stat -f%z "$LOGFILE" 2>/dev/null || stat -c%s "$LOGFILE" 2>/dev/null)
    SIZE_MB=$(( SIZE_BYTES / 1048576 ))
    if [ "$SIZE_MB" -gt 50 ]; then
        warn "$LABEL log is ${SIZE_MB}MB — consider truncating"
    fi

    # Last active: use file modification time (most reliable — log format has no timestamps)
    LOG_MOD=$(stat -f "%m" "$LOGFILE" 2>/dev/null || echo 0)
    NOW_S=$(date +%s)
    AGE_S=$(( NOW_S - LOG_MOD ))
    if [ "$AGE_S" -lt 60 ]; then
        LAST_ACTIVE="just now"
    elif [ "$AGE_S" -lt 3600 ]; then
        LAST_ACTIVE="${AGE_S}s ago"
    else
        LAST_ACTIVE=$(date -r "$LOG_MOD" "+%H:%M" 2>/dev/null || echo "unknown")
    fi

    # Scan last 200 lines for errors (no timestamp needed — if they're recent they matter)
    RECENT_ERRORS=$(tail -200 "$LOGFILE" 2>/dev/null | grep -iE "error|traceback|conflict|failed|exception|critical" | grep -viE "no error|error_description|KeyError.*'error'" | tail -5)

    if [ -n "$RECENT_ERRORS" ]; then
        ERRCOUNT=$(echo "$RECENT_ERRORS" | grep -c ".")
        fail "$LABEL — $ERRCOUNT error line(s) in recent logs (last active: $LAST_ACTIVE)"
        echo "$RECENT_ERRORS" | while IFS= read -r line; do
            echo -e "     ${RED}${line:0:100}${NC}"
        done
    else
        ok "$LABEL — clean (last active: $LAST_ACTIVE)"
    fi
}

check_log "$LOGS/rex_backend.log"       "REX Backend"
check_log "$LOGS/rexxie_telegram.log"   "Rexxie Telegram"
check_log "$LOGS/rex_telegram.log"      "REX Telegram"
check_log "$LOGS/dashboard_startup.log" "GOJ Dashboard"


# ──────────────────────────────────────────────────────────────────
hdr "I  BACKUP STATUS"
# ──────────────────────────────────────────────────────────────────

# REX snapshots live on the Cartoons external drive only.
# Auto-detect mount (both casings). If not mounted, warn plainly.
BACKUP_DIR=""
for candidate in "/Volumes/Cartoons/REX_Backups" "/Volumes/cartoons/REX_Backups"; do
    if [ -d "$candidate" ]; then
        BACKUP_DIR="$candidate"
        break
    fi
done
GOJ_BACKUP_DIR="$REX_DIR/GOJ_Backups"

if [ -n "$BACKUP_DIR" ]; then
    LAST_REX=$(ls -td "$BACKUP_DIR"/REX_* 2>/dev/null | head -1)
    if [ -n "$LAST_REX" ]; then
        BNAME=$(basename "$LAST_REX")
        BDATE=$(echo "$BNAME" | grep -oE "[0-9]{4}-[0-9]{2}-[0-9]{2}")
        TODAY=$(date '+%Y-%m-%d')
        if [ "$BDATE" = "$TODAY" ]; then
            ok "REX backup: $BNAME (TODAY ✓) — on Cartoons"
        else
            warn "REX backup: $BNAME (last backup NOT today) — on Cartoons"
        fi
    else
        warn "Cartoons mounted but no REX snapshots found in $BACKUP_DIR"
    fi
else
    warn "Cartoons drive NOT mounted — cannot verify REX snapshot status"
fi

if [ -d "$GOJ_BACKUP_DIR" ]; then
    LAST_GOJ=$(ls -td "$GOJ_BACKUP_DIR"/GOJ_* 2>/dev/null | head -1)
    if [ -n "$LAST_GOJ" ]; then
        GNAME=$(basename "$LAST_GOJ")
        GDATE=$(echo "$GNAME" | grep -oE "[0-9]{4}-[0-9]{2}-[0-9]{2}")
        TODAY=$(date '+%Y-%m-%d')
        if [ "$GDATE" = "$TODAY" ]; then
            ok "GOJ backup: $GNAME (TODAY ✓)"
        else
            warn "GOJ backup: $GNAME (last backup was NOT today)"
        fi
    else
        warn "No GOJ backups found in $GOJ_BACKUP_DIR"
    fi
else
    warn "GOJ_Backups folder not found"
fi


# ──────────────────────────────────────────────────────────────────
hdr "J  DISK SPACE"
# ──────────────────────────────────────────────────────────────────

DISK_FREE=$(df -h "$HOME" | awk 'NR==2{print $4}')
DISK_PCT=$(df "$HOME" | awk 'NR==2{print $5}' | tr -d '%')
if [ "$DISK_PCT" -gt 90 ]; then
    fail "Disk $DISK_PCT% full — only $DISK_FREE free. Clear space!"
elif [ "$DISK_PCT" -gt 75 ]; then
    warn "Disk $DISK_PCT% full ($DISK_FREE free)"
else
    ok "Disk space: $DISK_FREE free ($DISK_PCT% used)"
fi


# ──────────────────────────────────────────────────────────────────
#  SUMMARY
# ──────────────────────────────────────────────────────────────────

TOTAL=$((PASS + WARN + FAIL))
echo ""
echo -e "${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}  HEALTH CHECK SUMMARY${NC}"
echo -e "${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  ${GREEN}✅ PASS:${NC}  $PASS"
echo -e "  ${YELLOW}⚠️  WARN:${NC}  $WARN"
echo -e "  ${RED}❌ FAIL:${NC}  $FAIL"
echo ""

if [ "$FAIL" -eq 0 ] && [ "$WARN" -eq 0 ]; then
    echo -e "  ${GREEN}${BOLD}🦖 REX IS FULLY OPERATIONAL. Nothing to fix!${NC}"
elif [ "$FAIL" -eq 0 ]; then
    echo -e "  ${YELLOW}${BOLD}⚠️  Minor warnings only — REX is mostly healthy.${NC}"
else
    echo -e "  ${RED}${BOLD}❌ $FAIL issue(s) need attention (see RED items above).${NC}"
    echo ""
    echo -e "  ${BOLD}Quick fixes:${NC}"
    echo -e "  • 409 Telegram conflict  → double-click ${CYAN}fix_rexxie_launchd.command${NC}"
    echo -e "  • All services broken    → double-click ${CYAN}FIX_REXXIE.command${NC}"
    echo -e "  • REX bot not answering  → double-click ${CYAN}start_rex_bot.command${NC}"
    echo -e "  • DB schema errors       → double-click ${CYAN}fix_schedule_changes_schema.command${NC}"
fi

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Press Enter to close..."
read
