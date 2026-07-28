#!/bin/bash
# CC_reset_webui_password.command
# Resets Open WebUI admin password to: GoldHealth2026!
# Double-click to run

LOG="$HOME/Desktop/REX/logs/CC_reset_webui_password_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'
BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "${GREEN}✅  $1${NC}"; }
fail() { echo -e "${RED}❌  $1${NC}"; }
info() { echo -e "${CYAN}ℹ️   $1${NC}"; }

echo -e "${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║     Open WebUI — Password Reset              ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""

NEW_PASSWORD="GoldHealth2026!"

# ── 1. Check container is running ─────────────────────────────────────────
if ! docker inspect open-webui &>/dev/null; then
  fail "open-webui container not found"
  echo "Start it with: docker start open-webui"
  echo ""; echo "Press any key to close..."; read -n 1; exit 1
fi

STATUS=$(docker inspect -f '{{.State.Running}}' open-webui 2>/dev/null)
if [ "$STATUS" != "true" ]; then
  info "Starting open-webui container..."
  docker start open-webui
  sleep 3
fi
ok "Container running"

# ── 2. Find the admin user email ──────────────────────────────────────────
info "Finding admin user..."
USERS=$(docker exec open-webui sqlite3 /app/backend/data/webui.db \
  "SELECT id, email, role FROM user ORDER BY created_at ASC;" 2>/dev/null)

if [ -z "$USERS" ]; then
  fail "Could not query user table — DB path may differ"
  # Try alternate path
  USERS=$(docker exec open-webui sqlite3 /app/backend/data/data.db \
    "SELECT id, email, role FROM user ORDER BY created_at ASC;" 2>/dev/null)
fi

if [ -z "$USERS" ]; then
  fail "Could not find user database inside container"
  echo ""; echo "Press any key to close..."; read -n 1; exit 1
fi

echo "  Registered users:"
echo "$USERS" | while IFS='|' read id email role; do
  echo "    [$role] $email"
done

# Get the first admin email
ADMIN_EMAIL=$(echo "$USERS" | grep "admin" | head -1 | cut -d'|' -f2)
if [ -z "$ADMIN_EMAIL" ]; then
  # Fall back to first user
  ADMIN_EMAIL=$(echo "$USERS" | head -1 | cut -d'|' -f2)
fi
info "Resetting password for: $ADMIN_EMAIL"

# ── 3. Hash the new password with bcrypt ──────────────────────────────────
info "Hashing new password..."
HASHED=$(docker exec open-webui python3 -c "
from passlib.context import CryptContext
ctx = CryptContext(schemes=['bcrypt'], deprecated='auto')
print(ctx.hash('${NEW_PASSWORD}'))
" 2>/dev/null)

if [ -z "$HASHED" ]; then
  # Try alternate import path
  HASHED=$(docker exec open-webui python3 -c "
import bcrypt
h = bcrypt.hashpw('${NEW_PASSWORD}'.encode(), bcrypt.gensalt())
print(h.decode())
" 2>/dev/null)
fi

if [ -z "$HASHED" ]; then
  fail "Could not hash password inside container"
  echo ""; echo "Press any key to close..."; read -n 1; exit 1
fi
ok "Password hashed"

# ── 4. Update the database ────────────────────────────────────────────────
info "Writing new password to DB..."
docker exec open-webui sqlite3 /app/backend/data/webui.db \
  "UPDATE user SET password='${HASHED}' WHERE email='${ADMIN_EMAIL}';" 2>/dev/null

ROWS=$(docker exec open-webui sqlite3 /app/backend/data/webui.db \
  "SELECT changes();" 2>/dev/null)
ok "Password updated ($ROWS row changed)"

# ── 5. Summary ────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}══════════════════════════════════════════════${NC}"
ok "Done! Your new Open WebUI credentials:"
echo ""
echo -e "  Email:    ${BOLD}${ADMIN_EMAIL}${NC}"
echo -e "  Password: ${BOLD}${NEW_PASSWORD}${NC}"
echo ""
info "Go to http://localhost:3000 (or https://webui.hermestigerclaw.com)"
info "Change the password after logging in if you want something different"
echo ""
echo "Log: $LOG"
echo ""; echo "Press any key to close..."; read -n 1
