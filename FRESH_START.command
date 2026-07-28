#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  FRESH START — Reset login tokens ONLY, keep all data intact
#  Double-click to get back in when REX won't answer
#  ✅ Preserves: all users, chat history, documents, patterns
#  🔄 Resets:   login password → chairman2026, JWT secret, sessions
# ─────────────────────────────────────────────────────────────────

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'
REX_DIR="$HOME/Desktop/REX"
LOGS="$REX_DIR/logs"
DB="$HOME/.rex/rex_journeys.db"
mkdir -p "$LOGS"

echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}   🔄  FRESH START — Resetting tokens only${NC}"
echo -e "${BLUE}   (All your data is safe)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

# ── Step 1: Kill everything ────────────────────────────────────────
echo -e "${YELLOW}[1/4]${NC} Stopping all services..."
for PROC in "rex_rexxie_telegram_bot.py" "rex_telegram_bot.py" "uvicorn" "app.py"; do
    PIDS=$(pgrep -f "$PROC" 2>/dev/null)
    [ -n "$PIDS" ] && kill -9 $PIDS 2>/dev/null && echo -e "  ${GREEN}✓${NC} Stopped: $PROC"
done
for PORT in 8000 8080; do
    PID=$(lsof -ti :$PORT 2>/dev/null)
    [ -n "$PID" ] && kill -9 $PID 2>/dev/null && echo -e "  ${GREEN}✓${NC} Freed port $PORT"
done
sleep 2
echo -e "  ${GREEN}✓ All clear${NC}"

# ── Step 2: Reset tokens only — data untouched ────────────────────
echo -e "\n${YELLOW}[2/4]${NC} Resetting auth tokens (data is safe)..."

# Reset admin password file → default: chairman2026
rm -f "$LOGS/.admin_pass"
echo -e "  ${GREEN}✓${NC} Login password reset → chairman2026"

# Regenerate JWT secret — only invalidates browser sessions (forces re-login)
# Does NOT delete any users, history, or documents
rm -f "$HOME/.rex/auth/jwt_secret.key"
echo -e "  ${GREEN}✓${NC} JWT secret refreshed (you'll just need to log in again)"

# Reset the chairman password hash in the DB to match the default above
# This updates the password WITHOUT deleting any accounts or data
VENV_PYTHON="$REX_DIR/.venv/bin/python"
[ ! -f "$VENV_PYTHON" ] && VENV_PYTHON="$HOME/debate-chamber/.venv/bin/python3"
[ ! -f "$VENV_PYTHON" ] && VENV_PYTHON="python3"

"$VENV_PYTHON" - <<'PYEOF'
import sys, hashlib, secrets, sqlite3
from pathlib import Path

DB = Path.home() / ".rex" / "rex_journeys.db"
if not DB.exists():
    print("  ℹ️  No DB yet — will be created fresh on startup")
    sys.exit(0)

def hash_pw(password, salt=None):
    if not salt:
        salt = secrets.token_hex(16)
    h = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}:{h}"

conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row
cur = conn.execute("SELECT COUNT(*) FROM staff_users WHERE role='chairman'")
count = cur.fetchone()[0]
if count == 0:
    print("  ℹ️  No chairman account found — will be auto-created on first login")
else:
    new_hash = hash_pw("chairman2026")
    conn.execute("UPDATE staff_users SET password_hash=? WHERE role='chairman'", (new_hash,))
    conn.commit()
    row = conn.execute("SELECT username, first_name, last_name FROM staff_users WHERE role='chairman' LIMIT 1").fetchone()
    print(f"  ✅  Chairman password reset for: {row['first_name']} {row['last_name']} (@{row['username']})")
conn.close()
PYEOF

echo -e "  ${GREEN}✓${NC} All other accounts, data, and documents are untouched"

# ── Step 3: Start REX backend ─────────────────────────────────────
echo -e "\n${YELLOW}[3/4]${NC} Starting REX backend..."
cd "$REX_DIR"

if [ -f "$REX_DIR/.env" ]; then
    set -a; source "$REX_DIR/.env" 2>/dev/null; set +a
    echo -e "  ${GREEN}✓${NC} .env loaded"
fi

nohup "$VENV_PYTHON" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 >> "$LOGS/rex_backend.log" 2>&1 &
REX_PID=$!
sleep 5
if lsof -i :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "  ${GREEN}✓ REX backend running (PID $REX_PID)${NC}"
else
    echo -e "  ${RED}❌ REX backend failed — last 10 lines:${NC}"
    tail -10 "$LOGS/rex_backend.log"
fi

# ── Step 4: Start Rexxie ──────────────────────────────────────────
echo -e "\n${YELLOW}[4/4]${NC} Starting Rexxie..."
cd "$REX_DIR"
nohup "$VENV_PYTHON" rex_rexxie_telegram_bot.py >> "$LOGS/rexxie_telegram.log" 2>&1 &
sleep 4
if pgrep -f "rex_rexxie_telegram_bot.py" > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓ Rexxie is live${NC}"
else
    echo -e "  ${RED}❌ Rexxie failed — last 8 lines:${NC}"
    tail -8 "$LOGS/rexxie_telegram.log"
fi

# ── Done ──────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  ✅  READY — All your data is intact${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  Open:      ${CYAN}http://localhost:8000${NC}"
echo -e "  Username:  ${CYAN}chairman${NC}"
echo -e "  Password:  ${CYAN}chairman2026${NC}"
echo ""
echo -e "  ${YELLOW}Change your password after logging in.${NC}"
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo "Press Enter to close..."
read
