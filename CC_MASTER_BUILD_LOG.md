# GHS Master Build Log
## Gold Health Systems — Living Document
### Last Updated: June 4, 2026
### Maintained by: Hermes (Documentation Agent)
### Source of truth: ~/Desktop/Gold_Health_Systems/BRAIN/MASTER.md

---

> **HOW TO READ THIS FILE:** This is the definitive operational reference for all GHS agents and sessions. Start with SYSTEM IDENTITY, then jump to TODAY'S CHANGES, then consult OPEN ITEMS. The 19-PHASE BUILD MAP is the architectural backbone. Every fact here traces to CLAUDE.md, CC_HERMES_KNOWLEDGE.md, or direct audit evidence.

---

## SYSTEM IDENTITY

**Gold Health Systems (GHS)** — parent company (AKC Managing C-Corp). Kato (Alejandro, username `mainsobhelper`, email `atigerclawai@gmail.com`, Telegram `5587703834`) is Chairman. He overrides everything. Never call him Allen — Allen Khiger is a former GOJ employee, different person. Vlad = business partner, financial view only, not Chairman.

**Mission:** Fully local, privacy-first, multi-agent AI OS for Gold Health Systems. Proving ground: Garden of Joy adult day care (425 clients, Brooklyn NY). Every build must advance GHS operations or justify its existence.

**Businesses:**

- **Gold Health Systems (GHS)** — parent. Domains: `hermestigerclaw.com` (REX/Hermes platform), `goldhealthsys.com` (marketing + employee login, 34 modules, Railway/Tiger Claw hosted). Note: "LIVE" on goldhealthsys.com ≠ fully functional — verify each module independently.
- **Garden of Joy (GOJ)** — adult day care, Brooklyn NY. ~425 active clients. Russian-speaking population. HIPAA-covered. Daily automation runs all GOJ operations.
- **Boardwalk Beer Garden (BBG)** — Brighton Beach. Adults-only after 8PM. No DJ until summer. Clover POS: C051UQ41540458. Instagram: @boardwalkbeergarden (account ID: 27923669980556036). No auto-posting — Kato approves every post before it goes live.

**North Star (non-negotiable):** local-first · privacy-first · deterministic · no unapproved cloud · ideas integrate · check regressions · check future complexity · strong disclosure protection · locked architecture parameters

---

## DERIVATION CHAIN

```
BRAIN/MASTER.md  ← Kato maintains. ONE source of truth.
      ↓
CLAUDE.md        ← Governs all agents. Every session reads this.
      ↓                         ↓
SOUL.md                    MEMORY.md
~/.hermes/profiles/        ~/.hermes/profiles/
cloud/memories/            cloud/memories/
~50 lines identity         §-delimited, 2800 chars
      ↓
master_list.json  ← Build registry. rex_coordinator.py reads this.
      ↓
CC_MASTER_BUILD_LOG.md  ← This file. Documentation layer.
```

---

## 19-PHASE BUILD MAP

### Phase 1: REX Foundation — Status: LOCKED / COMPLETE
Core FastAPI backend, auth, encrypted storage, and service infrastructure.

**What was built:** FastAPI server (`backend/main.py`, 3,976 lines), Desktop Mode (localhost always trusted), JWT device pairing, EncryptedStorage (AES-256-GCM, SQLite, Argon2 key derivation), AuditLogger, LiteLLMProxy, AgentBus (AES-256-GCM inter-agent comms), Alert Bus (`/data/alert_bus_fallback.jsonl`, `/data/rex_events.db`).

**Key files:** `backend/main.py`, `backend/auth.py`, `backend/storage.py`, `backend/config.py`, `backend/audit.py`, `backend/agent_bus.py`

**Start REX (dev):** `source ~/debate-chamber/.venv/bin/activate && cd ~/Desktop/REX && uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload`

**Start REX (production):** `launchctl load ~/Library/LaunchAgents/com.rex.backend.plist` (uses `~/.rex-venv/`)

**Status:** ✅ Running on port 8000. v3.0.0. 395 active clients, 438 menus, rexxie_alive=true.

---

### Phase 2: OCR Pipeline + Memory Steward — Status: LOCKED / ACTIVE (Memory: REGRESSION)
Menu PDF processing with multi-engine OCR consensus, plus persistent memory layer.

**What was built:**
- **OCR**: `goj_menu_consensus_ocr.py` — Claude Vision API as primary, 3-pass consensus voting, schema validation (`name`, `quantity`, `unit`, `allergens[]`). Tesseract + Google Drive + Paperless-ngx + Claude Vision = 4-engine consensus.
- **Memory**: `backend/memory.py` (RexMemory), `rex_memory.db` (BROKEN — 0KB), `rexxie_memory.db` (60K, healthy).

**Key files:** `goj_menu_consensus_ocr.py`, `goj_menu_ocr_schema.py`, `backend/memory.py`, `rex_memory.db`, `rexxie_memory.db`

**Known regression:** `rex_memory.db` is 0KB — RexMemory never populates. Fix is one line in `backend/memory.py`. Rexxie starts cold every session. This is a critical open item.

**Status:** OCR ✅ Active. Memory ⚠️ Regression — rex_memory.db empty.

---

### Phase 3: Alert Router — Status: LOCKED / COMPLETE
Chairman Command Center routing for system events.

**What was built:** `backend/rex_command_center.py` — Chairman Dashboard API routes (`GET /api/chairman/system-health`, `/api/chairman/red-flags`, `/api/chairman/unresolved`, `POST /api/chairman/resolve/{id}`, `POST /api/chairman/escalate/{id}`). Alert bus events routed to web UI. Chairman-only auth via `rex_role_auth.verify_role()`.

**Key files:** `backend/rex_command_center.py`, `/data/rex_events.db`, `/data/rex_unresolved.db`

**Status:** ✅ Active.

---

### Phase 4: Gauntlet (Review Gate) — Status: LOCKED / COMPLETE
OCR output review before production.

**What was built:** `rex_vision_flag_processor.py` — flags OCR results with confidence < 70%, missing fields, policy violations. Quarantine at `/data/ocr_quarantine/`. Approved items move to `/data/gauntlet_reports/`. Chairman reviews in Command Center.

**Key files:** `rex_vision_flag_processor.py`, `/data/ocr_quarantine/`, `/data/gauntlet_reports/`

**Status:** ✅ Active. Safety gate functioning.

---

### Phase 5: Rexxie Telegram Bot + Policy Enforcement — Status: LOCKED / ACTIVE (Enforcement: Partial)
Telegram chat interface and inbound/outbound policy gates.

**What was built:** `rex_rexxie_telegram_bot.py`, `rex_rexxie_telegram_config.json` — Rexxie listens to Telegram, routes to Claude via `private_confidant_gold.py`. Policy gate: `rex_policy_enforcer.py` (checks jailbreaks, PHI, sovereignty rules). 4 Rexxie lanes, 1 token. Lane 2 = private/personal (local ONLY — never cloud, never divulges). `rexxie.db` isolated.

**Key files:** `rex_rexxie_telegram_bot.py`, `rex_policy_enforcer.py`, `rex_policy_rules.json`, `private_confidant_gold.py`, `rex_rexxie_telegram_config.json`

**Known issues:**
- Three policy enforcers exist with overlapping names → collision risk (RED_TEAM finding #4)
- Fallback policy is a security blackhole if enforcer fails to import (finding #5)
- Disclosure tier enforcement is advisory only — any Telegram user can request sensitive data (finding #6)

**Status:** ✅ Rexxie active. ⚠️ Policy enforcement incomplete — disclosure tier not gated.

---

### Phase 6: GOJ Dashboard + Daily Scheduler — Status: LOCKED / ACTIVE
Flask dashboard for GOJ operations and n8n-powered daily automation.

**What was built:** GOJ Dashboard at `~/.hermes-cloud/home/goj-pipeline/datarex/app.py` (Flask, port 8080). DB: `~/Documents/goj files/dashboard/auth_tracker.db` (SQLite, NOT SQLCipher). Daily scheduler: 7:30 AM morning report · 10:30 AM kitchen+distribution PDFs · 3:15 PM signin+driver sheets · 8:30 PM Fri missing menus · 9 PM drop-off rundown · 9 PM Fri weekly email. 7-System Schedule Change Cascade (atomic — all 7 or nothing).

**Key files:** `~/.hermes-cloud/home/goj-pipeline/datarex/app.py`, `~/Documents/goj files/dashboard/auth_tracker.db`, `goj_daily_scheduler.py`

**n8n workflows (6 active):** ShellCore Health Watchdog (5m), Morning System Report (8am), GOJ Daily Delivery (2pm), GOJ Nightly Handoff (9pm weekdays), Obsidian Nightly Digest (10pm), GOJ Kitchen Correction (manual).

**⚠️ CRITICAL PATH NOTE:** Dashboard port 8080 returns 404 on `/health` route but server IS running (Flask routing issue, not server-down). Confirm live dashboard path before any changes: `~/.hermes-cloud/home/goj-pipeline/datarex/app.py` (LIVE) — NOT `~/Documents/goj files/dashboard/app.py` (NOT running).

**Status:** ✅ Dashboard running. ✅ n8n 6 workflows active. ⚠️ /health route mismatch.

---

### Phase 7: PAE Engine (Propose → Approve → Execute) — Status: LOCKED / COMPLETE
Production governance layer for all real-world actions.

**What was built:** PAE engine embedded in REX FastAPI `:8000`. No real-world action without Chairman authorization. Completed Phase 2B.5. Every destructive or production action must go through Propose → Kato Approves → Execute. Kato saying "build it" / "do it" / "just do it" = approved, proceed without further questions.

**Key files:** `backend/main.py` (PAE integration), `rex_role_auth.py`

**Status:** ✅ Active. Governs all production actions.

---

### Phase 8: Intelligence Architecture (Planning + User Model + Reflection) — Status: LOCKED / ACTIVE
Multi-layer intelligence system: planner, user model, reflection engine.

**What was built:**
- `rex_planner.py` — 19 IntentTypes. Classify → Plan → Validate → Enrich → Route → Audit.
- `rex_user_model.py` — 4 tiers: Session, Short-term (21d), Long-term, Reflection. NOTE: `rex_user_model.db` = 0KB broken.
- `rex_reflection.py` — 5 growth signals. Writes Tier 4 every 20 exchanges.
- `rex_human_behavior.py` — strips AI filler from Rexxie responses.
- `rex_coordinator.py` — Build Coordinator. Reads `master_list.json`, fuzzy-matches ideas.
- 9-Step Growth Loop (every message): signal detection → memory retrieval → user model build → policy check → plan → respond → log exchange → update user model → periodic reflection (every 20 exchanges).

**Known regression:** `rex_user_model.db` = 0KB. User model starts cold every session.

**Status:** ✅ Architecture active. ⚠️ User model DB empty — same root cause as Phase 2 memory regression.

---

### Phase 9: CLS v3 (Continuous Learning System) — Status: LOCKED / ACTIVE (GAUNTLET_ENV disabled)
Two-tier governed learning system, no silent memory writes.

**What was built:**
- `core/cls_v3.py` — Tier A (automatic pattern scoring, zero writes) + Tier B (candidate promotion, gated).
- `core/cls_gate.py` — Only path from pattern → MemorySteward write. Requires explicit Kato Telegram approval.
- `backend/rex_nightly_brief.py` — Nightly briefing with required metadata (window, timestamp, event counts).
- `core/gauntlet/scenarios/cls_v3_safety.yaml` — 10 safety scenarios.

**Rules:** GAUNTLET_ENV → CLS self-disables. No reads from `ocr_quarantine/`, `rexxie.db`, L3+ memory. CLS never updates existing memory records (insert-only). All writes tagged `agent_owner="rex_cls"` for rollback.

**Key files:** `core/cls_v3.py`, `core/cls_gate.py`, `backend/rex_nightly_brief.py`, `data/vaults/cls_v3_patterns.db`, `data/vaults/cls_v3_candidates.db`

**Status:** ✅ Built. ⚠️ Currently disabled by GAUNTLET_ENV.

---

### Phase 10: Schema Validator + Prompt Registry — Status: LOCKED / COMPLETE
Governed prompt management with versioning, approval tiers, and rollback.

**What was built:** `backend/rex_prompt_registry.py`, `state/prompt_registry.json` (15 entries), 10 prompt `.md` files across `prompts/` (identity, governance, knowledge, operational, cls, ocr categories). Append-only audit log (`state/prompt_audit.log`). Usage tracking (`data/vaults/prompt_usage.db`). Protected prompts (48h staging, second confirmation required): `rex-identity-v1`, `rexxie-identity-v1`, `role-disclosure-rules-v1`, `agent-security-rules-v1`, `ocr-safety-policy-v1`.

**Approval tiers:** Tier 1 (training/style) = immediate. Tier 2 (knowledge/operational) = 24h staged, Kato acknowledge. Tier 3 (identity/governance/ocr/cls/memory/override) = 72h staged, explicit approval required.

**Kato commands:** `approve/reject/rollback prompt edit <id>`, `prompt status <id>`, `list prompts [category]`, `list pending prompt edits`.

**Status:** ✅ Active. All 10 prompts governed.

---

### Phase 11: System Audit — Status: LOCKED / COMPLETE
Comprehensive security and architecture audit (RED_TEAM_AUDIT_2026-04-13).

**What was found (critical):**
1. Telegram bot token in plaintext across 33 files → fix: revoke, store in Keychain
2. Anthropic API key in `.env` backed up unencrypted → fix: revoke, Keychain, add `.env` to exclusion
3. TOTP secret = RFC example value `JBSWY3DPEHPK3PXP` → fix: generate unique, store in vault

**Key file:** `REX_RED_TEAM_AUDIT_2026-04-13.md`

**Status:** ✅ Audit complete. ⚠️ Critical findings still partially open (TOTP rotation not yet done — see OPEN ITEMS).

---

### Phase 12: Domain Separation + Training Classifier — Status: LOCKED / COMPLETE
Separation of GOJ, BBG, GHS domains. Training data classification.

**What was built:** Domain isolation for GOJ vs. BBG vs. GHS data. Training classifier to prevent cross-domain contamination. `rex_training.py` for feedback/training data capture. `rex_ai_enrichment.py` for background context enrichment. `rex_behavior_monitor.py` for response safety.

**Status:** ✅ Active.

---

### Phase 13: Training Privacy Panel + Snapshot Engine — Status: LOCKED / COMPLETE
Privacy layer for training data + snapshot-based state backup system.

**What was built:** `rex_encrypted_transcript.py` — `TranscriptStore` + `EncryptedSessionCache` for session backup and resume. Snapshot engine captures full system state. `state/prompt_audit.log` + `data/vaults/prompt_edits.db` included in snapshots. Backup script (`rex-backup-goj.command`) with 5-section capture including Prompt Registry.

**State snapshots path:** `~/.hermes/state-snapshots/` — nightly 2AM rolling 7-day to `/Volumes/cartoons/`.

**Status:** ✅ Active. June 4 pre-incident snapshot saved at `~/.hermes/state-snapshots/20260604-023854-pre-update`.

---

### Phase 13-V: Verification Sprint — Status: MANDATORY CHECKPOINT (Not yet complete)
9-step integration test that MUST complete before ANY Phase 14+ work.

**Required steps:**
1. Bot comes online without errors
2. `/start` from Chairman Telegram → Rexxie responds
3. Test GOJ intake message → routing logs appear
4. Ollama API → `qwen3:14b-hermie` listed
5. LM Studio port 1234 → `nomic-embed-text-v1.5` available
6. Clause daily report → posts to Telegram
7. `rex_unified_enforcer.py` standalone → no import errors
8. `index.html` → all 17 tabs, no JS errors in console
9. MSU unlock with code `CHAIRMAN` → Finance panel → lock again

**⛔ GATE: No Phase 14+ work until this sprint passes.**

**Status:** ⚠️ NOT YET COMPLETE. Blocking Phase 14+.

---

### Phase 14: MultiContext_Ventures — Status: PLANNED
Four business contexts within a single REX installation.

**Planned scope:** GOJ (adult day care ops), sports_bar (BBG operations), web_design (GHS web presence), social_media (BBG/GHS social automation). Each context gets its own data namespace, agent routing, and UI theme.

**Dependency:** Phase 13-V must pass first.

**Status:** ⛔ Blocked by Phase 13-V. Not started.

---

### Phase 15: AgentForge — Status: PLANNED
Agent creation and management framework for spinning up new specialized agents.

**Planned scope:** Tooling to define, configure, deploy, and monitor new agents within the GHS system. Prerequisites: Phase 14 MultiContext foundation.

**Status:** ⛔ Planned. Not started.

---

### Phase 16: Claus / Manager-General + Unified Enforcer — Status: IN PROGRESS (Enforcer built, not activated)
Claus-as-Manager-General vision + activating the unified policy enforcer.

**What exists:** `rex_unified_enforcer.py` (858 lines) — written, annotated, verified. NOT yet imported by any file. One-line activation: in `rex_rexxie_telegram_bot.py` line 84, swap `from rex_policy_enforcer import PolicyEnforcer` for `from rex_unified_enforcer import UnifiedEnforcer as PolicyEnforcer`. Backward compatible — same interface.

**Phase 13-V carry-forwards (P16-CF):**
- P16-CF-1: 3 CRITICAL credential fixes (TOTP, API key, Telegram token) — ⚠️ OPEN
- P16-CF-2: Activate `rex_unified_enforcer.py` — ⚠️ READY TO ACTIVATE
- P16-CF-3: Phase 13-V verification sprint (9 steps) — ⚠️ OPEN

**Status:** 🔄 In progress. Unified enforcer ready but not activated. Phase 13-V blocking.

---

### Phase 17: WebRex_Topology — Status: PLANNED
Web topology layer — external-facing infrastructure, routing, and security.

**Planned scope:** Cloudflare tunnel hardening, gateway authentication proxy (auth proxy built as `CC_gateway_auth_proxy.py` — see TODAY'S CHANGES), WebAuthn/Face ID, JWT session management, rate limiting by tier, usage dashboard.

**Note:** `CC_gateway_auth_proxy.py`, `CC_gateway_watchdog.py`, `com.ghs.gateway-auth.plist`, `com.ghs.gateway-watchdog.plist` are already built and sitting in `~/Desktop/REX/` — they are Phase 17 work product awaiting Kato activation approval. See `CC_gateway_enhancement_proposal.md` for full activation checklist.

**Status:** 🔄 Files built, awaiting Kato activation approval. Not yet active.

---

### Phase 18: Claus Watchman — Status: COMPLETE / RUNNING
Claus-as-watchdog: persistent system monitor.

**What was built:** `com.hermes.claus-watchman.plist` — Claus Watchman LaunchAgent. Hermes IS Claus realized. Phase 18 = completing that vision as a running persistent monitor.

**Important history:** Claus was the concept BEFORE Hermes. Hermes IS the Claus vision realized. ShellCore (5-agent spine, FastAPI port 8081, Ed25519-signed governance, Tauri console) was a separate earlier prototype — Phase 1 complete, then SHELVED as "too early." ShellCore is NOT the 13-agent planned system.

**Status:** ✅ Running. `com.hermes.claus-watchman.plist` confirmed active.

---

### Phase 19: Jarvis HUD — Status: NOT RUNNING (Critical open item)
Real-time heads-up display for system state and operations.

**What exists:** TigerClaw API at port 27226 (`com.tigerclaw.api.plist` ✅ running) — M01–M24 stats endpoint. Tiger Claw Screensaver active (updated May 29). HUD website is the screensaver display. Connected to Jarvis data feed. LaunchAgent plists exist but are NOT loaded (exited clean). 

**Tiger Claw Screensaver:** Active. idle-monitor + hotcorner triggers. `com.tigerclaw.screensaver.plist` + `com.tigerclaw.hudsite.plist`.

**Planned tech stack for full 13-agent system (Phase 20+):** LangGraph · Ollama · Docker Compose (one container per agent) · Tauri (Command Console UI, Locker Room) · Tailscale (3-node WireGuard mesh) · SQLite WAL (Scribe ledger, hash-chained, encrypted).

**Planned 13-agent activation order (LOCKED):** Riggs → Archivist → Horizon → PostMaster → Spark → OCR → Jarvis → Luna.

**Status:** ❌ Not running. Plists exist, not loaded. Critical open item.

---

### Phase 20+: Full 13-Agent System — Status: PLANNED
The full planned agent roster (NOT yet built):

Claus (Chief of Staff), Sentinel (Egress Firewall), TechGuard (IT Integrity), The Chronicler (Scribe+Sage), Officer Riggs (Red-Team), IntegrityGuard, Horizon, The Archivist, PostMaster, Spark, OCR Vision Engineer, Jarvis (Video-Chat), Luna (Child Companion — LAST TO ACTIVATE, highest stakes).

**Status:** ⛔ Planned. Architecture locked. Not started.

---

## TODAY'S CHANGES (June 4, 2026)

### Changes Made

**1. Hermes Gateway Config Revert (~12:47 PM)**
- Problem: `hermes-workspace` desktop app modified `~/.hermes/config.yaml`, injected ~1.2KB of content breaking DeepSeek routing.
- Fix: Reverted using `~/.hermes/state-snapshots/20260604-023854-pre-update/config.yaml`.
- Backup at: `~/.hermes/config.yaml.bak.20260604_124719` (PRE-INCIDENT SAFE VERSION).
- Script: `CC_hermes_revert.command` ✅ Run successfully.
- Rule: `hermes-workspace` desktop app must NOT write to `~/.hermes/config.yaml`.

**2. Dock Autohide Fix (Permanent)**
- Problem: Dock kept disappearing. Dual cause: System Settings autohide ON + `com.ghs.dock-fix.plist` calling `killall Dock` every 5 min.
- Fix: System Settings → Dock & Menu Bar → Autohide → OFF. Removed `killall Dock` from LaunchAgent interval script.
- Script: `CC_fix_dock_permanent.command` ✅ Run.

**3. Chrome Keychain Error Fix**
- Problem: Chrome showing "Keychain Not Found" — `login.keychain` not set as default.
- Script: `CC_fix_keychain.command` ✅ Run. Chrome restarted clean.

**4. Killed com.hermes.rexxie-bot Zombie**
- Problem: `com.hermes.rexxie-bot.plist` was actively running (PID 1803), stealing Rexxie's Telegram token.
- Fix: `launchctl unload` + `pkill -f rexxie-bot`. Confirmed killed.
- ⚠️ PERMANENT RULE: This plist stays DISABLED FOREVER. Never re-enable.

**5. System Audit Run (June 4, 2026)**
- Tailscale: ✅ Running — connected (100.98.90.26, iPhone 100.80.16.53 connected)
- Ollama: ✅ Running — `gemma4:26b` (17GB, NEW TODAY), `mistral-hermie`, `qwen3:14b-hermie`, `minicpm-v`, `mistral-small`, `llama3.1:8b`
- Karpathy AutoResearch: ⚠️ Exists at `~/Documents/autoresearch` (not expected `~/Desktop/autoresearch`)
- Obsidian: ✅ 4 vaults found (GHS BRAIN, Chairman Second Brain iCloud, Chairman Second Brain local, GHS-Vault)
- Service health: REX 8000 ✅, Hermes 3002 ✅, GOJ 8080 ⚠️ (running but /health route 404)

### Files Created Today

| File | Path | Status |
|------|------|--------|
| `CC_hermes_revert.command` | `~/Desktop/REX/` | ✅ Run |
| `CC_fix_keychain.command` | `~/Desktop/REX/` | ✅ Run |
| `CC_fix_dock_permanent.command` | `~/Desktop/REX/` | ✅ Run |
| `CC_google_oauth_fix.command` | `~/Desktop/REX/` | ⚠️ Created, NOT yet run |
| `CC_hermes_change_log_2026.md` | `~/Desktop/REX/` | ✅ Created |
| `CC_hermes_goj_knowledge.md` | `~/Desktop/REX/` | ✅ Created |
| `CC_audit_report_june4.md` | `~/Desktop/REX/` | ✅ Created |
| `CC_gateway_auth_proxy.py` | `~/Desktop/REX/` | ✅ Built (Phase 17, not yet activated) |
| `CC_gateway_watchdog.py` | `~/Desktop/REX/` | ✅ Built (Phase 17, not yet activated) |
| `com.ghs.gateway-auth.plist` | `~/Desktop/REX/` | ✅ Built (not yet installed) |
| `com.ghs.gateway-watchdog.plist` | `~/Desktop/REX/` | ✅ Built (not yet installed) |
| `CC_gateway_enhancement_proposal.md` | `~/Desktop/REX/` | ✅ Created (activation checklist) |
| `CC_MASTER_BUILD_LOG.md` | `~/Desktop/REX/` | ✅ This file |

### Currently Building
- **Command Center Phase 2** — `CC_command_center_PHASE2_PLAN.md` written. Execution order: P2-B (Bills JSON) → P2-F (Calendar Sync) → P2-C (TTS) → P2-D (Live Skill Events) → P2-E (Tiger Claw full) → P2-A (Electron wrapper) → P2-G (Obsidian). None activated yet.
- **Gateway Auth Enhancement (Phase 17)** — Files built (`CC_gateway_auth_proxy.py`, etc.), awaiting Kato activation approval per PAE.

### Pending Actions (PAE-blocked, awaiting Kato)

| Action | File | What it does |
|--------|------|-------------|
| Run Google OAuth fix | `CC_google_oauth_fix.command` | Fixes Gmail token expiry (forces offline refresh_token) |
| Approve gateway quarantine | `CC_quarantine_proposal.txt` | Move `hermes-workspace.app` to quarantine |
| Switch hermie-local to gemma4:26b | Config change | `gemma4:26b` (17GB) now installed, ready |
| Activate gateway auth proxy | `CC_gateway_auth_proxy.py` → port 3005 | Phase 17 deployment |
| Activate unified enforcer | `rex_unified_enforcer.py` | Phase 16 completion — one-line swap in bot |
| Unload hermes-workspace LaunchAgents | `com.hermes.cloud-workspace.plist`, `com.hermes.workspace.plist` | Stop auto-restart of problematic desktop app |

---

## ACTIVE STACK (Mac Mini M4, 24GB, `mainsobhelper`)

| Service | Port | Manager | June 4 Status |
|---------|------|---------|---------------|
| Hermes cloud gw | 3002 | `ai.hermes.gateway-cloud.plist` | ✅ Running — 15 sessions, 1019 req, ~17.5h uptime |
| Hermes local gw (Hermie) | 65001 | `ai.hermes.gateway.plist` | ⚠️ Repairing — switching to mistral-hermie |
| REX FastAPI (Nemobot) | 8000 | `com.rex.backend.plist` | ✅ Running — v3.0.0 |
| GOJ Dashboard (Flask) | 8080 | `com.goj.datarex.plist` | ✅ Running — /health returns 404 (route issue, server OK) |
| TigerClaw API | 27226 | `com.tigerclaw.api.plist` | ✅ Active |
| Open WebUI | 3000 | `ai.openwebui.hermes.plist` | Docker. PID 72079 listed May 30. |
| LibreChat | 3080 | Docker | ❌ Not running by design |
| Hermes AI Hub | 3003 | Docker | — |
| Hermes Kanban | 9119 | launchd | — |
| Hermes Portal | 3847 | launchd | Landing page |
| Claus Watchman | — | `com.hermes.claus-watchman.plist` | ✅ Running |
| n8n | — | `com.goj.n8n.plist` | ✅ 6 live workflows |
| Kapso WhatsApp | 18789 | `com.hermes.kapso-whatsapp.plist` | — |
| Phone Unlock | 8765 | launchd | — |
| Ollama | 11434 | local | ✅ Running — 7 models |
| LM Studio | 1234 | local | ❌ Not running today |
| Cloudflare tunnel | — | `~/.cloudflared/hermestigerclaw.yml` | ✅ Active |
| Tailscale VPN | — | system extension | ✅ Connected |

**⚠️ Two Hermes installs:**
- `~/.hermes/` — main gateway source, cloud profile (THIS is Hermes)
- `~/.hermes-cloud/` — BBG social pipeline + GOJ datarex

**Restart any Hermes gateway:**
```bash
launchctl unload <plist>
pkill -f "hermes_cli.main.*gateway"
sleep 8
launchctl load <plist>
```
Always include `pkill` — `launchctl unload` alone causes Telegram token conflicts.

**Model Routing:**

| Role | Model | Provider |
|------|-------|---------|
| Primary | `deepseek-v4-pro` | `https://api.deepseek.com/v1` DIRECT — NEVER OpenRouter |
| Orchestration/fallback | `claude-sonnet-4-6` | Anthropic |
| Fallback 2 | `gemini-2.0-flash` | Google |
| Fallback 3 | `moonshotai/kimi-k2.6:free` | OpenRouter (non-DeepSeek only, 262K context) |
| High-stakes | `claude-opus-4-6` | Anthropic |
| Cheap reasoning | `grok-3-mini` | xAI |
| Local default | `mistral-hermie` | Ollama :11434 |
| Local code | `qwen2.5-coder:7b` | Ollama :11434 |
| Local primary (LM Studio) | `qwen3.5-9b` | LM Studio :1234 (MLX) |

---

## OPEN ITEMS BY PRIORITY

### 🔴 Critical (Blocking or HIPAA Risk)

| # | Item | Notes |
|---|------|-------|
| 1 | **TransitionAgent Drive hook NOT built** | Bookkeeper left May 31. Deadline ~June 7. Drive monitoring hook missing — transition tracking broken. `com.goj.transition-agent.plist` loaded May 28 but hook not wired. |
| 2 | **QuickBooks handoff** | New bookkeeper taking over. Capture workflow, export from QuickBooks. Deadline ~June 7. |
| 3 | **auth_tracker.db NOT SQLCipher encrypted** | 426 clients of PHI in unencrypted SQLite. Top HIPAA priority. |
| 4 | **akc_tokenizer.py Gate 1 = skeleton only** | HARD BLOCK on all cloud PHI routing until built. Located at `~/Desktop/dashboard/akc_tokenizer.py`. |
| 5 | **Disclosure tier auth gate = advisory only** | Any Telegram user can request sensitive GOJ data. Must wire enforcement in `private_confidant_gold.py`. |
| 6 | **Hermes-workspace LaunchAgents unloaded** | `com.hermes.cloud-workspace.plist` + `com.hermes.workspace.plist` will auto-restart the app that corrupted config.yaml. Quick fix: `launchctl unload` both (1 min, reversible, no approval needed). |
| 7 | **Google OAuth token** | `CC_google_oauth_fix.command` created but NOT run. Gmail scanner broken when token expires (~10 min). |
| 8 | **TOTP secret = RFC example value** | `JBSWY3DPEHPK3PXP` in `core/enforcer.py` + `rex_sqlcipher_vault.py`. Zero real security. Must rotate immediately. |

### 🟡 High Priority

| # | Item | Notes |
|---|------|-------|
| 9 | **Jarvis Phase 19 not running** | Plists exist, not loaded. Real-time HUD dead. |
| 10 | **victoria/Masha (Retell) 404** | Likely expired Retell API key. GOJ confirmation calls not working. |
| 11 | **rex_memory.db + rex_user_model.db both 0KB** | One-line fix in `backend/memory.py`. Rexxie and REX start cold every session — no learned context. |
| 12 | **Phase 13-V verification sprint not done** | 9-step integration test required before Phase 14+. GATE is in place. |
| 13 | **hermes-workspace quarantine** | App modified config.yaml; proposal at `CC_quarantine_proposal.txt`. Awaiting Kato approval. |
| 14 | **Evening/Nextday launchd jobs failing** | Using `~/Desktop/REX/.venv/` — macOS TCC blocks Desktop venv from launchd. Fix: update plists to use `~/.rex-venv/` instead. |
| 15 | **Railway DB not synced to local auth_tracker.db** | Known regression. Two databases diverging. |

### 🟢 Active Building

| # | Item | Notes |
|---|------|-------|
| 16 | **Command Center Phase 2** | Plan written. 7 sub-items (Bills, Calendar, TTS, Live Skills, Tiger Claw, Electron, Obsidian). None started. |
| 17 | **Gateway Auth Enhancement (Phase 17)** | Files built, awaiting Kato approval to activate. |
| 18 | **Hermes local gw / Hermie repair** | `mistral-hermie` model built, port 65001 still not reliable. `gemma4:26b` now available as alternative. |
| 19 | **Activate rex_unified_enforcer.py** | One-line swap. Ready to do when Kato says go. |
| 20 | **Switch hermie-local to gemma4:26b** | Model installed today (17GB). Awaiting Kato approval. |

### ⚪ Planned / Someday

| # | Item | Notes |
|---|------|-------|
| 21 | **MemPalace wiring** | `palace_main.db` + `palace_cloud.db` on `/Volumes/cartoons/`. Never connected. Tier 1 repo. Install: `uv tool install mempalace`. |
| 22 | **hermes-dreaming plugin** | Most important Hermes plugin: `hermes plugins install asimons81/hermes-dreaming --enable`. Not yet installed. |
| 23 | **ECC install** | Kato's #1 repo priority: `bash install.sh` or `npx ecc-universal install`. 60 agents, 232 skills. |
| 24 | **iMessage watcher** | Monitors 3 GOJ group chats via iPad-Mac Mini connection. NOT built. Needed for 7-System Cascade trigger. |
| 25 | **Fireflies activation** | Wired but inactive. API key likely in Keychain. Use: meeting transcription → Obsidian. |
| 26 | **Phase docs library** | One DOCX per phase, all phases 1–current. Requested by Kato Apr 16. Never built. |
| 27 | **Command Panel + iOS App guide** | Standalone setup guide requested Apr 16. Never built. |
| 28 | **Patter phone alerting** | Agent phone number for alerting Kato via call/SMS. Not configured. |
| 29 | **TOTP rotation** | See 🔴 item #8 — rotate RFC example TOTP secret. |
| 30 | **Port audit** | Ports assigned ad hoc. Verify all active, document conflicts, deprecate defunct. |

---

## ALL CC_ BUILD ARTIFACTS

### Documentation Files
| File | Purpose | Status |
|------|---------|--------|
| `CC_MASTER_BUILD_LOG.md` | This file — definitive system reference | ✅ Active |
| `CC_HERMES_KNOWLEDGE.md` | Full operational reference — all Q&A rounds + verified state | ✅ Reference |
| `CC_KNOWLEDGE_STATE_May31_2026.md` | May 31 knowledge state snapshot | ✅ Archive |
| `CC_SESSION_LOG_2026-05-31.md` | May 31 full session capture | ✅ Archive |
| `CC_SESSION_HANDOFF_May31_2026.md` | May 31 → June 4 handoff doc | ✅ Reference |
| `CC_SESSION_MASTER_BACKUP_May31_2026.md` | May 31 session backup | ✅ Archive |
| `CC_DIAGNOSTIC_REPORT_20260601.md` | June 1 autonomous diagnostic | ✅ Archive |
| `CC_audit_report_june4.md` | June 4 system audit | ✅ Active |
| `CC_hermes_change_log_2026.md` | Running change log | ✅ Active |
| `CC_hermes_goj_knowledge.md` | GOJ-specific knowledge | ✅ Active |
| `CC_command_center_PHASE2_PLAN.md` | Phase 2 plan for Command Center | ✅ Planning |
| `CC_gateway_enhancement_proposal.md` | Phase 17 gateway auth — activation checklist | ✅ Planning |
| `CC_PHASE_STATUS.md` | Phase tracker (companion to this file) | ✅ Active |
| `CC_DOCUMENTATION_AGENT_README.md` | How to update and maintain docs | ✅ Active |

### SOUL/MEMORY Drafts
| File | Purpose | Status |
|------|---------|--------|
| `CC_SOUL_DRAFT_v5.2.md` | Latest SOUL.md draft | ✅ Installed as of Jun 1 |
| `CC_MEMORY_DRAFT.md` | MEMORY.md working draft | ✅ Reference |
| `CC_MEMORY_FINAL.md` | MEMORY.md final installed | ✅ Installed |

### Scripts (Command Files)
| File | Purpose | Status |
|------|---------|--------|
| `CC_hermes_revert.command` | Revert Hermes config to pre-incident state | ✅ Run Jun 4 |
| `CC_fix_keychain.command` | Fix Chrome keychain error | ✅ Run Jun 4 |
| `CC_fix_dock_permanent.command` | Permanent dock autohide fix | ✅ Run Jun 4 |
| `CC_google_oauth_fix.command` | Fix Gmail OAuth permanent refresh token | ⚠️ NOT YET RUN |
| `CC_june4_backup_run.command` | Complete Mac-side backup | ⚠️ NOT YET RUN |
| `CC_audit_runner.command` | System audit script | ✅ Run Jun 4 |
| `CC_bot_fix_20260604_180806.command` | Bot fix script | ✅ Run Jun 4 |
| `CC_RUN_OCR.command` | OCR pipeline runner | ✅ Active |
| `CC_RUN_CLEANUP.command` | Cleanup script | ✅ Active |
| `CC_backup_to_drive.command` | Google Drive backup | ✅ Active |
| `CC_backup_to_external.command` | External drive backup | ✅ Active |
| `CC_ecc_install_claude.command` | ECC install via Claude Code | ✅ Ready (not run) |
| `CC_phase2_work.command` | Command Center Phase 2 work | — |

### Phase 17 (Built, Awaiting Activation)
| File | Purpose | Status |
|------|---------|--------|
| `CC_gateway_auth_proxy.py` | FastAPI auth proxy, port 3005 | ✅ Built, NOT active |
| `CC_gateway_watchdog.py` | Auto-restart daemon for gateway :3002 | ✅ Built, NOT active |
| `com.ghs.gateway-auth.plist` | LaunchAgent for auth proxy | ✅ Built, NOT installed |
| `com.ghs.gateway-watchdog.plist` | LaunchAgent for watchdog | ✅ Built, NOT installed |

### Command Center
| File | Purpose | Status |
|------|---------|--------|
| `CC_command_center.html` | Command Center Phase 1 web app | ✅ Complete — Phase 1 done |
| `CC_command_center_launcher.command` | Launch Command Center | ✅ Active |
| `CC_config_current.yaml` | Current Hermes config snapshot | ✅ Reference |
| `CC_config_pre_incident.yaml` | Pre-incident Hermes config (safe version) | ✅ Recovery reference |
| `CC_config_diff_june4.txt` | Diff showing what hermes-workspace changed | ✅ Evidence |

---

## KEY DECISIONS LOG

| Date | Decision | Rationale | Approved by |
|------|---------|-----------|-------------|
| Mar 2026 | Claude Vision as primary OCR (D-001) | Better accuracy than Tesseract for scanned PDFs, handles handwriting/rotation | Kato (inferred) |
| Mar 2026 | Consensus voting for OCR (D-002) | Single Claude call hallucination risk; voting reduces false positives | Kato (inferred) |
| Apr 2026 | FRESH_START command (D-003) | Recovery without nuking DB — resets auth only, preserves all data | Kato |
| Apr 2026 | FIX_REXXIE command (D-004) | Atomic restart of all services when one hangs | Kato |
| Apr 2026 | Memory Steward added (D-007) | REX forgetting preferences between sessions | Kato |
| Apr 2026 | Prompt Registry governance (Phase 10) | All prompts = governed assets with versioning, approval tiers, rollback | Kato |
| Apr 2026 | CLS v3 two-tier learning (Phase 9) | Prevent uncontrolled drift; zero silent memory writes | Kato |
| Apr 2026 | PAE Engine production rule | No real-world action without Chairman authorization | Kato |
| Apr 2026 | ShellCore shelved | "Too early" — concept carried to Jarvis Phase 19 | Kato |
| May 2026 | Source-of-truth architecture | BRAIN/MASTER.md = ONE truth; all docs derive from it | Kato |
| Jun 4 2026 | hermes-workspace blocked | App corrupted config.yaml; LaunchAgents pending unload | Pending |
| Jun 4 2026 | DeepSeek direct-only rule | NEVER via OpenRouter; always `provider: deepseek` + `base_url: https://api.deepseek.com/v1` | Kato |

---

## KNOWN ISSUES & WORKAROUNDS

| Issue | Severity | Workaround | Fix Status |
|-------|---------|-----------|-----------|
| `com.hermes.rexxie-bot.plist` zombie | 🔴 | Keep DISABLED FOREVER. Never re-enable. | ✅ Permanent rule |
| hermes-workspace modifies config.yaml | 🔴 | `CC_hermes_revert.command` to restore; unload LaunchAgents | ⚠️ Workaround in place, quarantine pending |
| rex_memory.db 0KB | 🟡 | Rexxie starts cold (no persistent memory) | ⚠️ One-line fix pending |
| rex_user_model.db 0KB | 🟡 | User model cold every session | ⚠️ Same fix as above |
| Hermie local gw (port 65001) unreliable | 🟡 | Use cloud gateway :3002 | 🔄 mistral-hermie repair in progress |
| launchd Evening/Nextday jobs failing | 🟡 | Run manually from dev venv | ⚠️ Update plists to use `~/.rex-venv/` |
| GOJ Dashboard /health returns 404 | 🟢 | Use direct URL; server IS running | ⚠️ Flask routing issue |
| TOTP = RFC example value | 🔴 | No workaround — real security gap | ⚠️ Rotation pending |
| Disclosure tier advisory only | 🔴 | Monitor access manually | ⚠️ Engineering fix pending |
| Railway DB out of sync | 🟡 | Use local auth_tracker.db | ⚠️ Sync not yet built |
| Gmail token expires ~10 min | 🟡 | `CC_google_oauth_fix.command` ready | ⚠️ NOT YET RUN |
| LM Studio not running today | 🟢 | Use Ollama models | ⚠️ Start manually when needed |

---

## AGENT ROSTER

| Agent | Bot/Handle | Port | Status | Role |
|-------|-----------|------|--------|------|
| **Hermes** | `@Hermes_Cloud_May_bot` | 3002 | ✅ Running | Primary AI gateway. DeepSeek-v4-pro primary. Cloud profile. THIS file's author. |
| **Hermie** | `@HermieChatt_bot` | 65001 | ⚠️ Repairing | Local Ollama gateway. mistral-hermie. Context floor bug. |
| **Rexxie (4 lanes)** | `@goldhealth_rexxie_bot` | — | ✅ Running | Private confidant + GOJ ops. Lane 2 = local-only ALWAYS. rexxie.db isolated. |
| **Nemobot (REX)** | — | 8000 | ✅ Running | REX FastAPI. LiteLLM router. PAE engine. |
| **Claus** | — | — | ✅ Watchman active | Chief of Staff concept realized as Hermes + Watchman. |
| **Jarvis** | — | 27226 (TC) | ❌ Not running | Real-time HUD. Phase 19. Plists exist, not loaded. |
| **Victoria** | GOJ M12 | — | ⚠️ 404 | Retell AI. Appointment confirmations. Phone: 347-587-9913. Likely expired API key. |
| **Masha** | BBG persona | — | ⚠️ 404 | Retell AI. Same 404 issue as Victoria. |
| **TransitionAgent** | — | — | ✅ Plist loaded | `com.goj.transition-agent.plist` loaded May 28. Drive hook NOT built. |
| **Red Team** | — | — | ✅ Built | `rex_red_team.py`. 60% random probe sample → Rexxie Telegram. |
| **Blue Team** | — | — | ✅ Built | `rex_blue_team.py`. Self-evolving. Audits Red Team, auto-generates probes. |
| **@RexOfGold_bot** | GOJ ops | — | ❌ 404 loop | Bot may have been deleted from BotFather. Check /mybots. |
| **@GOJReceipts_bot** | Billing | — | ✅ Active | Billing/bookkeeping uploads. |
| **@GojAttendance_bot** | Attendance | — | ✅ Active | Attendance stats. |

**Planned (Phase 20+, NOT YET BUILT):** Claus (Chief of Staff), Sentinel (Egress Firewall), TechGuard, The Chronicler, Officer Riggs, IntegrityGuard, Horizon, The Archivist, PostMaster, Spark, OCR Vision Engineer, Jarvis (Video-Chat), Luna (Child Companion — LAST, highest stakes).

---

## DATA SOURCES

| Source | Type | Path | Contents | Notes |
|--------|------|------|----------|-------|
| `auth_tracker.db` | SQLite | `~/Documents/goj files/dashboard/auth_tracker.db` | 426 clients, authorizations, menus, employees, schedule changes | NOT SQLCipher. PHI. Never to cloud. |
| `rexxie.db` | SQLite | `~/Desktop/REX/rexxie.db` | Rexxie private conversations | 100% isolated. Zero GOJ data. Local ONLY. |
| `rex_memory.db` | SQLite | `~/Desktop/REX/data/` | REX persistent facts | ⚠️ 0KB broken |
| `rex_user_model.db` | SQLite | `~/Desktop/REX/data/` | User preferences, model tiers | ⚠️ 0KB broken |
| `rex_events.db` | SQLite | `~/Desktop/REX/data/` | Alert bus events | Active |
| `cls_v3_patterns.db` | SQLite | `~/Desktop/REX/data/vaults/` | CLS learning patterns | Active |
| `prompt_usage.db` | SQLite | `~/Desktop/REX/data/vaults/` | Prompt load event history | Active |
| `palace_main.db` | SQLite | `/Volumes/cartoons/` | MemPalace main database | Dormant — never wired |
| `palace_cloud.db` | SQLite | `/Volumes/cartoons/` | MemPalace cloud sync | Dormant |
| `webui.db` | SQLite | Open WebUI data | Open WebUI chat history | Active via Docker |
| `master_list.json` | JSON | `~/Desktop/REX/` | Build registry — all components and status | Read by `rex_coordinator.py` |
| `state/prompt_registry.json` | JSON | `~/Desktop/REX/state/` | 15 governed prompts with metadata | Active |
| `state/prompt_audit.log` | Log | `~/Desktop/REX/state/` | Append-only prompt change history | Active |
| Gmail / Google Drive | Cloud | `atigerclawai@gmail.com` | Menu scan intake, Drive backup, templates | OAuth: `~/.rex_google_token.json` |
| Obsidian Vault | Local | `~/Desktop/Gold_Health_Systems/BRAIN/` | MASTER.md + GHS documentation | Primary vault |
| GHS-Vault | Local | `~/Documents/GHS-Vault/` | Extended documentation | Secondary vault |
| NotebookLM | Cloud | One-directional bridge | ghs-strategy ~268K chars, goj-ops ~1.27M chars | Read-only from GHS side |
| OCR Google Drive templates | Cloud | Drive `templates/` folder | Doc type recognition templates | LOCKED — do not move/rename |

---

## SECURITY STATUS

| Control | Status | Gap |
|---------|--------|-----|
| Presidio de-id on outbound | ✅ Active | — |
| AES-256-GCM Rexxie messages | ✅ Active | — |
| SQLCipher vault (`rex_sqlcipher_vault.py`) | ✅ Built | Not applied to auth_tracker.db yet |
| ChaCha20 for large blobs | ✅ Active | — |
| Master keys in macOS Keychain | ✅ Active | — |
| RBAC via `rex_permissions.py` (4 tiers) | ✅ Active | Disclosure tier not enforced (advisory) |
| PHI firewall (5 layers) | ✅ Framework built | Gate 1 (akc_tokenizer.py) = skeleton only |
| auth_tracker.db encryption | ❌ NOT ENCRYPTED | Top HIPAA gap — plain SQLite |
| TOTP secret | ❌ RFC EXAMPLE VALUE | Must rotate immediately |
| Disclosure tier enforcement | ❌ ADVISORY ONLY | Any Telegram user can request sensitive data |
| Telegram bot token | ⚠️ Rotated Jun 4 | Confirm no plaintext copies remain |
| Anthropic API key in .env | ⚠️ Present | Add .env to backup exclusion |

---

## HARDWARE TOPOLOGY

| Node | Spec | Status | Role |
|------|------|--------|------|
| Mac Mini M4 | 24GB RAM, M4 chip, `mainsobhelper` | ✅ PRIMARY | All production services. Main dev machine. |
| Alienware Aurora R8 | 32GB RAM, RTX 2070, home | 📋 Planned | IRONWALL node. Pop!_OS. Not yet integrated. |
| Office Mac | 16GB RAM | 📋 Planned | Work gateway. Air-gapped from GOJ data. Not set up. |
| iPad | — | ✅ Connected via Tailscale | Connected to Mac Mini; basis for planned iMessage watcher. |
| iPhone | — | ✅ Tailscale (100.80.16.53) | Kato's primary mobile interface. |
| External drive | 581GB free, `/Volumes/cartoons/` | ✅ Active | Nightly backups 2AM, 7-day rolling. palace_main.db + palace_cloud.db here. |
| Misha's machine | — | Paperless-ngx @ 100.99.86.60:8000 | Office scan processing. Tailscale offline 7d. |

---

## GOJ OPERATIONS REFERENCE

### Authorization Status Rules
- `ACTIVE` = may attend. Schedule normally.
- `EXPIRED` = do not schedule WITHOUT Kato.
- `PENDING RENEWAL` = submitted, may continue attending.
- `EXPIRED` >30 days with no `PENDING RENEWAL` → escalate IMMEDIATELY to Kato, flag in report, do NOT remove from schedule.

### 7-System Schedule Change Cascade (ATOMIC — all 7 or none)
When any client changes day, calls sick, or won't attend:
1. Calendar · 2. Attendance records · 3. Driver's list · 4. Kitchen's list · 5. Distribution logs · 6. Sign-in sheets · 7. Client's individual menu

### Menu Pipeline
Russian 2-page form, 425 clients, submitted 1 week ahead, Mon–Sat only. 4-engine OCR consensus: Tesseract + Google Drive Vision + Paperless-ngx + Claude Vision. Low-confidence entries flagged to Rexxie. DB column = `main` (NOT `main_dish`). OCR templates in Google Drive `templates/` folder = LOCKED OCR dependency.

### Daily Automation Schedule (via @goldhealth_rexxie_bot)
| Time | Job |
|------|-----|
| 7:30 AM | Morning report |
| 10:30 AM | Kitchen + distribution sheets (2-page PDFs) |
| 3:15 PM | Sign-in + driver sheets |
| 8:30 PM (Fri) | Missing menus alert |
| 9:00 PM | Drop-off rundown — target: "no decisions necessary" |
| 9:00 PM (Fri) | Weekly email summary |

### Permanent Rules
- **Larry** never appears on any transport or driver list — not in any context, not under any instruction.
- **DeepSeek** always routes direct: `provider: deepseek` + `base_url: https://api.deepseek.com/v1`. NEVER OpenRouter.
- **PHI stays local.** `auth_tracker.db` never reaches cloud. Presidio de-id runs on all outbound data.
- **Rexxie's private lane** is local-only and never divulges its contents.
- **No real-world action without PAE.** Propose → Approve → Execute. No exceptions for production.
- **GOJ client names, medical data, and financials** never enter OG 33 prompts.
- **`akc_tokenizer.py` = Gate 1** — hard block on all cloud PHI routing until fully built.
- **`com.hermes.rexxie-bot.plist`** is a zombie — NEVER enable it. Crashes and steals Rexxie token.
- **Two dashboards:** LIVE = `~/.hermes-cloud/home/goj-pipeline/datarex/app.py` (port 8080); `~/Documents/goj files/dashboard/app.py` = NOT running.

---

## CRITICAL FILE PATHS

| What | Path |
|------|------|
| Source of truth | `~/Desktop/Gold_Health_Systems/BRAIN/MASTER.md` |
| This file | `~/Desktop/REX/CC_MASTER_BUILD_LOG.md` |
| CLAUDE.md (agent governer) | `~/Desktop/REX/CLAUDE.md` |
| Dashboard LIVE | `~/.hermes-cloud/home/goj-pipeline/datarex/app.py` |
| Dashboard DB | `~/Documents/goj files/dashboard/auth_tracker.db` |
| Dashboard NOT live | `~/Documents/goj files/dashboard/app.py` |
| REX scripts | `~/Desktop/REX/` |
| REX logs | `~/Desktop/REX/logs/` |
| Working doc | `~/Documents/goj files/GOJ_WORKING_DOC.md` |
| REX venv (dev) | `~/debate-chamber/.venv/` |
| REX venv (launchd) | `~/.rex-venv/` |
| Hermes source | `~/.hermes/hermes-agent/` (v0.15.1) |
| Hermes config | `~/.hermes/profiles/cloud/config.yaml` |
| Hermes SOUL | `~/.hermes/profiles/cloud/memories/SOUL.md` |
| Hermes MEMORY | `~/.hermes/profiles/cloud/memories/MEMORY.md` |
| Hermes .env | `~/.hermes/profiles/cloud/.env` |
| Rexxie DB | `~/Desktop/REX/rexxie.db` |
| Build registry | `~/Desktop/REX/master_list.json` |
| Knowledge archive | `~/Desktop/REX/CC_HERMES_KNOWLEDGE.md` |
| GOJ Master Routes | `~/Desktop/Gold_Health_Systems/GOJ_Master_Routes (1).json` |
| Google credentials | `~/Desktop/REX/google_credentials.json` (symlinked from `~/.rex_google_credentials.json`) |
| Gmail OAuth token | `~/.rex_google_token.json` |
| Rexxie config | `~/Desktop/REX/rex_rexxie_telegram_config.json` |
| External drive | `/Volumes/cartoons/` |
| GHS BRAIN vault | `~/Desktop/Gold_Health_Systems/BRAIN/` |
| GHS-Vault (Obsidian) | `~/Documents/GHS-Vault/` |
| Pre-incident config | `~/.hermes/config.yaml.bak.20260604_124719` |
| Hermes state snapshot | `~/.hermes/state-snapshots/20260604-023854-pre-update` |

---

## DEV COMMANDS REFERENCE

```bash
# Health checks
curl -s http://localhost:8080/health && curl -s http://localhost:8000/health

# Service status
launchctl list | grep -E "hermes|rex|goj"

# Restart Hermes cloud gateway
launchctl unload ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist
pkill -f "hermes_cli.main.*gateway" && sleep 8
launchctl load ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist

# Tail gateway log
tail -f ~/.hermes/profiles/cloud/logs/gateway.log

# Database
sqlite3 "~/Documents/goj files/dashboard/auth_tracker.db" ".tables"

# Activate dev venv
source ~/debate-chamber/.venv/bin/activate

# Verify REX venv
~/.rex-venv/bin/python --version

# Check Ollama models
curl -s http://localhost:11434/api/tags | python3 -m json.tool | grep name

# Run tests
source ~/debate-chamber/.venv/bin/activate
cd ~/Desktop/dashboard && python -m pytest tests/ -v
```

---

*Generated by Hermes Documentation Agent · June 4, 2026 · Gold Health Systems*
*Next update: At each session end, or when any phase status changes, or when a critical open item is resolved.*
