#!/bin/bash
# CC_full_system_audit.command — Full GHS Stack Health Check
# Double-click to run

LOG="$HOME/Desktop/REX/logs/CC_system_audit_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'
YELLOW='\033[1;33m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'

ok()   { echo -e "${GREEN}✅  $1${NC}"; }
fail() { echo -e "${RED}❌  $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️   $1${NC}"; }
info() { echo -e "${CYAN}ℹ️   $1${NC}"; }
head() { echo -e "\n${BOLD}── $1 ──────────────────────────────${NC}"; }

echo -e "${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║     GHS FULL SYSTEM AUDIT · $(date +%H:%M\ %b\ %d)       ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}"

# ── 1. SERVICES ──────────────────────────────────────────────
head "SERVICES (localhost)"
declare -A SERVICES=(
  ["REX FastAPI :8000"]="http://localhost:8000/api/health"
  ["Hermes Cloud :3002"]="http://localhost:3002/health"
  ["GOJ Dashboard :8080"]="http://localhost:8080/health"
  ["n8n :5678"]="http://localhost:5678/healthz"
  ["LM Studio :1234"]="http://localhost:1234/v1/models"
  ["Ollama :11434"]="http://localhost:11434/api/tags"
  ["Tiger Claw :27226"]="http://localhost:27226/health"
)
UP=0; DOWN=0
for name in "${!SERVICES[@]}"; do
  url="${SERVICES[$name]}"
  code=$(curl -s --max-time 4 -o /dev/null -w "%{http_code}" "$url" 2>/dev/null)
  if [[ "$code" =~ ^2 ]]; then ok "$name → $code"; ((UP++)); else fail "$name → ${code:-TIMEOUT}"; ((DOWN++)); fi
done
echo -e "\n${BOLD}Services: ${GREEN}$UP UP${NC} / ${RED}$DOWN DOWN${NC}"

# ── 2. LAUNCHD ────────────────────────────────────────────────
head "LAUNCHD AGENTS"
plists=(
  "ai.hermes.gateway-cloud"
  "ai.hermes.gateway"
  "com.rex.backend"
  "com.goj.datarex"
  "com.tigerclaw.api"
  "com.hermes.claus-watchman"
  "com.goj.n8n"
)
for p in "${plists[@]}"; do
  status=$(launchctl list | grep "$p" 2>/dev/null | awk '{print $1}')
  if [[ "$status" =~ ^[0-9]+$ ]]; then ok "$p (PID $status)"
  elif [[ "$status" == "-" ]]; then warn "$p (loaded, not running)"
  else fail "$p (not loaded)"; fi
done

# ── 3. CLOUDFLARE TUNNEL ─────────────────────────────────────
head "CLOUDFLARE TUNNEL"
if launchctl list | grep -q "cloudflared\|com.cloudflare"; then
  ok "cloudflared agent loaded"
else
  tpid=$(pgrep -x cloudflared 2>/dev/null)
  if [ -n "$tpid" ]; then ok "cloudflared running (PID $tpid)"
  else fail "cloudflared not running"; fi
fi
code=$(curl -s --max-time 5 -o /dev/null -w "%{http_code}" "https://hermestigerclaw.com" 2>/dev/null)
[[ "$code" =~ ^2 ]] && ok "hermestigerclaw.com → $code (LIVE)" || fail "hermestigerclaw.com → $code"

# ── 4. DATABASE ───────────────────────────────────────────────
head "DATABASE"
DB="$HOME/Documents/goj files/dashboard/auth_tracker.db"
if [ -f "$DB" ]; then
  size=$(du -sh "$DB" | cut -f1)
  clients=$(sqlite3 "$DB" "SELECT COUNT(*) FROM clients;" 2>/dev/null)
  active=$(sqlite3 "$DB" "SELECT COUNT(*) FROM authorization WHERE status='ACTIVE';" 2>/dev/null)
  expired=$(sqlite3 "$DB" "SELECT COUNT(*) FROM authorization WHERE status='EXPIRED';" 2>/dev/null)
  ok "auth_tracker.db found ($size)"
  info "  Clients: $clients | Active: $active | Expired: $expired"
else
  fail "auth_tracker.db not found at expected path"
fi

# ── 5. BUILT FILES ────────────────────────────────────────────
head "CC_ DASHBOARD FILES"
CC_DIR="$HOME/Desktop/REX"
HTML_FILES=(
  "CC_command_center.html"
  "CC_kanban_center.html"
  "CC_home_base.html"
  "CC_mission_control.html"
  "CC_rex_bill_dashboard.html"
  "CC_attendance_bot_command_center.html"
  "CC_social_media_command_center.html"
  "CC_lead_connector.html"
  "CC_web_rack.html"
  "CC_live_progress_v2.html"
)
for f in "${HTML_FILES[@]}"; do
  fp="$CC_DIR/$f"
  if [ -f "$fp" ]; then
    sz=$(du -sh "$fp" | cut -f1)
    ok "$f ($sz)"
  else
    fail "$f NOT FOUND"
  fi
done

# ── 6. PENDING BUILDS ─────────────────────────────────────────
head "PENDING (not yet built)"
warn "CC_login.html          — unified auth login page"
warn "CC_settings.html       — system settings + toggles"
warn "CC_kato_hub.html       — Kato personal hub (Obsidian + vision)"
warn "GOJ live frontend      — SSE updates + propose/revert bar"
warn "Cloudflare route rules — map /kanban /command /goj /settings"
warn "hermestigerclaw.com/setup — first-run password setup"

# ── 7. OPEN ISSUES ────────────────────────────────────────────
head "KNOWN OPEN ISSUES"
fail "Hermes Cloud auth — deepseek model name invalid (see CC_hermes_cloud_fix_handoff.md)"
fail "Gmail token daily break — systemic OAuth refresh issue"
warn "auth_tracker.db not SQLCipher encrypted — top HIPAA item"
warn "TOTP using RFC example key — must rotate"
warn "TransitionAgent Drive hook — NOT deployed (deadline June 7)"
warn "QuickBooks workflow — bookkeeper left May 31, docs not captured"

# ── 8. HERMES GATEWAY LOG ────────────────────────────────────
head "HERMES CLOUD LAST 5 ERRORS"
LOG_FILE="$HOME/.hermes/profiles/cloud/logs/gateway.log"
if [ -f "$LOG_FILE" ]; then
  grep -i "error\|fail\|auth\|deepseek" "$LOG_FILE" 2>/dev/null | tail -5 | sed 's/^/  /'
else
  warn "Gateway log not found at $LOG_FILE"
fi

echo ""
echo -e "${BOLD}══════════════════════════════════════════════${NC}"
echo -e "${BOLD}Audit complete: $(date)${NC}"
echo -e "Log saved to: $LOG"
echo ""
echo "Press any key to close..."
read -n 1
