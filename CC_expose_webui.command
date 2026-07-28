#!/bin/bash
# CC_expose_webui.command
# Adds webui.hermestigerclaw.com → localhost:3000 to the Cloudflare tunnel
# Double-click to run

LOG="$HOME/Desktop/REX/logs/CC_expose_webui_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "${GREEN}✅  $1${NC}"; }
fail() { echo -e "${RED}❌  $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️   $1${NC}"; }
info() { echo -e "${CYAN}ℹ️   $1${NC}"; }

echo -e "${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   Expose Open WebUI via Cloudflare Tunnel    ║${NC}"
echo -e "${BOLD}║   webui.hermestigerclaw.com → :3000          ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""

CONFIG="$HOME/.cloudflared/hermestigerclaw.yml"

# ── 1. Verify config exists ────────────────────────────────────────────────
if [ ! -f "$CONFIG" ]; then
  fail "Config not found: $CONFIG"
  echo "Run: ls ~/.cloudflared/ to find the correct config file"
  echo ""; echo "Press any key to close..."; read -n 1; exit 1
fi
ok "Found config: $CONFIG"

# ── 2. Check if already added ─────────────────────────────────────────────
if grep -q "webui.hermestigerclaw.com" "$CONFIG"; then
  warn "webui.hermestigerclaw.com already in config — skipping YAML edit"
else
  info "Adding webui.hermestigerclaw.com → localhost:3000 to config..."

  # Back up the original
  cp "$CONFIG" "${CONFIG}.bak_$(date +%Y%m%d_%H%M%S)"
  ok "Backup saved"

  # Insert the new ingress rule before the first existing rule
  # Uses Python for safe YAML-aware editing
  python3 << 'PYEOF'
import re, sys

config_path = __import__('pathlib').Path.home() / ".cloudflared" / "hermestigerclaw.yml"
content = config_path.read_text()

new_rule = (
    "  - hostname: webui.hermestigerclaw.com\n"
    "    service: http://localhost:3000\n"
)

# Find the first '  - hostname:' line under 'ingress:' and insert before it
ingress_match = re.search(r'^ingress:\s*\n', content, re.MULTILINE)
if not ingress_match:
    print("ERROR: could not find 'ingress:' section in config")
    sys.exit(1)

insert_pos = ingress_match.end()
# Find the first rule line after ingress:
first_rule = re.search(r'  - ', content[insert_pos:])
if first_rule:
    insert_pos = insert_pos + first_rule.start()

new_content = content[:insert_pos] + new_rule + "\n" + content[insert_pos:]
config_path.write_text(new_content)
print("YAML updated successfully")
PYEOF

  if [ $? -ne 0 ]; then
    fail "YAML edit failed — config unchanged"
    echo ""; echo "Press any key to close..."; read -n 1; exit 1
  fi
  ok "YAML updated"
fi

# ── 3. Add DNS CNAME via cloudflared ──────────────────────────────────────
info "Adding DNS record for webui.hermestigerclaw.com..."

# Get tunnel name from the config
TUNNEL_NAME=$(grep -E "^tunnel:" "$CONFIG" | awk '{print $2}' | tr -d '"')
if [ -z "$TUNNEL_NAME" ]; then
  warn "Could not read tunnel name from config — DNS record must be added manually"
  info "  In Cloudflare dashboard: CNAME webui.hermestigerclaw.com → <tunnel-id>.cfargotunnel.com"
else
  info "  Tunnel: $TUNNEL_NAME"
  cloudflared tunnel route dns "$TUNNEL_NAME" webui.hermestigerclaw.com 2>&1 && \
    ok "DNS record added: webui.hermestigerclaw.com" || \
    warn "DNS route command returned an error (may already exist — check dash.cloudflare.com)"
fi

# ── 4. Verify Open WebUI is running ───────────────────────────────────────
echo ""
info "Checking Open WebUI status..."
code=$(curl -s --max-time 4 -o /dev/null -w "%{http_code}" http://localhost:3000 2>/dev/null)
if [[ "$code" =~ ^2|^3 ]]; then
  ok "Open WebUI is running at localhost:3000 (HTTP $code)"
else
  fail "Open WebUI not responding at localhost:3000 (got: ${code:-TIMEOUT})"
  warn "Start it with: launchctl load ~/Library/LaunchAgents/ai.openwebui.hermes.plist"
  warn "Or: docker start open-webui"
fi

# ── 5. Restart Cloudflare tunnel ──────────────────────────────────────────
echo ""
info "Restarting Cloudflare tunnel to apply new route..."

# Try launchd first
CF_PLIST=$(launchctl list 2>/dev/null | grep -i "cloudflare\|cloudflared" | awk '{print $3}' | head -1)
if [ -n "$CF_PLIST" ]; then
  info "  Reloading via launchctl: $CF_PLIST"
  PLIST_PATH=$(ls ~/Library/LaunchAgents/*cloudflare* ~/Library/LaunchAgents/*cloudflared* 2>/dev/null | head -1)
  if [ -n "$PLIST_PATH" ]; then
    launchctl unload "$PLIST_PATH" 2>/dev/null
    sleep 2
    launchctl load "$PLIST_PATH" 2>/dev/null
    ok "Tunnel restarted via launchd"
  else
    warn "Could not find plist path — trying pkill"
    pkill -f "cloudflared tunnel" 2>/dev/null
    sleep 2
    cloudflared tunnel --config "$CONFIG" run &
    ok "Tunnel restarted in background"
  fi
else
  warn "cloudflared not found in launchctl — trying pkill + restart"
  pkill -f "cloudflared tunnel" 2>/dev/null
  sleep 2
  cloudflared tunnel --config "$CONFIG" run &
  ok "Tunnel restarted"
fi

# ── 6. Summary ────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}══════════════════════════════════════════════${NC}"
ok "Done!"
echo ""
info "Your Open WebUI is now available at:"
echo -e "  ${BOLD}https://webui.hermestigerclaw.com${NC}"
echo ""
warn "First visit may take 30–60 seconds for DNS to propagate"
warn "If you have Cloudflare Zero Trust Access rules on hermestigerclaw.com,"
warn "  you may need to add webui.hermestigerclaw.com to the Access policy too"
echo ""
echo "Log saved to: $LOG"
echo ""; echo "Press any key to close..."; read -n 1
