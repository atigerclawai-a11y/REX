#!/bin/bash
# CC_rebuild_bbg.command
# Rebuilds BBG reservation book with updated staff (Allen/3152, Doni/2222, Lyuba/3333, Dima/4444)
# Restarts the server and adds bbg.hermestigerclaw.com to Cloudflare tunnel.

LOG="$HOME/Desktop/REX/logs/CC_rebuild_bbg_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✅  $1${NC}"; }
fail() { echo -e "${RED}❌  $1${NC}"; echo ""; echo "Log: $LOG"; echo "Press any key..."; read -n 1; exit 1; }
warn() { echo -e "${YELLOW}⚠️   $1${NC}"; }
info() { echo -e "${CYAN}ℹ️   $1${NC}"; }

echo -e "${BOLD}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   BBG Rebuild — Staff Update + Cloudflare Tunnel   ║${NC}"
echo -e "${BOLD}╚════════════════════════════════════════════════════╝${NC}"
echo ""

BBG_DIR="$HOME/Downloads/bbg-app"
PID_FILE="$BBG_DIR/serve.pid"
BBG_PORT=4173
TUNNEL_CONFIG="$HOME/.cloudflared/hermestigerclaw.yml"  # 🔴 2026-08-01: was config.yml (dormant direct-exposure, neutralized). hermestigerclaw.yml is the ONLY valid tunnel config — all ingress goes through the auth gateway.

[ -d "$BBG_DIR" ] || fail "BBG app not found at $BBG_DIR"

# ── STEP 1: Stop existing server ──────────────────────────────────────────────
info "Stopping existing BBG server..."
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        kill "$OLD_PID" 2>/dev/null
        sleep 1
        ok "Stopped PID $OLD_PID"
    else
        info "Server was not running (stale PID)"
    fi
fi
# Also kill any vite preview on that port
pkill -f "vite.*preview\|vite.*4173" 2>/dev/null
sleep 1
ok "Port $BBG_PORT clear"

# ── STEP 2: Build ─────────────────────────────────────────────────────────────
info "Building BBG (npm run build)..."
cd "$BBG_DIR"
npm run build
[ $? -eq 0 ] || fail "Build failed — check errors above"
ok "Build complete"

# ── STEP 3: Start server ──────────────────────────────────────────────────────
info "Starting BBG server on port $BBG_PORT..."
nohup npx vite preview --port $BBG_PORT --host 0.0.0.0 > "$BBG_DIR/serve.log" 2>&1 &
echo $! > "$PID_FILE"
disown
sleep 2

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "http://localhost:$BBG_PORT" 2>/dev/null)
if [[ "$HTTP_CODE" =~ ^[23] ]]; then
    ok "BBG server live on port $BBG_PORT (HTTP $HTTP_CODE)"
else
    warn "Server returning HTTP $HTTP_CODE — check $BBG_DIR/serve.log"
fi

# ── STEP 4: Add bbg.hermestigerclaw.com to Cloudflare tunnel ─────────────────
info "Updating Cloudflare tunnel config..."
if [ ! -f "$TUNNEL_CONFIG" ]; then
    warn "Tunnel config not found at $TUNNEL_CONFIG — skipping"
else
    if grep -q "bbg\.hermestigerclaw\.com" "$TUNNEL_CONFIG"; then
        ok "bbg.hermestigerclaw.com already in tunnel config"
        # Update port in case it changed
        sed -i '' "/bbg\.hermestigerclaw\.com/{n;s|service:.*|service: http://localhost:${BBG_PORT}|;}" \
            "$TUNNEL_CONFIG" 2>/dev/null
    else
        info "Adding bbg.hermestigerclaw.com → localhost:$BBG_PORT ..."
        TEMP=$(mktemp)
        awk -v port="$BBG_PORT" '
          /service: http_status/ && !added {
            print "  - hostname: bbg.hermestigerclaw.com"
            print "    service: http://localhost:" port
            added = 1
          }
          { print }
        ' "$TUNNEL_CONFIG" > "$TEMP"

        if [ -s "$TEMP" ] && grep -q "bbg.hermestigerclaw.com" "$TEMP"; then
            cp "$TUNNEL_CONFIG" "${TUNNEL_CONFIG}.bak.$(date +%Y%m%d_%H%M%S)"
            mv "$TEMP" "$TUNNEL_CONFIG"
            ok "Route added to tunnel config"
        else
            warn "Auto-insert failed — add manually to $TUNNEL_CONFIG:"
            echo "  - hostname: bbg.hermestigerclaw.com"
            echo "    service: http://localhost:$BBG_PORT"
            rm -f "$TEMP"
        fi
    fi

    # Reload cloudflared
    CF_LABEL=$(launchctl list 2>/dev/null | grep -i "cloudflare" | awk '{print $3}' | head -1)
    if [ -n "$CF_LABEL" ]; then
        info "Reloading cloudflared ($CF_LABEL)..."
        launchctl kickstart -k "gui/$(id -u)/$CF_LABEL" 2>/dev/null && \
            ok "Cloudflared reloaded — bbg.hermestigerclaw.com is live" || \
            warn "Could not reload cloudflared — restart manually"
    else
        warn "cloudflared not found in launchctl — restart it manually to pick up new route"
    fi
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   BBG — Rebuilt and Live ✅                        ║${NC}"
echo -e "${BOLD}╚════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Local:     ${CYAN}http://localhost:$BBG_PORT${NC}"
echo -e "  External:  ${CYAN}https://bbg.hermestigerclaw.com${NC}"
echo ""
echo -e "  Staff logins:"
echo -e "    Allen  (Owner)   → PIN ${BOLD}3152${NC}"
echo -e "    Doni   (Manager) → PIN ${BOLD}2222${NC}"
echo -e "    Lyuba  (Host)    → PIN ${BOLD}3333${NC}"
echo -e "    Dima   (Server)  → PIN ${BOLD}4444${NC}"
echo ""
echo "  Note: employees can clear browser cache if they see old staff names."
echo ""
echo "Log: $LOG"
echo ""; echo "Press any key..."; read -n 1
