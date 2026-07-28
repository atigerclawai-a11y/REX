# CC_RECOVERY.md — SINGLE SOURCE OF TRUTH
# Every fix, API key, endpoint, and procedure hardcoded here.
# Delete all other CC_fix_*/CC_restart_*/CC_gateway_* scripts — they're stale.
# Generated: 2026-07-01 · Hermes Agent

---

## SYSTEM FIX — File Descriptor Exhaustion

**Symptom:** All terminal commands fail with `[Errno 24] Too many open files`
**Check:** `ulimit -n` (should be 4096+, was 256)
**Root cause:** macOS default ulimit 256 + gateway process FD leak

### Fix (must run at physical Mac or SSH with GUI access):

```bash
# Permanent: raise system limit
sudo launchctl limit maxfiles 524288 1048576

# Restart work gateway
launchctl kickstart -k gui/501/ai.hermes.gateway-work
sleep 5

# Verify
ulimit -n                    # should be 4096+
curl -s http://127.0.0.1:8765/health
```

### If gateway restart blocked from within gateway session:
Use `no_agent=true` script cron (fires in separate process):
```bash
# Write script to ~/.hermes/profiles/work/scripts/emergency_restart.sh
# Create cron: cronjob action=create no_agent=true script="emergency_restart.sh"
```

---

## SERVICE HEALTH SWEEP

```bash
# One-liner health check
for port in 8000 8080 8100 9000 8765 3000 5678; do
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "http://127.0.0.1:$port" 2>/dev/null)
  echo "  :$port → $code"
done

# DeepSeek balance
DEEPSEEK_KEY=$(grep DEEPSEEK_API_KEY ~/.hermes/profiles/work/.env | cut -d= -f2-)
curl -s https://api.deepseek.com/user/balance -H "Authorization: Bearer $DEEPSEEK_KEY"

# Launchd gateways
launchctl list | grep -E 'ai\.hermes\.gateway'
```

### Service restart commands:

| Service | Port | Command |
|---------|------|---------|
| GOJ Dashboard | 8080 | `launchctl kickstart -k gui/501/com.goj.datarex` |
| REX Backend | 8000 | `launchctl kickstart -k gui/501/com.rex.backend` |
| BBG Ops | 8100 | `cd ~/Desktop/REX && nohup /usr/bin/python3 CC_bbg_operations.py &` |
| Tiger Claw Hub | 9000 | `launchctl kickstart -k gui/501/com.goj.hub` |
| Tiger Claw API | 27226 | `launchctl kickstart -k gui/501/com.tigerclaw.api` |
| Hermes Gateway Work | 3022 | `launchctl kickstart -k gui/501/ai.hermes.gateway-work` |
| Hermes Gateway Cloud | — | `launchctl kickstart -k gui/501/ai.hermes.gateway-cloud` |
| Hermes Gateway Rexxie | 3024 | `launchctl kickstart -k gui/501/ai.hermes.gateway-rexxie` |
| Cloudflare Tunnel | — | Tunnel restart: bootout BOTH `com.cloudflare.cloudflared` AND `com.cloudflare.hermestigerclaw`, then bootstrap only `hermestigerclaw` |
| Docker | — | `open -a Docker` |

---

## N8N — COMPLETE REFERENCE

### Connection
- **URL:** http://localhost:5678
- **Health:** `curl http://localhost:5678/healthz` → `{"status":"ok"}`
- **DB:** `/Users/mainsobhelper/.n8n/database.sqlite`

### Authentication
- **Owner login:** `atigerclawai@gmail.com` / `TigerClaw30$`
- **API Key:** `n8n_api_1227408ec75568a8b134aed2b2617b2ffc0c6f0ec60df86e` (label: tiger-claw-hub)
- **API Key scopes:** workflow:read, workflow:create, workflow:update, workflow:delete, workflow:list, workflow:execute, workflow:publish, workflow:unpublish, credential:read, credential:list, execution:read, execution:list, execution:delete, tag:read, tag:list, variable:read, variable:list

### Toggle workflow (activate/deactivate) — MUST use owner cookie, API key returns 403:

```bash
# Login
curl -s -c /tmp/n8n_cookies.txt -X POST http://localhost:5678/rest/login \
  -H "Content-Type: application/json" \
  -d '{"emailOrLdapLoginId":"atigerclawai@gmail.com","password":"TigerClaw30$"}'

# Deactivate
curl -s -b /tmp/n8n_cookies.txt -X POST "http://localhost:5678/rest/workflows/$WF_ID/deactivate"

# Wait 3s, then activate
sleep 3
curl -s -b /tmp/n8n_cookies.txt -X POST "http://localhost:5678/rest/workflows/$WF_ID/activate"

# Wait 5s for webhook registration, then test
sleep 5
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:5678/webhook/watchdog-alert
```

### Workflow IDs (full UUIDs from SQLite):
| Short ID (API) | Full UUID (SQLite) | Name |
|---|---|---|
| 88121b84-ad08 | 88121b84-ad08-45c3-80b6-ee50d7bf1420 | 🚨 Watchdog Escalation (Webhook) |
| 2rAqHTiiwTXQJyY5 | 2rAqHTiiwTXQJyY5 | ShellCore Health Watchdog |
| 5nnqRdEHlxA2RscU | 5nnqRdEHlxA2RscU | GOJ Nightly Handoff — 9pm |
| dw5HxFEOLs0QNUHX | dw5HxFEOLs0QNUHX | GOJ Daily Delivery — 2pm |
| idAvSEEaGWP9dr44 | idAvSEEaGWP9dr44 | Morning System Report — 8am |
| oCaXa5P0IrFVs1cM | oCaXa5P0IrFVs1cM | GOJ Kitchen Correction (Manual) |

### Direct SQLite toggle (n8n in-memory state won't update — use cookie login above):
```bash
sqlite3 ~/.n8n/database.sqlite "UPDATE workflow_entity SET active=0 WHERE id='FULL_UUID'"
sleep 3
sqlite3 ~/.n8n/database.sqlite "UPDATE workflow_entity SET active=1 WHERE id='FULL_UUID'"
```
**⚠️ SQLite toggle alone does NOT register webhooks — n8n needs in-memory activation. Use cookie method above.**

---

## SUPABASE

- **BBG Reservations project:** `nudjprnnqfgmrnwvgjxm`
- **Dashboard:** https://supabase.com/dashboard/project/nudjprnnqfgmrnwvgjxm
- **Issue:** Free tier pauses after 7 days inactivity → must manually unpause or upgrade to Pro
- **Fix:** Log into supabase.com → dashboard → click Unpause

---

## CONFIG DRIFT — Profiles

**Work:** `~/.hermes/profiles/work/config.yaml`
- provider: deepseek, model: deepseek-v4-pro
- fallback: ['anthropic', 'minimax'] ✅

**Cloud:** `~/.hermes/profiles/cloud/config.yaml`
- provider: deepseek, model: deepseek-v4-pro
- fallback: ['minimax', 'anthropic'] (fixed 2026-07-01)

**Check:** 
```bash
python3 -c "
import yaml
for p in ['work','cloud']:
    with open(f'/Users/mainsobhelper/.hermes/profiles/{p}/config.yaml') as f:
        c = yaml.safe_load(f)
    print(f'{p}: {c[\"model\"][\"provider\"]}/{c[\"model\"][\"default\"]} fb={c.get(\"fallback_providers\",[])}')
"
```

---

## CRON JOBS — Delivery Fix

If jobs show `last_delivery_error: "unknown platform 'webui'"`:
- Check `~/.hermes/profiles/work/cron/jobs.json`
- All jobs should have `"deliver": "origin"` (NOT "webui")
- Fix: python3 script to set deliver='origin' on any job with 'webui'

---

## API KEYS REFERENCE

| Key | Location | Value (truncated) |
|-----|----------|-------------------|
| DeepSeek | work/.env `DEEPSEEK_API_KEY` | sk-60fb85f9... |
| Anthropic | work/config.yaml `providers.anthropic.api_key` | sk-ant-api03-RhXYx... |
| MiniMax | work/config.yaml `providers.minimax.api_key` | sk-api-ghDGcq... |
| Google/Gemini | work/config.yaml `providers.gemini.api_key` | AIzaSyAU4... |
| n8n API | .hermes/.env `N8N_API_KEY` | n8n_api_1227408e... |
| Telegram | (in gateway config) | — |

---

## BBG RESERVATION PIPELINE

- **Poller:** `~/Desktop/REX/CC_owner_reservation_poller.py`
- **Confirmation:** `~/Desktop/REX/CC_confirm_reservation.py`
- **Data:** `~/Desktop/REX/CC_bbg_reservations.json`
- **Cron:** `ef3bd16a87e6` every 5min
- **Python:** MUST use `/opt/homebrew/bin/python3.11` (system python3 is 3.9)
- **Supabase backend:** `nudjprnnqfgmrnwvgjxm`

### Manual poll:
```bash
cd ~/Desktop/REX && /opt/homebrew/bin/python3.11 CC_owner_reservation_poller.py --cron
```

---

## DELETED STALE FILES

These 30+ scripts were archived to `~/Desktop/REX/CC_archive/fix_scripts/` on 2026-07-01:
CC_fix_victoria_routing.command, CC_check_gateway_status.command, CC_diagnose_and_fix_gateway.command,
CC_diagnose_local_gateway.command, CC_diagnose_local_gateway2.command, CC_docker_force_restart.command,
CC_gateway_audit.command, CC_gateway_auth_proxy.py, CC_gateway_diag.command,
CC_gateway_enhancement_proposal.md, CC_gateway_errlog.command, CC_gateway_quickcheck.command,
CC_gateway_watchdog.py, CC_health_check_gateway.command, CC_hermes_fix_restart.command,
CC_hermes_full_recovery.command, CC_hermes_gateway_check.command, CC_hermes_gateway_probe.command,
CC_hermes_restart.command, CC_instrument_and_restart.command, CC_restart_gateway.scpt,
CC_restart_hermes_cloud.command, CC_restart_hermes_gateway.command, CC_restart_hermes_workspace.command,
CC_restart_rexxie.command, CC_restart_stats_api.command, CC_restart_stats_api_final.command,
CC_trace_gateway_config.command, CC_unified_gateway_auth.py, CC_verify_local_gateway.command,
CC_verify_local_gateway2.command

**Single replacement:** `CC_full_recovery.command` (kept) + this `CC_RECOVERY.md`
