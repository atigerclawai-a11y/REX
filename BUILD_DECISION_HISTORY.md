# BUILD DECISION HISTORY — REX/Rexxie Architecture Evolution
**Document Date:** 2026-04-14 05:35 UTC  
**Last Updated:** 2026-04-15 — Prompt Registry additions locked  
**Scope:** Architectural decisions, feature additions, deprecations, and regressions from Jan 2026 to Apr 2026  

---

## PROMPT REGISTRY ADDITIONS — Locked (2026-04-15)

**Approved by:** Kato  
**Status:** LOCKED — part of the governed prompt system  

### What is locked

| Feature | File | Status |
|---|---|---|
| `POST /prompt-registry/diff` endpoint | `rex_command_center.py` | Locked |
| Rich approval payload (diff preview, reason, risk, version delta) | `rex_prompt_registry.py` | Locked |
| Append-only audit log (`state/prompt_audit.log`) | `rex_prompt_registry.py` | Locked |
| YAML frontmatter on all 10 prompt `.md` files | `prompts/*/` | Locked |
| Body-only diffing and integrity comparison (frontmatter stripped) | `rex_prompt_registry.py` | Locked |
| Auto-version bump in frontmatter on every applied edit | `rex_prompt_registry.py` | Locked |

### Governance rule
Do not drift from the governed prompt model. No prompt in `state/prompt_registry.json` may be edited without going through the tier-appropriate approval flow. No exceptions for "quick fixes."

### Carry-forward items (not yet built — build when appropriate)

These are locked as planned work, in priority order:

**PR-CF-1 — Prompt status badges** ✅ DONE 2026-04-15  
`status_badge` property on every `PromptEntry` — returns `status_label`, `status_color`, `risk_label`, `risk_color`, `risk_icon`, `tier_label`, `protected_label`. Included in `to_dict()` so every API response carries badge data. `badge_rollup` (risk color → count) added to `summary()`. Command Center renders with no extra logic needed.

**PR-CF-2 — Prompt usage tracking** ✅ DONE 2026-04-15  
`data/vaults/prompt_usage.db` — one row per load event: `prompt_id`, `context`, `role`, `used_at`. `track_usage(id, context, role)` call point. `usage_summary(days=30)` returns load counts + never-used list. `usage_for(id)` returns per-prompt event history. API routes: `GET /prompt-registry/usage` and `GET /prompt-registry/{id}/usage`.

**PR-CF-3 — Protected prompt class** ✅ DONE 2026-04-15  
`protected: true` flag on 5 prompts: `rex-identity-v1`, `rexxie-identity-v1`, `role-disclosure-rules-v1`, `agent-security-rules-v1`, `ocr-safety-policy-v1`. Protected edits require: (1) 48h minimum staging window enforced in code (`PROTECTED_MIN_HOURS = 48`), (2) second confirmation via `confirm_protected_edit(edit_id)` / `POST /prompt-registry/confirm/{edit_id}`. Both gates checked in `approve_edit()` — either missing = hard block with clear error and instructions.

**PR-CF-4 — Prompt registry state in snapshots** ✅ DONE 2026-04-15  
`rex-backup-goj.command`: added `[5/5] Prompt Registry` section — captures `state/prompt_registry.json`, `state/prompt_audit.log`, `data/vaults/prompt_edits.db`, and full `prompts/` tree (including `prompts/versions/`) into `prompt_registry/` subfolder. Errors loudly if registry index or prompts dir is missing.  
`rex-backup.command`: added explicit governed-asset verification block after rsync — confirms all prompt registry files landed in the snapshot. Warns with ⚠️ if any are absent. Does not abort (rsync succeeded) but makes the gap impossible to miss.

---

## PROMPT REGISTRY — Governed Prompt Management (2026-04-15)

**Approved by:** Kato  
**Built:** 2026-04-15  
**Status:** ACTIVE  

### Decision
All operational prompts (identity, governance, OCR safety, CLS scope, training, knowledge) are now governed system assets — not loose text. The Prompt Registry enforces versioning, approval tiers, and rollback for every prompt in the system.

### Files Created / Modified
| File | Action | Purpose |
|------|---------|---------|
| `backend/rex_prompt_registry.py` | Created | Registry engine: load/save, staged edits, versioning, rollback |
| `state/prompt_registry.json` | Created | Authoritative registry — 15 entries, all required fields |
| `prompts/identity/rex_identity.md` | Created | Extracted from sovereign.py REX_IDENTITY |
| `prompts/identity/rexxie_identity.md` | Created | Extracted from rex_rexxie.py REXXIE_IDENTITY |
| `prompts/identity/claude_mentor_principles.md` | Created | Extracted from sovereign.py CLAUDE_MENTOR_PRINCIPLES |
| `prompts/governance/role_disclosure_rules.md` | Created | Extracted from sovereign.py ROLE_DISCLOSURE_RULES |
| `prompts/governance/agent_security_rules.md` | Created | Extracted from sovereign.py AGENT_SECURITY_RULES |
| `prompts/knowledge/goj_knowledge.md` | Created | Extracted from sovereign.py GOJ_KNOWLEDGE |
| `prompts/operational/transparency_block.md` | Created | Extracted from telegram bot _TRANSPARENCY_BLOCK |
| `prompts/operational/language_block.md` | Created | Extracted from telegram bot _LANGUAGE_BLOCK |
| `prompts/cls/cls_v3_observation_note.md` | Created | CLS scope governance prompt |
| `prompts/ocr/ocr_safety_policy.md` | Created | OCR safety rules prompt |
| `backend/rex_command_center.py` | Modified | Added 10 prompt-registry API routes |

### Approval Tier Rules
- **Tier 1** (low risk): training prompts, style blocks → apply immediately, snapshot created
- **Tier 2** (medium risk): knowledge, operational → staged 24h, Kato acknowledge to apply
- **Tier 3** (governed): identity, governance, ocr, cls, memory, override → staged 72h, explicit approval required. No edit lands without Kato's explicit command.

### Governed Categories (always Tier 3 minimum)
`identity`, `governance`, `ocr`, `cls`, `memory`, `override`

### Versioning & Rollback
Every applied edit (any tier) creates an immutable snapshot in `prompts/versions/<id>/`.  
Rollback for Tier 3: staged as a new edit (goes through the same approval flow).  
Rollback for Tier 1: immediate.  

### Kato Commands (Telegram / REX chat)
- `approve prompt edit <id>` — applies a staged edit
- `reject prompt edit <id>` — discards staged edit, no change
- `rollback prompt <id> to v<n>` — restore a prior version
- `prompt status <id>` — show current metadata
- `list prompts [category]` — list registry
- `list pending prompt edits` — show queue

---

## PHASE 9 — CLS v3: CONTINUOUS LEARNING SYSTEM (2026-04-15)

**Approved by:** Kato  
**Built:** 2026-04-15  
**Status:** ACTIVE  

### Decision
Build CLS v3 — a governed, two-tier learning system connected to REXXIE, with no uncontrolled drift, no silent memory writes, and no bypass of the existing governance stack.

### Files Created
| File | Purpose |
|------|---------|
| `core/cls_v3.py` | Tier A pattern scoring engine + Tier B candidate promotion |
| `core/cls_gate.py` | Approval gate — only path from pattern → MemorySteward |
| `backend/rex_nightly_brief.py` | Nightly briefing generator with required metadata |
| `core/gauntlet/scenarios/cls_v3_safety.yaml` | 10 safety test scenarios (A–J) |

### Learning Model Split
- **Tier A (Pattern Learning):** Automatic, zero writes. Observes rex_events.db, alert bus, menu learning, behavior flags. Scores patterns in cls_v3_patterns.db only.
- **Tier B (Informational Learning):** Gated. Activates only when pattern hits threshold (≥3 obs, ≥2 days). Queues LearningCandidate in cls_v3_candidates.db. Requires explicit Kato approval. Hard cap: L1 secrecy max.

### Safety Decisions
- GAUNTLET_ENV → CLS self-disables immediately
- Forbidden reads: ocr_quarantine/, rexxie.db, L3+ memory
- No direct MemorySteward calls from cls_v3.py — only cls_gate.py may call steward.write()
- All writes tagged agent_owner="rex_cls" for rollback traceability
- insert-only: CLS never updates existing memory records
- Mobile access governed by same role checks as desktop (staff role omits chairman sections)

### Nightly Briefing Change
`rex_nightly_brief.py` replaces ad-hoc briefing scripts. Every brief now includes:
1. Covered time window (window_start → window_end)
2. Generation timestamp (generated_at, UTC ISO-8601)
3. Source/event counts (rex_events, alerts, unresolved)
Staff-role briefs omit behavior_flags and cls_summary (chairman-only).

### Rollback
```
# Disable CLS v3
rm ~/Desktop/REX/core/cls_v3.py ~/Desktop/REX/core/cls_gate.py
# Or: set cls_v3.enabled=false in ACTIVE_SYSTEM_MANIFEST.json

# Undo any approved writes
python -c "from core.memory_steward import MemorySteward; MemorySteward().delete_by_owner('rex_cls')"

# Drop pattern/candidate stores
rm ~/Desktop/REX/data/vaults/cls_v3_patterns.db
rm ~/Desktop/REX/data/vaults/cls_v3_candidates.db
```

### STOP — Phase 9 only. Phase 10 not started.

---
**Purpose:** Explain WHY each major component was built, replaced, or changed; flag contradictions and recovery points

---

## CRITICAL FINDINGS (RED TEAM AUDIT 2026-04-13)

The `REX_RED_TEAM_AUDIT_2026-04-13.md` report identified:

**CRITICAL (3):**
1. **Telegram Bot Token — Plaintext in 33 Files**
   - Token `8657319466:AAGqWut7BHTTNIEYJvnXIDlNSDCOiML7tic` appears in config JSON, backups, shell scripts, and `private_confidant_gold.py` line 354 (printed to stdout)
   - Fix: Revoke immediately, store in macOS Keychain, use `keyring.get_password()` at runtime

2. **Anthropic API Key in Plaintext .env — Backed Up Unencrypted**
   - `~/.env` contains `ANTHROPIC_API_KEY=sk-ant-api03-...` 
   - Backups contain the key unencrypted (REX_Backups/REX_2026-04-12_20-37/.env)
   - Fix: Revoke key, store in Keychain, add `.env` to backup exclusion

3. **Hardcoded TOTP Secret — RFC Well-Known Value**
   - `core/enforcer.py` line 55: `secret = "JBSWY3DPEHPK3PXP"` (the canonical RFC example)
   - Same secret appears in `rex_sqlcipher_vault.py` line 940
   - Fix: Generate unique secrets per agent, store in SQLCipher vault, not source code

**HIGH (5):**
4. Three policy enforcers with conflicting names; unified enforcer is dead code (not imported)
5. Fallback policy is a security blackhole—if enforcer fails to import, all messages pass unchecked
6. Disclosure tier authentication not wired—no actual auth gate in bot (tier enforcement is "advisory")
7. Cloud fallback present in `backend/config.py` line 103 (should default to Ollama, not Claude)
8. Owner chat ID hardcoded in `rex_policy_enforcer.py` line 117

---

## MAJOR FEATURE DECISIONS

### Decision D-001: Claude Vision Fast-Path (Mar 2026)
**Date:** ~2026-03-15  
**What Changed:** Added Claude Vision API as primary OCR method (vs. Tesseract/Paperless)  
**Why:** Vision provides better accuracy for menu PDFs; can extract handwritten notes; more robust to skew/rotation  
**Authorization Source:** Inferred from Kato's workflow; prompted by OCR quality complaints  
**What Was Lost:** Tesseract local-only OCR (now legacy in `_archive/old_ocr_scripts/`)  
**Current File:** `goj_menu_consensus_ocr.py` (line 100+)  
**Contradiction Risk:** LOW — Vision is clearly better; legacy code archived  
**Recovery Notes:** If Vision API fails, can fallback to Tesseract (still installed) but would need to reactivate old scripts

---

### Decision D-002: Consensus Vote Weighted Upgrade (Mar 2026)
**Date:** ~2026-03-20  
**What Changed:** Added voting layer for OCR results — multiple Claude runs, score each, pick best  
**Why:** Single Claude call can hallucinate or miss items; voting reduces false positives  
**Current File:** `goj_menu_consensus_ocr.py` (lines 30-60)  
**What Was Lost:** Single-pass OCR (no longer used)  
**Contradiction Risk:** MEDIUM — voting adds latency; if time budget is tight, might need fast-path  
**Recovery Notes:** Can reduce from 3 votes to 1 vote by removing voting loop; will be faster but less accurate

---

### Decision D-003: FRESH_START Command (Apr 2026)
**Date:** ~2026-04-10  
**What Changed:** Created token-reset-only recovery script—preserves all data, resets auth tokens  
**Why:** Kato needed a way to get back in after JWT expiration or admin password loss without nuking database  
**What Was Preserved:** All user accounts, chat history, documents, trained patterns  
**What Was Reset:** JWT secret, admin password → `chairman2026`, session tokens  
**Current File:** `FRESH_START.command`  
**Authorization Source:** Direct user need (Kato locked out scenario)  
**Contradiction Risk:** LOW — orthogonal to other systems  
**Recovery Notes:** Safe to run; only affects auth layer  
**Note on Side Effects:** Step [2/4] calls `hash_pw("chairman2026")` and updates the DB; if called multiple times, is idempotent

---

### Decision D-004: FIX_REXXIE Command (Apr 2026)
**Date:** ~2026-04-12  
**What Changed:** Created full-restart script—kills all services, starts backend + dashboard + bots fresh  
**Why:** When one service hangs or crashes, others can't start; needed atomic "just restart everything" button  
**What It Does:**
  - Kills all `uvicorn`, `telegram_bot`, and `dashboard` processes
  - Frees ports 8000, 8080
  - Loads `.env` and restarts REX backend on 8000
  - Tries to find Flask-enabled Python and starts GOJ Dashboard on 8080
  - Starts Rexxie and Rex Telegram bots if tokens are configured
**Current File:** `FIX_REXXIE.command`  
**Contradiction Risk:** LOW — designed for clean recovery  
**Recovery Notes:** Does NOT rebuild frontend (use `rex-rebuild.command` for that); does NOT touch databases

---

### Decision D-005: Audit Scripts Disabled Today (Apr 2026, 04:35 UTC)
**Date:** 2026-04-14 04:35  
**What Changed:** Disabled `REX_AUDIT.command` and `GHS_AUDIT.command` during forensic recovery  
**Why:** Both are READ-ONLY tools (don't modify state) but were flagged as potentially contributing to regressions  
**What They Were:** REX_AUDIT — security audit log; GHS_AUDIT — Gold Health Systems compliance check  
**What They Did:** Generated audit reports; logged findings; did NOT make changes  
**Current State:** Disabled by renaming to `.DISABLED_2026_04_14`  
**Recovery Notes:** Can be re-enabled once recovery is complete; read-only, so no data lost  
**Important Note:** The "12-hour audit" referenced in system notes is NOT a launchd timer—it's the `REX_RED_TEAM_AUDIT_2026-04-13.md` security report run April 13 as a one-time analysis

---

### Decision D-006: OCR Schema Layer Added (Phase 1, ~Mar 2026)
**Date:** ~2026-03-18  
**What Changed:** Separated OCR input schema from processing logic  
**Files:**
  - `goj_menu_ocr_schema.py` — defines menu item, quantity, allergen fields
  - `goj_menu_consensus_ocr.py` — uses schema to parse and validate output
**Why:** Schema prevents hallucinated fields; enforces type validation; makes testing easier  
**Contradiction Risk:** LOW — schema enforces correctness  
**Recovery Notes:** If schema is too strict, can loosen validators; if too loose, can tighten them

---

### Decision D-007: Memory Steward Added (Phase 2, ~Mar 25 2026)
**Date:** ~2026-03-25  
**What Changed:** Created persistent memory layer for REX and Rexxie  
**Files:**
  - `rex_memory.db` — RexMemory class (in `backend/memory.py`)
  - `rexxie_memory.db` — RexxieMemory (separate persistence)
  - `rex_memory.py` (if exists) — planner that refreshes memory before each request
**Why:** REX and Rexxie were forgetting user preferences, past decisions, and learned context between sessions  
**Current Status:** **REGRESSION** — both DBs are 0K (empty)  
**Contradiction Risk:** CRITICAL — If memory isn't being recalled, users see no learning  
**Recovery Notes:** Per `project_rex_critical_issues_apr2026.md`, "memory never recalled" is an open critical issue

---

### Decision D-008: Alert Router Added (Phase 3, ~Apr 1 2026)
**Date:** ~2026-04-01  
**What Changed:** Created Phase 0 Alert Bus for routing unresolved items to Chairman Command Center  
**Files:**
  - `/data/alert_bus_fallback.jsonl` — event log for alerts
  - `/data/rex_events.db` — persistent event database
  - `backend/rex_command_center.py` — routes to display alerts
**Why:** Chairman needed visibility into exceptions, flags, and escalations without checking log files  
**Current Status:** ACTIVE — events are being logged  
**Contradiction Risk:** LOW — purely informational; no side effects  
**Recovery Notes:** If alert bus is backed up, old entries are in JSONL format

---

### Decision D-009: Gauntlet Added (Phase 4, ~Apr 5 2026)
**Date:** ~2026-04-05  
**What Changed:** Added review gate for flagged items before they reach production  
**Files:**
  - `rex_vision_flag_processor.py` — flags OCR results, escalations, policy violations
  - `/data/gauntlet_reports/` — reviewed + approved items stored here
  - `/data/ocr_quarantine/` — items awaiting review
**What It Does:** 
  - Runs post-OCR to check for confidence < 70%, missing fields, or policy violations
  - Flags items; stores in quarantine
  - Chairman reviews in Command Center; approves or rejects
  - Approved items move to production
**Why:** OCR hallucinations and policy edge cases needed human review before affecting participants  
**Contradiction Risk:** LOW — safety feature; no downside to having it  
**Recovery Notes:** Items in quarantine are safe—they're not active until approved

---

### Decision D-010: Rexxie Telegram Bot Architecture (Mar-Apr 2026)
**Date:** ~2026-03-10 (initial), evolved through Apr  
**Core Files:**
  - `rex_rexxie_telegram_bot.py` — main bot event handler
  - `private_confidant_gold.py` — Claude integration + policy enforcer wrapper
  - `rex_policy_enforcer.py` — security gates (jailbreak blocking, PHI detection, tone)
  - `rex_policy_rules.json` — rule definitions
**Why:** Kato needed a private Telegram bot for urgent comms outside of web UI  
**Contradiction Risk:** MEDIUM — per RED_TEAM_AUDIT, there are 3 policy enforcers (collision risk)  
**Current Issue:** Per D-008 below, tier-based access control is "advisory" (not enforced)  
**Recovery Notes:** Bot is running; rules are loaded; enforcer is active

---

### Decision D-011: Unified Enforcer Attempted (Apr 2026, unfinished)
**Date:** ~2026-04-05  
**What Changed:** Created `rex_unified_enforcer.py` to merge `rex_policy_enforcer.py` and `core/enforcer.py`  
**Why:** Three separate enforcers with overlapping names were a collision/maintenance risk  
**Current Status:** **DEAD CODE** — file exists but imported by zero operational modules  
**Per RED_TEAM_AUDIT Finding #4:** 
  - Enforcer 1 (`rex_policy_enforcer.py`) — used by live bot ✓
  - Enforcer 2 (`core/enforcer.py`) — orphaned
  - Enforcer 3 (`rex_unified_enforcer.py`) — written but not wired
**What Was Lost:** Nothing; unification is pending  
**Contradiction Risk:** HIGH — if someone imports wrong enforcer, silent behavior change  
**Recovery Notes:** To complete: update `private_confidant_gold.py` to use `UnifiedEnforcer`, then deprecate the other two

---

### Decision D-012: Disclosure Tier System (Mar 2026, incomplete)
**Date:** ~2026-03-20  
**What Changed:** Defined three access tiers (public/staff/admin) in policy rules  
**File:** `rex_policy_rules.json` line 63: "Tier enforcement is advisory until auth is wired into the bot."  
**Why:** Different users should see different data (clients see their own data; staff see schedules; admin sees financials)  
**Current Status:** **NOT ENFORCED** — per RED_TEAM_AUDIT Finding #6, "no actual auth gate in bot"  
**What This Means:** Any Telegram user can ask for billing data, incident reports, or staff schedules  
**Recovery Notes:** To complete, add auth check in `private_confidant_gold.py` handle() before answering sensitive queries

---

### Decision D-013: GOJ Dashboard Separation (design decision, unclear date)
**Date:** Unknown (predates forensic session)  
**What Changed:** GOJ Dashboard (`~/Documents/goj files/dashboard/`) uses separate `auth_tracker.db` from REX  
**Why:** Dashboard needed its own auth layer, user/client/staff management not coupled to REX backend  
**Current Problem:** **REGRESSION POINT** — Dashboard and REX are not synced; if Dashboard DB is empty, users see nothing  
**Contradiction Risk:** CRITICAL — Three separate database systems:
  1. REX/Rexxie local (`/Desktop/REX/*.db`)
  2. GOJ Dashboard local (`~/Documents/goj files/dashboard/auth_tracker.db`)
  3. Railway website remote (unknown location)
**Recovery Notes:** To fix regressions: (a) check if `auth_tracker.db` is empty/corrupted, (b) restore from backup, (c) implement sync between GOJ and REX

---

### Decision D-014: Railway Website Separate Deployment (design, unknown date)
**Date:** Unknown  
**What Changed:** Public website deployed to Railway (`respectful-intuition-production-0acf.up.railway.app`)  
**Why:** Local system is desktop-only, no remote public access; website needed separate remote database  
**Current Problem:** If Railway DB was rolled back or reset, website is out of sync with local  
**Recovery Notes:** Check Railway deployment history and database state with ops team

---

## "IF I VEER OFF PATH AGAIN" — RECOVERY CHECKLIST

### If Memory Stops Working (D-007 Regression)
1. Check if `rex_memory.db` and `rexxie_memory.db` are empty (0K)
2. Check if `backend/memory.py` is loading correctly (import errors in logs?)
3. Check if `RexMemory.recall()` is being called before each Claude request
4. If both DBs are empty: likely caused by a reset command or database wipe
5. Recovery: Restore from `REX_Backups/REX_2026-04-13_03-04/` (both memory DBs were 0K there too—this is a pre-existing issue per MEMORY.md)

### If Authentication Breaks (D-012 Regression)
1. Check if `private_confidant_gold.py` has an auth gate (should have after fix)
2. Check if `rex_permissions.db` is corrupted or empty
3. If both DBs are empty: `FIX_REXXIE.command` may have wiped them
4. Recovery: Restore from latest backup

### If OCR Stops Working (D-002 / D-006 Regression)
1. Check if `ANTHROPIC_API_KEY` is set in `.env` or Keychain
2. Check if Claude Vision API is accessible (no rate limit?)
3. Check if `goj_menu_consensus_ocr.py` can import `claude` client
4. If Vision fails: fallback to Tesseract (but reactivate old scripts in `_archive/old_ocr_scripts/`)

### If Policy Enforcer Fails (D-011 Regression)
1. Check `private_confidant_gold.py` line ~100 for the import
2. If import fails, the fallback `_FallbackPolicy` allows **all messages** (security blackhole)
3. Per RED_TEAM_AUDIT Finding #5, add a startup check that crashes if enforcer fails to load
4. Recovery: Fix the import error; never let enforcer silently fail

### If Dashboard Shows No Clients (D-013 Regression)
1. Check if `auth_tracker.db` exists and is non-empty
2. Check if `~/Documents/goj files/dashboard/app.py` is running (port 8080?)
3. Check if Flask can connect to the database
4. Recovery: Restore `auth_tracker.db` from GOJ_Backups or REX_Backups if available

### If Website Is Out of Sync
1. Check Railway deployment history (was there a rollback?)
2. Check if the Railway database schema matches the local GOJ Dashboard schema
3. If schemas diverged: need manual schema migration
4. Recovery: Contact Railway ops or manually sync via REST API

---

## RED TEAM AUDIT RECOMMENDATIONS (IMMEDIATE)

**CRITICAL ACTIONS (do now):**

1. **Revoke Telegram Token**
   - Go to BotFather on Telegram
   - Run `/revoke` and select Rexxie bot
   - Generate new token
   - Store in macOS Keychain: `security add-generic-password -s "rexxie_telegram_bot" -a "token" -w "<new_token>"`
   - Update `rex_rexxie_telegram_bot.py` to load from Keychain instead of JSON

2. **Revoke Anthropic API Key**
   - Go to console.anthropic.com
   - Delete old key `sk-ant-api03-...`
   - Generate new key
   - Store in Keychain: `security add-generic-password -s "REX-PrivacyProxy" -a "rex_anthropic_api_key" -w "<new_key>"`
   - Update `backend/config.py` to load from Keychain (already supports it via `keyring`)

3. **Fix TOTP Secret**
   - Generate new secret: `python3 -c "import secrets, base64; print(base64.b32encode(secrets.token_bytes(20)).decode())"`
   - Store in SQLCipher vault (not source code)
   - Update `core/enforcer.py` to retrieve from vault at runtime

4. **Unify Policy Enforcers**
   - Delete `core/enforcer.py` (orphaned)
   - Make `rex_unified_enforcer.py` the single source of truth
   - Update `private_confidant_gold.py` to import `UnifiedEnforcer` from it
   - Deprecate `rex_policy_enforcer.py` once unified version is confirmed working
   - Enable behavioral integrity monitor (Layer 2) in unified enforcer

5. **Wire Authorization into Bot**
   - Add auth check in `private_confidant_gold.py` handle() method
   - Check sender `chat_id` against staff/admin allowlist before answering sensitive queries
   - Use `rex_permissions.db` for permission lookups
   - Return "access denied" for unauthorized tiers

6. **Fix Config Fallback**
   - Change `backend/config.py` line 103 from `anthropic/claude-sonnet-4-5` to `ollama/llama3`
   - Ensures code-level default matches documented sovereign default

---

## SUMMARY TABLE

| Feature ID | Decision | Date | Status | Risk | Recovery Notes |
|-----------|----------|------|--------|------|-----------------|
| D-001 | Claude Vision fast-path | Mar 2026 | ACTIVE | LOW | Fall back to Tesseract if Vision fails |
| D-002 | Consensus vote upgrade | Mar 2026 | ACTIVE | MEDIUM | Can reduce votes if latency critical |
| D-003 | FRESH_START command | Apr 10 2026 | ACTIVE | LOW | Safe to use; idempotent |
| D-004 | FIX_REXXIE command | Apr 12 2026 | ACTIVE | LOW | Kills all services; use carefully |
| D-005 | Audit scripts disabled | Apr 14 2026 | DISABLED | N/A | Re-enable after recovery |
| D-006 | OCR schema layer | Mar 2026 | ACTIVE | LOW | Can loosen/tighten validators |
| D-007 | Memory steward | Mar 25 2026 | **REGRESSION** | CRITICAL | Both memory DBs are empty |
| D-008 | Alert router | Apr 1 2026 | ACTIVE | LOW | Informational; no side effects |
| D-009 | Gauntlet review gate | Apr 5 2026 | ACTIVE | LOW | Safety feature; no downside |
| D-010 | Rexxie bot architecture | Mar 2026 | ACTIVE | MEDIUM | Per audit, needs auth wiring |
| D-011 | Unified enforcer | Apr 5 2026 | **DEAD CODE** | HIGH | Not imported; needs activation |
| D-012 | Disclosure tier system | Mar 2026 | **INCOMPLETE** | CRITICAL | Tier enforcement advisory; not enforced |
| D-013 | GOJ Dashboard separation | Unknown | **REGRESSION POINT** | CRITICAL | Not synced with REX; own DB |
| D-014 | Railway website | Unknown | **OUT OF SYNC** | CRITICAL | Separate remote database |


---

## PHASE 10 — Session Authority + Governance Hardening (2026-04-15)

**Approved by:** Kato  
**Built:** 2026-04-15  
**Status:** ACTIVE  

### Refinements applied before build
- Session `integrity_hash` in `session_state.json`, HMAC-SHA256 verified on every read, session invalidated and event logged on tamper
- Restore drill: SHA-256 computed on every governed file; drill FAILS explicitly if any hash verification fails
- Schema mismatches surfaced in Command Center with structured `SCHEMA_WARNING` state (yellow — distinct from HALTED red), including affected file list and mismatch detail
- Optional improvements: session extension threshold (max 20/session before re-auth required), restore drill cooldown (5 min configurable), CLS aging transitions logged to alert bus

### Files Created
| File | Purpose |
|---|---|
| `config/session.yaml` | Session + drill + schema + CLS aging configuration |
| `state/session_state.json` | Live MSU session state with integrity_hash |
| `backend/rex_session.py` | MSU engine: unlock/lock/extend/tamper-detect/HALTED |
| `backend/rex_restore_drill.py` | Restore drill: SHA-256 verification, cooldown, explicit failure |
| `backend/rex_schema_check.py` | Schema validator: SCHEMA_WARNING state, affected file list |
| `core/gauntlet/scenarios/phase10_safety.yaml` | 13 safety test scenarios |

### Files Modified
| File | What changed |
|---|---|
| `core/cls_v3.py` | aging_state column, run_aging(), action trail logging, status_report aging breakdown |
| `backend/rex_command_center.py` | +9 routes: session (5), restore drill (2), schema (1), CLS (1) |
| `backend/rex_prompt_registry.py` | MSU gate in stage_edit() for protected prompts |
| `state/prompt_registry.json` | Added schema_version: "1.0" |
| `ACTIVE_SYSTEM_MANIFEST.json` | _version: 3.0-phase10, schema_version: "2.2", phase10 section |

### Architecture decisions
- Session integrity key stored at ~/.rex/session.key (chmod 600, machine-local)
- HALTED overrides UNLOCKED — protected execution blocked regardless of session state
- Unlocking grants access to protected controls; does NOT bypass approval tiers, 48h window, audit log, Gauntlet, or OCR quarantine
- Restore drill never passes silently; every failure is named and logged
- CLS aging never silently deletes; sensitive categories (identity/governance/memory/ocr) cannot auto-escalate to review_required — require explicit action
- Schema check uses "degrade" mode by default; "strict" mode available via config

### Carry-forward
- P10-CF-1: Protected edit countdown visibility in Command Center
- P10-CF-2: Override request flow (gate exists, full flow not built)
- P10-CF-3: Snapshot/revert controls (gate exists, full UI not built)

### STOP — Phase 10 only. Phase 11 not started.

---

## PHASE 11 — Final System Audit + Deployment Readiness (2026-04-15)

**Status:** COMPLETE — System is deployment ready.

### Audit results

| Part | Scope | Result |
|---|---|---|
| A | Integrity scan | PASS — 1 hash mismatch found and fixed (training-chatgpt-wednesday-v1). 15/15 clean after fix. Schema 4/4 → 5/5 |
| B | Permission boundaries | PASS — All 38 routes guarded. Role escalation blocked. OCR quarantine blocked. MSU gate verified. |
| C | Failure simulation | PASS — Tamper detection, auto-lock, max extensions, HALTED override, protected prompt gates all confirmed |
| D | Governance flow | PASS — Full Tier 2 lifecycle (stage→diff→approve→version bump→frontmatter). Reject, expire paths confirmed. |
| E | Restore drill history | BUILT — `state/restore_drill_history.jsonl` (last 50 entries). `GET /restore-drill/history` route added. |
| F | Session key lifecycle | BUILT — `rotate_key()`, `key_status()`, `POST /session/rotate-key`, `GET /session/key-status`. Lifecycle documented in code. |
| G | CLS aging report | BUILT — `state/cls_aging_report.json` written on each `run_aging()`. `review_needed` flag added. Added to schema checker. |
| H | Deployment readiness | BUILT — `state/DEPLOYMENT_READINESS.md` — full operational runbook for daily use. |

### Files created
- `state/DEPLOYMENT_READINESS.md` — operational runbook
- `state/restore_drill_history.jsonl` — persistent drill history

### Files modified
- `backend/rex_session.py` — `rotate_key()`, `key_status()`, key lifecycle docs
- `backend/rex_restore_drill.py` — `_append_history()`, `get_history()`, `DRILL_HISTORY` constant
- `backend/rex_schema_check.py` — added `cls_aging_report.json` to KNOWN_SCHEMAS
- `backend/rex_command_center.py` — +3 routes (key-status, rotate-key, drill-history) = 41 total
- `core/cls_v3.py` — `AGING_REPORT` constant, persistent report write in `run_aging()`, `review_needed` in `status_report()`
- `state/prompt_registry.json` — hash mismatch fixed (training-chatgpt-wednesday-v1)

### Final state
- Schema: 5/5 (ok)
- Prompt integrity: 15/15 clean
- Command Center routes: 41
- Governed prompts: 15 (5 protected)
- State files with schema_version: 5/5
- Session: LOCKED (correct initial state)
- Audit log entries: 40+

### STOP — Phase 11 complete.

---

## PHASE 12 — Rex/Rexxie Separation + Rex Training Foundation (2026-04-15)

**Approved by:** Kato  
**Status:** COMPLETE  

### Contamination path closed

`backend/main.py`: `rexxie.get_sovereign_block()` was previously merged into `_training_context` and passed to `_build_system_prompt()` regardless of mode. This created a path where Rexxie's private sovereign block could leak into Rex session context.

**Fix:** Explicit domain separation with two distinct variables:
- `_rexxie_context` — populated ONLY when `_is_rexxie_active=True`; used ONLY in Rexxie-mode prompt builds
- `_rex_training` — populated ONLY when `_is_rexxie_active=False`; used ONLY in Rex-mode prompt builds
These are never merged or swapped. Same fix applied to WebSocket paths.

### Files created
| File | Purpose |
|---|---|
| `backend/rex_training_classifier.py` | Classify + sanitize (fail-closed) + gate for all Rex training material |
| `state/rex_training_corpus.json` | Training candidates (pending_review → approved → committed) |
| `state/rex_separation_rules.json` | Machine-readable governance rules; in KNOWN_SCHEMAS |
| `state/rex_foundation_manifest.json` | Rex foundation tracking: approved IDs, corpus version, deployment eligibility |
| `core/gauntlet/scenarios/separation_safety.yaml` | 10 safety scenarios covering SEP-01 through SEP-10 |

### Files modified
| File | Change |
|---|---|
| `backend/main.py` | Explicit domain separation; contamination path removed |
| `backend/rex_training.py` | `log_lesson()` routes through classifier; fails closed |
| `backend/rex_schema_check.py` | +3 new state files in KNOWN_SCHEMAS (8/8 total) |
| `COMMAND_CENTER_APP.html` | Session-aware Rex/Rexxie mode toggle with immediate collapse on lock/HALTED |

### Separation rules enforced
1. `rex_may_read_rexxie_memory: false`
2. `rexxie_may_auto_enter_rex_training: false`
3. `sanitization_fails_closed: true` — uncertain content is blocked, not downgraded
4. `chairman_approval_required_for_commit: true`
5. `rexxie_exportable_by_default: false`
6. Training audit events go to `state/rex_training_audit.log` (separate from `prompt_audit.log`)

### UI — mode toggle
Session-aware Rex/Rexxie mode toggle in Command Center header.
- Rex always available (teal, 🦖)
- Rexxie toggle disabled when session LOCKED
- Rexxie toggle enabled when session UNLOCKED_PRIVILEGED
- `PRIVATE MODE: REXXIE` badge visible when Rexxie active
- Immediate collapse to Rex if session locks or HALTED triggers mid-use (polls every 15s)
- Background polling does NOT reset MSU session timer

### Schema: 8/8 (ok)

### Carry-forward
- P12-CF-1: Rex foundation badge in UI (`REX FOUNDATION v0.x`)
- P12-CF-2: Training corpus version in Command Center
- P12-CF-3: Telegram commands: `approve training <id>` / `reject training <id>`

### STOP — Phase 12 complete.

---

## PHASE 13 — Training Privacy Panel + Snapshot Governance + UI v3 (2026-04-15)

**Approved by:** Kato (with 4 refinements)  
**Status:** COMPLETE

### 4 Refinements applied before build
1. **Snapshot version context** — every snapshot includes `system_manifest_version` and `schema_version`. Safe rollback across schema changes.
2. **Quarantine manual review path** — quarantine entries include `reviewable` and `override_required` fields. Private content can be flagged as reviewable (may be salvageable via manual rewrite); sanitization failures can be resubmitted. `override_required` is always `True` — Chairman must approve any override. Auto-retry never permitted.
3. **Drift score persisted** — drift score computed and written to `state/rex_drift_history.jsonl` on every `/training/drift` request. Enables trend tracking and correlation with training batches.
4. **Batch grouping in pipeline UI** — candidates grouped by `training_batch_id` in the pipeline view. Each batch shows snapshot_id, status summary, and a Rollback Batch button.

### Files created
| File | Purpose |
|---|---|
| `backend/rex_training_snapshot.py` | Snapshot engine: create (with version context), rollback by batch |
| `backend/rex_training_panel.py` | 6-section Training Privacy Panel API (A–F) |
| `state/rex_training_quarantine.json` | Quarantine store: metadata + hash only, no raw content |
| `state/rex_training_snapshots.jsonl` | Pre-training snapshots (append-only) |
| `state/rex_drift_history.jsonl` | Drift score history (append-only) |
| `core/gauntlet/scenarios/training_privacy_redteam.yaml` | 7 red-team scenarios: C2, D1-D3, E1-E3 |

### Files modified
| File | Change |
|---|---|
| `backend/rex_training_classifier.py` | snapshot_id + batch_id on every submit; quarantine writes with reviewable/override_required; commit_approved requires snapshot_id |
| `backend/rex_command_center.py` | +2 agent registry/fleet routes = 43 total |
| `backend/rex_schema_check.py` | Added rex_training_quarantine.json to KNOWN_SCHEMAS = 9/9 |
| `COMMAND_CENTER_APP.html` | Full UI v3 restructure: 15-tab nav, Training workspace (6 sub-sections), Agent Registry, Home dashboard |

### Final state
- Schema: 9/9 (ok)
- Command Center routes: 43
- Gauntlet scenarios: 9 files
- State files: 14
- Audit separation: 20 training events in rex_training_audit.log, 0 in prompt_audit.log

### Carry-forward (Packet B)
- Agent Forge (clone/create/template engine)
- Profiles system (per-user preferences)
- Setup Studio
- Clause Oversight engine
- WebRex agent lineage integration

### STOP — Phase 13 complete.
