# MASTER BUILD LEDGER — REX/Rexxie Living Build History
**Document Date:** 2026-04-14 05:35 UTC  
**Scope:** Every major feature, subsystem, and architectural change from Jan 2026 to Apr 2026  
**Purpose:** Living record of what each major component does, why it was built, what it replaced, and what depends on it

---

## OCAML OCR PIPELINE SYSTEM

### Feature: OCR Consensus Vote
- **ID:** FEAT-OCR-001
- **Subsystem:** OCR Pipeline (Phase 1)
- **Name:** Multi-Claude Consensus Voting Engine
- **Current Status:** ACTIVE
- **Authoritative Files:** `goj_menu_consensus_ocr.py` (lines 30-60)
- **Last Major Change:** ~2026-03-20 (upgrade to consensus voting)
- **What It Does:**
  - Takes a single menu PDF from Gmail
  - Runs Claude Vision 3x to extract menu items, quantities, allergens
  - Scores each run (completeness, confidence, field validity)
  - Picks the highest-scoring result
  - Returns JSON with item list
- **What Was Replaced:** Single-pass OCR (file: `_archive/old_ocr_scripts/goj_direct_ocr_reader.py`)
- **Why It Changed:** Single pass hallucinations (e.g., inventing allergens, doubling quantities); voting reduces false positives
- **What Was Lost:** Speed (now 3x slower, ~45 sec/menu vs ~15 sec)
- **Contradiction Risk:** MEDIUM — if time budget is critical, might need single-pass mode
- **Recovery Notes:** Can reduce voting iterations from 3 to 1 by removing loop; trade accuracy for speed
- **Dependencies:** Claude Vision API key (in `.env` or Keychain)

### Feature: OCR Flag Processor
- **ID:** FEAT-OCR-002
- **Subsystem:** OCR Pipeline (Phase 4 Gauntlet)
- **Name:** Vision Result Review Gate
- **Current Status:** ACTIVE
- **Authoritative Files:** `rex_vision_flag_processor.py` (all of it)
- **Last Major Change:** ~2026-04-05 (added to prevent bad OCR reaching production)
- **What It Does:**
  - Runs post-OCR on consensus output
  - Checks for: confidence < 70%, missing required fields, policy violations (forbidden items), allergen contradictions
  - Flags low-confidence items; stores in `/data/ocr_quarantine/`
  - Approved items move to `/data/gauntlet_reports/`
  - Chairman reviews in Command Center
- **What Was Replaced:** Direct OCR→production (no review)
- **Why It Changed:** OCR edge cases and policy violations needed human review before affecting participants
- **Contradiction Risk:** LOW — safety feature; no downside
- **Recovery Notes:** Items in quarantine are not active; safe to leave there indefinitely
- **Dependencies:** `goj_menu_consensus_ocr.py`

### Feature: OCR Schema Validation
- **ID:** FEAT-OCR-003
- **Subsystem:** OCR Pipeline (Phase 1)
- **Name:** Menu Item Schema Enforcer
- **Current Status:** ACTIVE
- **Authoritative Files:** (embedded in `goj_menu_consensus_ocr.py`)
- **Last Major Change:** ~2026-03-18 (added schema validation)
- **What It Does:**
  - Defines required fields: `name`, `quantity`, `unit`, `allergens[]`
  - Validates each Claude output against schema
  - Rejects hallucinated fields (e.g., "color", "temperature")
  - Type-checks quantities (must be numeric)
- **Contradiction Risk:** LOW — enforces correctness
- **Recovery Notes:** If schema is too strict, loosen validators; if too loose, tighten them

---

## CLAUDE VISION FAST-PATH

### Feature: Claude Vision as Primary OCR
- **ID:** FEAT-VISION-001
- **Subsystem:** OCR Vision
- **Name:** Claude Vision API Integration
- **Current Status:** ACTIVE
- **Authoritative Files:** `goj_menu_consensus_ocr.py` (Claude Vision calls)
- **Last Major Change:** ~2026-03-15 (initial integration)
- **What It Does:**
  - Calls Claude Vision (claude-3-5-sonnet by default) to extract text from menu PDFs
  - Handles rotation, skew, handwritten notes
  - More accurate than Tesseract for natural images
- **What Was Replaced:** Tesseract OCR (local, free, but lower accuracy)
- **Why It Changed:** Menu PDFs have poor scan quality, handwritten notes, rotated text; Tesseract struggles; Vision handles it
- **What Was Lost:** Local-only operation (Vision requires API key + internet)
- **Contradiction Risk:** HIGH if Vision API becomes unavailable (network, rate limit, key expiration)
- **Recovery Notes:** Tesseract is still installed; can revert to old scripts in `_archive/old_ocr_scripts/` if Vision fails
- **Dependencies:** `ANTHROPIC_API_KEY` (in `.env` or Keychain)

---

## LUCY CORE: ALERT BUS, MEMORY STEWARD, GAUNTLET

### Feature: Phase 0 Alert Bus
- **ID:** LUCY-PHASE0-001
- **Subsystem:** Lucy Core (Observability)
- **Name:** Event Bus for Unresolved Items & Escalations
- **Current Status:** ACTIVE
- **Authoritative Files:** `/data/alert_bus_fallback.jsonl`, `/data/rex_events.db`
- **Last Major Change:** ~2026-04-01 (initial implementation)
- **What It Does:**
  - Logs all exceptions, policy violations, red flags
  - Stores in JSONL (streaming) and SQLite (queryable)
  - Chairman Command Center reads this to show red flags panel
  - Each event: timestamp, actor, event_type, severity, description
- **What Was Replaced:** Nothing (new feature)
- **Contradiction Risk:** LOW — purely informational; no side effects
- **Recovery Notes:** Safe to clear old entries; current events will continue to log
- **Dependencies:** None

### Feature: Phase 1 OCR Schema & Consensus
- **ID:** LUCY-PHASE1-001
- **Subsystem:** OCR Pipeline
- **Name:** Structured OCR Output + Consensus Voting
- **Current Status:** ACTIVE
- **Authoritative Files:** `goj_menu_consensus_ocr.py`
- **Last Major Change:** ~2026-03-20 (consensus voting)
- **What It Does:**
  - Validates OCR output against schema
  - Runs multiple passes and scores results
  - Returns best result with confidence score
- **Dependencies:** Claude Vision API

### Feature: Phase 2 Memory Steward
- **ID:** LUCY-PHASE2-001
- **Subsystem:** Lucy Core (Memory)
- **Name:** Persistent Memory for REX & Rexxie
- **Current Status:** **REGRESSION — CRITICAL**
- **Authoritative Files:** `rex_memory.db` (0K — EMPTY), `rexxie_memory.db` (60K), `backend/memory.py`
- **Last Major Change:** ~2026-03-25 (initial implementation)
- **What It Does:**
  - REX stores facts, user preferences, learned context in `rex_memory.db`
  - Rexxie stores chat context, user profiles in `rexxie_memory.db`
  - Before each Claude request, memory is queried and injected into system prompt
  - System learns from past interactions
- **Current Problem:** `rex_memory.db` is 0K (empty); memory is not being recalled
- **Per MEMORY.md:** "memory never recalled" is a critical open issue
- **What Was Replaced:** Stateless (no memory between sessions)
- **Why It Changed:** REX was forgetting user preferences and past decisions
- **Contradiction Risk:** CRITICAL — if memory isn't recalled, system has no learning
- **Recovery Notes:** Check if `backend/memory.py` RexMemory class is loading and recall() is being called; likely needs restoration from backup
- **Dependencies:** Both memory DBs

### Feature: Phase 3 Alert Router
- **ID:** LUCY-PHASE3-001
- **Subsystem:** Lucy Core (Routing)
- **Name:** Chairman Command Center Alert Routing
- **Current Status:** ACTIVE
- **Authoritative Files:** `backend/rex_command_center.py` (API routes), `/data/rex_events.db` (queries)
- **Last Major Change:** ~2026-04-01 (initial implementation)
- **What It Does:**
  - Routes alert_bus events to web UI
  - Chairman sees red flags panel (critical/high events)
  - Chairman sees unresolved queue
  - Chairman can resolve, escalate, or note each item
- **What Was Replaced:** Nothing (new feature)
- **Contradiction Risk:** LOW — routing layer only
- **Dependencies:** Alert Bus (Phase 0)

### Feature: Phase 4 Gauntlet
- **ID:** LUCY-PHASE4-001
- **Subsystem:** OCR Pipeline + Alert Bus (Review Gate)
- **Name:** Flagged Item Review & Approval Workflow
- **Current Status:** ACTIVE
- **Authoritative Files:** `rex_vision_flag_processor.py`, `/data/ocr_quarantine/`, `/data/gauntlet_reports/`
- **Last Major Change:** ~2026-04-05 (initial implementation)
- **What It Does:**
  - Flags OCR results, escalations, policy violations
  - Stores flagged items in quarantine (not active)
  - Chairman reviews in Command Center
  - Approved items move to production
- **What Was Replaced:** Direct OCR→production
- **Why It Changed:** Need for human review of edge cases
- **Contradiction Risk:** LOW — safety feature
- **Dependencies:** Alert Router (Phase 3), OCR Flag Processor

---

## REXXIE TELEGRAM BOT & POLICY ENFORCEMENT

### Feature: Rexxie Telegram Bot
- **ID:** FEAT-REXXIE-001
- **Subsystem:** Rexxie (Telegram Bot)
- **Name:** Rexxie Telegram Command Bot
- **Current Status:** ACTIVE
- **Authoritative Files:** `rex_rexxie_telegram_bot.py`, `rex_rexxie_telegram_config.json`
- **Last Major Change:** ~2026-04-13 (last update)
- **What It Does:**
  - Listens for Telegram messages from Kato
  - Routes to Claude via `private_confidant_gold.py`
  - Policy enforcer checks inbound/outbound
  - Returns response via Telegram
- **What Was Replaced:** Manual email/dashboard checks
- **Why It Changed:** Kato needed urgent chat interface outside of web UI
- **Contradiction Risk:** MEDIUM — per RED_TEAM_AUDIT, three policy enforcers create collision risk
- **Recovery Notes:** Bot is running; check logs for errors
- **Dependencies:** Telegram API (token in config), Claude API, policy enforcer

### Feature: Claude Policy Enforcer (Jailbreak/PHI/Tone)
- **ID:** FEAT-POLICY-001
- **Subsystem:** Rexxie (Security)
- **Name:** Inbound/Outbound Message Policy Gate
- **Current Status:** ACTIVE
- **Authoritative Files:** `rex_policy_enforcer.py`, `rex_policy_rules.json`
- **Last Major Change:** ~2026-03-20 (rules updates)
- **What It Does:**
  - **Inbound:** Blocks jailbreak attempts, detects PHI (SSN, DOB, medical terms), checks sovereignty rules
  - **Outbound:** Scrubs PHI from Claude response, tone-corrects (checks for insults, overly casual), checks disclosure tier
- **Rules Defined In:** `rex_policy_rules.json` (forbidden terms, allowed models, disclosure tiers)
- **What Was Replaced:** No enforcer (all messages passed through)
- **Why It Changed:** Need to block jailbreaks, prevent PHI leaks, enforce sovereignty
- **Contradiction Risk:** HIGH — per RED_TEAM_AUDIT Finding #5, if this fails to import, fallback allows **all** messages
- **Current Issue:** Per RED_TEAM_AUDIT Finding #6, tier enforcement is "advisory" (not enforced in code)
- **Recovery Notes:** Check `private_confidant_gold.py` line ~100 for import; if import fails, sends Telegram alert
- **Dependencies:** Policy rules JSON

### Feature: Unified Policy Enforcer (INCOMPLETE)
- **ID:** FEAT-POLICY-002
- **Subsystem:** Rexxie (Security)
- **Name:** Unified Policy Enforcer (Merges Enforcer1 + Enforcer2)
- **Current Status:** **DEAD CODE** — written but not imported
- **Authoritative Files:** `rex_unified_enforcer.py` (unimported), `build_coordinator/` (mirror, also unimported)
- **Last Major Change:** ~2026-04-05 (written but not wired)
- **What It Does (in theory):**
  - Merges `rex_policy_enforcer.py` (Rexxie gates) and `core/enforcer.py` (GHS gates) into single module
  - Would eliminate name collision risk
  - Would enable behavioral integrity monitor (Layer 2)
- **Why It Was Created:** Three separate enforcers with overlapping names (collision risk)
- **What It Should Replace:** Both `rex_policy_enforcer.py` and `core/enforcer.py`
- **Current Problem:** Per RED_TEAM_AUDIT Finding #4, it exists but imported by zero files
- **Recovery Notes:** To complete: update `private_confidant_gold.py` to use `UnifiedEnforcer`, deprecate others
- **Dependencies:** (none currently active)

### Feature: Disclosure Tier Access Control (INCOMPLETE)
- **ID:** FEAT-POLICY-003
- **Subsystem:** Rexxie (Authorization)
- **Name:** Disclosure Tier Authentication & Gating
- **Current Status:** **INCOMPLETE** — rules defined but not enforced
- **Authoritative Files:** `rex_policy_rules.json` (lines 50-80), `rex_policy_enforcer.py` (check_inbound)
- **Last Major Change:** ~2026-03-20 (rules defined), never wired into bot
- **What It Should Do:**
  - Define three tiers: public (anyone), staff (authenticated staff), admin (Chairman only)
  - Check sender `chat_id` against allowlist before answering
  - Reject unauthorized tiers with "access denied"
- **What It Actually Does:** **Advisory only** — logs violations but doesn't block
- **Per `rex_policy_rules.json` line 63:** "Tier enforcement is advisory until auth is wired into the bot."
- **Current Problem:** Any Telegram user can ask for billing, incident reports, staff schedules
- **What It Should Replace:** Currently nothing; new feature
- **Why It Changed (should have):** Different users need different data visibility
- **Recovery Notes:** To complete: add auth check in `private_confidant_gold.py` handle() before answering sensitive queries
- **Dependencies:** `rex_permissions.db`, allowed staff/admin ID lists

---

## REX BACKEND & CHAIRMAN COMMAND CENTER

### Feature: FastAPI Backend
- **ID:** FEAT-BACKEND-001
- **Subsystem:** REX Backend
- **Name:** REX FastAPI Server (Desktop Mode)
- **Current Status:** ACTIVE
- **Authoritative Files:** `backend/main.py` (1-150 lines for startup)
- **Last Major Change:** ~2026-04-13 (last update)
- **What It Does:**
  - Starts on `localhost:8000` (macOS desktop only)
  - Serves React frontend (static files)
  - WebSocket for real-time chat
  - REST endpoints for memory, uploads, config
  - Mounts sub-routers: Chairman Command Center, Executive, Chat
- **What Was Replaced:** Flask app (earlier version)
- **Why It Changed:** FastAPI is faster, has better async/await support, better for WebSocket
- **Contradiction Risk:** LOW — FastAPI is well-established
- **Recovery Notes:** Started by `FIX_REXXIE.command` step 2; runs in background
- **Dependencies:** Python 3.11+, FastAPI, Uvicorn

### Feature: Chairman Command Center
- **ID:** FEAT-CC-001
- **Subsystem:** REX Command Center
- **Name:** Chairman Dashboard API Routes
- **Current Status:** ACTIVE
- **Authoritative Files:** `backend/rex_command_center.py` (all of it)
- **Last Major Change:** ~2026-04-13 (last update)
- **What It Does:**
  - **GET /api/chairman/system-health** — uptime, event counts, DB status
  - **GET /api/chairman/red-flags** — critical/high events from alert bus
  - **GET /api/chairman/unresolved** — queue of pending decisions
  - **POST /api/chairman/resolve/{id}** — mark item resolved
  - **POST /api/chairman/escalate/{id}** — escalate to next level
- **Auth:** Chairman-only via `rex_role_auth.verify_role()`
- **What Was Replaced:** Manual log file inspection
- **Why It Changed:** Chairman needed real-time visibility without terminal access
- **Contradiction Risk:** LOW — read-heavy; limited write scope
- **Recovery Notes:** Backend must be running; check port 8000
- **Dependencies:** `/data/rex_events.db`, `/data/rex_unresolved.db`

### Feature: Encrypted Storage & Keys
- **ID:** FEAT-BACKEND-002
- **Subsystem:** REX Backend (Security)
- **Name:** Master Key Encryption & Storage
- **Current Status:** ACTIVE
- **Authoritative Files:** `backend/storage.py`, `backend/config.py`
- **What It Does:**
  - Generates/loads master encryption key from `~/.rex/master_key` or Keychain
  - All persistent data encrypted with this key
  - Singleton pattern ensures single key per session
- **Contradiction Risk:** LOW — encryption is transparent
- **Recovery Notes:** If master key is lost, all encrypted data becomes unreadable (no recovery possible)
- **Dependencies:** macOS Keychain (optional but recommended)

### Feature: Authentication & JWT
- **ID:** FEAT-BACKEND-003
- **Subsystem:** REX Backend (Auth)
- **Name:** JWT Session Management + Device Trust
- **Current Status:** ACTIVE
- **Authoritative Files:** `backend/auth.py`
- **Last Major Change:** ~2026-04-13
- **What It Does:**
  - JWT tokens for browser sessions
  - Device trust model (desktop always trusted, iPhone pairing required)
  - Phone unlock server (background thread)
- **What Was Replaced:** Basic HTTP auth
- **Why It Changed:** Need for stateful sessions and device trust
- **Recovery Notes:** `FRESH_START.command` resets JWT secret; forces re-login
- **Dependencies:** JWT library, phone unlock protocol

---

## GOJ DASHBOARD & SCHEDULER

### Feature: GOJ Dashboard Application
- **ID:** FEAT-GOJ-001
- **Subsystem:** GOJ Dashboard (Web App)
- **Name:** Garden of Joy Management Dashboard
- **Current Status:** **REGRESSION** — reported as not working
- **Authoritative Files:** `~/Documents/goj files/dashboard/` (Flask app)
- **Database:** `~/Documents/goj files/dashboard/auth_tracker.db` (separate from REX)
- **Last Major Change:** ~2026-04-13
- **What It Does:**
  - Displays client profiles, staff list, schedules, forms
  - Manages menus, routes, sign-in sheets
  - Produces PDF driver/kitchen sheets
- **What Was Replaced:** Manual spreadsheets
- **Why It Changed:** Centralized management for Garden of Joy operations
- **Current Problem:** Client profiles and staff list not working (per report)
- **Contradiction Risk:** CRITICAL — uses separate `auth_tracker.db`, not synced with REX
- **Recovery Notes:** If empty, check if `auth_tracker.db` is corrupted; restore from backup
- **Dependencies:** `auth_tracker.db`, Flask, file system access

### Feature: GOJ Daily Scheduler
- **ID:** FEAT-GOJ-002
- **Subsystem:** GOJ Scheduler
- **Name:** Scheduled GOJ Operations (Rexxie Integration)
- **Current Status:** ACTIVE
- **Authoritative Files:** `goj_daily_scheduler.py`
- **Schedule:** Per `GOJ_LOCKED_PARAMETERS.md`
  - 7:30am daily → morning_report
  - 10:30am daily → kitchen_sheets
  - 3:15pm daily → changes_routes
  - 8:30pm Fri → missing_menus_fri
  - 9:00pm daily → nightly_rundown
  - 9:00pm Fri → weekly_email_fri
- **What It Does:**
  - Runs scheduled jobs (morning briefing, schedule updates, nightly rundown)
  - Sends output to Kato via Rexxie Telegram bot
  - Reads from `auth_tracker.db` to get client data
- **What Was Replaced:** Manual job triggers
- **Why It Changed:** Automation for Garden of Joy daily operations
- **Recovery Notes:** Triggers via launchd (macOS scheduler); check if launchd jobs are loaded
- **Dependencies:** Rexxie Telegram bot, `auth_tracker.db`, launchd

---

## DATABASE PERSISTENCE & MEMORY

### Feature: RexMemory (REX Persistent Memory)
- **ID:** FEAT-MEM-001
- **Subsystem:** Memory (REX)
- **Name:** REX Persistent Fact Storage
- **Current Status:** **REGRESSION — EMPTY (0K)**
- **Authoritative Files:** `rex_memory.db`, `backend/memory.py`
- **Last Major Change:** ~2026-03-25 (implementation)
- **What It Does:**
  - Stores facts about Chairman (preferences, past decisions, learned context)
  - Before each request, `RexMemory.recall()` is called to load relevant facts
  - System prepends facts to Claude system prompt
  - System learns and adapts to preferences
- **What Was Replaced:** Stateless system (no memory)
- **Why It Changed:** REX was forgetting user preferences and past decisions
- **Current Problem:** `rex_memory.db` is 0K; memory is not being stored or recalled
- **Per MEMORY.md:** "memory never recalled" is critical issue
- **Recovery Notes:** Check if `backend/memory.py` is loading; check if recall() is being called
- **Dependencies:** `rex_memory.db` SQLite file

### Feature: RexxieMemory (Rexxie Persistent Memory)
- **ID:** FEAT-MEM-002
- **Subsystem:** Memory (Rexxie)
- **Name:** Rexxie Persistent Chat Context & User Profiles
- **Current Status:** ACTIVE (60K, healthy)
- **Authoritative Files:** `rexxie_memory.db`
- **Last Major Change:** ~2026-03-25
- **What It Does:**
  - Stores chat context from Telegram conversations
  - User profiles (preferences, past topics, learned behaviors)
  - Telegram message history
- **Recovery Notes:** Regularly pruned to prevent unbounded growth
- **Dependencies:** `rexxie_memory.db` SQLite file

### Feature: User Model Database
- **ID:** FEAT-MEM-003
- **Subsystem:** Memory (User Model)
- **Name:** REX User Model Persistence
- **Current Status:** **REGRESSION — EMPTY (0K)**
- **Authoritative Files:** `rex_user_model.db`
- **Last Major Change:** ~2026-03-25
- **What It Does:**
  - Stores user preferences, learning models, behavioral patterns
  - Per MEMORY.md: "user model empty"
- **Current Problem:** 0K — no data
- **Per MEMORY.md:** "user model empty" is critical issue
- **Recovery Notes:** Unknown if ever populated; may be vestigial
- **Dependencies:** `rex_user_model.db`

---

## AUDIT & MONITORING

### Feature: Audit Logger
- **ID:** FEAT-AUDIT-001
- **Subsystem:** Audit (Logging)
- **Name:** System Audit Log
- **Current Status:** ACTIVE
- **Authoritative Files:** `backend/audit.py`, `/data/rex_events.db`
- **Last Major Change:** ~2026-04-13
- **What It Does:**
  - Logs all API calls, policy decisions, role checks
  - Records timestamp, actor, action, result
  - Persists to SQLite for querying
- **Contradiction Risk:** LOW — read-only operations don't affect business logic
- **Dependencies:** `/data/rex_events.db`

### Feature: Red Team Security Audit
- **ID:** FEAT-AUDIT-002
- **Subsystem:** Audit (Security)
- **Name:** Red Team Audit Report (Apr 13)
- **Current Status:** **CRITICAL FINDINGS DOCUMENTED**
- **Authoritative Files:** `REX_RED_TEAM_AUDIT_2026-04-13.md`
- **Last Run:** 2026-04-13 02:58
- **What It Documents:**
  - 3 CRITICAL findings (token/key/TOTP exposure)
  - 5 HIGH findings (enforcer conflicts, fallback blackhole, etc.)
  - 4 MEDIUM/LOW findings
- **Contradiction Risk:** CRITICAL — multiple unaddressed security issues
- **Recovery Notes:** See BUILD_DECISION_HISTORY.md section "RED TEAM AUDIT RECOMMENDATIONS"
- **Dependencies:** Entire system

### Feature: Disabled Audit Commands
- **ID:** FEAT-AUDIT-003
- **Subsystem:** Audit (Tools)
- **Name:** REX_AUDIT.command & GHS_AUDIT.command
- **Current Status:** DISABLED (2026-04-14 04:35)
- **Authoritative Files:** `REX_AUDIT.command.DISABLED_2026_04_14`, `GHS_AUDIT.command.DISABLED_2026_04_14`
- **What They Do:** Generate audit reports; READ-ONLY tools (don't modify state)
- **Why Disabled:** Flagged as potentially contributing to regressions (investigation)
- **Recovery Notes:** Re-enable after forensic analysis complete; no data lost
- **Important Note:** NOT the same as red team audit; these are operational audit runners

---

## CONFIGURATION & KEYS

### Feature: Backend Configuration
- **ID:** FEAT-CONFIG-001
- **Subsystem:** Configuration
- **Name:** REX Backend Settings Loader
- **Current Status:** ACTIVE
- **Authoritative Files:** `backend/config.py`
- **Last Major Change:** ~2026-04-13
- **What It Does:**
  - Loads API keys from environment or Keychain
  - Sets default model (should be Ollama, not Claude)
  - Configures encryption, storage paths
- **Per RED_TEAM_AUDIT Finding #7:** Line 103 defaults to `anthropic/claude-sonnet-4-5` instead of `ollama/llama3`
- **Recovery Notes:** Should use Keychain for API keys, not `.env`
- **Dependencies:** `~/.rex/config.json`, macOS Keychain (optional)

### Feature: API Key Management (.env)
- **ID:** FEAT-CONFIG-002
- **Subsystem:** Configuration (Secrets)
- **Name:** Environment Variables File
- **Current Status:** **RISKY** — plaintext keys
- **Authoritative Files:** `.env` (in /Desktop/REX/)
- **What It Contains:**
  - `ANTHROPIC_API_KEY=sk-ant-api03-...` (plaintext)
  - Other API keys
- **Per RED_TEAM_AUDIT Finding #2:** Key is backed up unencrypted
- **Recovery Notes:** Move all keys to macOS Keychain; keep `.env` but use `keyring` library to load at runtime
- **Dependencies:** `.env` file, macOS Keychain (recommended target)

### Feature: Telegram Config
- **ID:** FEAT-CONFIG-003
- **Subsystem:** Configuration (Secrets)
- **Name:** Rexxie Telegram Bot Configuration
- **Current Status:** **RISKY** — plaintext token
- **Authoritative Files:** `rex_rexxie_telegram_config.json`
- **What It Contains:**
  - Bot token `8657319466:AAGqWut7BHTTNIEYJvnXIDlNSDCOiML7tic` (plaintext)
  - Owner chat ID
- **Per RED_TEAM_AUDIT Finding #1:** Token appears 33 times across codebase
- **Recovery Notes:** Revoke immediately; store new token in Keychain; load via `keyring` at runtime
- **Dependencies:** Keychain (recommended target)

---

## FRONT END & STATIC ASSETS

### Feature: React Frontend
- **ID:** FEAT-FRONTEND-001
- **Subsystem:** Frontend (UI)
- **Name:** REX Web UI (React SPA)
- **Current Status:** ACTIVE
- **Authoritative Files:** `frontend/` directory (source), `frontend/dist/` (built)
- **Last Major Change:** ~2026-04-13
- **What It Does:**
  - Single-page app served from FastAPI
  - WebSocket chat with REX
  - Chairman dashboard (when built)
  - Configuration UI
- **Build Command:** `npm run build` (run by `rex-rebuild.command`)
- **Recovery Notes:** Use `rex-rebuild.command` to rebuild; cleans old build
- **Dependencies:** Node.js, npm, React

### Feature: Build & Restart Script
- **ID:** FEAT-CONTROL-001
- **Subsystem:** Control (Operations)
- **Name:** rex-rebuild.command (Full Rebuild + Restart)
- **Current Status:** ACTIVE
- **Authoritative Files:** `rex-rebuild.command`
- **What It Does:**
  - Stops existing backend
  - Rebuilds React frontend from scratch (`npm run build`)
  - Restarts REX backend on port 8000
  - Restarts Telegram bots
- **Warning:** Step 2/4 can revert custom dashboard assets if source was overwritten
- **Recovery Notes:** Only run if you want to rebuild React code; don't use just to restart
- **Dependencies:** npm, Node.js, Python

---

## SUMMARY: FEATURES BY MATURITY

| Status | Count | Examples | Notes |
|--------|-------|----------|-------|
| **ACTIVE** | 25+ | OCR consensus, bot, backend, command center, alert bus | Core system working |
| **REGRESSION** | 4 | RexMemory, User Model, Client Profiles, Staff List | Databases empty or out of sync |
| **DEAD CODE** | 1 | Unified Enforcer | Written but not imported; needs activation |
| **INCOMPLETE** | 2 | Disclosure Tier Auth, Config Fallback | Designed but not wired; needs fix |
| **OUT OF SYNC** | 2 | GOJ Dashboard, Railway Website | Separate DBs not synced |
| **CRITICAL FINDINGS** | 8 | Per RED_TEAM_AUDIT | Security issues to address |

