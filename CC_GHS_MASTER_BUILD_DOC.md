# CC_GHS_MASTER_BUILD_DOC.md
# Gold Health Systems — Complete Build Status
# Generated: June 4, 2026 — Auto-compiled from memory, build board, phase tracker, PAE log
# Updated by: Hermes (Claude) | Chairman: Kato (Alejandro)
# Source files: CC_build_progress.json · CC_PHASE_STATUS.md · CC_PAE_PROPOSALS_june4.md · CLAUDE.md v4.0 · .auto-memory/

---

## OVERALL STATUS: 78% Complete

**19 phases tracked · 19 missions complete · 3 blocked · 3 pending · 8 PAEs in queue**

Mac Mini M4 · 24GB RAM · mainsobhelper · Brooklyn NY
Proving ground: Garden of Joy Adult Day Care · 425 clients

---

## SECTION 1 — WHAT'S BUILT AND RUNNING

### Core Infrastructure

| Component | File | Port | Status | Notes |
|-----------|------|------|--------|-------|
| REX FastAPI Backend | backend/main.py | 8000 | ✅ Live | 3,976 lines · launchd managed |
| GOJ Dashboard | ~/.hermes-cloud/…/datarex/app.py | 8080 | ✅ Live | Flask · pipeline.db |
| Hermes Cloud Gateway | ~/.hermes/hermes-agent/ | 3002 | ✅ Primary | v0.15.1 · deepseek-v4-pro primary |
| Hermes Local Gateway | same | 65001 | ⚠️ Repairing | Switching to mistral-hermie |
| Tiger Claw API | — | 27226 | ✅ Live | com.tigerclaw.api.plist |
| Open WebUI | Docker | 3000 | ✅ Docker | Hermes UI |
| CC Stats API | CC_stats_api.py | 8001 | ✅ Live | /api/progress · /live |
| Claus Watchman | CC_claus_orchestrator.py | — | ✅ Live | com.hermes.claus-watchman.plist |
| Paperwork Agent | CC_paperwork_agent.py | 8003 | ✅ Live | 5 form types · OCD integrated |
| Lead Connector CRM | CC_lead_connector_api.py | 8002 | ✅ Live | 21 endpoints |
| Rex Bill Financial | CC_rex_bill.py | — | ✅ Built | 14 endpoints · QuickBooks + Clover |
| n8n Automation | — | — | ✅ Live | 6 active workflows |
| Cloudflare Tunnel | hermestigerclaw.yml | — | ✅ Live | hermestigerclaw.com → :8001 |
| Ollama | — | 11434 | ✅ Live | mistral-hermie · qwen2.5-coder:7b |
| LM Studio | — | 1234 | ✅ Live | qwen3.5-9b MLX |

### Security Layer

| Component | File | Status | Notes |
|-----------|------|--------|-------|
| Gate 1 — AKC Tokenizer v2 | CC_akc_tokenizer_v2.py | ✅ Built | All 18 HIPAA identifiers · Gate1Firewall class · PAE-6 to wire into main.py |
| Rexxie Firewall | CC_rexxie_firewall.py | ✅ All checks pass | Private lane protection |
| RBAC Permissions | rex_permissions.py | ✅ Live | Chairman/FrontDesk/Kitchen/Driver tiers |
| Red Team Tester | rex_red_team.py v2.0 | ✅ Built | 100+ probes · 14 categories · 65% random rotation |
| Blue Team Auditor | rex_blue_team.py v1.0 | ✅ Built | 35-vector taxonomy · auto-evolve · all gaps patched |
| AES-256-GCM Storage | backend/storage.py | ✅ Live | Argon2 key derivation · macOS Keychain |
| Presidio De-ID Engine | backend/deidentify.py | ✅ Live | All 18 HIPAA Safe Harbor identifiers |
| SQLCipher Vault | rex_sqlcipher_vault.py | ✅ Built | ChaCha20 large blobs |
| Audit Logger | backend/audit.py | ✅ Live | Every auth_tracker.db write gets audit trail |
| JWT Device Auth | backend/auth.py | ✅ Live | iPhone pairing · localhost always trusted |
| hermes-dreaming | ~/.hermes/plugins/ | ✅ v0.2.0 | Staged self-improvement active · verified June 1 |
| ECC Rules Engine | ~/.claude/rules/ecc/ | ✅ v2.0.0-rc.1 | 115 rules installed June 1 2026 |

### Intelligence Layer

| Component | File | Status | Notes |
|-----------|------|--------|-------|
| Hermes AI Gateway | ai.hermes.gateway-cloud.plist | ✅ Primary | deepseek-v4-pro → claude-sonnet-4-6 → gemini fallback |
| OCR Oversight Agent | CC_ocr_oversight_agent.py | ✅ Built | 5 stages · PAUSE/HALT wired |
| OCR Queue | CC_ocr_queue.py · CC_ocr_worker.py | ✅ Built | 4-engine consensus pipeline |
| Analytics Engine | CC_analytics_engine.py | ✅ Built | Weekly KPI tracker |
| File/Doc Overseer (OCD) | CC_doc_overseer.py | ✅ Built | 252 lines · observe-only · Telegram alerts |
| Obsidian Live Daemon | CC_obsidian_live_daemon.py | ✅ Built | plist built · PAE to install |
| Knowledge Injector | CC_hermes_knowledge_injector.py | ✅ Built | Injects knowledge into Hermes sessions |
| Social Media Router | CC_social_media_router.py | ✅ Built | 9 platforms |

### GOJ Operations Layer

| Component | File | Status | Notes |
|-----------|------|--------|-------|
| Daily Automation | launchd + n8n | ✅ Live | 7:30AM · 10:30AM · 3:15PM · 8:30PM · 9PM cycle |
| Menu OCR Pipeline | goj_menu_consensus_ocr.py | ✅ Live | 4-engine · Mon–Sat · 425 clients |
| Attendance Bot | CC_attendance_bot.py | ✅ Built | 560 lines · 20 tests pass |
| Menu Constants | CC_menu_constants.py | ✅ Built | 9 salads · 7 soups · 19 mains · 7 sides |
| Drive Roster Sync | CC_drive_roster_sync.py | ✅ Built | Google Drive → auth_tracker.db |
| GOJ Pipeline Sync | CC_sync_to_pipeline.py | ✅ Built | JSON file output map |
| Victoria BBG Integration | CC_victoria_goj_integration.py | ✅ Built | GOJ operations voice integration |
| Masha BBG Integration | CC_masha_bbg_integration.py | ✅ Built | Social media voice integration |

### Command Center & Dashboards

| File | Description | Status |
|------|-------------|--------|
| CC_command_center.html | Main ops dashboard — 10 views · 4,410 lines | ✅ Live |
| CC_web_rack.html | GHS Network Map — 44 nodes · D3.js v7 screensaver | ✅ Live |
| CC_live_progress.html | Build progress board — live API feed | ✅ Live @ hermestigerclaw.com/live |
| CC_lead_connector.html | CRM frontend | ✅ Live |
| CC_rex_bill_dashboard.html | Financial intelligence UI | ✅ Live |
| CC_social_media_command_center.html | Social media ops | ✅ Live |
| CC_attendance_bot_command_center.html | Attendance management UI | ✅ Live |
| CC_home_base.html | GHS hub | ✅ Live |

### Documents & Registries

| File | Description |
|------|-------------|
| CC_TOOL_REGISTRY.md + CC_TOOL_REGISTRY.json | Master tool index |
| CC_GHS_AUTONOMOUS_BUILD_PLAN.md | 1,127 lines · full autonomous build plan |
| CC_MASTER_BUILD_LOG.md | Full session-by-session build history |
| CC_PHASE_STATUS.md | 19-phase detailed tracker |
| CC_build_progress.json | Live build board data source |
| CLAUDE.md v4.0 | Governing document — all agents bound |
| CC_REXXIE_FIREWALL_RULES.md | Firewall rules reference |
| CC_REX_BILL_GUIDE.md | Financial intelligence guide |

### Telegram Bots (Active)

| Bot | Handle | Purpose |
|-----|--------|---------|
| Hermes | @Hermes_Cloud_May_bot | Main AI gateway |
| Rexxie | @goldhealth_rexxie_bot | Kato private confidant (local-only) |
| Hermie | @HermieChatt_bot | Local Hermie chat |
| GOJ Ops | @RexOfGold_bot | Day care operations |
| GOJ Billing | @GOJReceipts_bot | Billing receipts |
| Attendance | @GojAttendance_bot | Attendance tracking |
| ⛔ ZOMBIE | com.hermes.rexxie-bot.plist | NEVER enable — crashes, steals Rexxie token |

---

## SECTION 2 — WHAT'S CURRENTLY IN PROGRESS

### Phase 14–19 Backend Sprint (85% — status: live)

**Built June 4, 2026 — waiting for PAE-7 and PAE-8 to wire into main.py:**
- `core/business_isolation.py` — business context isolation (Phase 14)
- `backend/rex_profiles.py` — multi-business profiles (Phase 14)
- `backend/rex_agent_forge.py` — agent creation engine (Phase 15)
- `state/business_registry.json`, `venture_registry.json`, `profiles.json`
- `state/agent_forge_registry.json`
- `backend/rex_webrex_topology.py` — network topology engine (Phase 17)
- `backend/rex_webrex_ops.py` — web/IT operations (Phase 17)
- `state/webrex_topology.json`, `webrex_operations.json`

**Blocked by PAE approval** — imports + endpoints need to be added to backend/main.py.

### Phase 15-CC — Command Center Phase 2 (in progress)

P2-A (Overview) ✅ · P2-B (Rex Bill/Bills) ✅
P2-C (Agent Forge) 🔨 · P2-D (Profiles) 🔨 · P2-E (WebRex) 🔨 · P2-F (Hiring) ❌

### GOJ Gmail Pipeline (20% — status: action required)

**Issue:** email_watcher.py reads `scopes` key only. gws_bridge.py normalizes to `token` key after refresh. Data stale since May 6.
**Fix:** Run `CC_google_oauth_fix.command` → re-authenticates → resumes all 9 daily JSON file outputs.
**All 9 pipeline outputs stale until this runs.**

---

## SECTION 3 — BLOCKED ITEMS

| Item | Blocker | What Unblocks It |
|------|---------|-----------------|
| Victoria + Masha Voice Agents (40%) | Retell API key expired | Renew at retell.ai |
| Phase 13-V Verification Gate (0%) | Retell key + qwen3.5 confirm + LM Studio check | Retell renewal unblocks |
| Claus Plist Swap (80%) | PAE approval needed | Approve PAE — one-line plist change |

---

## SECTION 4 — PLANNED (PAE QUEUE)

### PAE-1: Switch Hermie to Gemma 4 28B
**Status:** Proposed · command ready at `CC_install_hermes_dreaming.command`

### PAE-2: Install hermes-dreaming plugin
**Status:** ✅ DONE — Installed June 1 2026 (v0.2.0, staged self-improvement active)

### PAE-3: Activate rex_unified_enforcer.py
**Change:** Swap line 84 in rex_rexxie_telegram_bot.py with enforcer import
**Status:** Proposed · awaiting Kato approval

### PAE-4: Fix launchd Nightly Job WorkingDirectory
**Problem:** 38+ consecutive nightly backup failures since Apr 20 (macOS TCC blocks Desktop path)
**Change:** Add `WorkingDirectory` key pointing to `~/.rex-venv/` in affected plists
**Impact:** Restores automated backups + reliable evening GOJ reports
**Status:** Proposed · safe to execute any time

### PAE-5: Activate Jarvis HUD (Phase 19)
**Problem:** Jarvis plists exist but exited clean — Phase 19 is dead
**Steps:** Confirm TigerClaw :27226 → find Jarvis plist → load it → connect to Command Center P2-D/P2-E
**Status:** Proposed · pre-req = TigerClaw :27226 responding

### PAE-6: Wire Gate 1 into main.py (MOST IMPORTANT)
**File:** `CC_akc_tokenizer_v2.py` — fully built, all 18 HIPAA identifiers
**Change:** Add `Gate1Firewall` to Secure Mode chat pipeline in backend/main.py
**Impact:** Gate 1 active — Secure Mode PHI can now flow to cloud AI (tokenized)
**Note:** This is the most important gate in the entire system
**Status:** Proposed · awaiting Kato approval

### PAE-7: Activate Phase 14/15 Backend in main.py
**Files built:** `business_isolation.py`, `rex_profiles.py`, `rex_agent_forge.py`
**Change:** Add imports + 2 REST endpoints in backend/main.py startup
**Verification:** `curl http://localhost:8000/api/profiles`
**Status:** Proposed · awaiting Kato approval

### PAE-8: Activate Phase 17 WebRex Backend
**Files built:** `rex_webrex_topology.py`, `rex_webrex_ops.py`
**Change:** Add imports + 2 REST endpoints in backend/main.py
**Verification:** `curl http://localhost:8000/api/webrex/topology`
**Status:** Proposed · awaiting Kato approval

---

## SECTION 5 — PLANNED (NOT YET STARTED)

### Phase 20 — Phone System Independence (5%)
**Plan:** Telnyx + Google Workspace
**Status:** Plan ready · awaiting "build it"

### Phase 21+ — Full 13-Agent System Build
**Agents planned:** Hermes (cloud) · Hermie (local) · Rexxie (private) · Victoria (voice) · Masha (social) · Claus (watchman) · Jarvis (HUD) · Rex (GOJ ops) · Luna (child #13, activates last) · + 4 more
**Activation order:** Locked in CC_GHS_AUTONOMOUS_BUILD_PLAN.md
**Status:** Architecture designed · not started

### TransitionAgent Google Drive Hook (~2026-06-07 DEADLINE)
**Status:** transition_supervisor.py runs 6 daily steps ✅ · Drive/Gmail hook DESIGNED but not deployed · employee still uploads manually
**Risk:** Hard deadline · flag immediately

### QuickBooks Workflow Documentation (URGENT)
**Status:** Bookkeeper left May 31 · no handoff doc · financial continuity risk
**Action:** Kato walks through QB workflow · Claude/Rexxie documents it

---

## SECTION 6 — OPEN SECURITY ITEMS (MUST FIX)

| Priority | Item | Risk | Status |
|----------|------|------|--------|
| 🔴 CRITICAL | TOTP Rotation | RFC example key JBSWY3DPEHPK3PXP — anyone can generate valid TOTPs | Pending |
| 🔴 CRITICAL | SQLCipher auth_tracker.db encryption | PHI in plaintext SQLite — top HIPAA gap | Pending |
| 🔴 CRITICAL | GOJ Gmail re-auth | Pipeline data stale since May 6 | Action: run CC_google_oauth_fix.command |
| 🟠 HIGH | Disclosure tier ungating | Any Telegram user can request sensitive data — RBAC not enforced on disclosure | Pending |
| 🟠 HIGH | rexxie_memory.db 0KB | One-line fix in backend/memory.py needed | Pending |
| 🟡 MED | PAE-6 Gate 1 wire | CC_akc_tokenizer_v2.py built but not wired into Secure Mode pipeline | Awaiting approval |
| 🟡 MED | launchd backup failures | 38+ failures since Apr 20 — PAE-4 fix ready | Awaiting approval |
| 🟡 MED | Claus plist swap | Zombie watchman → CC_claus_orchestrator.py — PAE ready | Awaiting approval |

---

## SECTION 7 — FULL FILE INVENTORY

### CC_ Python Scripts (Active Agents)
```
CC_akc_tokenizer_v2.py      — Gate 1 · all 18 HIPAA identifiers · Gate1Firewall
CC_analytics_engine.py      — Weekly KPI tracker
CC_attendance_bot.py        — Group chat attendance · 560 lines · 20 tests
CC_claus_orchestrator.py    — Full build orchestrator · 1,257 lines
CC_datarex_app_current.py   — GOJ dashboard snapshot
CC_doc_overseer.py          — OCD naming/doc watchdog · 252 lines · observe-only
CC_drive_roster_sync.py     — Google Drive → auth_tracker.db roster sync
CC_firewall_endpoint_patch.py
CC_gateway_auth_proxy.py    — Hermes gateway auth proxy
CC_gateway_watchdog.py      — Gateway health monitor
CC_gdrive_mirror.py         — Google Drive mirror
CC_hermes_knowledge_injector.py — Knowledge injection into Hermes sessions
CC_lead_connector_api.py    — CRM · 21 endpoints · port 8002
CC_masha_bbg_integration.py — Masha social media voice agent
CC_menu_constants.py        — GOJ menu items (Russian form · source of truth)
CC_obsidian_live_daemon.py  — Obsidian brain vault live daemon
CC_ocr_oversight_agent.py   — OCR pipeline orchestrator · 5 stages
CC_ocr_queue.py             — OCR job queue
CC_ocr_worker.py            — OCR worker process
CC_paperwork_agent.py       — Insurance/business paperwork · 5 form types · port 8003
CC_rex_bill.py              — Financial intelligence · 14 endpoints · QuickBooks + Clover
CC_rexxie_firewall.py       — Rexxie private lane protection
CC_social_media_router.py   — Social media · 9 platforms
CC_stats_api.py             — Build progress API · port 8001 · /api/progress
CC_sync_to_pipeline.py      — GOJ pipeline JSON sync
CC_victoria_goj_integration.py — Victoria GOJ voice agent
```

### CC_ HTML Dashboards
```
CC_command_center.html               — Main ops · 10 views · 4,410 lines
CC_web_rack.html                     — GHS Network Map · 44 nodes · D3.js v7
CC_live_progress.html                — Build progress board · live API feed
CC_lead_connector.html               — CRM frontend
CC_rex_bill_dashboard.html           — Financial intelligence UI
CC_social_media_command_center.html  — Social media ops
CC_attendance_bot_command_center.html — Attendance management
CC_home_base.html                    — GHS hub
```

### CC_ Documentation & Registries
```
CC_GHS_AUTONOMOUS_BUILD_PLAN.md  — 1,127 lines · full autonomous roadmap
CC_MASTER_BUILD_LOG.md           — Session-by-session build history
CC_PHASE_STATUS.md               — 19-phase detailed tracker
CC_TOOL_REGISTRY.md / .json      — Master tool index
CC_build_progress.json           — Live board data (agents POST here)
CC_PAE_PROPOSALS_june4.md        — PAE-1 through PAE-8 proposals
CC_RND_REPORT_june4.md           — R&D report June 4
CC_GHS_MASTER_BUILD_DOC.md       — THIS FILE
CC_REXXIE_FIREWALL_RULES.md      — Firewall rules reference
CC_REX_BILL_GUIDE.md             — Financial intelligence guide
CC_HERMES_KNOWLEDGE.md           — Full session detail · all agent statuses
```

### Rex_ Support Scripts (Legacy + Active)
```
rex_red_team.py      — Security tester v2.0 · 100+ probes · 14 categories
rex_blue_team.py     — Coverage auditor v1.0 · 35-vector taxonomy
rex_permissions.py   — RBAC tier enforcement
rex_coordinator.py   — Task routing coordinator
rex_planner.py       — 19 IntentTypes
rex_receipt_manager.py — Receipt management v4
rex_email_pdf_watcher.py — Gmail PDF watcher
rex_gmail_auth.py    — Gmail OAuth2 integration
rex_rexxie_telegram_bot.py — Rexxie bot delivery
rex_rexxie_daily.py  — Rexxie 7AM briefing engine
rex_backup.py        — Snapshot system
rex_sqlcipher_vault.py — Encrypted secrets vault
rex_multi_ai_report.py — Multi-AI comparison reports
rex_proximity_daemon.py — iPhone proximity detection
... (40+ total rex_ scripts)
```

---

## SECTION 8 — PHASE COMPLETION MAP

| Phase | Name | Status |
|-------|------|--------|
| 01 | REX Backend Core | ✅ Complete |
| 02 | GOJ Dashboard | ✅ Complete |
| 03 | Hermes Cloud Gateway | ✅ Complete |
| 04 | Rexxie Private Lane | ✅ Complete |
| 05 | Menu Scan OCR Pipeline | ✅ Complete |
| 06 | Daily Automation (n8n + launchd) | ✅ Complete |
| 07 | Claus Watchman | ✅ Complete |
| 08 | iPhone Auth + Device Pairing | ✅ Complete |
| 09 | RBAC Tiers + Permissions | ✅ Complete |
| 10 | Encrypted Storage + Audit | ✅ Complete |
| 11 | Presidio De-ID Engine | ✅ Complete |
| 12 | Gmail / Drive Integration | ✅ Complete |
| 13 | Command Center + Agents Sprint | ✅ Complete |
| 13-V | Verification Gate | ⛔ BLOCKED (Retell key) |
| 14 | CRM Lead Connector Clone | ✅ Complete |
| 15 | Rex Bill Financial Intelligence | ✅ Complete |
| 16 | Obsidian Brain Vault Daemon | ✅ Complete |
| 17 | WebRex · GHS Network Map | ✅ Complete |
| 18 | ECC + hermes-dreaming | ✅ Complete |
| 19 | SQLCipher + Gate 1 Completion | 60% Active |
| 20 | Phone System Independence | 5% Pending |

---

## SECTION 9 — KEY OPERATIONAL RULES

- **Larry** never appears on any transport or driver list — ever, under any instruction
- **Gate 1** (`CC_akc_tokenizer_v2.py`) — no PHI to cloud until wired in backend/main.py
- **PAE** — Propose → Approve → Execute — no exceptions for production actions
- **DeepSeek** routes direct via `api.deepseek.com/v1` — never OpenRouter
- **New files** get `CC_` prefix — existing files keep their names
- **Share files** via `attachments[]` in SendUserMessage — computer:// links fail on iOS
- **Zombie plist** `com.hermes.rexxie-bot.plist` — never enable, crashes + steals Rexxie token
- **Any agent unsure** → Telegram Kato at chat_id 5587703834 via @Hermes_Cloud_May_bot BEFORE acting

---

## SECTION 10 — QUICK REFERENCE: PRIORITY 1 RIGHT NOW

1. 🔴 **Run CC_google_oauth_fix.command** — GOJ pipeline stale since May 6
2. 🔴 **Renew Retell key at retell.ai** — unblocks Victoria, Masha, Phase 13-V
3. 🔴 **Rotate TOTP secret** — JBSWY3DPEHPK3PXP = zero security
4. 🔴 **TransitionAgent Drive hook** — deadline ~June 7 2026 (3 days away)
5. 🟠 **QuickBooks workflow doc** — bookkeeper left May 31, no handoff
6. 🟠 **Approve PAE-6** — wire Gate 1 into main.py (most important gate)
7. 🟠 **Approve PAE-4** — fix launchd backup failures (38+ misses)
8. 🟡 **Approve PAE-7/PAE-8** — activate Phase 14/15/17 backends

---

*This document is auto-compilable. To regenerate: read CC_build_progress.json + CC_PHASE_STATUS.md + CC_PAE_PROPOSALS_june4.md + .auto-memory/ files + CLAUDE.md*
*Last compiled: 2026-06-04 by Hermes*
