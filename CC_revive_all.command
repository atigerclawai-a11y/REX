#!/bin/bash
# CC_revive_all.command — Restart all GHS services and report status
# Run by double-clicking in Finder

LOG="$HOME/Desktop/REX/logs/CC_revive_all_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; GOLD='\033[0;33m'; BOLD='\033[1m'; NC='\033[0m'
pass(){ echo -e "${GREEN}✅  $1${NC}"; }
fail(){ echo -e "${RED}❌  $1${NC}"; }
info(){ echo -e "${CYAN}ℹ️   $1${NC}"; }
warn(){ echo -e "${GOLD}⚠️   $1${NC}"; }

echo -e "${BOLD}╔══════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   GHS FULL SERVICES REVIVAL          ║${NC}"
echo -e "${BOLD}║   $(date +"%a %b %d %H:%M:%S")          ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════╝${NC}"
echo ""

AGENTS="$HOME/Library/LaunchAgents"

# ── Helper: reload a plist ────────────────────────────────────
reload_plist() {
  local label="$1"
  local plist="$2"
  if [ -f "$plist" ]; then
    launchctl unload "$plist" 2>/dev/null
    sleep 1
    launchctl load "$plist" 2>/dev/null
    sleep 2
    # Check if running (PID present)
    local pid
    pid=$(launchctl list | grep "$label" | awk '{print $1}')
    if [[ "$pid" =~ ^[0-9]+$ ]]; then
      pass "$label — PID $pid"
    else
      local exit_code
      exit_code=$(launchctl list | grep "$label" | awk '{print $2}')
      warn "$label — not running (exit=$exit_code)"
    fi
  else
    warn "$label — plist not found: $plist"
  fi
}

# ── Helper: HTTP check ────────────────────────────────────────
check_http() {
  local name="$1"
  local url="$2"
  local code
  code=$(curl -s --max-time 8 -o /dev/null -w "%{http_code}" "$url" 2>/dev/null)
  if [ "$code" = "200" ] || [ "$code" = "302" ] || [ "$code" = "301" ]; then
    pass "$name → HTTP $code ✓"
  else
    fail "$name → HTTP $code ✗"
  fi
}

# ══════════════════════════════════════════════════════════════
echo -e "${BOLD}── 1. HERMES CLOUD GATEWAY (port 3002) ────────────────${NC}"
HERMES_PLIST="$AGENTS/ai.hermes.gateway-cloud.plist"
pkill -f "hermes_cli.main.*gateway" 2>/dev/null && info "Killed old Hermes process" || true
sleep 2
reload_plist "ai.hermes.gateway-cloud" "$HERMES_PLIST"
echo ""

# ══════════════════════════════════════════════════════════════
echo -e "${BOLD}── 2. REX FASTAPI BACKEND (port 8000) ─────────────────${NC}"
reload_plist "com.rex.backend" "$AGENTS/com.rex.backend.plist"
echo ""

# ══════════════════════════════════════════════════════════════
echo -e "${BOLD}── 3. GOJ DASHBOARD / DATAREX (port 8080) ─────────────${NC}"
DATAREX_PLIST="$AGENTS/com.goj.datarex.plist"
# Verify WorkingDirectory is correct before loading
WORKDIR=$(grep -A1 "WorkingDirectory" "$DATAREX_PLIST" 2>/dev/null | grep string | sed 's/.*<string>\(.*\)<\/string>.*/\1/')
CORRECT_WORKDIR="$HOME/Documents/goj files/dashboard"
if [ "$WORKDIR" != "$CORRECT_WORKDIR" ]; then
  warn "datarex plist WorkingDirectory is WRONG ($WORKDIR)"
  warn "Auto-fixing WorkingDirectory..."
  cp "$DATAREX_PLIST" "${DATAREX_PLIST}.bak_$(date +%Y%m%d_%H%M%S)"
  sed -i '' "s|<string>$WORKDIR</string>|<string>$CORRECT_WORKDIR</string>|g" "$DATAREX_PLIST" 2>/dev/null
  pass "Fixed WorkingDirectory → $CORRECT_WORKDIR"
fi
reload_plist "com.goj.datarex" "$DATAREX_PLIST"
echo ""

# ══════════════════════════════════════════════════════════════
echo -e "${BOLD}── 4. TIGER CLAW API (port 27226) ─────────────────────${NC}"
reload_plist "com.tigerclaw.api" "$AGENTS/com.tigerclaw.api.plist"
echo ""

# ══════════════════════════════════════════════════════════════
echo -e "${BOLD}── 5. GOJ HUB ──────────────────────────────────────────${NC}"
reload_plist "com.goj.hub" "$AGENTS/com.goj.hub.plist"
reload_plist "com.goj.hub-dev" "$AGENTS/com.goj.hub-dev.plist"
echo ""

# ══════════════════════════════════════════════════════════════
echo -e "${BOLD}── 6. N8N ──────────────────────────────────────────────${NC}"
reload_plist "com.goj.n8n" "$AGENTS/com.goj.n8n.plist"
echo ""

# ══════════════════════════════════════════════════════════════
echo -e "${BOLD}── 7. CLAUS WATCHMAN ───────────────────────────────────${NC}"
reload_plist "com.hermes.claus-watchman" "$AGENTS/com.hermes.claus-watchman.plist"
echo ""

# ══════════════════════════════════════════════════════════════
echo -e "${BOLD}── 8. TIGER CLAW APP ───────────────────────────────────${NC}"
reload_plist "com.goj.tigerclaw-app" "$AGENTS/com.goj.tigerclaw-app.plist"
echo ""

# ══════════════════════════════════════════════════════════════
echo -e "${BOLD}── 9. WAITING FOR SERVICES TO START (15s) ─────────────${NC}"
sleep 15
echo ""

# ══════════════════════════════════════════════════════════════
echo -e "${BOLD}── 10. HTTP HEALTH CHECKS ──────────────────────────────${NC}"
check_http "REX Backend       (8000)" "http://localhost:8000/health"
check_http "GOJ Dashboard     (8080)" "http://localhost:8080"
check_http "GOJ Admin         (8080)" "http://localhost:8080/dashboard"
check_http "Hermes Gateway    (3002)" "http://localhost:3002/health"
check_http "Tiger Claw        (27226)" "http://localhost:27226/health"
echo ""

# ══════════════════════════════════════════════════════════════
echo -e "${BOLD}── 11. ALL GOJ LAUNCHD SERVICES ────────────────────────${NC}"
launchctl list | grep -E "goj|hermes|rex|tigerclaw" | sort | while read line; do
  pid=$(echo "$line" | awk '{print $1}')
  exit_code=$(echo "$line" | awk '{print $2}')
  label=$(echo "$line" | awk '{print $3}')
  if [[ "$pid" =~ ^[0-9]+$ ]]; then
    echo -e "  ${GREEN}●${NC} $label (PID $pid)"
  else
    echo -e "  ${RED}○${NC} $label (exit=$exit_code)"
  fi
done
echo ""

# ══════════════════════════════════════════════════════════════
echo -e "${BOLD}── 12. OCR DATA STATUS ─────────────────────────────────${NC}"
DB="$HOME/Documents/goj files/dashboard/auth_tracker.db"
if [ -f "$DB" ]; then
  LAST=$(sqlite3 "$DB" "SELECT MAX(created_at) FROM client_menus;" 2>/dev/null)
  COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM client_menus;" 2>/dev/null)
  info "Last OCR: $LAST | Total records: $COUNT"
else
  warn "auth_tracker.db not found"
fi
echo ""

echo -e "${BOLD}╔══════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   REVIVAL COMPLETE  $(date +"%H:%M:%S")           ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════╝${NC}"
echo ""
echo "Log: $LOG"
echo ""
echo "Press any key to close..."
read -n 1
