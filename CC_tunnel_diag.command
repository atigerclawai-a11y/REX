#!/bin/bash
# CC_tunnel_diag.command — Diagnose Cloudflare tunnel path routing issue
exec > >(tee "$HOME/Desktop/REX/logs/tunnel_diag_$(date +%Y%m%d_%H%M%S).log") 2>&1

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
pass(){ echo -e "${GREEN}✅  $1${NC}"; }
fail(){ echo -e "${RED}❌  $1${NC}"; }
info(){ echo -e "${CYAN}ℹ️   $1${NC}"; }

echo -e "${BOLD}=== CLOUDFLARE TUNNEL DIAGNOSTIC ===${NC}"
echo ""

# 1. Show exactly what cloudflared process is running
echo -e "${BOLD}--- cloudflared process ---${NC}"
ps aux | grep cloudflared | grep -v grep
echo ""

# 2. Show the LaunchAgent plist (what command launchd is using)
echo -e "${BOLD}--- LaunchAgent plist ---${NC}"
PLIST="$HOME/Library/LaunchAgents/com.cloudflare.cloudflared.plist"
if [ -f "$PLIST" ]; then
    cat "$PLIST"
else
    fail "Plist not found at $PLIST"
    ls "$HOME/Library/LaunchAgents/" | grep cloud
fi
echo ""

# 3. Show the actual config file cloudflared is using
echo -e "${BOLD}--- ~/.cloudflared/hermestigerclaw.yml ---${NC}"
CONFIG="$HOME/.cloudflared/hermestigerclaw.yml"
if [ -f "$CONFIG" ]; then
    cat "$CONFIG"
else
    fail "Not found: $CONFIG"
fi
echo ""

echo -e "${BOLD}--- ~/.cloudflared/config.yml ---${NC}"
CONFIG2="$HOME/.cloudflared/config.yml"
if [ -f "$CONFIG2" ]; then
    cat "$CONFIG2"
else
    info "Not found: $CONFIG2"
fi
echo ""

# 4. Check if cloudflared supports path routing (version check)
echo -e "${BOLD}--- cloudflared version ---${NC}"
cloudflared --version 2>/dev/null || which cloudflared
echo ""

# 5. Local endpoint checks
echo -e "${BOLD}--- Local endpoint checks ---${NC}"
for path in health progress cc; do
    code=$(curl -s --max-time 5 -o /dev/null -w "%{http_code}" http://localhost:8001/$path 2>/dev/null)
    [ "$code" = "200" ] && pass "localhost:8001/$path → $code" || fail "localhost:8001/$path → $code"
done
echo ""

# 6. Check what :8000 returns for /cc (confirm it's the one returning the error)
echo -e "${BOLD}--- :8000/cc response (should be 'not found') ---${NC}"
curl -s --max-time 5 http://localhost:8000/cc 2>/dev/null | head -5
echo ""

echo -e "${BOLD}=== DONE ===${NC}"
read -p "Press Enter to close..."
