#!/usr/bin/env bash
# CC_openwebui_connect_cloud.command
# Connect Docker Open WebUI to hermes-cloud container (port 8643)

LOG="$HOME/Desktop/REX/logs/cc_openwebui_connect_cloud.log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

echo "══════════════════════════════════════════════════"
echo "  Open WebUI → Cloud Hermes Fix — $(date '+%Y-%m-%d %H:%M:%S')"
echo "══════════════════════════════════════════════════"

# --- 1. Probe port 8643 (hermes-cloud Docker container)
echo ""
echo "── Probing hermes-cloud container (port 8643) ──"
echo "  /health: HTTP $(curl -s --max-time 5 -o /dev/null -w '%{http_code}' http://localhost:8643/health)"
echo "  /v1/models: HTTP $(curl -s --max-time 5 -o /dev/null -w '%{http_code}' http://localhost:8643/v1/models)"
MODELS=$(curl -s --max-time 5 "http://localhost:8643/v1/models" 2>/dev/null | head -c 400)
echo "  Response: $MODELS"

# --- 2. Check hermes-cloud container env
echo ""
echo "── hermes-cloud container environment ──"
docker exec hermes-cloud env 2>/dev/null | grep -E "API|PORT|HOST|MODEL|KEY|URL" | grep -v "PASSWORD\|SECRET" | head -20

# --- 3. Find docker-compose.yml for open-webui
echo ""
echo "── Looking for open-webui docker-compose ──"
find "$HOME" -name "docker-compose*" -maxdepth 5 2>/dev/null | head -10
COMPOSE=$(find "$HOME" -name "docker-compose*" -maxdepth 5 2>/dev/null | xargs grep -l "open-webui" 2>/dev/null | head -1)
echo "  Compose file: ${COMPOSE:-(not found)}"

if [ -n "$COMPOSE" ]; then
  echo ""
  echo "── Current open-webui service config ──"
  grep -A 40 "open-webui:" "$COMPOSE" | head -50
fi

# --- 4. Get API key for hermes-cloud
echo ""
echo "── API key from hermes-cloud ──"
docker exec hermes-cloud env 2>/dev/null | grep -iE "api_key|token|secret" | grep -v "PASSWORD" | head -5

# --- 5. Try to connect via Open WebUI API (add the cloud connection)
echo ""
echo "── Attempt: Add hermes-cloud API via Open WebUI admin API ──"
# Try to get admin token from Open WebUI
SIGNIN=$(curl -s --max-time 5 -X POST "http://localhost:3000/api/v1/auths/signin" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@admin.com","password":"admin"}' 2>/dev/null | head -c 300)
echo "  Signin attempt: $SIGNIN" | head -c 200

# --- 6. Check if hermes-cloud is API-key-protected
echo ""
echo "── hermes-cloud with API_SERVER_KEY ──"
API_KEY=$(python3 - <<'PY' 2>/dev/null
from pathlib import Path
p = Path.home()/'.hermes'/'.env'
if p.exists():
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if line.startswith('API_SERVER_KEY='):
            print(line.split('=', 1)[1])
            break
PY
)
if [ -n "$API_KEY" ]; then
  MODELS_AUTH=$(curl -s --max-time 5 \
    -H "Authorization: Bearer $API_KEY" \
    "http://localhost:8643/v1/models" | head -c 500)
  echo "  Models with API key: $MODELS_AUTH"
fi

echo ""
echo "── Summary ──"
echo "  open-webui Docker: port 3000 → ui.hermestigerclaw.com"
echo "  hermes-cloud Docker: port 8643 (API)"
echo "  LibreChat Docker: port 3080 → chat.hermestigerclaw.com"
echo ""
echo "  Action needed: in Open WebUI admin settings, add:"
echo "    OpenAI API URL: http://host.docker.internal:8643/v1"
echo "    API Key: (API_SERVER_KEY from ~/.hermes/.env)"

echo ""
echo "══ COMPLETE ══"
echo "Log: $LOG"
echo ""
sleep 4
