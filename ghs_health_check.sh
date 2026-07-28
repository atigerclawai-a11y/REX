#!/bin/bash
# GHS full-stack health check — read-only. Run anytime: bash ~/Desktop/REX/ghs_health_check.sh
PASS=0; FAIL=0; WARN=0
ok(){ echo "  ✅ $1"; PASS=$((PASS+1)); }
bad(){ echo "  ❌ $1"; FAIL=$((FAIL+1)); }
warn(){ echo "  ⚠️  $1"; WARN=$((WARN+1)); }

echo "════ GHS HEALTH CHECK — $(date '+%Y-%m-%d %H:%M') ════"

echo "◆ 1. Core venv integrity (the silent killer)"
V=~/.hermes/hermes-agent/venv
if [ -x "$V/bin/python" ] && [ "$(ls $V/lib/python*/site-packages 2>/dev/null | wc -l)" -gt 20 ]; then
  ok "venv intact ($($V/bin/python --version 2>&1))"
else bad "venv broken/missing — rebuild: cd ~/.hermes/hermes-agent && UV_PROJECT_ENVIRONMENT=venv uv sync --frozen --python 3.11"; fi

echo "◆ 2. Local services"
declare -a SVC=("3001 hermes-webui" "3000 open-webui" "3002 gateway-cloud" "3022 gateway-work" "3023 gateway-hermie" "3024 gateway-rexxie" "3010 privacy-router" "9000 hub-jarvis" "8090 goj-dashboard" "5678 n8n" "27125 obsidian-api" "8085 signal-cli" "9119 hermes-dashboard")
for s in "${SVC[@]}"; do
  port=${s%% *}; name=${s#* }
  code=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 4 http://127.0.0.1:$port/health 2>/dev/null)
  [ "$code" = "000" ] && code=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 4 http://127.0.0.1:$port/ 2>/dev/null)
  case $code in 200|302|301|401|404|405) ok "$name (:$port -> $code)";; *) bad "$name (:$port -> $code) DOWN";; esac
done

code=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 4 https://127.0.0.1:27124/)
case $code in 200|301|302|401|404|405) ok "obsidian-plugin (https :27124 -> $code)";; *) bad "obsidian-plugin (https :27124 -> $code) DOWN";; esac

echo "◆ 3. Public URLs"
for pub in hermes ui chat jarvis hub review; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 https://$pub.hermestigerclaw.com)
  case $code in 200|302|301|401) ok "$pub.hermestigerclaw.com ($code)";; *) bad "$pub.hermestigerclaw.com ($code)";; esac
done

echo "◆ 4. Telegram / gateway agent errors (last 30 min)"
CUT=$(date -v-30M '+%Y-%m-%d %H:%M')
for p in cloud work hermie rexxie; do
  n=$(awk -v c="$CUT" '$0 >= c' ~/.hermes/profiles/$p/logs/gateway.log 2>/dev/null | grep -c 'ERROR gateway.run: Agent error')
  [ "$n" = "0" ] && ok "$p: no agent errors" || bad "$p: $n agent errors in last 30 min (check ~/.hermes/profiles/$p/logs/gateway.log)"
done
pgrep -f CC_ghs_staff_daemon.py >/dev/null && ok "GHS staff bot daemon running" || bad "GHS staff bot daemon NOT running"

echo "◆ 5. Key launchd jobs"
for job in com.ghs.vault-autocommit com.goj.n8n com.goj.drive_signin_sync com.goj.privacy-router com.shellcore.audit ai.hermes.gateway-cloud ai.hermes.gateway-work ai.hermes.gateway-hermie ai.hermes.gateway-rexxie; do
  line=$(launchctl list 2>/dev/null | grep -w "$job")
  if [ -z "$line" ]; then warn "$job: not loaded"; else
    st=$(echo "$line" | awk '{print $2}')
    case $st in 0|-9|-15) ok "$job (status $st)";; *) warn "$job last exit status $st";; esac
  fi
done

echo "◆ 6. MCP servers (spawn test, stdio only)"
python3 - <<'PYEOF'
import json, subprocess, os
cfg = json.load(open(os.path.expanduser('~/.claude.json')))
init='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"hc","version":"1"}}}\n{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n'
okc=badc=0; bad=[]
for name,s in cfg.get('mcpServers',{}).items():
    if s.get('url') or s.get('type')=='http': continue
    env=dict(os.environ); env.update(s.get('env') or {})
    try:
        p=subprocess.run([s['command']]+s.get('args',[]),input=init,capture_output=True,text=True,timeout=10,env=env)
        # standard MCP replies with "result"; the custom lightweight JSON-RPC servers reply with "tools"/"error: Unknown" — both mean alive
        alive=('"result"' in p.stdout) or ('"tools"' in p.stdout) or ('Unknown' in p.stdout and p.returncode==0)
    except subprocess.TimeoutExpired: alive=True
    except Exception: alive=False
    if alive: okc+=1
    else: badc+=1; bad.append(name)
print(f"  {'✅' if not bad else '❌'} MCP stdio servers: {okc} ok, {badc} broken {bad if bad else ''}")
PYEOF

echo "◆ 7. OCR pipeline"
DB="/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db"
for f in ~/Desktop/REX/ocr_staging.py ~/Desktop/REX/CC_supervised_email_ocr.py ~/Desktop/REX/goj_drive_signature_pipeline.py ~/Desktop/REX/CC_daily_ocr_loop.py; do
  python3 -m py_compile "$f" 2>/dev/null && ok "$(basename $f) compiles" || bad "$(basename $f) broken/missing"
done
AL=$(sqlite3 "$DB" "SELECT COUNT(*) FROM attendance_log;" 2>/dev/null)
[ -n "$AL" ] && ok "live DB reachable (attendance_log=$AL)" || bad "live DB unreachable at $DB"

echo "◆ 8. Vault versioning + backups"
cd "/Users/mainsobhelper/Documents/GHS-Vault" 2>/dev/null && {
  AGE=$(( ($(date +%s) - $(git log -1 --format=%ct)) / 3600 ))
  [ "$AGE" -lt 24 ] && ok "vault git: last snapshot ${AGE}h ago" || warn "vault git: last snapshot ${AGE}h ago (>24h)"
}
if [ -d /Volumes/cartoons/GHS-Vault-Backup/GHS-Vault ]; then
  ok "cartoons mirror present ($(du -sh /Volumes/cartoons/GHS-Vault-Backup/GHS-Vault 2>/dev/null | cut -f1))"
else warn "cartoons drive not plugged in (mirror skipped)"; fi

echo "◆ 9. Ollama local models"
curl -s --max-time 4 http://127.0.0.1:11434/api/tags | grep -q qwen3.5:9b && ok "ollama up, qwen3.5:9b present" || bad "ollama down or qwen3.5:9b missing"

echo "◆ 10. Disk"
FREE=$(df -g / | tail -1 | awk '{print $4}')
[ "$FREE" -gt 30 ] && ok "boot disk ${FREE}GB free" || warn "boot disk only ${FREE}GB free"

echo "════ RESULT: $PASS pass / $WARN warn / $FAIL fail ════"
[ "$FAIL" -eq 0 ] && echo "VERDICT: HEALTHY" || echo "VERDICT: NEEDS ATTENTION"
