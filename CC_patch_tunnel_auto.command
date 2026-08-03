#!/bin/bash
# CC_patch_tunnel_auto.command — Automatically patch Cloudflare tunnel config
# Adds /progress, /cc, /api/stats ingress rules pointing to :8001
exec > >(tee "$HOME/Desktop/REX/logs/patch_tunnel_$(date +%Y%m%d_%H%M%S).log") 2>&1

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; BOLD='\033[1m'; YELLOW='\033[1;33m'; NC='\033[0m'
pass(){ echo -e "${GREEN}✅  $1${NC}"; }
fail(){ echo -e "${RED}❌  $1${NC}"; }
info(){ echo -e "${CYAN}ℹ️   $1${NC}"; }
warn(){ echo -e "${YELLOW}⚠️   $1${NC}"; }

echo -e "${BOLD}=== CLOUDFLARE TUNNEL AUTO-PATCH ===${NC}"
echo "Adding /progress, /cc, /api/stats → localhost:8001"
echo ""

CONFIG="$HOME/.cloudflared/hermestigerclaw.yml"
CONFIG2="$HOME/.cloudflared/config.yml"  # 🔴 NEUTRALIZED 2026-08-01 — dormant direct-exposure config, moved to config.yml.bak-dormant-20260801. Never use: it routes hostnames DIRECTLY to origin ports bypassing the auth gateway.

if [ -f "$CONFIG" ]; then
    info "Using config: $CONFIG"
else
    fail "🔴 SECURITY: hermestigerclaw.yml missing — REFUSING to fall back to config.yml (dormant direct-exposure config, neutralized 2026-08-01). Restore hermestigerclaw.yml first."
    read -p "Press Enter to close..."
    exit 1
fi

echo ""
info "Current config:"
cat "$CONFIG"
echo ""

# Check if already patched
if grep -q "8001" "$CONFIG"; then
    pass "Config already has :8001 routes — checking endpoints"
else
    warn "Config missing :8001 routes — patching now"
    echo ""

    # Back up
    BACKUP="${CONFIG}.backup_$(date +%Y%m%d_%H%M%S)"
    cp "$CONFIG" "$BACKUP"
    pass "Backed up to: $BACKUP"

    # Extract the tunnel ID and credentials from existing config
    TUNNEL_ID=$(grep "tunnel:" "$CONFIG" | awk '{print $2}')
    CREDS=$(grep "credentials-file:" "$CONFIG" | awk '{print $2}')

    info "Tunnel ID: $TUNNEL_ID"
    info "Credentials: $CREDS"

    # Write the new config with proper ingress rules
    cat > "$CONFIG" << YAML
tunnel: $TUNNEL_ID
credentials-file: $CREDS

ingress:
  - hostname: hermestigerclaw.com
    path: /progress
    service: http://localhost:8001
  - hostname: hermestigerclaw.com
    path: /cc
    service: http://localhost:8001
  - hostname: hermestigerclaw.com
    path: /api/stats
    service: http://localhost:8001
  - hostname: hermestigerclaw.com
    service: http://localhost:8000
  - service: http_status:404
YAML

    pass "Config patched"
    echo ""
    info "New config:"
    cat "$CONFIG"
    echo ""

    # Restart cloudflared
    info "Restarting Cloudflare tunnel..."
    PLIST="$HOME/Library/LaunchAgents/com.cloudflare.cloudflared.plist"
    if [ -f "$PLIST" ]; then
        launchctl unload "$PLIST" 2>/dev/null && info "Unloaded cloudflared"
        sleep 2
        launchctl load "$PLIST" && pass "Reloaded cloudflared"
        sleep 5
    else
        warn "LaunchAgent plist not found at $PLIST"
        info "Try: cloudflared service restart"
        # Try restarting via pkill if running as a process
        pkill -f "cloudflared" 2>/dev/null && info "Killed cloudflared process" || true
        sleep 2
        cloudflared tunnel run --config "$CONFIG" &
        sleep 3
    fi
fi

echo ""
info "Testing endpoints..."
sleep 3

for path in health progress cc; do
    code=$(curl -s --max-time 8 -o /dev/null -w "%{http_code}" http://localhost:8001/$path 2>/dev/null)
    [ "$code" = "200" ] && pass "localhost:8001/$path → $code" || fail "localhost:8001/$path → $code"
done

echo ""
for path in progress cc; do
    code=$(curl -s --max-time 12 -o /dev/null -w "%{http_code}" https://hermestigerclaw.com/$path 2>/dev/null)
    [ "$code" = "200" ] && pass "hermestigerclaw.com/$path → $code ✓ LIVE" || fail "hermestigerclaw.com/$path → $code (tunnel may still be starting)"
done

echo ""
echo -e "${BOLD}=== DONE ===${NC}"
echo ""
echo "  Local:  http://localhost:8001/progress"
echo "  Local:  http://localhost:8001/cc"
echo "  Domain: https://hermestigerclaw.com/progress"
echo "  Domain: https://hermestigerclaw.com/cc"
echo ""
read -p "Press Enter to close..."
