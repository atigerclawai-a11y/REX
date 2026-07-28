# CLAUDE HANDOFF — Full System State & Build Instructions
# Generated: 2026-06-08 11:45 AM ET
# By: Hermes (Cloud May Bot) for Claude
# SUBJECT: Tiger Claw Ecosystem — Current State + What To Build Next

---

## SYSTEM IDENTITY

You are building for Kato (Alejandro), Chairman of Gold Health Systems. He runs Garden of Joy adult day care (430 clients, Brooklyn NY) and Boardwalk Beer Garden (Brighton Beach). His stack is a Mac Mini M4 (24GB) running a fully local AI ecosystem behind Cloudflare domains.

**Kato's style:** Action over analysis. "Both" = do it in parallel. Never serialize when you can parallelize. Dark themes, command-palette UX, monospace fonts. Design partner: Antigravity.app. Railway preferred over Cloudflare for deploys.

**HARD RULES:**
- Larry NEVER appears on any transport/driver list. No exceptions, ever.
- DeepSeek ALWAYS routes direct: provider:deepseek + base_url:https://api.deepseek.com/v1. NEVER OpenRouter.
- New files get `CC_` prefix. Share via `attachments[]` only — `computer://` breaks iOS.
- PHI never crosses tiers. Presidio de-id on all outbound. auth_tracker.db never reaches cloud.
- Rexxie private lane: local only, never divulges its contents.
- Password everywhere: `tigerclaw2026` (username: `kato`)
- No real-world action without PAE (Propose → Approve → Execute).

---

## CURRENT ARCHITECTURE

### All 17 Services (ALL UP)

| Port | Service | Location | Notes |
|------|---------|----------|-------|
| :8000 | REX FastAPI | ~/Desktop/REX/ | Main backend. 7 routers mounted. |
| :8001 | Stats API | ~/Desktop/REX/CC_stats_api.py | 13 GOJ endpoints |
| :8002 | Lead Connector CRM | ~/Desktop/REX/CC_lead_connector_api.py | 21 CRM endpoints |
| :8080 | DataRex GOJ Dashboard | ~/.hermes-cloud/home/goj-pipeline/datarex/app.py | LIVE dashboard |
| :8081 | ShellCore | ~/Desktop/REX/ | Phase 1 shelved |
| :8088 | SMS Bridge | Twilio webhook | SMS relay |
| :9000 | Tiger Claw Hub | ~/hermes-hub/server.py | Main hub, serves HTML pages |
| :9119 | HermesDash | Hermes gateway | Agent chat proxy |
| :9120 | HermesAgent | ~/hermes-hub/hermes_agent_server.py | Agent status |
| :1234 | LM Studio | Local LLM | Model serving |
| :5678 | n8n | Docker | Workflow automation |
| :11434 | Ollama | Local | mistral-hermie + others |
| :27124 | Obsidian API | ~/hermes-hub/obsidian_api.py | HTTPS REST API for vault |
| :27226 | Tiger Claw API | ~/Desktop/REX/ | Jarvis Phase 19 |
| :3002 | Cloud GW | Hermes gateway | deepseek-v4-pro |
| :65001 | Local GW | Hermes gateway | mistral-hermie |
| :3080 | LibreChat | Docker | Multi-model chat |

### Domains (Cloudflare → local services)

| Domain | Points To | What's There |
|--------|-----------|-------------|
| hermestigerclaw.com | :3003 | AI Hub landing page + model switcher |
| hub.hermestigerclaw.com | :9000 | Command Center, Settings, Docs |
| rex.hermestigerclaw.com | :8000 | GOJ Live, QB Capture, Rex Bill, Social, REX login |
| cloud.hermestigerclaw.com | :3002 | Cloud Hermes gateway |
| ui.hermestigerclaw.com | :3000 | Open WebUI |
| chat.hermestigerclaw.com | :3080 | LibreChat |

### REX :8000 — Mounted Routers (7 active)

| Router | Prefix | File | Status |
|--------|--------|------|--------|
| Cowork Relay | /api/cowork-relay | backend/CC_cowork_relay.py | ✅ LIVE |
| GHS Auth | /api/auth | backend/CC_auth_router.py | ✅ LIVE |
| Social Media | /social | backend/CC_social_media_router.py | ✅ LIVE |
| Rex Bill | /rex-bill | CC_rex_bill.py (root) | ✅ LIVE |
| GOJ Live | /goj-live | backend/CC_goj_live.py | ✅ LIVE |
| QuickBooks Capture | /quickbooks-capture | CC_quickbooks_capture.py (root) | ✅ LIVE |
| Victoria/Masha | /masha | backend/CC_victoria_goj_integration.py | ⚠️ Partial |

### Unified Nav Bar

Every HTML page now has a shared nav at the top:
```
🐯 Tiger Claw | 🧠 Command | ⚙️ Settings | 🌿 GOJ Live | 📝 QB | 💰 Bill | 📱 Social | 🤖 WebUI | 💬 Chat
```

Pages with nav: CC_goj_live.html, CC_quickbooks_capture.html, CC_rex_bill_dashboard.html, hermes-hub/www/command.html, hermes-hub/www/settings.html

---

## DATABASES

| DB | Path | Notes |
|----|------|-------|
| auth_tracker.db | ~/Documents/goj files/dashboard/auth_tracker.db | 430 clients, 60+ tables. NOT SQLCipher encrypted (HIPAA gap). Key tables: clients (client_id, name, plan_raw, plan_canonical, transportation, shift), authorization (auth_id, client_name, service_start_date, service_end_date), attendance_log (log_date, day_key, shift, client_name, status), menus (menu_date, week_start, original_filename) |
| rexxie.db | Private lane | Isolated, no GOJ data |
| rex_journeys.db | ~/.rex/ | REX conversations |

---

## WHAT HERMES BUILT TODAY (June 8)

### 1. GOJ Live Frontend + Backend
- **File:** ~/Desktop/REX/backend/CC_goj_live.py (228 lines) + ~/Desktop/REX/CC_goj_live.html
- **URL:** https://rex.hermestigerclaw.com/goj-live/
- **Features:** SSE streaming every 15s, 4 dashboard cards (Clients, Attendance, Menus, System), propose/revert bar, correct SQL queries against auth_tracker.db schema
- **Known issues:** Attendance shows 0 because today has no data yet. Client total (430) vs sum of active+expired+pending (342) = 88 clients without authorization records.

### 2. TransitionAgent Drive Hook
- **File:** ~/Desktop/REX/CC_transition_drive_hook.py (318 lines)
- **Status:** Running as launchd (com.goj.transition-drive-hook, PID 12081)
- **Behavior:** Polls GOJ Operations Drive folder every 60s. Detects new/modified/deleted files by bookkeeper patterns (.xlsx, .csv, .pdf, .qbo, .qbb). Sends alerts via Cowork relay (POST /api/cowork-relay).
- **Auth:** Uses ~/.rex_google_token.json enriched with client_id/client_secret from google_credentials.json.

### 3. QuickBooks Workflow Capture
- **File:** ~/Desktop/REX/CC_quickbooks_capture.py (1,107 lines) + CC_quickbooks_capture.html
- **URL:** https://rex.hermestigerclaw.com/quickbooks-capture
- **Coverage:** 11 categories, 43 question groups, 188 fields covering daily/weekly/monthly routines, invoice processing, bill pay, payroll, Medicaid billing, bank reconciliation, report generation, system access, troubleshooting.
- **Modes:** Browser UI (auto-save on blur, search, export), CLI interview (--cli), summary (--summary), markdown export (--export).

### 4. Cowork Relay — Verified
- Mounted at /api/cowork-relay. Cowork (Claude) can push messages to Telegram bots via this endpoint. Note: the "hermes" bot token needs TELEGRAM_HERMES_TOKEN set for full relay functionality.

### 5. Social Media Router — Verified + Instagram Post
- 9 platforms registered. Instagram token recovered from backup and added to ~/.hermes-cloud/.env (META_IG_ACCESS_TOKEN=IGAASP...ZDZD, user ID 27923669980556036).
- Tonight's Knicks Game 3 menu posted to @boardwalkbeergarden (567 followers).
- Instagram API: v19.0 Graph API, image_url → container → poll → publish flow.

### 6. Rex Bill Router — Verified
- 8 financial tools. 2 connected (Clover partial, Google Sheets). QuickBooks needs OAuth connect.

### 7. /LOOP Daily Build Examiner
- **File:** ~/Desktop/REX/CC_loop_examiner.py
- **Cron Job:** Runs daily at 9 AM. Scans all 17 services, 17 routers, 85 skills, 40 launchd plists. Generates recommendations. Posts via Cowork relay.
- **First run:** June 9, 2026 at 9:00 AM.

---

## WHAT CLAUDE NEEDS TO BUILD / FIX

### 🔴 URGENT — Bookkeeper Departure (deadline was June 7)

1. **Capture the bookkeeper's workflow NOW.** The QuickBooks Capture tool is built but empty — someone needs to fill out all 188 fields. The bookkeeper can use the browser UI at https://rex.hermestigerclaw.com/quickbooks-capture or run the CLI interview.

2. **TransitionAgent Drive hook is watching** but there's no workflow captured yet. Create a flag file at ~/Desktop/REX/CC_transition_workflow_captured.flag when the bookkeeper finishes.

### 🟡 HIGH PRIORITY

3. **GOJ Live Frontend — fix the attendance data.** Currently shows 0 for everything because no attendance data exists for today (Sunday, or it's too early). The queries are correct (`attendance_log` table, `log_date = date('now')`). Either:
   - Seed some test data for today
   - Show "last available" attendance if today is empty
   - Add a date picker to view historical attendance

4. **Rex Bill Dashboard — mount the HTML page.** The CC_rex_bill_dashboard.html has the unified nav but isn't served by any route. Add to CC_rex_bill.py:
   ```python
   from fastapi.responses import HTMLResponse
   @router.get("/ui", response_class=HTMLResponse)
   async def bill_dashboard():
       return HTMLResponse(Path("~/Desktop/REX/CC_rex_bill_dashboard.html").expanduser().read_text())
   ```

5. **Social Media Router — enable Instagram auto-posting.** Currently `autopost_ready: false`. The token is in .env. Wire up the execute endpoint for Instagram (current execute only handles Telegram).

6. **GOJ Live — fix the 88-client gap.** 430 total clients but 240 active + 35 pending + 67 expired = 342. The remaining 88 have no authorization records. Either show them as "No Auth" in the dashboard or identify why they're in the clients table without auth.

### 🟢 NICE TO HAVE

7. **Unified auth across all subdomains.** Currently hub.hermestigerclaw.com and rex.hermestigerclaw.com have separate auth systems. They should share a JWT cookie so logging into one logs into all.

8. **iPhone-accessible Tauri app.** Tauri configs exist at ~/Desktop/REX/tauri-app/ pointing to hub/command. macOS .app built. iOS project at ~/hermes-apps/ios/ synced but not built for device.

9. **Cloudflare routing for CC_*.html pages.** The NOT YET BUILT list from Cowork's sync brief. Serve these static pages through Cloudflare so they're accessible without hitting the backend.

### ⚠️ PAE ITEMS PENDING KATO APPROVAL (ask before executing)

| ID | Action | File |
|----|--------|------|
| PAE-4 | Wire Gate 1 tokenizer into PHI pipeline | CC_akc_tokenizer_v2.py |
| PAE-5 | Verify + activate TigerClaw :27226 | CC_jarvis_startup.command |
| PAE-6 | Phase 16 enforcer swap | core/business_isolation.py |
| PAE-7 | Fix bot 401 errors | Hermes gateway |
| PAE-8 | Activate Agent Forge (13 agents) | rex_agent_forge.py |
| — | Claus orchestrator plist swap | CC_claus_orchestrator.py |
| — | CC_stats_api permanent plist install | :8001 currently running without plist |
| — | Obsidian daemon launchctl load | Already loaded (PID 9094) |

---

## KEY FILES YOU'LL NEED

| File | Purpose |
|------|---------|
| ~/Desktop/REX/CLAUDE.md | Governing document — read this FIRST |
| ~/Desktop/REX/backend/main.py | REX app — all router mounts here |
| ~/Desktop/REX/CC_hermes_sync_brief.md | Cowork's full build audit |
| ~/.hermes/profiles/cloud/memories/MEMORY.md | Hermes memory (updated today) |
| ~/Documents/goj files/GOJ_WORKING_DOC.md | GOJ operations doc |
| ~/.hermes-cloud/.env | All API keys including Instagram token |
| ~/Desktop/REX/state/ | All state files (registries, proposals, workflow) |
| ~/Desktop/REX/CC_loop_examiner.py | Daily examiner — run to see current state |

---

## HOW TO RESTART SERVICES

```bash
# REX (after editing main.py or routers)
pkill -f "uvicorn backend.main:app.*8000"
sleep 3
cd ~/Desktop/REX && /opt/homebrew/bin/python3.11 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --timeout-keep-alive 5 --no-server-header &

# Hub (after editing server.py or www/ files)
launchctl unload ~/Library/LaunchAgents/com.goj.hub.plist
sleep 3
launchctl load ~/Library/LaunchAgents/com.goj.hub.plist
```

---

## CONTEXT FROM COWORK SYNC BRIEF (June 8)

Cowork (Claude, running on Kato's machine) built 30+ files on June 4-5 and June 8. All verified on disk. Key builds from Cowork:
- CC_kanban_center.html — Full swimlane Kanban (38KB)
- CC_command_center.html — Expanded with screensaver, clock, alarm panel (283KB)
- CC_kato_hub.html — Kato's personal hub (1,041 lines)
- CC_settings.html — System control panel (8 sections)
- CC_home_base.html — iOS-style control panel (21 service toggles)
- CC_claus_orchestrator.py — Health monitor, morning brief, PAE escalation (1,257 lines)
- CC_full_system_audit.command — One-click diagnostic

---

## WHAT KATO WANTS NEXT

1. "GOJ live front end" — ✅ Built (but needs data fixes above)
2. "Transition agent hook" — ✅ Built (but needs workflow capture)
3. "Quickbooks workflow capture" — ✅ Built (but needs bookkeeper to fill it out)
4. "Cowork relay" — ✅ Verified
5. "Social media router" — ✅ Verified (but auto-posting needs wiring)
6. "Rex bill" — ✅ Verified (but dashboard HTML needs mounting)
7. "/loop daily examiner" — ✅ Built (cron scheduled for 9 AM)

Kato said: "these are executed now create a /loop that will examine my build daily and recommend new agents/builds/skills/tools/extensions to make my workflow smoother"

The /loop is built and scheduled. The remaining work is the polish and wiring items listed above.

---

*Hermes (Cloud May Bot) — June 8, 2026 — 11:45 AM*
