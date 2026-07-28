#!/bin/bash
# =============================================================
# setup-paperless-tunnel.command
# One-time setup: exposes Paperless-NGX through Cloudflare Tunnel
# so Claude/REX can reach it from anywhere via HTTPS.
#
# What this does:
#   - Installs cloudflared (via Homebrew)
#   - Creates a Cloudflare Tunnel named "paperless"
#   - Routes paperless.goldhealthsys.com → Tailscale Paperless Mac
#   - Installs a LaunchAgent so it auto-starts on login
#   - Updates ~/Documents/goj files/.env with the new URL
#
# Run ONCE from Terminal: bash ~/Desktop/REX/setup-paperless-tunnel.command
# =============================================================

set -euo pipefail

PAPERLESS_BACKEND="http://100.99.86.60:8000"
TUNNEL_NAME="paperless"
PUBLIC_HOST="paperless.goldhealthsys.com"
ENV_FILE="$HOME/Documents/goj files/.env"
CLOUDFLARED_DIR="$HOME/.cloudflared"
PLIST_SRC="$HOME/Desktop/REX/launchd/com.rex.paperless-tunnel.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.rex.paperless-tunnel.plist"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   Paperless Cloudflare Tunnel — One-Time Setup       ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Step 1: Install cloudflared ───────────────────────────────────────────
echo "▶ Step 1: Installing cloudflared..."
if command -v cloudflared &>/dev/null; then
  echo "  cloudflared already installed: $(cloudflared --version 2>&1 | head -1)"
else
  brew install cloudflared
  echo "  cloudflared installed."
fi

# ── Step 2: Authenticate with Cloudflare ─────────────────────────────────
echo ""
echo "▶ Step 2: Authenticating with Cloudflare..."
echo "  A browser window will open. Log in and select goldhealthsys.com."
echo "  (If already authenticated, this step will be skipped automatically.)"
echo ""
if [ ! -f "$CLOUDFLARED_DIR/cert.pem" ]; then
  cloudflared tunnel login
else
  echo "  Already authenticated (cert.pem found)."
fi

# ── Step 3: Create tunnel ─────────────────────────────────────────────────
echo ""
echo "▶ Step 3: Creating tunnel '$TUNNEL_NAME'..."
EXISTING=$(cloudflared tunnel list 2>/dev/null | grep -w "$TUNNEL_NAME" | awk '{print $1}' || true)
if [ -n "$EXISTING" ]; then
  TUNNEL_ID="$EXISTING"
  echo "  Tunnel '$TUNNEL_NAME' already exists: $TUNNEL_ID"
else
  TUNNEL_ID=$(cloudflared tunnel create "$TUNNEL_NAME" 2>&1 | grep -E "^[0-9a-f-]{36}$" | head -1 || \
              cloudflared tunnel list | grep -w "$TUNNEL_NAME" | awk '{print $1}')
  echo "  Tunnel created: $TUNNEL_ID"
fi

if [ -z "$TUNNEL_ID" ]; then
  echo "ERROR: Could not determine tunnel ID. Run 'cloudflared tunnel list' manually."
  exit 1
fi

# ── Step 4: Write tunnel config ───────────────────────────────────────────
echo ""
echo "▶ Step 4: Writing cloudflared config..."
CONFIG_FILE="$CLOUDFLARED_DIR/config.yml"

# Check if there's an existing config with a different tunnel
if grep -q "tunnel:" "$CONFIG_FILE" 2>/dev/null && ! grep -q "$TUNNEL_ID" "$CONFIG_FILE" 2>/dev/null; then
  echo "  Existing config found — appending paperless ingress rule."
  # Just append to ingress
  python3 - "$CONFIG_FILE" "$TUNNEL_ID" "$PUBLIC_HOST" "$PAPERLESS_BACKEND" << 'PYEOF'
import sys, re

config_file = sys.argv[1]
tunnel_id   = sys.argv[2]
public_host = sys.argv[3]
backend     = sys.argv[4]

with open(config_file) as f:
    content = f.read()

new_rule = f"""  - hostname: {public_host}
    service: {backend}"""

if public_host in content:
    print(f"  Rule for {public_host} already exists.")
else:
    # Insert before catch-all
    content = re.sub(
        r'(\s*- service: http_status:404)',
        f'\n{new_rule}\1',
        content
    )
    with open(config_file, 'w') as f:
        f.write(content)
    print(f"  Appended ingress rule for {public_host}.")
PYEOF
else
  cat > "$CONFIG_FILE" << YAML
tunnel: $TUNNEL_ID
credentials-file: $CLOUDFLARED_DIR/$TUNNEL_ID.json

ingress:
  - hostname: $PUBLIC_HOST
    service: $PAPERLESS_BACKEND
  - service: http_status:404
YAML
  echo "  Config written to $CONFIG_FILE"
fi

# ── Step 5: DNS route ─────────────────────────────────────────────────────
echo ""
echo "▶ Step 5: Setting up DNS (paperless.goldhealthsys.com → tunnel)..."
cloudflared tunnel route dns "$TUNNEL_NAME" "$PUBLIC_HOST" 2>&1 || \
  echo "  (DNS may already be configured — check Cloudflare dashboard if needed)"

# ── Step 6: Install LaunchAgent ───────────────────────────────────────────
echo ""
echo "▶ Step 6: Installing LaunchAgent for auto-start..."
mkdir -p "$(dirname "$PLIST_DEST")"
cat > "$PLIST_DEST" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.rex.paperless-tunnel</string>
  <key>ProgramArguments</key>
  <array>
    <string>/opt/homebrew/bin/cloudflared</string>
    <string>tunnel</string>
    <string>--config</string>
    <string>$CLOUDFLARED_DIR/config.yml</string>
    <string>run</string>
    <string>$TUNNEL_NAME</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$HOME/Library/Logs/paperless-tunnel.log</string>
  <key>StandardErrorPath</key>
  <string>$HOME/Library/Logs/paperless-tunnel.error.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key>
    <string>$HOME</string>
  </dict>
</dict>
</plist>
PLIST

launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"
echo "  LaunchAgent loaded."

# ── Step 7: Update .env ───────────────────────────────────────────────────
echo ""
echo "▶ Step 7: Updating .env with new Paperless URL..."
if [ -f "$ENV_FILE" ]; then
  # Replace or add PAPERLESS_URL
  if grep -q "^PAPERLESS_URL=" "$ENV_FILE"; then
    sed -i '' "s|^PAPERLESS_URL=.*|PAPERLESS_URL=https://$PUBLIC_HOST|" "$ENV_FILE"
    echo "  Updated PAPERLESS_URL in .env"
  else
    echo "PAPERLESS_URL=https://$PUBLIC_HOST" >> "$ENV_FILE"
    echo "  Added PAPERLESS_URL to .env"
  fi
else
  echo "PAPERLESS_URL=https://$PUBLIC_HOST" > "$ENV_FILE"
  echo "  Created .env with PAPERLESS_URL"
fi

# ── Done ──────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   ✅ DONE — Paperless Tunnel is live                 ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║                                                      ║"
printf "║   Public URL: https://%-30s ║\n" "$PUBLIC_HOST"
echo "║   Backend:    $PAPERLESS_BACKEND                  ║"
echo "║   Auto-start: LaunchAgent installed ✓               ║"
echo "║   .env:       PAPERLESS_URL updated ✓               ║"
echo "║                                                      ║"
echo "║   Test it:                                           ║"
printf "║   curl https://%s/api/ ║\n" "$PUBLIC_HOST      "
echo "║                                                      ║"
echo "║   ⚠ Make sure PAPERLESS_TOKEN is in your .env too   ║"
echo "║   Get it: Paperless → Settings → API Token          ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# Quick test
echo "Testing tunnel connection..."
sleep 3
HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://$PUBLIC_HOST/" 2>/dev/null || echo "000")
if [ "$HTTP" = "200" ] || [ "$HTTP" = "302" ] || [ "$HTTP" = "401" ]; then
  echo "✅ Tunnel is responding (HTTP $HTTP)"
else
  echo "⚠ Tunnel not responding yet (HTTP $HTTP) — may take 30-60 seconds to propagate"
fi
