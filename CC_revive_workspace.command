#!/bin/bash
# CC_revive_workspace.command
# Revives Hermes Workspace (React/Node.js) — Conductor, Swarm, Operations,
# Memory Browser, Skills, Terminal, Files, all the custom features.
# Pulls ghcr.io/outsourc-e/hermes-workspace:latest (always newest).
# Connects to main Hermes gateway on port 3002 (Telegram bots stay wired).
# Runs on port 3001 (Open WebUI already has 3000).
# Adds workspace.hermestigerclaw.com to Cloudflare tunnel.

LOG="$HOME/Desktop/REX/logs/CC_revive_workspace_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
ok()     { echo -e "${GREEN}✅  $1${NC}"; }
fail()   { echo -e "${RED}❌  $1${NC}"; echo ""; echo "Log: $LOG"; echo ""; echo "Press any key..."; read -n 1; exit 1; }
warn()   { echo -e "${YELLOW}⚠️   $1${NC}"; }
info()   { echo -e "${CYAN}ℹ️   $1${NC}"; }
header() { echo ""; echo -e "${BOLD}━━━ $1${NC}"; }

echo -e "${BOLD}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   Hermes Workspace — Revival + Upgrade                    ║${NC}"
echo -e "${BOLD}║   React/Node.js  ·  Conductor  ·  Swarm  ·  Operations   ║${NC}"
echo -e "${BOLD}║   Memory Browser  ·  Skills  ·  Terminal  ·  Files       ║${NC}"
echo -e "${BOLD}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""

WORKSPACE_IMAGE="ghcr.io/outsourc-e/hermes-workspace:latest"
WORKSPACE_CONTAINER="hermes-workspace"
WORKSPACE_HOST_PORT=3004
HERMES_GATEWAY_PORT=3002
HERMES_DASHBOARD_HOST_PORT=9120
# Password to protect the workspace web UI
WORKSPACE_PASSWORD="GoldHealth2026!"
# Allowed external hostnames (comma-separated)
ALLOWED_HOSTS="workspace.hermestigerclaw.com,localhost,127.0.0.1"

# ── STEP 1: Verify main Hermes gateway is up ──────────────────────────────────
header "STEP 1: Verifying main Hermes gateway (port $HERMES_GATEWAY_PORT)"

GW_OK=false
for HEALTH_PATH in "/health" "/api/health" "/api/status" "/"; do
  GW_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 \
    "http://localhost:${HERMES_GATEWAY_PORT}${HEALTH_PATH}" 2>&1)
  if [[ "$GW_CODE" =~ ^[2345] ]]; then
    GW_OK=true
    ok "Main gateway responding on :${HERMES_GATEWAY_PORT}${HEALTH_PATH} (HTTP $GW_CODE)"
    break
  fi
done

if [ "$GW_OK" = false ]; then
  # Port might still be listening even if health returns odd codes
  if lsof -i ":${HERMES_GATEWAY_PORT}" 2>/dev/null | grep -q LISTEN; then
    GW_OK=true
    ok "Port $HERMES_GATEWAY_PORT is listening (gateway is up)"
  else
    fail "Main Hermes gateway is NOT running on port $HERMES_GATEWAY_PORT.
Start it first:
  launchctl load ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist
Then re-run this script."
  fi
fi

# Check dashboard availability (non-fatal)
DASH_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 \
  "http://localhost:${HERMES_DASHBOARD_HOST_PORT}/" 2>&1)
if [[ "$DASH_CODE" =~ ^[23] ]]; then
  ok "Hermes dashboard available on port $HERMES_DASHBOARD_HOST_PORT"
else
  warn "Dashboard not on port $HERMES_DASHBOARD_HOST_PORT (HTTP $DASH_CODE) — non-fatal, workspace will work without it"
fi

# ── STEP 2: Pull latest workspace image ───────────────────────────────────────
header "STEP 2: Pulling latest workspace image"
info "Image: $WORKSPACE_IMAGE"
info "This may take a minute if pulling new layers..."
echo ""
docker pull "$WORKSPACE_IMAGE"
if [ $? -ne 0 ]; then
  fail "docker pull failed. Check: docker login ghcr.io  (or internet connection)"
fi
ok "Latest image pulled"

# Show what version was pulled
DIGEST=$(docker inspect "$WORKSPACE_IMAGE" --format='{{.RepoDigests}}' 2>/dev/null | tr -d '[]' | awk '{print $1}')
info "Image digest: ${DIGEST:-unknown}"

# ── STEP 3: Remove any old workspace container ────────────────────────────────
header "STEP 3: Clearing old workspace container"
if docker inspect "$WORKSPACE_CONTAINER" &>/dev/null; then
  OLD_IMAGE=$(docker inspect "$WORKSPACE_CONTAINER" --format='{{.Config.Image}}' 2>/dev/null)
  info "Found existing container (image: $OLD_IMAGE) — removing..."
  docker stop "$WORKSPACE_CONTAINER" 2>/dev/null
  docker rm "$WORKSPACE_CONTAINER" 2>/dev/null
  ok "Old container removed"
else
  ok "No existing workspace container — clean start"
fi

# ── STEP 4: Run workspace container ───────────────────────────────────────────
header "STEP 4: Starting Hermes Workspace"

# Try to get API token from hermes .env (used if gateway requires auth)
API_TOKEN_FLAG=""
for ENV_FILE in \
  "$HOME/.hermes/profiles/cloud/.env" \
  "$HOME/.hermes-cloud/.env" \
  "$HOME/.hermes/.env"; do
  if [ -f "$ENV_FILE" ]; then
    TOKEN_VAL=$(grep -E "^API_SERVER_KEY=|^HERMES_API_TOKEN=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)
    if [ -n "$TOKEN_VAL" ]; then
      API_TOKEN_FLAG="-e HERMES_API_TOKEN=${TOKEN_VAL}"
      info "API token found in $ENV_FILE"
      break
    fi
  fi
done
if [ -z "$API_TOKEN_FLAG" ]; then
  info "No API token found — connecting to gateway without token (should work for local gateway)"
fi

info "Launching workspace..."
echo ""
echo "  Image:        $WORKSPACE_IMAGE"
echo "  Host port:    $WORKSPACE_HOST_PORT → 3000 (container)"
echo "  Gateway:      http://localhost:$HERMES_GATEWAY_PORT (main Python gateway)"
echo "  Password:     $WORKSPACE_PASSWORD"
echo "  Allowed hosts: $ALLOWED_HOSTS"
echo ""

docker run -d \
  --name "$WORKSPACE_CONTAINER" \
  --restart unless-stopped \
  -p "127.0.0.1:${WORKSPACE_HOST_PORT}:3000" \
  -e "HERMES_API_URL=http://host.docker.internal:${HERMES_GATEWAY_PORT}" \
  -e "HERMES_DASHBOARD_URL=http://host.docker.internal:${HERMES_DASHBOARD_HOST_PORT}" \
  -e "HERMES_PASSWORD=${WORKSPACE_PASSWORD}" \
  -e "CLAUDE_PASSWORD=${WORKSPACE_PASSWORD}" \
  -e "CLAUDE_ALLOWED_HOSTS=${ALLOWED_HOSTS}" \
  -e "COOKIE_SECURE=false" \
  -e "TRUST_PROXY=1" \
  -e "NODE_ENV=production" \
  ${API_TOKEN_FLAG} \
  --add-host "host.docker.internal:host-gateway" \
  "$WORKSPACE_IMAGE"

if [ $? -ne 0 ]; then
  fail "docker run failed — see error above."
fi
ok "Workspace container started"

# Give it time to boot (Node.js cold start + SSR init)
info "Waiting for workspace to initialize (20s)..."
for i in {1..4}; do
  sleep 5
  WS_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 \
    "http://localhost:${WORKSPACE_HOST_PORT}/" 2>&1)
  if [[ "$WS_CODE" =~ ^[23] ]]; then
    ok "Workspace is responding (HTTP $WS_CODE)"
    break
  fi
  echo "  ... still starting (${i}0s, HTTP $WS_CODE)"
done

if [[ ! "$WS_CODE" =~ ^[23] ]]; then
  warn "Workspace not responding yet (HTTP $WS_CODE after 20s)"
  warn "Last 25 lines of container logs:"
  docker logs --tail 25 "$WORKSPACE_CONTAINER"
  warn "Container may still be starting — check again in 30s:  curl -s -o /dev/null -w \"%{http_code}\" http://localhost:${WORKSPACE_HOST_PORT}/"
fi

# ── STEP 5: Verify workspace → gateway connectivity ───────────────────────────
header "STEP 5: Testing workspace → gateway connectivity"

GW_INSIDE=$(docker exec "$WORKSPACE_CONTAINER" \
  curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 \
  "http://host.docker.internal:${HERMES_GATEWAY_PORT}/health" 2>&1)

if [[ "$GW_INSIDE" =~ ^[2345] ]]; then
  ok "Workspace can reach gateway at host.docker.internal:${HERMES_GATEWAY_PORT} (HTTP $GW_INSIDE)"
else
  # Try /api/health
  GW_INSIDE2=$(docker exec "$WORKSPACE_CONTAINER" \
    curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 \
    "http://host.docker.internal:${HERMES_GATEWAY_PORT}/api/health" 2>&1)
  if [[ "$GW_INSIDE2" =~ ^[2345] ]]; then
    ok "Workspace can reach gateway (HTTP $GW_INSIDE2)"
  else
    warn "Workspace cannot reach gateway (got: $GW_INSIDE / $GW_INSIDE2)"
    warn "Check that the gateway is actually bound to 0.0.0.0 (not just 127.0.0.1)"
    info "To verify:  lsof -i :${HERMES_GATEWAY_PORT} | grep LISTEN"
    warn "If bound to 127.0.0.1 only, add --listen 0.0.0.0 to the gateway config"
  fi
fi

# ── STEP 6: Cloudflare tunnel — add workspace route ───────────────────────────
header "STEP 6: Adding workspace route to Cloudflare tunnel"

TUNNEL_CONFIG="$HOME/.cloudflared/hermestigerclaw.yml"
if [ ! -f "$TUNNEL_CONFIG" ]; then
  warn "Tunnel config not found at: $TUNNEL_CONFIG"
  warn "Add this manually before the catch-all line:"
  echo ""
  echo "  - hostname: workspace.hermestigerclaw.com"
  echo "    service: http://localhost:${WORKSPACE_HOST_PORT}"
  echo ""
else
  if grep -q "workspace\.hermestigerclaw\.com" "$TUNNEL_CONFIG"; then
    ok "workspace.hermestigerclaw.com route already in tunnel config"
    # Update port if it was set to something else
    sed -i '' "/workspace\.hermestigerclaw\.com/{n;s|service:.*|service: http://localhost:${WORKSPACE_HOST_PORT}|;}" \
      "$TUNNEL_CONFIG" 2>/dev/null
    ok "Port confirmed as $WORKSPACE_HOST_PORT"
  else
    info "Adding workspace.hermestigerclaw.com → localhost:${WORKSPACE_HOST_PORT} ..."
    TEMP=$(mktemp)
    # Insert before the last "http_status" catch-all line
    awk -v port="${WORKSPACE_HOST_PORT}" '
      /service: http_status/ && !added {
        print "  - hostname: workspace.hermestigerclaw.com"
        print "    service: http://localhost:" port
        added = 1
      }
      { print }
    ' "$TUNNEL_CONFIG" > "$TEMP"

    if [ -s "$TEMP" ] && grep -q "workspace.hermestigerclaw.com" "$TEMP"; then
      cp "$TUNNEL_CONFIG" "${TUNNEL_CONFIG}.bak.$(date +%Y%m%d_%H%M%S)"
      mv "$TEMP" "$TUNNEL_CONFIG"
      ok "Route added to $TUNNEL_CONFIG"
    else
      warn "Auto-insert failed (catch-all pattern not found?)"
      rm -f "$TEMP"
      warn "Add manually to $TUNNEL_CONFIG:"
      echo ""
      echo "  - hostname: workspace.hermestigerclaw.com"
      echo "    service: http://localhost:${WORKSPACE_HOST_PORT}"
      echo ""
    fi
  fi

  # Reload cloudflared tunnel
  CF_LABEL=$(launchctl list 2>/dev/null | grep -i "cloudflare" | awk '{print $3}' | head -1)
  if [ -n "$CF_LABEL" ]; then
    info "Reloading cloudflared ($CF_LABEL)..."
    launchctl kickstart -k "gui/$(id -u)/$CF_LABEL" 2>/dev/null && \
      ok "Cloudflared reloaded" || \
      warn "Could not reload cloudflared — restart manually to pick up new route"
  elif pgrep -x cloudflared > /dev/null 2>&1; then
    # Try SIGUSR1 (some versions support config reload)
    pkill -USR1 cloudflared 2>/dev/null || \
      warn "cloudflared running but could not reload — restart manually"
  else
    warn "cloudflared is not running — tunnel config updated but route not active yet"
  fi
fi

# ── STEP 7: Final summary ──────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   Hermes Workspace — LIVE                                 ║${NC}"
echo -e "${BOLD}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""

WS_FINAL=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 \
  "http://localhost:${WORKSPACE_HOST_PORT}/" 2>&1)
if [[ "$WS_FINAL" =~ ^[23] ]]; then
  ok "Workspace is UP"
else
  warn "Workspace returning HTTP $WS_FINAL — may still be warming up (check in 30s)"
fi

echo ""
echo -e "${BOLD}  Access:${NC}"
echo -e "    Local      →  ${CYAN}http://localhost:${WORKSPACE_HOST_PORT}${NC}"
echo -e "    External   →  ${CYAN}https://workspace.hermestigerclaw.com${NC}"
echo -e "    Password   →  ${BOLD}${WORKSPACE_PASSWORD}${NC}"
echo ""
echo -e "${BOLD}  Connected to:${NC}"
echo -e "    Main Hermes gateway  →  port ${HERMES_GATEWAY_PORT}"
echo -e "    @Hermes_Cloud_May_bot, @goldhealth_rexxie_bot, all bots stay wired"
echo ""
echo -e "${BOLD}  Features available:${NC}"
echo "    • Chat — full session history, SSE streaming, tool call rendering"
echo "    • Conductor — spawn missions, assign workers, live cost tracking"
echo "    • Operations — agent registry, pause/steer/kill live agents"
echo "    • Memory Browser — read/edit MEMORY.md and all memory files"
echo "    • Skills Browser — 2000+ skills"
echo "    • Terminal — full PTY (xterm.js) in your browser"
echo "    • Files — Monaco editor, full file browser"
echo "    • Dashboard — metrics, session overview"
echo ""
echo -e "${BOLD}  Container commands:${NC}"
echo "    docker logs -f $WORKSPACE_CONTAINER"
echo "    docker restart $WORKSPACE_CONTAINER"
echo "    docker stop $WORKSPACE_CONTAINER"
echo ""
echo "  Log: $LOG"
echo ""
echo "Press any key to close..."
read -n 1
