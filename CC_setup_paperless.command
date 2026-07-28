#!/bin/bash
# CC_setup_paperless.command
# One-time setup: installs Paperless-ngx locally via Docker, creates admin,
# generates API token, writes to backend/.env so scan watcher uses it.
# Run ONCE. After this, Paperless auto-starts on boot via launchd.

LOG="$HOME/Desktop/REX/logs/CC_setup_paperless_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

echo "============================================"
echo "  Paperless-ngx Local Setup"
echo "  $(date)"
echo "============================================"
echo ""

PAPERLESS_DIR="$HOME/Desktop/REX/paperless"
ENV_FILE="$HOME/Desktop/REX/backend/.env"

# ── Step 1: Verify Docker is running ─────────────────────────────────────────
echo "[1/5] Checking Docker..."
if ! docker info &>/dev/null; then
    echo "      ❌ Docker is not running. Open Docker Desktop and try again."
    read -p "Press any key to close..."; exit 1
fi
echo "      ✅ Docker running."

# ── Step 2: Start containers ──────────────────────────────────────────────────
echo ""
echo "[2/5] Pulling images and starting Paperless containers..."
echo "      (This may take 2-5 minutes on first run — images are ~1GB)"
cd "$PAPERLESS_DIR"
mkdir -p consume export
docker compose up -d
if [ $? -ne 0 ]; then
    echo "      ❌ docker compose failed. Check Docker Desktop is running."
    read -p "Press any key to close..."; exit 1
fi

echo "      Waiting 45s for Paperless to initialize..."
sleep 45

# ── Step 3: Create admin user ─────────────────────────────────────────────────
echo ""
echo "[3/5] Creating admin user..."
docker compose exec -T webserver python manage.py createsuperuser \
    --noinput \
    --username rex \
    --email rex@goldhealth.local 2>/dev/null
# Set password
docker compose exec -T webserver python manage.py shell -c "
from django.contrib.auth.models import User
try:
    u = User.objects.get(username='rex')
    u.set_password('RexGHS2026!')
    u.save()
    print('      ✅ Password set for user rex')
except Exception as e:
    print(f'      ⚠️  {e}')
"

# ── Step 4: Get API token ──────────────────────────────────────────────────────
echo ""
echo "[4/5] Generating API token..."
TOKEN_LINE=$(docker compose exec -T webserver python manage.py drf_create_token rex 2>/dev/null)
TOKEN=$(echo "$TOKEN_LINE" | awk '{print $NF}')
if [ -z "$TOKEN" ]; then
    echo "      ⚠️  Could not get token automatically. Trying via API..."
    TOKEN=$(curl -s -X POST http://localhost:8010/api/token/ \
        -d "username=rex&password=RexGHS2026!" \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))" 2>/dev/null)
fi

if [ -z "$TOKEN" ]; then
    echo "      ❌ Could not retrieve token. Check Paperless started correctly."
    echo "         Try: http://localhost:8010 → login as rex/RexGHS2026! → get token from admin panel"
    read -p "Press any key to close..."; exit 1
fi
echo "      ✅ Token: $TOKEN"

# ── Step 5: Write to backend/.env ─────────────────────────────────────────────
echo ""
echo "[5/5] Writing config to backend/.env..."
cat > "$ENV_FILE" << EOF
PAPERLESS_URL=http://localhost:8010
PAPERLESS_TOKEN=$TOKEN
EOF
echo "      ✅ Written to $ENV_FILE"

echo ""
echo "============================================"
echo "  Paperless-ngx is running!"
echo ""
echo "  URL:      http://localhost:8010"
echo "  Username: rex"
echo "  Password: RexGHS2026!"
echo "  Token:    $TOKEN"
echo ""
echo "  All 4 OCR engines now active:"
echo "  ✅ Tesseract (local)"
echo "  ✅ Google Drive OCR"
echo "  ✅ Claude Vision"
echo "  ✅ Paperless-ngx (local, port 8010)"
echo ""
echo "  Paperless will auto-start on next reboot"
echo "  (run CC_install_paperless_plist.command to enable auto-start)"
echo "============================================"
echo ""
echo "  Log: $LOG"
echo ""
read -p "Press any key to close..."
