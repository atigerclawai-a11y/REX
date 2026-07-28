# CC Missing-Link Report — Tiger Claw / REX / Hermes / GOJ

_Generated 2026-06-09 16:22  by `~/Desktop/REX/CC_missing_link_audit.py` (READ-ONLY). Re-run anytime: `python3 ~/Desktop/REX/CC_missing_link_audit.py` (add `--json` for machine output)._

This report finds **every broken connection** so the system can be tied together. Each finding is `{what, where, status, how_to_fix}`. **Nothing was changed** — this is diagnosis only. All fixes below are recommendations for you (or the guardian safe-update flow) to apply.

## Counts at a glance

| Category | Broken | Missing/Orphaned | Warn | Stale | OK |
|---|---|---|---|---|---|
| **HERMES (priority #1)** | 2 | 0 | 2 | - | - |
| Gateways / Tunnels | 3 | 0 | 2 | - | 10 |
| API Keys | - | 3 | - | - | 11 |
| Auth / Passwords | 0 | 0 | 0 | - | 4 |
| Local Services (launchd) | 16 | 10 | 0 | - | 37 |
| Stale References | - | - | 1 | 16 | - |

---

# 🔴 HERMES FIX (do this first — owner's #1 priority)

**Symptom:** `hermes.hermestigerclaw.com` and `desktop.hermestigerclaw.com` return **502**.

**Root cause (confirmed):** Both hostnames route to `http://127.0.0.1:8787` in BOTH cloudflared configs, but **nothing listens on :8787 and no launchd job binds it.** The Hermes WebUI that lived there was a manually-started app (`~/hermes-webui`, `HERMES_WEBUI_PORT` in `.env.local`) / Docker container that exited and was never brought back. The *live* Hermes processes are **messaging gateways, not a browser chat UI**:

- `ai.hermes.gateway` → **:8088 + :65001** (UP, `/health` 200)
- `ai.hermes.gateway-cloud` → **:3002** (UP, `/health` 200)
- The only **live browser chat UIs** are **LibreChat :3080** (Docker, up 31h) and **Open WebUI :3000**.

## Fix A — fastest, zero new services (recommended)
Repoint both hostnames to the live LibreChat UI. **Edit BOTH** `~/.cloudflared/config.yml` **AND** `~/.cloudflared/hermestigerclaw.yml` (the two cloudflared instances each load one):

```yaml
  # was: http://127.0.0.1:8787  (DEAD)
  - hostname: hermes.hermestigerclaw.com
    service: http://127.0.0.1:3080      # LibreChat (live)
  - hostname: desktop.hermestigerclaw.com
    service: http://127.0.0.1:3080      # LibreChat (live)
```

Then validate + reload **the two tunnels SEQUENTIALLY** (simultaneous reload = ~45s 530 outage; guardian rule):

```bash
cloudflared tunnel ingress validate            # against each config
# reload com.cloudflare.cloudflared first, wait, THEN com.cloudflare.hermestigerclaw
```

`chmod 600 ~/.cloudflared/*.yml` after editing (Python/editor writes can reset perms to 644).

## Fix B — keep the dedicated Hermes WebUI on :8787
Bring `~/hermes-webui` back up so it binds :8787 (it has a `Dockerfile`, a `.venv`, and `HERMES_WEBUI_PYTHON`/`HERMES_WEBUI_PORT` in `.env.local`), **and create a launchd job for it** — it is currently unmanaged, which is exactly why it keeps disappearing after a reboot/crash. Leave the tunnel pointing at :8787. Use the guardian safe-update flow; do not hand-spawn a new service/subdomain.

## Also part of Hermes (chat works end-to-end only after these)

**Hermes REST API :8642 is DOWN** — breaks WhatsApp + any OpenAI-compatible client. The zeroclaw-adapter (and any OpenAI-compatible client) POST to http://127.0.0.1:8642/v1/chat/completions, but nothing listens on :8642. The gateway's API server is governed by API_SERVER_ENABLED / API_SERVER_HOST / API_SERVER_PORT in ~/.hermes/.env — confirm API_SERVER_PORT matches what the adapter expects (8642) and that API_SERVER_ENABLED=true, then restart ai.hermes.gateway. The gateway currently exposes only :8088 and :65001; if the REST API is meant to be :65001, repoint the adapter's HERMES_URL to :65001 instead. This is WHY the WhatsApp path is dead end-to-end.

**zeroclaw-adapter websocket errors** — the adapter's ws server on :18789 is up but receives truncated/non-ws connections (health probes or kapso bridge using the wrong URL). Non-fatal log noise; the real cause is :8642 being down. Point `com.hermes.kapso-whatsapp` at `ws://127.0.0.1:18789` and fix :8642 first.

**Signal adapter retry loop** — local gateway can't reach `signal-cli` on :8085; start signal-cli or disable the Signal platform in `~/.hermes/.env`. Cosmetic but floods the log.

---

# Other categories — every missing link with a tie-it-together fix

## API Keys — what to add for the integrations you want

**Configured (11):** anthropic, openai, deepseek, perplexity, retell, twilio, elevenlabs, google, xai, openrouter — confirmed via `~/.hermes/.env` + REX `/api/keys/status`. (Note: REX backend itself reports `google:false` and `librechat:false`, but a Google key **is** present in `~/.hermes/.env` — REX just hasn't been given it.)

**Missing (3) — these block the integrations Kato wants:**

- **API key: poe (WANTED INTEGRATION)** — [KATO WANTS THIS] poe integration has NO key. No key for poe. Add the key to ~/.hermes/.env (POE_API_KEY/POE_TOKEN) and/or hermes-hub/api_keys.json, then restart the consuming service. Poe uses an API key from poe.com/api_key (POE_API_KEY).
- **API key: huggingface** — No key for huggingface. Add the key to ~/.hermes/.env (HF_TOKEN/HUGGINGFACE_API_KEY/HUGGINGFACEHUB_API_TOKEN) and/or hermes-hub/api_keys.json, then restart the consuming service.
- **API key: typingmind (WANTED INTEGRATION)** — [KATO WANTS THIS] typingmind integration has NO key. No key for typingmind. Add the key to ~/.hermes/.env (TYPINGMIND_API_KEY/TYPINGMIND_TOKEN) and/or hermes-hub/api_keys.json, then restart the consuming service. TypingMind is a frontend that needs YOUR provider keys (it has no key of its own) — point it at the live Hermes/REX endpoint or paste your Anthropic/OpenAI keys into TypingMind directly; set TYPINGMIND_API_KEY only if you run TypingMind's hosted sync.

> Perplexity is already keyed (good). **Poe** and **TypingMind** have no key anywhere. TypingMind is a frontend that uses *your* provider keys rather than one of its own — point it at the live Hermes/REX endpoint (once :8642 or :65001 is settled) or paste your Anthropic/OpenAI keys into it directly.

## Gateways / Tunnels

10 routes healthy. Broken/degraded:

- **hermes / desktop → :8787** — 502 (see HERMES FIX above).
- **rex-mcp.hermestigerclaw.com → :8766** — dead upstream; the Rex MCP Bridge isn't running. Start it or remove the `rex-mcp` ingress route until needed.
- **files / hud → :27223** — upstream is UP but returns **503** publicly (the HUD server rejects `/` or needs a host/path header / the fail-closed gate is returning 503). Verify `curl -I http://127.0.0.1:27223/` locally and confirm the DNS CNAME points at the tunnel.

## Auth / Passwords — healthy

Hub `auth.json` has `kato` (admin, salted hash — wildcard `*` perms, confirm password is strong) and `vlad` (viewer, expires 2026-06-10). `pin.json` present. HUD gate behaves (fail-closed). No fail-open/setup-mode gaps detected. Remember `chmod 600 ~/hermes-hub/auth.json` after any reset.

## Local Services (launchd)

37 healthy/running. **10 orphaned** (the plist runs a script that has been **deleted** — restore the file or `launchctl bootout` the job so it stops failing on every load):

- `~/Library/LaunchAgents/ai.hermes.watchdog.plist` — exit 127 = command not found: ProgramArguments runs /Users/mainsobhelper/.hermes/bin/hermes-watchdog which DOES NOT EXIST. Either restore the watchdog script or unload+remove this job (`launchctl bootout`).
- `~/Library/LaunchAgents/com.goj.imessage-poller.plist` — The plist runs /Users/mainsobhelper/.hermes/bin/goj_imessage_poller.py, which does NOT exist — orphaned job. Restore the file, or `launchctl bootout gui/$UID/com.goj.imessage-poller` + remove the plist so it stops trying on every load.
- `~/Library/LaunchAgents/com.goj.jarvis-daemon.plist` — The plist runs /Users/mainsobhelper/.hermes/bin/jarvis_daemon.py, which does NOT exist — orphaned job. Restore the file, or `launchctl bootout gui/$UID/com.goj.jarvis-daemon` + remove the plist so it stops trying on every load.
- `~/Library/LaunchAgents/com.goj.jarvis-morning.plist` — The plist runs /Users/mainsobhelper/.hermes/bin/jarvis_morning_brief.py, which does NOT exist — orphaned job. Restore the file, or `launchctl bootout gui/$UID/com.goj.jarvis-morning` + remove the plist so it stops trying on every load.
- `~/Library/LaunchAgents/com.goj.tigerclaw-backup.plist` — exit 127 = the backup script path in the plist does not exist. Inspect ~/Library/LaunchAgents/com.goj.tigerclaw-backup.plist ProgramArguments and restore the target or remove the job.
- `~/Library/LaunchAgents/com.hermes.backup.plist` — exit 127 = /Users/mainsobhelper/.hermes/bin/hermes-backup MISSING. Restore the backup script or remove the job.
- `~/Library/LaunchAgents/com.hermes.claus-watchman.plist` — exit 2 = /Users/mainsobhelper/.hermes/bin/claus_watchman.py MISSING (Phase-16 Claus agent watchman). Restore the script or remove the job.
- `~/Library/LaunchAgents/com.hermes.docker-guardian.plist` — exit 127 = /Users/mainsobhelper/.hermes/bin/docker-guardian MISSING. Restore or remove.
- `~/Library/LaunchAgents/com.hermes.memory-archive-daily.plist` — exit 127 = /Users/mainsobhelper/.hermes/bin/memory-archive MISSING. Restore the memory-archive script or remove this job (memory-archive-monthly may share it).
- `~/Library/LaunchAgents/com.hermes.memory-archive-monthly.plist` — The plist runs /Users/mainsobhelper/.hermes/bin/memory-archive, which does NOT exist — orphaned job. Restore the file, or `launchctl bootout gui/$UID/com.hermes.memory-archive-monthly` + remove the plist so it stops trying on every load.

**16 failing with a non-zero exit (script exists — inspect the log):** com.goj.imessage-watcher, com.goj.menuaudit, com.goj.rexcurriculum, com.goj.rexxiedaily, com.goj.scanprocessor, com.goj.scheduler.changes_routes, com.goj.scheduler.kitchen_sheets, com.goj.scheduler.morning_report, com.goj.scheduler.signin_driver_sheets, com.goj.shellcore-orchestrator, com.goj.transition-agent, com.hermes.python-resign, com.rex.daily-backup, com.rex.encrypted-backup, com.rex.rexxie-bot, com.tigerclaw.backup.

> Several of these are GOJ one-shot scheduled jobs (`scheduler.*`, `rexcurriculum`, `rexxiedaily`, `menuaudit`, `scanprocessor`) whose launchctl line shows a *stale* non-zero exit between runs — check each job's `StandardErrorPath` log before acting; some may have simply errored on their last scheduled run. `com.rex.*-backup` exit 2/3 and `com.hermes.python-resign` exit 2 are real and worth a log check.

## Stale References

16 stale references — ingress routes to dead local ports (:8787, :8766) and **launchd plists pointing at deleted scripts** (same set as the orphaned services above), plus a config-divergence check. Each is listed with its fix in the full output below. Tie-together: every orphaned plist + dead ingress route should either be restored or removed so the system map matches reality.

---

# Full audit output (verbatim, all 118 findings)

```text
==============================================================================
CC MISSING-LINK AUDIT  —  Tiger Claw / REX / Hermes / GOJ
READ-ONLY diagnosis. Hermes section first (owner priority).
==============================================================================

SUMMARY (findings per category):
  HERMES DEEP-DIVE (owner priority #1)       BROKEN/MISSING= 2  WARN= 2  STALE= 0  OK= 0
  GATEWAYS / TUNNELS                         BROKEN/MISSING= 3  WARN= 2  STALE= 0  OK=10
  API KEYS                                   BROKEN/MISSING= 3  WARN= 0  STALE= 0  OK=11
  AUTH / PASSWORDS                           BROKEN/MISSING= 0  WARN= 0  STALE= 0  OK= 3
  LOCAL SERVICES (launchd)                   BROKEN/MISSING=26  WARN= 0  STALE= 0  OK=37
  STALE REFERENCES                           BROKEN/MISSING= 0  WARN= 1  STALE=16  OK= 0

------------------------------------------------------------------------------
## HERMES DEEP-DIVE (owner priority #1)
------------------------------------------------------------------------------

[BROKEN] hermes.hermestigerclaw.com + desktop.hermestigerclaw.com are 502 (Hermes WebUI down)
    where : ~/.cloudflared/config.yml + hermestigerclaw.yml :: both -> http://127.0.0.1:8787
    fix   : ROOT CAUSE: nothing listens on :8787 and NO launchd job binds it. The Hermes WebUI on :8787 was a manually-started Python app (~/hermes-webui, HERMES_WEBUI_PORT in .env.local) / Docker container that exited and was never restarted, so cloudflared returns 502. The LIVE Hermes processes are MESSAGING gateways, not the browser chat UI: local gateway on :8088 + :65001 (ai.hermes.gateway) and cloud gateway on :3002 (ai.hermes.gateway-cloud) — both answer /health 200 but 404 on '/'. EXACT FIX (recommended, fastest, zero new services): edit BOTH cloudflared configs so hermes.hermestigerclaw.com AND desktop.hermestigerclaw.com point at a LIVE chat UI — LibreChat 'http://127.0.0.1:3080' (running 31h) is the best match; Open WebUI 'http://127.0.0.1:3000' is the alternate. Then run `cloudflared tunnel ingress validate` and reload the tunnel (brief blip). ALTERNATIVE (keep the dedicated WebUI): bring ~/hermes-webui back up so it binds :8787 (it has a Dockerfile + .venv + HERMES_WEBUI_PYTHON) and create a launchd job so it survives reboot — currently it is unmanaged, which is why it keeps disappearing.

[BROKEN] Hermes REST API :8642 is DOWN (breaks WhatsApp/zeroclaw bridge + any /v1/chat client)
    where : ~/.hermes/bin/zeroclaw-adapter (HERMES_URL=http://127.0.0.1:8642/v1/chat/completions)
    fix   : The zeroclaw-adapter (and any OpenAI-compatible client) POST to http://127.0.0.1:8642/v1/chat/completions, but nothing listens on :8642. The gateway's API server is governed by API_SERVER_ENABLED / API_SERVER_HOST / API_SERVER_PORT in ~/.hermes/.env — confirm API_SERVER_PORT matches what the adapter expects (8642) and that API_SERVER_ENABLED=true, then restart ai.hermes.gateway. The gateway currently exposes only :8088 and :65001; if the REST API is meant to be :65001, repoint the adapter's HERMES_URL to :65001 instead. This is WHY the WhatsApp path is dead end-to-end.

[WARN] com.hermes.zeroclaw-adapter logs websocket InvalidMessage / EOF handshake errors
    where : ~/.hermes/logs/zeroclaw-adapter.error.log (adapter listens ws on :18789)
    fix   : The adapter's websocket server on :18789 is up, but it receives non-websocket / truncated connections ('did not receive a valid HTTP request', EOF on handshake) — typically health-check probes or the kapso-whatsapp bridge connecting with the wrong URL/protocol. These are noisy but non-fatal. Real fix is upstream: once :8642 (Hermes REST API) is alive, the adapter can actually serve responses; until then every WhatsApp turn 500s. Point com.hermes.kapso-whatsapp at ws://127.0.0.1:18789 and silence bare-TCP health probes against that port.

[WARN] Hermes gateway: Signal adapter cannot reach signal-cli at :8085 (retry loop)
    where : ~/.hermes/logs/gateway.log (gateway.platforms.signal)
    fix   : signal-cli daemon on :8085 is not running, so the local gateway logs a reconnect loop every few minutes. Either start the signal-cli HTTP daemon on :8085, or disable the Signal platform in ~/.hermes/.env (SIGNAL_HTTP_URL/SIGNAL_ACCOUNT) if Signal is not in use. Cosmetic for chat, but it floods the gateway log and wastes cycles.

[INFO] Hermes live-port inventory (for the repoint decision)
    where : lsof TCP LISTEN snapshot
    fix   : :8787 WebUI=DOWN | :3002 cloud-gw=UP | :8088 local-gw=UP | :65001 local-gw-alt=UP | :8642 REST-API=DOWN | :3080 LibreChat=UP | :3000 OpenWebUI=UP. Repoint hermes/desktop -> :3080 (LibreChat) for an immediate working chat UI.

------------------------------------------------------------------------------
## GATEWAYS / TUNNELS
------------------------------------------------------------------------------

[BROKEN] Tunnel route hermes.hermestigerclaw.com -> dead upstream :8787
    where : config.yml & hermestigerclaw.yml :: hermes.hermestigerclaw.com -> http://127.0.0.1:8787
    fix   : DEAD upstream :8787 (Hermes WebUI). Nothing listens here and NO launchd job binds 8787 — it was a manually-started Python WebUI (see ~/hermes-webui/.env.local HERMES_WEBUI_PORT) / docker container that died. FIX (fastest): repoint hermes+desktop ingress to a LIVE chat UI — LibreChat :3080 (running) or Open WebUI :3000 — then `cloudflared tunnel ... ingress validate` + reload. ALT: revive the WebUI (~/hermes-webui) so it binds :8787, then leave ingress as-is.

[BROKEN] Tunnel route desktop.hermestigerclaw.com -> dead upstream :8787
    where : config.yml & hermestigerclaw.yml :: desktop.hermestigerclaw.com -> http://127.0.0.1:8787
    fix   : DEAD upstream :8787 (Hermes WebUI). Nothing listens here and NO launchd job binds 8787 — it was a manually-started Python WebUI (see ~/hermes-webui/.env.local HERMES_WEBUI_PORT) / docker container that died. FIX (fastest): repoint hermes+desktop ingress to a LIVE chat UI — LibreChat :3080 (running) or Open WebUI :3000 — then `cloudflared tunnel ... ingress validate` + reload. ALT: revive the WebUI (~/hermes-webui) so it binds :8787, then leave ingress as-is.

[BROKEN] Tunnel route rex-mcp.hermestigerclaw.com -> dead upstream :8766
    where : config.yml & hermestigerclaw.yml :: rex-mcp.hermestigerclaw.com -> http://localhost:8766
    fix   : Local upstream :8766 is DEAD (nothing listening). Either start the service that should bind :8766, or repoint this ingress to a live port. 

[WARN] Tunnel route files.hermestigerclaw.com unhealthy
    where : config.yml & hermestigerclaw.yml :: files.hermestigerclaw.com -> http://127.0.0.1:27223
    fix   : Public probe returned HTTP 503. Upstream is alive on :27223; likely the app rejects '/' or needs a path/host header. Verify the service answers locally (`curl -I http://127.0.0.1:27223/`), and confirm cloudflared is running and the DNS CNAME for files.hermestigerclaw.com points at the tunnel.

[WARN] Tunnel route hud.hermestigerclaw.com unhealthy
    where : config.yml & hermestigerclaw.yml :: hud.hermestigerclaw.com -> http://127.0.0.1:27223
    fix   : Public probe returned HTTP 503. Upstream is alive on :27223; likely the app rejects '/' or needs a path/host header. Verify the service answers locally (`curl -I http://127.0.0.1:27223/`), and confirm cloudflared is running and the DNS CNAME for hud.hermestigerclaw.com points at the tunnel.

[OK] Tunnel route hermestigerclaw.com -> :3003
    where : config.yml & hermestigerclaw.yml :: hermestigerclaw.com -> http://127.0.0.1:3003
    fix   : Healthy (upstream alive, public HTTP 200). No action.

[OK] Tunnel route www.hermestigerclaw.com -> :3003
    where : config.yml & hermestigerclaw.yml :: www.hermestigerclaw.com -> http://127.0.0.1:3003
    fix   : Healthy (upstream alive, public HTTP 200). No action.

[OK] Tunnel route cloud.hermestigerclaw.com -> :3002
    where : config.yml & hermestigerclaw.yml :: cloud.hermestigerclaw.com -> http://127.0.0.1:3002
    fix   : Healthy (upstream alive, public HTTP 404). No action.

[OK] Tunnel route ui.hermestigerclaw.com -> :3000
    where : config.yml & hermestigerclaw.yml :: ui.hermestigerclaw.com -> http://127.0.0.1:3000
    fix   : Healthy (upstream alive, public HTTP 200). No action.

[OK] Tunnel route chat.hermestigerclaw.com -> :3080
    where : config.yml & hermestigerclaw.yml :: chat.hermestigerclaw.com -> http://127.0.0.1:3080
    fix   : Healthy (upstream alive, public HTTP 200). No action.

[OK] Tunnel route rex.hermestigerclaw.com -> :8000
    where : config.yml & hermestigerclaw.yml :: rex.hermestigerclaw.com -> http://127.0.0.1:8000
    fix   : Healthy (upstream alive, public HTTP 200). No action.

[OK] Tunnel route workspace.hermestigerclaw.com -> :9000
    where : config.yml & hermestigerclaw.yml :: workspace.hermestigerclaw.com -> http://127.0.0.1:9000
    fix   : Healthy (upstream alive, public HTTP 200). No action.

[OK] Tunnel route hub.hermestigerclaw.com -> :9000
    where : config.yml & hermestigerclaw.yml :: hub.hermestigerclaw.com -> http://127.0.0.1:9000
    fix   : Healthy (upstream alive, public HTTP 200). No action.

[OK] Tunnel route jarvis.hermestigerclaw.com -> :9000
    where : config.yml & hermestigerclaw.yml :: jarvis.hermestigerclaw.com -> http://127.0.0.1:9000
    fix   : Healthy (upstream alive, public HTTP 200). No action.

[OK] Tunnel route hermestigerclaw.com -> :8089
    where : hermestigerclaw.yml :: hermestigerclaw.com path=/victoria -> http://localhost:8089
    fix   : Healthy (upstream alive, public HTTP 404). No action.

------------------------------------------------------------------------------
## API KEYS
------------------------------------------------------------------------------

[MISSING] API key: poe (WANTED INTEGRATION)
    where : env files + api_keys.json + REX status
    fix   : [KATO WANTS THIS] poe integration has NO key. No key for poe. Add the key to ~/.hermes/.env (POE_API_KEY/POE_TOKEN) and/or hermes-hub/api_keys.json, then restart the consuming service. Poe uses an API key from poe.com/api_key (POE_API_KEY).

[MISSING] API key: huggingface
    where : env files + api_keys.json + REX status
    fix   : No key for huggingface. Add the key to ~/.hermes/.env (HF_TOKEN/HUGGINGFACE_API_KEY/HUGGINGFACEHUB_API_TOKEN) and/or hermes-hub/api_keys.json, then restart the consuming service.

[MISSING] API key: typingmind (WANTED INTEGRATION)
    where : env files + api_keys.json + REX status
    fix   : [KATO WANTS THIS] typingmind integration has NO key. No key for typingmind. Add the key to ~/.hermes/.env (TYPINGMIND_API_KEY/TYPINGMIND_TOKEN) and/or hermes-hub/api_keys.json, then restart the consuming service. TypingMind is a frontend that needs YOUR provider keys (it has no key of its own) — point it at the live Hermes/REX endpoint or paste your Anthropic/OpenAI keys into TypingMind directly; set TYPINGMIND_API_KEY only if you run TypingMind's hosted sync.

[OK] REX backend /api/keys/status reachable
    where : http://127.0.0.1:8000/api/keys/status
    fix   : Reported: {"anthropic": true, "openai": true, "google": false, "xai": true, "perplexity": true, "librechat": false}

[OK] API key: anthropic
    where : REX /api/keys/status
    fix   : CONFIGURED via REX /api/keys/status. No action.

[OK] API key: openai
    where : REX /api/keys/status
    fix   : CONFIGURED via REX /api/keys/status. No action.

[OK] API key: deepseek
    where : env (DEEPSEEK_API_KEY)
    fix   : CONFIGURED via env (DEEPSEEK_API_KEY). No action.

[OK] API key: perplexity
    where : REX /api/keys/status
    fix   : CONFIGURED via REX /api/keys/status. No action.

[OK] API key: retell
    where : env (RETELL_API_KEY)
    fix   : CONFIGURED via env (RETELL_API_KEY). No action.

[OK] API key: twilio
    where : env (TWILIO_AUTH_TOKEN)
    fix   : CONFIGURED via env (TWILIO_AUTH_TOKEN). No action.

[OK] API key: elevenlabs
    where : env (ELEVENLABS_API_KEY)
    fix   : CONFIGURED via env (ELEVENLABS_API_KEY). No action.

[OK] API key: google
    where : env (GOOGLE_API_KEY)
    fix   : CONFIGURED via env (GOOGLE_API_KEY). No action.

[OK] API key: xai
    where : REX /api/keys/status
    fix   : CONFIGURED via REX /api/keys/status. No action.

[OK] API key: openrouter
    where : env (OPENROUTER_API_KEY)
    fix   : CONFIGURED via env (OPENROUTER_API_KEY). No action.

------------------------------------------------------------------------------
## AUTH / PASSWORDS
------------------------------------------------------------------------------

[INFO] hub user 'kato' credential set
    where : /Users/mainsobhelper/hermes-hub/auth.json
    fix   : role=admin perms=['*']. Wildcard '*' = full admin; confirm this is intended and the password is strong.

[OK] hub user 'vlad' credential set
    where : /Users/mainsobhelper/hermes-hub/auth.json
    fix   : role=viewer perms=['view_dashboard'] expires_at=2026-06-10T18:50:41.826154+00:00. OK.

[OK] hub pin.json
    where : /Users/mainsobhelper/hermes-hub/pin.json
    fix   : Present (PIN lock configured).

[OK] HUD gate hud.hermestigerclaw.com (:27223)
    where : ~/.cloudflared :: hud -> 127.0.0.1:27223
    fix   : Public HTTP 503. 401/403 = gate working (fail-closed Basic auth as designed). If 200 with no prompt, the gate is OPEN — set the site password via ~/hermes-hub set-site-password and confirm fail-closed.

------------------------------------------------------------------------------
## LOCAL SERVICES (launchd)
------------------------------------------------------------------------------

[BROKEN] launchd job com.goj.imessage-watcher failing (exit 1)
    where : ~/Library/LaunchAgents/com.goj.imessage-watcher.plist (pid=-)
    fix   : exit 1: job failed on last run. Inspect its StandardErrorPath log and ProgramArguments (/opt/homebrew/bin/python3.11 /Users/mainsobhelper/Documents/goj files/imessage_watcher.py); fix the underlying script or dependency. (Note: one-shot scheduled jobs may show a stale non-zero exit between runs — confirm against the log before acting.)

[BROKEN] launchd job com.goj.menuaudit failing (exit 1)
    where : ~/Library/LaunchAgents/com.goj.menuaudit.plist (pid=-)
    fix   : exit 1: job failed on last run. Inspect its StandardErrorPath log and ProgramArguments (/bin/bash -c source /Users/mainsobhelper/Desktop/REX/.venv/bin/activate && python3 /Users/mainsobhelper/Desktop/REX/goj_menu_audit.py); fix the underlying script or dependency. (Note: one-shot scheduled jobs may show a stale non-zero exit between runs — confirm against the log before acting.)

[BROKEN] launchd job com.goj.rexcurriculum failing (exit 1)
    where : ~/Library/LaunchAgents/com.goj.rexcurriculum.plist (pid=-)
    fix   : exit 1: job failed on last run. Inspect its StandardErrorPath log and ProgramArguments (/bin/bash -c source /Users/mainsobhelper/Desktop/REX/.venv/bin/activate && python3 /Users/mainsobhelper/Desktop/REX/rex_daily_curriculum.py); fix the underlying script or dependency. (Note: one-shot scheduled jobs may show a stale non-zero exit between runs — confirm against the log before acting.)

[BROKEN] launchd job com.goj.rexxiedaily failing (exit 1)
    where : ~/Library/LaunchAgents/com.goj.rexxiedaily.plist (pid=-)
    fix   : exit 1: job failed on last run. Inspect its StandardErrorPath log and ProgramArguments (/bin/bash -c source /Users/mainsobhelper/Desktop/REX/.venv/bin/activate && python3 /Users/mainsobhelper/Desktop/REX/rex_rexxie_daily.py); fix the underlying script or dependency. (Note: one-shot scheduled jobs may show a stale non-zero exit between runs — confirm against the log before acting.)

[BROKEN] launchd job com.goj.scanprocessor failing (exit 1)
    where : ~/Library/LaunchAgents/com.goj.scanprocessor.plist (pid=-)
    fix   : exit 1: job failed on last run. Inspect its StandardErrorPath log and ProgramArguments (/bin/bash -c SINCE=$(date -v-1d +%Y-%m-%d) && source /Users/mainsobhelper/Desktop/REX/.venv/bin/activate && python3 "/Users/mainsobhelper/Documents/goj files/goj_scan_processor.py" --since "$SINCE" --limit 100); fix the underlying script or dependency. (Note: one-shot scheduled jobs may show a stale non-zero exit between runs — confirm against the log before acting.)

[BROKEN] launchd job com.goj.scheduler.changes_routes failing (exit 1)
    where : ~/Library/LaunchAgents/com.goj.scheduler.changes_routes.plist (pid=-)
    fix   : exit 1: job failed on last run. Inspect its StandardErrorPath log and ProgramArguments (/Users/mainsobhelper/Desktop/REX/.venv/bin/python3 /Users/mainsobhelper/Desktop/REX/goj_daily_scheduler.py --job changes_routes); fix the underlying script or dependency. (Note: one-shot scheduled jobs may show a stale non-zero exit between runs — confirm against the log before acting.)

[BROKEN] launchd job com.goj.scheduler.kitchen_sheets failing (exit 1)
    where : ~/Library/LaunchAgents/com.goj.scheduler.kitchen_sheets.plist (pid=-)
    fix   : exit 1: job failed on last run. Inspect its StandardErrorPath log and ProgramArguments (/Users/mainsobhelper/Desktop/REX/.venv/bin/python3 /Users/mainsobhelper/Desktop/REX/goj_daily_scheduler.py --job kitchen_sheets); fix the underlying script or dependency. (Note: one-shot scheduled jobs may show a stale non-zero exit between runs — confirm against the log before acting.)

[BROKEN] launchd job com.goj.scheduler.morning_report failing (exit 1)
    where : ~/Library/LaunchAgents/com.goj.scheduler.morning_report.plist (pid=-)
    fix   : exit 1: job failed on last run. Inspect its StandardErrorPath log and ProgramArguments (/Users/mainsobhelper/Desktop/REX/.venv/bin/python3 /Users/mainsobhelper/Desktop/REX/goj_daily_scheduler.py --job morning_report); fix the underlying script or dependency. (Note: one-shot scheduled jobs may show a stale non-zero exit between runs — confirm against the log before acting.)

[BROKEN] launchd job com.goj.scheduler.signin_driver_sheets failing (exit 1)
    where : ~/Library/LaunchAgents/com.goj.scheduler.signin_driver_sheets.plist (pid=-)
    fix   : exit 1: job failed on last run. Inspect its StandardErrorPath log and ProgramArguments (/Users/mainsobhelper/Desktop/REX/.venv/bin/python3 /Users/mainsobhelper/Desktop/REX/goj_daily_scheduler.py --job signin_driver_sheets); fix the underlying script or dependency. (Note: one-shot scheduled jobs may show a stale non-zero exit between runs — confirm against the log before acting.)

[BROKEN] launchd job com.goj.shellcore-orchestrator failing (exit 78)
    where : ~/Library/LaunchAgents/com.goj.shellcore-orchestrator.plist (pid=-)
    fix   : exit 78: job failed on last run. Inspect its StandardErrorPath log and ProgramArguments (/Users/mainsobhelper/Documents/Claude/Projects/Multi agent build/.venv/bin/python -m uvicorn dashboard.orchestrator:app --host 127.0.0.1 --port 8081 --log-level warning); fix the underlying script or dependency. (Note: one-shot scheduled jobs may show a stale non-zero exit between runs — confirm against the log before acting.)

[BROKEN] launchd job com.goj.transition-agent failing (exit 2)
    where : ~/Library/LaunchAgents/com.goj.transition-agent.plist (pid=-)
    fix   : exit 2: job failed on last run. Inspect its StandardErrorPath log and ProgramArguments (/opt/homebrew/opt/python@3.14/bin/python3.14 /Users/mainsobhelper/Desktop/REX/transition_supervisor.py full); fix the underlying script or dependency. (Note: one-shot scheduled jobs may show a stale non-zero exit between runs — confirm against the log before acting.)

[BROKEN] launchd job com.hermes.python-resign failing (exit 2)
    where : ~/Library/LaunchAgents/com.hermes.python-resign.plist (pid=-)
    fix   : exit 2 = /Users/mainsobhelper/.hermes-cloud/scripts/python_resign_after_brew.py MISSING. This re-signs Python after a brew upgrade; restore it or remove the job.

[BROKEN] launchd job com.rex.daily-backup failing (exit 3)
    where : ~/Library/LaunchAgents/com.rex.daily-backup.plist (pid=-)
    fix   : exit 3: job failed on last run. Inspect its StandardErrorPath log and ProgramArguments (/bin/bash /Users/mainsobhelper/.rex-scripts/rex-backup.sh); fix the underlying script or dependency. (Note: one-shot scheduled jobs may show a stale non-zero exit between runs — confirm against the log before acting.)

[BROKEN] launchd job com.rex.encrypted-backup failing (exit 2)
    where : ~/Library/LaunchAgents/com.rex.encrypted-backup.plist (pid=-)
    fix   : exit 2: job failed on last run. Inspect its StandardErrorPath log and ProgramArguments (/bin/bash /Users/mainsobhelper/.rex-scripts/rex-encrypted-backup.sh); fix the underlying script or dependency. (Note: one-shot scheduled jobs may show a stale non-zero exit between runs — confirm against the log before acting.)

[BROKEN] launchd job com.rex.rexxie-bot failing (exit 78)
    where : ~/Library/LaunchAgents/com.rex.rexxie-bot.plist (pid=-)
    fix   : exit 78: job failed on last run. Inspect its StandardErrorPath log and ProgramArguments (/Users/mainsobhelper/Desktop/REX/.venv/bin/python /Users/mainsobhelper/Desktop/REX/rex_rexxie_telegram_bot.py); fix the underlying script or dependency. (Note: one-shot scheduled jobs may show a stale non-zero exit between runs — confirm against the log before acting.)

[BROKEN] launchd job com.tigerclaw.backup failing (exit 1)
    where : ~/Library/LaunchAgents/com.tigerclaw.backup.plist (pid=-)
    fix   : exit 1: job failed on last run. Inspect its StandardErrorPath log and ProgramArguments (/bin/bash /Users/mainsobhelper/.hermes/scripts/nightly_backup.sh); fix the underlying script or dependency. (Note: one-shot scheduled jobs may show a stale non-zero exit between runs — confirm against the log before acting.)

[MISSING] launchd job ai.hermes.watchdog — orphaned (target script missing)
    where : ~/Library/LaunchAgents/ai.hermes.watchdog.plist (pid=-, last_exit=127, target=/Users/mainsobhelper/.hermes/bin/hermes-watchdog)
    fix   : exit 127 = command not found: ProgramArguments runs /Users/mainsobhelper/.hermes/bin/hermes-watchdog which DOES NOT EXIST. Either restore the watchdog script or unload+remove this job (`launchctl bootout`).

[MISSING] launchd job com.goj.imessage-poller — orphaned (target script missing)
    where : ~/Library/LaunchAgents/com.goj.imessage-poller.plist (pid=-, last_exit=2, target=/Users/mainsobhelper/.hermes/bin/goj_imessage_poller.py)
    fix   : The plist runs /Users/mainsobhelper/.hermes/bin/goj_imessage_poller.py, which does NOT exist — orphaned job. Restore the file, or `launchctl bootout gui/$UID/com.goj.imessage-poller` + remove the plist so it stops trying on every load.

[MISSING] launchd job com.goj.jarvis-daemon — orphaned (target script missing)
    where : ~/Library/LaunchAgents/com.goj.jarvis-daemon.plist (pid=-, last_exit=0, target=/Users/mainsobhelper/.hermes/bin/jarvis_daemon.py)
    fix   : The plist runs /Users/mainsobhelper/.hermes/bin/jarvis_daemon.py, which does NOT exist — orphaned job. Restore the file, or `launchctl bootout gui/$UID/com.goj.jarvis-daemon` + remove the plist so it stops trying on every load.

[MISSING] launchd job com.goj.jarvis-morning — orphaned (target script missing)
    where : ~/Library/LaunchAgents/com.goj.jarvis-morning.plist (pid=-, last_exit=2, target=/Users/mainsobhelper/.hermes/bin/jarvis_morning_brief.py)
    fix   : The plist runs /Users/mainsobhelper/.hermes/bin/jarvis_morning_brief.py, which does NOT exist — orphaned job. Restore the file, or `launchctl bootout gui/$UID/com.goj.jarvis-morning` + remove the plist so it stops trying on every load.

[MISSING] launchd job com.goj.tigerclaw-backup — orphaned (target script missing)
    where : ~/Library/LaunchAgents/com.goj.tigerclaw-backup.plist (pid=-, last_exit=127, target=/Users/mainsobhelper/.hermes/bin/tigerclaw-backup)
    fix   : exit 127 = the backup script path in the plist does not exist. Inspect ~/Library/LaunchAgents/com.goj.tigerclaw-backup.plist ProgramArguments and restore the target or remove the job.

[MISSING] launchd job com.hermes.backup — orphaned (target script missing)
    where : ~/Library/LaunchAgents/com.hermes.backup.plist (pid=-, last_exit=127, target=/Users/mainsobhelper/.hermes/bin/hermes-backup)
    fix   : exit 127 = /Users/mainsobhelper/.hermes/bin/hermes-backup MISSING. Restore the backup script or remove the job.

[MISSING] launchd job com.hermes.claus-watchman — orphaned (target script missing)
    where : ~/Library/LaunchAgents/com.hermes.claus-watchman.plist (pid=-, last_exit=2, target=/Users/mainsobhelper/.hermes/bin/claus_watchman.py)
    fix   : exit 2 = /Users/mainsobhelper/.hermes/bin/claus_watchman.py MISSING (Phase-16 Claus agent watchman). Restore the script or remove the job.

[MISSING] launchd job com.hermes.docker-guardian — orphaned (target script missing)
    where : ~/Library/LaunchAgents/com.hermes.docker-guardian.plist (pid=-, last_exit=127, target=/Users/mainsobhelper/.hermes/bin/docker-guardian)
    fix   : exit 127 = /Users/mainsobhelper/.hermes/bin/docker-guardian MISSING. Restore or remove.

[MISSING] launchd job com.hermes.memory-archive-daily — orphaned (target script missing)
    where : ~/Library/LaunchAgents/com.hermes.memory-archive-daily.plist (pid=-, last_exit=127, target=/Users/mainsobhelper/.hermes/bin/memory-archive)
    fix   : exit 127 = /Users/mainsobhelper/.hermes/bin/memory-archive MISSING. Restore the memory-archive script or remove this job (memory-archive-monthly may share it).

[MISSING] launchd job com.hermes.memory-archive-monthly — orphaned (target script missing)
    where : ~/Library/LaunchAgents/com.hermes.memory-archive-monthly.plist (pid=-, last_exit=0, target=/Users/mainsobhelper/.hermes/bin/memory-archive)
    fix   : The plist runs /Users/mainsobhelper/.hermes/bin/memory-archive, which does NOT exist — orphaned job. Restore the file, or `launchctl bootout gui/$UID/com.hermes.memory-archive-monthly` + remove the plist so it stops trying on every load.

[OK] launchd job ai.hermes.dashboard
    where : pid=24920 last_exit=-15
    fix   : Running (PID 24920). (last_exit=-15; that's the PRIOR exit — typically a restart/SIGTERM artifact, not a current failure) No action.

[OK] launchd job ai.hermes.gateway
    where : pid=27087 last_exit=0
    fix   : Running (PID 27087). No action.

[OK] launchd job ai.hermes.gateway-cloud
    where : pid=58496 last_exit=0
    fix   : Running (PID 58496). No action.

[OK] launchd job ai.hermes.signal
    where : pid=- last_exit=0
    fix   : Clean last exit (idle scheduled job or cleanly stopped). No action.

[OK] launchd job ai.openwebui.hermes
    where : pid=86130 last_exit=0
    fix   : Running (PID 86130). No action.

[OK] launchd job com.goj.datarex
    where : pid=58540 last_exit=0
    fix   : Running (PID 58540). No action.

[OK] launchd job com.goj.drive-ingest
    where : pid=46309 last_exit=-15
    fix   : Running (PID 46309). (last_exit=-15; that's the PRIOR exit — typically a restart/SIGTERM artifact, not a current failure) No action.

[OK] launchd job com.goj.hub
    where : pid=21364 last_exit=0
    fix   : Running (PID 21364). No action.

[OK] launchd job com.goj.n8n
    where : pid=58665 last_exit=0
    fix   : Running (PID 58665). No action.

[OK] launchd job com.goj.saturdayreview
    where : pid=- last_exit=0
    fix   : Clean last exit (idle scheduled job or cleanly stopped). No action.

[OK] launchd job com.goj.scheduler.missing_menus_fri
    where : pid=- last_exit=0
    fix   : Clean last exit (idle scheduled job or cleanly stopped). No action.

[OK] launchd job com.goj.scheduler.weekly_email_fri
    where : pid=- last_exit=0
    fix   : Clean last exit (idle scheduled job or cleanly stopped). No action.

[OK] launchd job com.goj.tigerclaw-app
    where : pid=58697 last_exit=0
    fix   : Running (PID 58697). No action.

[OK] launchd job com.goj.victoria-caller
    where : pid=- last_exit=0
    fix   : Clean last exit (idle scheduled job or cleanly stopped). No action.

[OK] launchd job com.hermes.alerter
    where : pid=- last_exit=0
    fix   : Clean last exit (idle scheduled job or cleanly stopped). No action.

[OK] launchd job com.hermes.deck
    where : pid=84996 last_exit=0
    fix   : Running (PID 84996). No action.

[OK] launchd job com.hermes.kapso-whatsapp
    where : pid=60146 last_exit=1
    fix   : Running (PID 60146). (last_exit=1; that's the PRIOR exit — typically a restart/SIGTERM artifact, not a current failure) No action. Note: exit 1 = /Users/mainsobhelper/.local/bin/kapso-whatsapp-bridge runs but fails — it depends on the Hermes REST API (:8642) which is DOWN, and on the zeroclaw-adapter ws (:18789). Fix :8642 first (see HERMES section), then this should connect.

[OK] launchd job com.hermes.landing
    where : pid=1582 last_exit=0
    fix   : Running (PID 1582). No action.

[OK] launchd job com.hermes.portal
    where : pid=58964 last_exit=0
    fix   : Running (PID 58964). No action.

[OK] launchd job com.hermes.show
    where : pid=22921 last_exit=0
    fix   : Running (PID 22921). No action.

[OK] launchd job com.hermes.zeroclaw-adapter
    where : pid=60169 last_exit=-15
    fix   : Running (PID 60169). (last_exit=-15; that's the PRIOR exit — typically a restart/SIGTERM artifact, not a current failure) No action. Note: Running (PID present) but logs websocket handshake errors — see HERMES section. Non-fatal; real fix is bringing up the Hermes REST API on :8642.

[OK] launchd job com.rex.backend
    where : pid=84418 last_exit=-15
    fix   : Running (PID 84418). (last_exit=-15; that's the PRIOR exit — typically a restart/SIGTERM artifact, not a current failure) No action.

[OK] launchd job com.rex.evening-report
    where : pid=- last_exit=0
    fix   : Clean last exit (idle scheduled job or cleanly stopped). No action.

[OK] launchd job com.rex.guardian-daily
    where : pid=- last_exit=0
    fix   : Clean last exit (idle scheduled job or cleanly stopped). No action.

[OK] launchd job com.rex.infra-sentinel
    where : pid=25110 last_exit=-15
    fix   : Running (PID 25110). (last_exit=-15; that's the PRIOR exit — typically a restart/SIGTERM artifact, not a current failure) No action.

[OK] launchd job com.rex.nextday-preview
    where : pid=- last_exit=0
    fix   : Clean last exit (idle scheduled job or cleanly stopped). No action.

[OK] launchd job com.rex.paperless
    where : pid=- last_exit=0
    fix   : Clean last exit (idle scheduled job or cleanly stopped). No action.

[OK] launchd job com.rex.proximity
    where : pid=22949 last_exit=0
    fix   : Running (PID 22949). No action.

[OK] launchd job com.rex.queue-processor
    where : pid=- last_exit=0
    fix   : Clean last exit (idle scheduled job or cleanly stopped). No action.

[OK] launchd job com.rex.reminders
    where : pid=- last_exit=0
    fix   : Clean last exit (idle scheduled job or cleanly stopped). No action.

[OK] launchd job com.rex.telegram-bot
    where : pid=1605 last_exit=0
    fix   : Running (PID 1605). No action.

[OK] launchd job com.tigerclaw.api
    where : pid=58596 last_exit=0
    fix   : Running (PID 58596). No action.

[OK] launchd job com.tigerclaw.hammerspoon
    where : pid=1583 last_exit=0
    fix   : Running (PID 1583). No action.

[OK] launchd job com.tigerclaw.hotcorner
    where : pid=1596 last_exit=0
    fix   : Running (PID 1596). No action.

[OK] launchd job com.tigerclaw.hudsite
    where : pid=1552 last_exit=0
    fix   : Running (PID 1552). No action.

[OK] launchd job com.tigerclaw.idle-monitor
    where : pid=- last_exit=0
    fix   : Clean last exit (idle scheduled job or cleanly stopped). No action.

[OK] launchd job com.tigerclaw.screensaver
    where : pid=27649 last_exit=0
    fix   : Running (PID 27649). No action.

------------------------------------------------------------------------------
## STALE REFERENCES
------------------------------------------------------------------------------

[STALE] Stale ingress target :8766 (no listener)
    where : ~/.cloudflared/config.yml / hermestigerclaw.yml
    fix   : One or more ingress hostnames route to 127.0.0.1:8766 but nothing listens there. Repoint to a live port or delete the route.

[STALE] Stale ingress target :8787 (no listener)
    where : ~/.cloudflared/config.yml / hermestigerclaw.yml
    fix   : One or more ingress hostnames route to 127.0.0.1:8787 but nothing listens there. Repoint to a live port or delete the route.

[STALE] rex-mcp.hermestigerclaw.com -> :8766 (Rex MCP Bridge) has no listener
    where : ~/.cloudflared :: rex-mcp -> http://localhost:8766
    fix   : The Rex MCP Bridge on :8766 is not running. Start the MCP bridge or remove the rex-mcp ingress route until it is needed.

[STALE] launchd plist references missing file: /Users/mainsobhelper/.hermes/bin/memory-archive
    where : ~/Library/LaunchAgents/com.hermes.memory-archive-monthly.plist
    fix   : The job com.hermes.memory-archive-monthly runs /Users/mainsobhelper/.hermes/bin/memory-archive, which does not exist. Restore the file or remove/disable the plist so it stops failing on every load.

[STALE] launchd plist references missing file: /Users/mainsobhelper/.hermes/bin/jarvis_daemon.py
    where : ~/Library/LaunchAgents/com.goj.jarvis-daemon.plist
    fix   : The job com.goj.jarvis-daemon runs /Users/mainsobhelper/.hermes/bin/jarvis_daemon.py, which does not exist. Restore the file or remove/disable the plist so it stops failing on every load.

[STALE] launchd plist references missing file: /Users/mainsobhelper/.hermes-cloud/scripts/python_resign_after_brew.py
    where : ~/Library/LaunchAgents/com.hermes.python-resign.plist
    fix   : The job com.hermes.python-resign runs /Users/mainsobhelper/.hermes-cloud/scripts/python_resign_after_brew.py, which does not exist. Restore the file or remove/disable the plist so it stops failing on every load.

[STALE] launchd plist references missing file: /Users/mainsobhelper/.hermes/bin/memory-archive
    where : ~/Library/LaunchAgents/com.hermes.memory-archive-daily.plist
    fix   : The job com.hermes.memory-archive-daily runs /Users/mainsobhelper/.hermes/bin/memory-archive, which does not exist. Restore the file or remove/disable the plist so it stops failing on every load.

[STALE] launchd plist references missing file: /Users/mainsobhelper/.hermes/bin/claus_watchman.py
    where : ~/Library/LaunchAgents/com.hermes.claus-watchman.plist
    fix   : The job com.hermes.claus-watchman runs /Users/mainsobhelper/.hermes/bin/claus_watchman.py, which does not exist. Restore the file or remove/disable the plist so it stops failing on every load.

[STALE] launchd plist references missing file: /Users/mainsobhelper/Desktop/REX/.venv/bin/python
    where : ~/Library/LaunchAgents/com.rex.rexxie-bot.plist
    fix   : The job com.rex.rexxie-bot runs /Users/mainsobhelper/Desktop/REX/.venv/bin/python, which does not exist. Restore the file or remove/disable the plist so it stops failing on every load.

[STALE] launchd plist references missing file: /Users/mainsobhelper/Documents/Claude/Projects/Multi agent build/.venv/bin/python
    where : ~/Library/LaunchAgents/com.goj.shellcore-orchestrator.plist
    fix   : The job com.goj.shellcore-orchestrator runs /Users/mainsobhelper/Documents/Claude/Projects/Multi agent build/.venv/bin/python, which does not exist. Restore the file or remove/disable the plist so it stops failing on every load.

[STALE] launchd plist references missing file: /Users/mainsobhelper/.hermes/bin/jarvis_morning_brief.py
    where : ~/Library/LaunchAgents/com.goj.jarvis-morning.plist
    fix   : The job com.goj.jarvis-morning runs /Users/mainsobhelper/.hermes/bin/jarvis_morning_brief.py, which does not exist. Restore the file or remove/disable the plist so it stops failing on every load.

[STALE] launchd plist references missing file: /Users/mainsobhelper/.hermes/bin/goj_imessage_poller.py
    where : ~/Library/LaunchAgents/com.goj.imessage-poller.plist
    fix   : The job com.goj.imessage-poller runs /Users/mainsobhelper/.hermes/bin/goj_imessage_poller.py, which does not exist. Restore the file or remove/disable the plist so it stops failing on every load.

[STALE] launchd plist references missing file: /Users/mainsobhelper/.hermes/bin/hermes-watchdog
    where : ~/Library/LaunchAgents/ai.hermes.watchdog.plist
    fix   : The job ai.hermes.watchdog runs /Users/mainsobhelper/.hermes/bin/hermes-watchdog, which does not exist. Restore the file or remove/disable the plist so it stops failing on every load.

[STALE] launchd plist references missing file: /Users/mainsobhelper/.hermes/bin/tigerclaw-backup
    where : ~/Library/LaunchAgents/com.goj.tigerclaw-backup.plist
    fix   : The job com.goj.tigerclaw-backup runs /Users/mainsobhelper/.hermes/bin/tigerclaw-backup, which does not exist. Restore the file or remove/disable the plist so it stops failing on every load.

[STALE] launchd plist references missing file: /Users/mainsobhelper/.hermes/bin/hermes-backup
    where : ~/Library/LaunchAgents/com.hermes.backup.plist
    fix   : The job com.hermes.backup runs /Users/mainsobhelper/.hermes/bin/hermes-backup, which does not exist. Restore the file or remove/disable the plist so it stops failing on every load.

[STALE] launchd plist references missing file: /Users/mainsobhelper/.hermes/bin/docker-guardian
    where : ~/Library/LaunchAgents/com.hermes.docker-guardian.plist
    fix   : The job com.hermes.docker-guardian runs /Users/mainsobhelper/.hermes/bin/docker-guardian, which does not exist. Restore the file or remove/disable the plist so it stops failing on every load.

[WARN] cloudflared config divergence for hermestigerclaw.com
    where : config.yml vs hermestigerclaw.yml
    fix   : The two tunnel configs route hermestigerclaw.com differently (config.yml=['http://127.0.0.1:3003'] vs hermestigerclaw.yml=['http://127.0.0.1:3003', 'http://localhost:8089']). Determine which file the running cloudflared actually loads and delete or reconcile the other to avoid confusion.

==============================================================================
```
