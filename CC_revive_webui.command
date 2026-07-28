#!/bin/bash
# CC_revive_webui.command — Restore Hermes WebUI from Downloads backup
# Port 8787 · docker-compose single-container

LOG="$HOME/Desktop/REX/logs/CC_revive_webui_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
pass(){ echo -e "${GREEN}✅  $1${NC}"; }
fail(){ echo -e "${RED}❌  $1${NC}"; }
info(){ echo -e "${CYAN}ℹ️   $1${NC}"; }

echo -e "${BOLD}=== Hermes WebUI Revival $(date) ===${NC}"
echo ""

WEBUI_DIR="$HOME/Downloads/hermes-webui-0.51.50"

# ── 1. Verify backup exists
echo -e "${BOLD}── 1. Checking backup ──────────────────────${NC}"
if [ -d "$WEBUI_DIR" ]; then
  pass "Found backup: $WEBUI_DIR"
  ls "$WEBUI_DIR/docker-compose.yml" 2>/dev/null && pass "docker-compose.yml present" || { fail "docker-compose.yml missing"; exit 1; }
else
  fail "Backup not found at $WEBUI_DIR"
  echo "  Expected: ~/Downloads/hermes-webui-0.51.50/"
  read -n 1 -p "Press any key to close..."; exit 1
fi
echo ""

# ── 2. Check Docker
echo -e "${BOLD}── 2. Checking Docker ──────────────────────${NC}"
if ! timeout 10 docker info &>/dev/null; then
  info "Docker not running — attempting to start..."
  open -a Docker
  echo "  Waiting 20s for Docker to start..."
  sleep 20
  if ! timeout 10 docker info &>/dev/null; then
    fail "Docker still not running. Open Docker Desktop manually then re-run."
    read -n 1 -p "Press any key to close..."; exit 1
  fi
fi
DOCKER_VER=$(docker --version 2>/dev/null)
pass "Docker running: $DOCKER_VER"
echo ""

# ── 3. Stop any running hermes-webui container
echo -e "${BOLD}── 3. Stopping old containers ──────────────${NC}"
cd "$WEBUI_DIR"
docker compose down 2>/dev/null && info "Stopped existing containers" || info "No containers were running"
# Also kill anything on port 8787
PID_8787=$(lsof -t -i:8787 2>/dev/null)
[ -n "$PID_8787" ] && kill -9 $PID_8787 2>/dev/null && info "Killed process on :8787" || true
echo ""

# ── 4. Create .env if needed
echo -e "${BOLD}── 4. Setting up .env ──────────────────────${NC}"
if [ ! -f "$WEBUI_DIR/.env" ]; then
  echo "UID=$(id -u)" > "$WEBUI_DIR/.env"
  echo "GID=$(id -g)" >> "$WEBUI_DIR/.env"
  echo "HERMES_SKIP_CHMOD=1" >> "$WEBUI_DIR/.env"
  pass "Created .env with UID=$(id -u) GID=$(id -g)"
else
  pass ".env already exists"
fi
echo ""

# ── 5. Build + start
echo -e "${BOLD}── 5. Starting Hermes WebUI ────────────────${NC}"
info "Building image (may take a minute if first time)..."
docker compose up -d --build 2>&1 | tail -20
echo ""

# ── 6. Wait and verify
echo -e "${BOLD}── 6. Verifying ────────────────────────────${NC}"
echo "  Waiting 15s for startup..."
sleep 15
CODE=$(curl -s --max-time 10 -o /dev/null -w "%{http_code}" http://localhost:8787 2>/dev/null)
if [ "$CODE" = "200" ] || [ "$CODE" = "302" ] || [ "$CODE" = "301" ]; then
  pass "Hermes WebUI → HTTP $CODE ✓ LIVE at http://localhost:8787"
  open "http://localhost:8787"
else
  fail "Hermes WebUI → HTTP $CODE — checking container logs..."
  docker compose logs --tail=30 2>/dev/null
fi
echo ""

# ── 7. Also check Open WebUI on 3000
echo -e "${BOLD}── 7. Checking Open WebUI :3000 ────────────${NC}"
OW_CODE=$(curl -s --max-time 5 -o /dev/null -w "%{http_code}" http://localhost:3000 2>/dev/null)
if [ "$OW_CODE" = "200" ] || [ "$OW_CODE" = "302" ]; then
  pass "Open WebUI :3000 → HTTP $OW_CODE ✓ also LIVE"
else
  info "Open WebUI :3000 → $OW_CODE (not running or different config)"
fi
echo ""

echo -e "${BOLD}=== Done $(date) ===${NC}"
echo "  Hermes WebUI: http://localhost:8787"
echo "  Log: $LOG"
echo ""
echo "Press any key to close..."
read -n 1
