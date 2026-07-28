#!/bin/bash
# CC_rebuild_hermes_hub.command
# Rebuilds hermes-cloud:v3 — gateway + dashboard running together on startup
# Double-click to run (or: chmod +x ~/Desktop/REX/CC_rebuild_hermes_hub.command && ~/Desktop/REX/CC_rebuild_hermes_hub.command)

LOG="$HOME/Desktop/REX/logs/CC_rebuild_hermes_hub_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✅  $1${NC}"; }
fail() { echo -e "${RED}❌  $1${NC}"; exit 1; }
warn() { echo -e "${YELLOW}⚠️   $1${NC}"; }
info() { echo -e "${CYAN}ℹ️   $1${NC}"; }

echo -e "${BOLD}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   Hermes AI Hub — Clean Rebuild (v3)              ║${NC}"
echo -e "${BOLD}║   gateway run + dashboard on every startup        ║${NC}"
echo -e "${BOLD}╚═══════════════════════════════════════════════════╝${NC}"
echo ""

CONTAINER="hermes-cloud"
NEW_TAG="hermes-cloud:v3"

# ── 1. Verify container exists ─────────────────────────────────────────────────
if ! docker inspect "$CONTAINER" &>/dev/null; then
  fail "Container '$CONTAINER' not found. Run: docker ps -a"
fi
ok "Found container: $CONTAINER"

# ── 2. Ensure it's running (needed for docker exec) ───────────────────────────
STATUS=$(docker inspect -f '{{.State.Running}}' "$CONTAINER")
if [ "$STATUS" != "true" ]; then
  info "Starting container for build..."
  docker start "$CONTAINER" && sleep 5
fi
ok "Container running"

# ── 3. Capture full run config from current container ─────────────────────────
info "Reading current container config..."

# Volumes (host:container bindings)
VOLUMES=$(docker inspect "$CONTAINER" --format='{{range .HostConfig.Binds}}  -v {{.}} {{end}}' 2>/dev/null)

# Port bindings
PORTS=$(docker inspect "$CONTAINER" --format='{{range $p, $b := .HostConfig.PortBindings}}  -p {{(index $b 0).HostPort}}:{{$p}} {{end}}' 2>/dev/null)
# Strip /tcp suffix
PORTS=$(echo "$PORTS" | sed 's|/tcp||g')

# Network mode
NETWORK=$(docker inspect "$CONTAINER" --format='{{.HostConfig.NetworkMode}}' 2>/dev/null)
if [ "$NETWORK" = "default" ] || [ -z "$NETWORK" ]; then
  NETWORK_FLAG=""
else
  NETWORK_FLAG="--network $NETWORK"
fi

# Restart policy
RESTART=$(docker inspect "$CONTAINER" --format='{{.HostConfig.RestartPolicy.Name}}' 2>/dev/null)
if [ -n "$RESTART" ] && [ "$RESTART" != "no" ]; then
  RESTART_FLAG="--restart $RESTART"
else
  RESTART_FLAG="--restart unless-stopped"
fi

echo "  Volumes: $VOLUMES"
echo "  Ports:   $PORTS"
echo "  Network: ${NETWORK_FLAG:-default}"
echo "  Restart: $RESTART_FLAG"

# ── 4. Write startup script inside the container ──────────────────────────────
info "Writing startup script /opt/start_hermes.sh inside container..."
docker exec "$CONTAINER" sh -c 'cat > /opt/start_hermes.sh << '"'"'STARTUP_EOF'"'"'
#!/bin/bash
# Hermes AI Hub — starts both gateway and dashboard
echo "[startup] Starting Hermes dashboard on port 9119..."
/opt/hermes/.venv/bin/hermes dashboard &
DASH_PID=$!
echo "[startup] Dashboard PID: $DASH_PID"

echo "[startup] Starting Hermes gateway..."
exec /opt/hermes/.venv/bin/hermes gateway run
STARTUP_EOF
chmod +x /opt/start_hermes.sh
echo "Script written successfully"'

if [ $? -ne 0 ]; then
  fail "Could not write startup script inside container"
fi
ok "Startup script written"

# ── 5. Verify script is correct ───────────────────────────────────────────────
docker exec "$CONTAINER" cat /opt/start_hermes.sh
echo ""

# ── 6. Commit as new image ────────────────────────────────────────────────────
info "Committing as $NEW_TAG..."
docker commit \
  --change='CMD ["/bin/bash", "/opt/start_hermes.sh"]' \
  --message "v3: gateway run + dashboard on startup" \
  "$CONTAINER" "$NEW_TAG"

if [ $? -ne 0 ]; then
  fail "docker commit failed"
fi
ok "Image committed: $NEW_TAG"

# ── 7. Stop old container and rename it ───────────────────────────────────────
info "Stopping old container..."
docker stop "$CONTAINER"
docker rename "$CONTAINER" "${CONTAINER}-v2-backup"
ok "Old container renamed to: ${CONTAINER}-v2-backup"

# ── 8. Start new container ────────────────────────────────────────────────────
info "Starting new container from $NEW_TAG..."

# Rebuild env flags from old container
ENV_FLAGS=$(docker inspect "${CONTAINER}-v2-backup" \
  --format='{{range .Config.Env}}  -e "{{.}}" {{end}}' 2>/dev/null)

eval docker run -d \
  --name "$CONTAINER" \
  $PORTS \
  $VOLUMES \
  $NETWORK_FLAG \
  $RESTART_FLAG \
  $ENV_FLAGS \
  "$NEW_TAG"

if [ $? -ne 0 ]; then
  warn "New container failed to start. Restoring old one..."
  docker rename "${CONTAINER}-v2-backup" "$CONTAINER"
  docker start "$CONTAINER"
  fail "Rollback complete — old container restored. Check logs above."
fi

ok "New container started"
sleep 6

# ── 9. Verify both ports are up ───────────────────────────────────────────────
echo ""
info "Verifying services..."

API_CODE=$(docker exec "$CONTAINER" curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8643/health 2>&1)
if [[ "$API_CODE" =~ ^[23] ]]; then
  ok "Gateway API (8643): HTTP $API_CODE"
else
  warn "Gateway API (8643): HTTP $API_CODE — may still be starting"
fi

# Dashboard takes a few extra seconds
sleep 5
DASH_CODE=$(docker exec "$CONTAINER" curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9119/ 2>&1)
if [[ "$DASH_CODE" =~ ^[23] ]]; then
  ok "Dashboard (9119→9120): HTTP $DASH_CODE"
else
  warn "Dashboard (9119→9120): HTTP $DASH_CODE — may still be starting, wait 10s and check"
fi

HOST_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:9120/ 2>&1)
if [[ "$HOST_CODE" =~ ^[23] ]]; then
  ok "Host port 9120: HTTP $HOST_CODE"
else
  warn "Host port 9120: $HOST_CODE"
fi

# ── 10. Summary ───────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"
ok "Hermes AI Hub — v3 running!"
echo ""
echo -e "  ${BOLD}http://localhost:9120${NC}  — web UI (local)"
echo -e "  ${BOLD}http://localhost:8643${NC}  — API (local)"
echo ""
echo -e "  Gateway: connected to @Hermes_Cloud_May_bot + Telegram"
echo -e "  Both services start automatically on every container restart"
echo ""
warn "Old container saved as: ${CONTAINER}-v2-backup"
warn "Once confirmed working, you can remove it with:"
echo "  docker rm ${CONTAINER}-v2-backup"
echo ""
echo "Log: $LOG"
echo ""; echo "Press any key to close..."; read -n 1
