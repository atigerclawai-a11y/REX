#!/bin/bash
# ════════════════════════════════════════════════════════════════════════════
#  PATCH_AND_DEPLOY.command  —  Railway DB Sync (works with v4)
#
#  Since railway link/exec are broken in v4, this uses the linked GOJ dir:
#    1. Back up app.py in ~/Documents/goj files/
#    2. Replace it with a tiny seed server
#    3. railway up  (from the already-linked GOJ directory)
#    4. POST the SQL dump to the seed endpoint
#    5. Restore original app.py and railway up again
# ════════════════════════════════════════════════════════════════════════════
set -uo pipefail

GOJ_DIR="$HOME/Documents/goj files"
RAILWAY_URL="https://respectful-intuition-production-0acf.up.railway.app"
TMP_SQL="$TMPDIR/goj_seed_$$.sql"
SEED_TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
ORIG_APP="$GOJ_DIR/app.py"
BACKUP_APP="$GOJ_DIR/app.py.preseed.bak"
SEEDER_APP="$GOJ_DIR/app.py"   # We temporarily write here

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; B='\033[1m'; N='\033[0m'

clear
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  GOJ → Railway: Smart Database Sync                 ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Safety: restore on Ctrl+C or error ───────────────────────────────────────
cleanup() {
    if [ -f "$BACKUP_APP" ]; then
        echo ""
        echo -e "${Y}  Restoring original app.py...${N}"
        cp "$BACKUP_APP" "$SEEDER_DEST" && rm -f "$BACKUP_APP"
        echo -e "${G}  ✅ app.py restored${N}"
    fi
    rm -f "$TMP_SQL"
}
trap cleanup EXIT

# ── Preflight ─────────────────────────────────────────────────────────────────
if ! command -v railway &>/dev/null; then
    echo -e "${R}❌ Railway CLI not found.${N}"; read -n 1; exit 1
fi

# Find database
LOCAL_DB=""
for candidate in \
    "$GOJ_DIR/auth_tracker.db" \
    "$GOJ_DIR/dashboard/auth_tracker.db"; do
    if [ -f "$candidate" ] && [ $(stat -f%z "$candidate" 2>/dev/null || echo 0) -gt 50000 ]; then
        LOCAL_DB="$candidate"; break
    fi
done
if [ -z "$LOCAL_DB" ]; then
    echo -e "${R}❌ Cannot find auth_tracker.db in $GOJ_DIR${N}"; read -n 1; exit 1
fi

# Find app.py — search GOJ dir and subdirectories, also look for .railway links
ORIG_APP=""
DEPLOY_DIR=""
# First: look for app.py directly
for candidate in \
    "$GOJ_DIR/app.py" \
    "$GOJ_DIR/dashboard/app.py" \
    "$GOJ_DIR/src/app.py"; do
    if [ -f "$candidate" ]; then
        ORIG_APP="$candidate"
        DEPLOY_DIR="$(dirname "$candidate")"
        break
    fi
done
# Second: search for any .railway config that matches our project
if [ -z "$DEPLOY_DIR" ]; then
    for raildir in \
        "$GOJ_DIR" \
        "$HOME/Desktop/REX" \
        "$HOME/Documents" \
        "$HOME"; do
        if [ -f "$raildir/.railway/config.json" ]; then
            PROJ=$(python3 -c "import json; d=json.load(open('$raildir/.railway/config.json')); print(d.get('projectId',''))" 2>/dev/null || echo "")
            if echo "$PROJ" | grep -q "970deb3c"; then
                DEPLOY_DIR="$raildir"
                break
            fi
        fi
    done
fi
if [ -z "$DEPLOY_DIR" ]; then
    echo -e "${R}❌ Could not find the Railway-linked GOJ directory.${N}"
    echo ""
    echo "   app.py was not found at $GOJ_DIR/app.py"
    echo "   and no .railway config was found in standard locations."
    echo ""
    echo "   Please open Terminal and tell me the output of:"
    echo "   find ~/Documents -name 'app.py' 2>/dev/null | head -10"
    read -n 1; exit 1
fi
SEEDER_DEST="$DEPLOY_DIR/app.py"
BACKUP_APP="$DEPLOY_DIR/app.py.preseed.bak"
echo -e "${G}✅ Deploy dir: $DEPLOY_DIR${N}"

echo -e "${G}✅ DB: $(du -sh "$LOCAL_DB" | cut -f1) — $LOCAL_DB${N}"
[ -n "$ORIG_APP" ] && echo -e "${G}✅ App: $ORIG_APP${N}" || echo -e "${Y}⚠️  app.py not found — will create fresh in deploy dir${N}"
echo -e "${G}✅ Railway: $(railway --version 2>/dev/null | head -1)${N}"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Step 1: Export SQL ────────────────────────────────────────────────────────
echo -e "${B}▶ Step 1/5 — Exporting local database...${N}"

# Dump and convert macOS unistr() calls → plain Unicode (Linux SQLite has no unistr)
sqlite3 "$LOCAL_DB" .dump | python3 -c "
import sys, re

def fix_unistr(sql):
    def expand(m):
        s = m.group(1)
        s = re.sub(r'\\\\([0-9a-fA-F]{1,6})', lambda x: chr(int(x.group(1), 16)), s)
        s = s.replace(\"'\", \"''\")
        return \"'\" + s + \"'\"
    return re.sub(r\"unistr\('((?:[^'\\\\]|\\\\.)*)'\\)\", expand, sql)

sql = sys.stdin.read()
count = sql.count('unistr(')
fixed = fix_unistr(sql)
sys.stdout.write(fixed)
if count:
    print(f'  Fixed {count} unistr() calls', file=sys.stderr)
" > "$TMP_SQL" 2>/dev/null || sqlite3 "$LOCAL_DB" .dump > "$TMP_SQL"

LINES=$(wc -l < "$TMP_SQL" | tr -d ' ')
CLIENTS=$(sqlite3 "$LOCAL_DB" "SELECT COUNT(*) FROM clients" 2>/dev/null || echo "?")
USERS=$(sqlite3   "$LOCAL_DB" "SELECT COUNT(*) FROM staff_users" 2>/dev/null || echo "?")
echo -e "${G}  ✅ ${LINES} lines · ${CLIENTS} clients · ${USERS} users${N}"

# ── Step 2: Back up app.py and write seeder ───────────────────────────────────
echo ""
echo -e "${B}▶ Step 2/5 — Backing up app.py and installing seed server...${N}"
if [ -n "$ORIG_APP" ] && [ -f "$ORIG_APP" ]; then
    cp "$ORIG_APP" "$BACKUP_APP"
    echo -e "${G}  ✅ Backup: $BACKUP_APP${N}"
else
    echo -e "${Y}  (No existing app.py to back up — writing fresh seeder)${N}"
fi

# Write the minimal seed server
# TOKEN_FINGERPRINT is embedded in /health so we KNOW we're talking to THIS deployment
TOKEN_FINGERPRINT=$(python3 -c "import hashlib; print(hashlib.sha256('${SEED_TOKEN}'.encode()).hexdigest()[:12])")

cat > "$SEEDER_DEST" << PYAPP
import os, json, sqlite3, shutil
from flask import Flask, request

app = Flask(__name__)
SEED_TOKEN   = "${SEED_TOKEN}"
FINGERPRINT  = "${TOKEN_FINGERPRINT}"
DATA_DIR     = os.environ.get('DATA_DIR', '/data')
DB_PATH      = os.path.join(DATA_DIR, 'auth_tracker.db')

@app.route('/health')
def health():
    # fp uniquely identifies THIS deployment — used to survive rolling restarts
    return json.dumps({'status':'seeder-ready','db':DB_PATH,'fp':FINGERPRINT}), 200

@app.route('/seed', methods=['POST'])
def seed():
    if request.headers.get('X-Seed-Token','') != SEED_TOKEN:
        return 'Unauthorized', 401
    sql = request.data.decode('utf-8')
    bak = DB_PATH + '.bak'
    try: shutil.copy2(DB_PATH, bak)
    except: pass
    tmp = DB_PATH + '.new'
    try:
        conn = sqlite3.connect(tmp)
        conn.executescript(sql)
        conn.commit()
        counts = {}
        for t in ['clients','staff_users','authorization']:
            try: counts[t] = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
            except: counts[t] = 0
        conn.close()
        os.replace(tmp, DB_PATH)
        return json.dumps({'status':'ok','counts':counts}), 200, {'Content-Type':'application/json'}
    except Exception as e:
        try: os.remove(tmp)
        except: pass
        return json.dumps({'error':str(e)}), 500, {'Content-Type':'application/json'}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',8080)))
PYAPP

echo -e "${G}  ✅ Seed server written to app.py${N}"

# ── Step 3: Deploy seeder ────────────────────────────────────────────────────
echo ""
echo -e "${B}▶ Step 3/5 — Deploying seed server to Railway...${N}"
cd "$DEPLOY_DIR"
railway up --detach 2>&1 | tail -5
echo ""
echo -e "${G}  ✅ Deployment started — waiting for seed server to go live...${N}"

READY=false
echo "  Waiting for THIS deployment (fingerprint: ${TOKEN_FINGERPRINT})..."
for i in $(seq 1 30); do
    sleep 5
    printf "\r  ⏳ %d/30..." "$i"
    BODY=$(curl -s --max-time 5 "${RAILWAY_URL}/health" 2>/dev/null || echo "")
    # Match on fingerprint — ensures we're talking to the NEW deployment, not the old one
    if echo "$BODY" | grep -q "${TOKEN_FINGERPRINT}"; then
        READY=true
        printf "\r                         \r"
        echo -e "${G}  ✅ Correct deployment is live (fp: ${TOKEN_FINGERPRINT})!${N}"
        break
    fi
done
[ "$READY" = "false" ] && printf "\r" && echo -e "${Y}  ⚠️  Timed out waiting for new deployment — trying anyway...${N}"

# ── Step 4: Seed the database ─────────────────────────────────────────────────
echo ""
echo -e "${B}▶ Step 4/5 — Pushing ${LINES} lines of SQL to Railway...${N}"

HTTP=$(curl -s -o /tmp/seed_resp.txt -w "%{http_code}" \
    --max-time 150 \
    -X POST \
    -H "X-Seed-Token: ${SEED_TOKEN}" \
    -H "Content-Type: text/plain" \
    --data-binary @"$TMP_SQL" \
    "${RAILWAY_URL}/seed" 2>/dev/null)

if [ "$HTTP" = "200" ]; then
    echo -e "${G}  ✅ DATABASE SEEDED!${N}"
    echo "  $(cat /tmp/seed_resp.txt)"
else
    echo -e "${R}  ❌ Seed failed (HTTP ${HTTP})${N}"
    [ -f /tmp/seed_resp.txt ] && echo "  $(cat /tmp/seed_resp.txt)"
    echo ""
    echo -e "${Y}  Restoring original app.py before exiting...${N}"
    cp "$BACKUP_APP" "$ORIG_APP"
    echo -e "${G}  ✅ app.py restored. Run railway up manually from:${N}"
    echo "  cd ~/Documents/goj\\ files && railway up"
    rm -f "$BACKUP_APP"
    read -n 1 -p "Press any key to close..."; exit 1
fi

rm -f /tmp/seed_resp.txt

# ── Step 5: Restore app.py and redeploy ──────────────────────────────────────
echo ""
echo -e "${B}▶ Step 5/5 — Restoring GOJ Dashboard and redeploying...${N}"
if [ -f "$BACKUP_APP" ]; then
    cp "$BACKUP_APP" "$SEEDER_DEST"
    rm -f "$BACKUP_APP"
    echo -e "${G}  ✅ Original app.py restored${N}"
else
    rm -f "$SEEDER_DEST"
    echo -e "${Y}  (No backup to restore — please redeploy GOJ Dashboard manually)${N}"
fi

cd "$DEPLOY_DIR"
railway up --detach 2>&1 | tail -5
echo ""
echo -e "${G}  ✅ GOJ Dashboard redeployment started${N}"

rm -f "$TMP_SQL"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo -e "${G}${B}✅ ALL DONE${N}"
echo ""
echo "  After ~60 seconds the GOJ Dashboard will be live with"
echo "  all ${CLIENTS} clients synced."
echo ""
echo "  🌐  $RAILWAY_URL"
echo "  👤  KChairman / ghs2026!"
echo ""
read -n 1 -p "Press any key to close..."
