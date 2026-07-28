#!/bin/bash
# ════════════════════════════════════════════════════════════════════════════
#  FIX_LOGIN.command — Creates KChairman on Railway directly
#  Deploys a tiny app that:
#    1. Reads the DB schema to find the user/login table
#    2. Creates KChairman / ghs2026! in the correct table
#    3. Restores the GOJ Dashboard
# ════════════════════════════════════════════════════════════════════════════
set -uo pipefail

GOJ_DIR="$HOME/Documents/goj files"
RAILWAY_URL="https://respectful-intuition-production-0acf.up.railway.app"
FIX_TOKEN="goj_fix_$(python3 -c 'import secrets; print(secrets.token_hex(8))')"
FINGERPRINT=$(python3 -c "import hashlib; print(hashlib.sha256('${FIX_TOKEN}'.encode()).hexdigest()[:12])")

G='\033[0;32m'; R='\033[0;31m'; B='\033[1m'; Y='\033[1;33m'; N='\033[0m'

clear
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  GOJ Railway — Fix Login (Create KChairman)         ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# Find app.py
APP_PY=""
DEPLOY_DIR=""
for c in "$GOJ_DIR/app.py" "$GOJ_DIR/dashboard/app.py"; do
    if [ -f "$c" ]; then APP_PY="$c"; DEPLOY_DIR="$(dirname "$c")"; break; fi
done
if [ -z "$APP_PY" ]; then
    echo -e "${R}❌ app.py not found${N}"; read -n 1; exit 1
fi

BAK="$APP_PY.fixlogin.bak"
cp "$APP_PY" "$BAK"

cleanup() {
    [ -f "$BAK" ] && cp "$BAK" "$APP_PY" && rm -f "$BAK"
}
trap cleanup EXIT

# Write diagnostic + fix app
cat > "$APP_PY" << PYAPP
import os, json, sqlite3, hashlib, uuid
from datetime import datetime
from flask import Flask, request

app = Flask(__name__)
FIX_TOKEN   = "${FIX_TOKEN}"
FINGERPRINT = "${FINGERPRINT}"
DATA_DIR    = os.environ.get('DATA_DIR', '/data')
DB_PATH     = os.path.join(DATA_DIR, 'auth_tracker.db')

@app.route('/health')
def health():
    return json.dumps({'status':'fix-ready','fp':FINGERPRINT}), 200

@app.route('/schema')
def schema():
    if request.headers.get('X-Fix-Token','') != FIX_TOKEN:
        return 'Unauthorized', 401
    conn = sqlite3.connect(DB_PATH)
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    result = {}
    for (t,) in tables:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})").fetchall()]
        count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        result[t] = {'columns': cols, 'rows': count}
    conn.close()
    return json.dumps(result, indent=2), 200

@app.route('/create-user', methods=['POST'])
def create_user():
    if request.headers.get('X-Fix-Token','') != FIX_TOKEN:
        return 'Unauthorized', 401
    data = request.get_json()
    table = data.get('table')
    password_hash = hashlib.sha256('ghs2026!'.encode()).hexdigest()
    try_bcrypt = False
    try:
        import bcrypt
        password_hash = bcrypt.hashpw('ghs2026!'.encode(), bcrypt.gensalt()).decode()
        try_bcrypt = True
    except ImportError:
        pass
    conn = sqlite3.connect(DB_PATH)
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    result = {'table': table, 'columns': cols, 'bcrypt': try_bcrypt, 'actions': []}
    now = datetime.utcnow().isoformat()
    uid = str(uuid.uuid4())
    # Try various insert patterns based on columns available
    try:
        if 'password_hash' in cols and 'role' in cols and 'username' in cols:
            conn.execute(f"DELETE FROM {table} WHERE username=?", ('KChairman',))
            conn.execute(
                f"INSERT INTO {table} (id, created_at, username, password_hash, first_name, last_name, role, active) VALUES (?,?,?,?,?,?,?,1)",
                (uid, now, 'KChairman', password_hash, 'Kato', 'Chairman', 'chairman')
            )
            result['actions'].append(f"Inserted into {table} (id,created_at,username,password_hash,first_name,last_name,role,active)")
        elif 'password' in cols and 'username' in cols:
            conn.execute(f"DELETE FROM {table} WHERE username=?", ('KChairman',))
            insert_cols = ['username', 'password']
            vals = ['KChairman', password_hash]
            if 'role' in cols: insert_cols.append('role'); vals.append('chairman')
            if 'id' in cols: insert_cols.insert(0, 'id'); vals.insert(0, uid)
            if 'created_at' in cols: insert_cols.append('created_at'); vals.append(now)
            if 'active' in cols: insert_cols.append('active'); vals.append(1)
            placeholders = ','.join(['?'] * len(vals))
            conn.execute(f"INSERT INTO {table} ({','.join(insert_cols)}) VALUES ({placeholders})", vals)
            result['actions'].append(f"Inserted into {table}: {insert_cols}")
        else:
            result['actions'].append(f"SKIP {table} — no usable username+password columns")
        conn.commit()
        result['status'] = 'ok'
    except Exception as e:
        result['error'] = str(e)
        result['status'] = 'error'
    conn.close()
    return json.dumps(result), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
PYAPP

echo -e "${G}✅ Fix app written${N}"
echo ""
echo -e "${B}▶ Deploying to Railway...${N}"
cd "$DEPLOY_DIR"
railway up --detach 2>&1 | tail -3
echo ""
echo -e "${B}  Waiting for fix app (fingerprint: ${FINGERPRINT})...${N}"

READY=false
for i in $(seq 1 30); do
    sleep 5
    printf "\r  ⏳ %d/30..." "$i"
    BODY=$(curl -s --max-time 5 "${RAILWAY_URL}/health" 2>/dev/null || echo "")
    if echo "$BODY" | grep -q "${FINGERPRINT}"; then
        READY=true; printf "\r                    \r"
        echo -e "${G}  ✅ Fix app live!${N}"; break
    fi
done
[ "$READY" = "false" ] && echo -e "\n${Y}  Timed out — trying anyway...${N}"

echo ""
echo -e "${B}▶ Reading DB schema...${N}"
SCHEMA=$(curl -s --max-time 10 -H "X-Fix-Token: ${FIX_TOKEN}" "${RAILWAY_URL}/schema" 2>/dev/null)
echo "$SCHEMA" | python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
for t, info in sorted(d.items()):
    u = 'username' in info['columns'] or 'user' in info['columns']
    p = 'password' in info['columns'] or 'password_hash' in info['columns']
    mark = '🔑' if (u and p) else '  '
    print(f'  {mark} {t}: {info[\"rows\"]} rows  cols={info[\"columns\"][:5]}')
" 2>/dev/null || echo "$SCHEMA" | head -40

# Find user table and create KChairman
USER_TABLE=$(echo "$SCHEMA" | python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
for t, info in sorted(d.items()):
    cols = info['columns']
    if ('username' in cols or 'user' in cols) and ('password' in cols or 'password_hash' in cols):
        print(t); break
" 2>/dev/null)

if [ -z "$USER_TABLE" ]; then
    echo -e "${R}❌ Could not identify user table from schema${N}"
    echo "Full schema:"
    echo "$SCHEMA"
else
    echo ""
    echo -e "${B}▶ Creating KChairman in table: $USER_TABLE${N}"
    RESULT=$(curl -s --max-time 10 \
        -X POST \
        -H "X-Fix-Token: ${FIX_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"table\":\"${USER_TABLE}\"}" \
        "${RAILWAY_URL}/create-user" 2>/dev/null)
    echo "  $RESULT"
    if echo "$RESULT" | grep -q '"status": "ok"'; then
        echo -e "${G}  ✅ KChairman created!${N}"
    fi
fi

echo ""
echo -e "${B}▶ Restoring GOJ Dashboard...${N}"
cp "$BAK" "$APP_PY"
rm -f "$BAK"
cd "$DEPLOY_DIR"
railway up --detach 2>&1 | tail -3
echo ""
echo -e "${G}  ✅ GOJ Dashboard redeployment started${N}"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo -e "${G}After ~60 seconds try:${N}"
echo "  🌐 $RAILWAY_URL"
echo "  👤 KChairman / ghs2026!"
echo ""
read -n 1 -p "Press any key to close..."
