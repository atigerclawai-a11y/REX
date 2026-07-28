# MASTER_SYSTEM_WORKING_LOG.md

**Document Status:** Recovery Build — Stability First  
**Last Updated:** 2026-04-14  
**Current Stability Level:** Recovery (no new features, only fixes and enforcement)

---

## 1. Document Purpose

This document provides a legible, human-readable overview of every major subsystem in the REX/Rexxie platform. It answers:
- What systems exist and what are they doing?
- What changed recently and why?
- Which old versions are still useful?
- What needs doing today?

For detailed change tracking, see `BUILD_DECISION_HISTORY.md` and `ledger.db`.

---

## 2. Current System at a Glance

| Component | Status | Authoritative File | Last Changed | Notes |
|-----------|--------|-------------------|--------------|-------|
| **OCR Pipeline** | Active | `goj_menu_consensus_ocr.py` | 2026-04-13 | 4-engine consensus, handles menus + flags |
| **Rexxie Bot v3.0** | Active | `rex_rexxie_telegram_bot.py` | 2026-04-05 | Post-merge, Ollama optional |
| **REX Telegram Bot** | Active | `rex_telegram_bot.py` | 2026-03-28 | Staff-facing operations |
| **FastAPI Backend** | Active | `backend/main.py` | 2026-04-10 | API server, health checks, DB gateway |
| **Lucy Core** | Active | `core/` (5 phases) | 2026-03-15 | Memory, alerts, compliance, testing |
| **Scheduler** | Active | `goj_daily_scheduler.py` | 2026-03-22 | Morning reports, menu distribution |
| **Command Center** | Active | `COMMAND_CENTER.command` | 2026-04-11 | HTML dashboard for Kato's daily ops |
| **Gauntlet** | Active | `core/gauntlet/` | 2026-03-10 | 32-test suite for memory safety |
| **Dashboard** | Deployed | `frontend/` + Railway | 2026-03-20 | React app at goldhealthsys.com |

---

## 3. Major Features — Full Lineage

### 3.1 OCR Pipeline (4-Engine Consensus)

**ID:** `ocr_v1`  
**Status:** Active  
**Current File:** `~/Desktop/REX/goj_menu_consensus_ocr.py` (v1.0.0)  
**Previous File:** `~/Desktop/REX/legacy_ocr.py` (v0.0.0)  
**Last Changed:** 2026-02-01  
**Why Changed:** Needed reliable menu OCR with automatic fallbacks across multiple engines  
**Authorization:** Recovery build (part of OCR snapshot verification)  
**What Was Lost:** Legacy single-engine approach (low value — consensus is strictly better)  
**Still Useful in Older Version:** No — consensus design is comprehensive

**Details:**
- Combines Claude Vision API, Ollama (Llava), Tesseract, and EasyOCR
- Majority voting on OCR results
- Extracts menu items with confidence scores
- Feeds into `goj_menu_flags_queue.json` for manual review
- Processes both menu images and document scans
- Handles menus → staff authorization → garden activities

---

### 3.2 Claude Vision Fast-Path

**ID:** `vision_fast_path`  
**Status:** Active  
**Current File:** `~/Desktop/REX/rex_vision_flag_processor.py` (v1.0.0)  
**Previous File:** None (new in recovery build era)  
**Last Changed:** 2026-02-15  
**Why Changed:** Claude Vision was faster than Ollama for initial triage  
**Authorization:** Recovery build  
**What Was Lost:** Nothing  
**Still Useful in Older Version:** N/A

**Details:**
- Fast pre-screening of images before consensus
- Routes high-confidence matches directly
- Reduces consensus processing load
- Used for flag validation and menu triage

---

### 3.3 Lucy Core Phases 0-4

Lucy Core is the backbone of system reliability and memory management. Developed in phases:

#### Phase 0 — Foundation (2026-02-10)
**ID:** `lucy_phase_0`  
**Current File:** `~/Desktop/REX/core/alert_bus.py` + `alert_client.py` + `alert_router.py`  
**Why:** Need distributed alert routing for health checks, errors, OCR flags  
**What Changed:** N/A (new subsystem)  
**Status:** Active — handles alert queuing and dispatch  

#### Phase 1 — Memory Foundation (2026-02-18)
**ID:** `lucy_phase_1`  
**Current File:** `~/Desktop/REX/core/memory_steward.py`  
**Previous File:** `~/Desktop/REX/core/basic_memory.py`  
**Why:** Rexxie needs to remember users across sessions  
**Status:** Active — persistent user/client state tracking  
**What Was Lost:** Simple in-memory state (acceptable; persistent is strictly better)  

#### Phase 2 — Safety & Compliance (2026-03-01)
**ID:** `lucy_phase_2`  
**Current File:** `~/Desktop/REX/core/compliance_layer.py`  
**Why:** Legal requirement for HIPAA/GDPR on health data  
**Status:** Active — wraps all memory writes with privacy checks  
**What Was Lost:** Nothing (compliance is non-negotiable)  

#### Phase 3 — Gauntlet (Test Suite) (2026-03-10)
**ID:** `lucy_phase_3`  
**Current File:** `~/Desktop/REX/core/gauntlet/` (32 tests)  
**Why:** Must verify no PHI leaks, no memory corruption  
**Status:** Active — critical for preventing regressions  
**What Was Lost:** Nothing  

#### Phase 4 — OCR Schema Integration (2026-03-15)
**ID:** `lucy_phase_4`  
**Current File:** `~/Desktop/REX/core/ocr_schema.py`  
**Why:** OCR pipeline needs standard format for all engines  
**Status:** Active — bridge between OCR and memory systems  
**What Was Lost:** Nothing  

---

### 3.4 REX FastAPI Backend

**ID:** `backend_v1`  
**Status:** Active  
**Current File:** `~/Desktop/REX/backend/main.py` (v1.0.1)  
**Previous File:** None (new subsystem)  
**Last Changed:** 2026-04-10  
**Why Path Fix:** Backend was reading from wrong database. Caused sync issues.  
**Authorization:** Recovery build  
**What Was Lost:** Nothing (bug fix)  
**Still Useful in Older Version:** No

**Details:**
- Unified REST API for dashboard, bots, and CLI
- Health check endpoints (all 5 services must respond OK)
- Auth gateway to `~/Documents/goj files/dashboard/auth_tracker.db`
- Serves React frontend at `/`
- Port 8000 (configurable)
- Dependencies: fastapi, uvicorn, sqlite3

---

### 3.5 Rexxie Bot v3.0 (Post-Merge)

**ID:** `rexxie_merge_v3`  
**Status:** Active  
**Current File:** `~/Desktop/REX/rex_rexxie_telegram_bot.py` (v3.0.0)  
**Previous File:** `~/Desktop/REX/legacy_rexxie_v2.py` (v2.1.0)  
**Last Changed:** 2026-04-05  
**Why Changed:** Simplify bot architecture. Reduce security surface.  
**Authorization:** Recovery build  
**What Was Lost:** Growth-loop variant data (low value, recoverable from chat logs)  
**Still Useful in Older Version:** Keep v2 as fallback if needed  

**Details:**
- Telegram interface for Kato and Garden residents
- Memory integration via Rexxie memory DB
- Ollama feature flag (optional local LLM inference)
- Message handling: ideas, medicals, attendance, menu feedback
- Reads from: rexxie_memory.db, rex_unresolved.db
- Writes to: rexxie_memory.db

---

### 3.6 REX Telegram Bot (Staff-Facing)

**ID:** `rex_ops_bot`  
**Status:** Active  
**Current File:** `~/Desktop/REX/rex_telegram_bot.py` (v1.0.0)  
**Previous File:** None  
**Last Changed:** 2026-03-28  
**Why Changed:** N/A (new)  
**Authorization:** Recovery build  
**What Was Lost:** Nothing  

**Details:**
- Staff operations interface
- Launches manual jobs: menu send, medical extraction, audit
- Logs all commands to auth_tracker.db
- Separate from Rexxie (no memory integration)

---

### 3.7 GOJ Daily Scheduler

**ID:** `scheduler_v1`  
**Status:** Active  
**Current File:** `~/Desktop/REX/goj_daily_scheduler.py` (v1.0.0)  
**Previous File:** None  
**Last Changed:** 2026-03-22  
**Why Changed:** N/A (new in recovery era)  
**Authorization:** Recovery build  

**Jobs:**
- `morning_report` — 07:00 — sends breakfast menu & daily summary
- `kitchen_sheets` — 10:00 — updates kitchen with attendance
- `nightly_rundown` — 18:00 — delivers evening summary
- `attendance_check` — 08:30 — marks late arrivals
- `ocr_sweep` — 16:00 — processes unresolved OCR flags
- `weekly_menus` — Monday 12:00 — distributes week's menus

---

### 3.8 Staff Medical OCR

**ID:** `staff_medical_ocr`  
**Status:** Not yet running  
**Current File:** `~/Desktop/REX/staff_medical_extraction.py` (stub)  
**Why:** Extract health info from staff sign-in sheets  
**Authorization:** Recovery build (framework in place)  
**Status:** Waiting for explicit Kato sign-off (PHI sensitive)  

---

### 3.9 Menu Forms (Personalized)

**ID:** `menu_forms`  
**Status:** Active  
**Current File:** `~/Desktop/REX/goj_menu_forms.py` (v1.0.0)  
**Why:** Residents choose dietary preferences  
**Status:** Works but not currently integrated with scheduler  
**What Was Lost:** Nothing  

---

### 3.10 Sign-in Sheet Processing

**ID:** `signin_processor`  
**Status:** Active  
**Current File:** `~/Desktop/REX/goj_signin_sheets.py` (v1.0.0)  
**Why:** Parse attendance from daily sign-in pages  
**Status:** Feeds into attendance_log  
**What Was Lost:** Nothing  

---

### 3.11 Flag Queue Processor

**ID:** `flag_queue`  
**Status:** Active  
**Current File:** `~/Desktop/REX/goj_menu_flags_queue.json` (queue file)  
**Current Count:** 28 unresolved items  
**Why:** Manual review queue for ambiguous OCR results  
**Status:** Active — Kato reviews and approves via COMMAND_CENTER  
**What Was Lost:** Nothing  

---

### 3.12 Command Center (HTML Dashboard)

**ID:** `command_center_v1`  
**Status:** Active  
**Current File:** `~/Desktop/REX/COMMAND_CENTER.command` (v1.0.0)  
**Last Changed:** 2026-04-11  
**Why Changed:** N/A (new)  
**Authorization:** Recovery build  

**Provides:**
- Dashboard for Kato to run daily jobs
- Menu send
- Medical extraction
- Flag review queue
- Attendance check
- OCR sweep
- Health check (all 5 services)
- Launch from `~/Desktop/REX/COMMAND_CENTER.command`

---

### 3.13 Gauntlet (32-Test Suite)

**ID:** `gauntlet_v1`  
**Status:** Active  
**Current File:** `~/Desktop/REX/core/gauntlet/` (test suite)  
**Last Run:** 2026-04-13  
**Results:** See `~/Desktop/REX/data/gauntlet_reports/`  
**Why:** Verify memory system correctness and safety  
**Tests Cover:**
- No PHI leaks to logs
- Memory writes persist correctly
- Compliance checks fire on sensitive data
- Circular reference detection
- State machine correctness

---

### 3.14 Alert Bus & Routing

**ID:** `alert_system`  
**Status:** Active  
**Current File:** `~/Desktop/REX/core/alert_bus.py` + `alert_router.py` (v1.0.0)  
**Why:** Distributed error/flag/warning routing  
**Status:** Fallback to JSONL file queue  
**Fallback Queue:** `~/Desktop/REX/data/alert_bus_fallback.jsonl`  

---

### 3.15 SEED_REXXIE_MEMORY

**ID:** `memory_seeding`  
**Status:** Available (not yet run)  
**Current File:** `~/Desktop/REX/SEED_REXXIE_MEMORY.command`  
**Purpose:** Initialize Rexxie memory with current user list, preferences, ideas  
**When to Run:** After security rotation, before FIX_REXXIE  
**Authorization:** Recovery build (Kato confirms)  

---

## 4. Idea Lineage

| Feature ID | Origin Idea | Decision Date | Implemented | Status |
|-----------|------------|---------------|-------------|--------|
| ocr_v1 | "Need menus electronically" | 2026-02-01 | Garden of Joy daily workflow | Active |
| lucy_phase_0-4 | "System must be reliable and trustworthy" | 2026-02-10 | Core subsystem | Active |
| rexxie_merge_v3 | "Simplify bot security surface" | 2026-04-05 | Single bot architecture | Active |
| backend_v1 | "Need unified API for web + bots" | 2026-03-20 | FastAPI server | Active |
| command_center_v1 | "Kato needs one dashboard for daily ops" | 2026-04-11 | HTML dashboard | Active |
| staff_medical_ocr | "Extract health info from sign-in sheets" | 2026-03-01 | Stub exists, not running | Waiting |

---

## 5. Duplicate / Override Registry

| What Was Overridden | Replaced By | Why | Worth Keeping Old? |
|--------------------|-------------|-----|-------------------|
| `legacy_ocr.py` | `goj_menu_consensus_ocr.py` | Single engine too unreliable | No — consensus is strictly better |
| `basic_memory.py` | `memory_steward.py` | In-memory state lost on restart | No — persistent memory is critical |
| `legacy_rexxie_v2.py` | `rex_rexxie_telegram_bot.py` (v3.0) | Security surface reduction + merge | Yes (as fallback) — keep for recovery |
| `private_confidant_gold.py` | (merged into main bot) | Simplify architecture | No — disabled by manifest |
| `start_rexxie.command` | `FIX_REXXIE.command` | Unified startup | No — old launcher disabled |

---

## 6. Security Status

**CRITICAL ISSUES (Immediate Action Required):**

1. **Telegram Token Exposure**
   - Currently in: `.env` file + 26 source files
   - **ACTION REQUIRED:** Rotate immediately to ~/.keychain (Mac)
   - Affected files: See `BUILD_DECISION_HISTORY.md` for full list

2. **Anthropic API Key Exposure**
   - Currently in: `.env` file
   - **ACTION REQUIRED:** Rotate immediately to ~/.keychain (Mac)
   - Used by: OCR consensus engine (Claude Vision)

3. **2FA Secrets in Files**
   - `.rexxie_2fa_secret` file
   - `.rexxie_device_secret` file
   - Should be in keychain, not plaintext

**Post-Rotation Checklist:**
- [ ] Rotate Telegram token to keychain
- [ ] Rotate Anthropic key to keychain
- [ ] Update `.env` with placeholder values only
- [ ] Run `SEED_REXXIE_MEMORY.command`
- [ ] Run `FIX_REXXIE.command` to start clean
- [ ] Verify all 5 services running
- [ ] Run `STAMP_KNOWN_GOOD.command` to lock state

---

## 7. Immediate Operational Needs (Today)

**For Kato to operate the system RIGHT NOW:**

1. **Send Today's Menus**
   - [ ] Open `~/Desktop/REX/COMMAND_CENTER.command`
   - [ ] Click "Send Menu"
   - [ ] Confirm recipients

2. **Check Attendance**
   - [ ] Click "Attendance Check" in Command Center
   - [ ] Review late arrivals
   - [ ] Manual corrections as needed

3. **Review OCR Flags**
   - [ ] Click "Review Flags" in Command Center
   - [ ] For each of 28 items: Approve or Quarantine
   - [ ] Quarantined items go to `~/Desktop/REX/data/ocr_quarantine/`

4. **Health Check**
   - [ ] Click "Health Check" in Command Center
   - All 5 services must show GREEN:
     - rex_backend (port 8000)
     - rexxie_bot
     - rex_telegram_bot
     - scheduler
     - alert_router

5. **Extract Staff Medicals** (IF Kato approves)
   - [ ] Click "Extract Medical Data"
   - [ ] Review extracted data
   - [ ] Confirm storage location
   - [ ] Log decision in ledger

---

## 8. Decision History Summary

Key architectural decisions with authorization source:

| Decision | Date | Subsystem | Authorized By | Status |
|----------|------|-----------|----------------|--------|
| Use 4-engine consensus for OCR | 2026-02-01 | OCR | Recovery build | Active |
| Lucy Core 5-phase architecture | 2026-02-10 | Core | Recovery build | Active |
| FastAPI + SQLite (no external DB) | 2026-03-20 | Backend | Recovery build | Active |
| Merge rexxie bots into single v3.0 | 2026-04-05 | Bot | Recovery build | Active |
| Disable REX_AUDIT and GHS_AUDIT | 2026-04-14 | Audit | Recovery build | Active |
| Quarantine Gold_Health_Systems/ | 2026-04-14 | Security | Recovery build | Active |

---

## 9. Known Issues / Open Items

### Critical Issues (From MEMORY.md)

1. **Memory Never Recalled**
   - Status: Open
   - Impact: Rexxie can't retrieve past user state
   - Workaround: SEED_REXXIE_MEMORY (partial)

2. **User Model Empty**
   - Status: Open
   - Impact: Memory system has no user profiles
   - Workaround: Manual seed via command

3. **Vault Recovery Incomplete**
   - Status: Open
   - Impact: Encrypted data not fully accessible
   - Files: `~/Desktop/REX/data/vaults/`

4. **RBAC Gap**
   - Status: Open
   - Impact: No fine-grained role access control
   - Workaround: Monolithic admin model for now

### Current Operational Issues

1. **28 Unresolved OCR Flags**
   - Queue: `~/Desktop/REX/goj_menu_flags_queue.json`
   - Action: Kato to review via Command Center

2. **Staff Medical Extraction Not Running**
   - Status: Stub complete, not deployed
   - Action: Await Kato's explicit OK (PHI)

3. **Railway Dashboard Disconnected**
   - URL: goldhealthsys.com (marketing site)
   - Note: Operational but not integrated with local system

---

## 10. System Recovery Procedures

If the system fails:

1. **Start Fresh**
   ```bash
   ~/Desktop/REX/FIX_REXXIE.command
   ```
   - Stops all processes
   - Verifies manifest
   - Starts all 5 services in correct order
   - Health check

2. **Verify Checksums**
   - Compare current state against `KNOWN_GOOD_STATE.json`
   - See `MASTER_SYSTEM_CHECKSUM.md` for forensics

3. **Review Ledger**
   - `~/Desktop/REX/data/ledger.db`
   - All changes logged with authorization

4. **Quarantine Suspect Files**
   - If unsure, move to `~/Desktop/REX/QUARANTINE/`
   - Log the decision in ledger

---

**Document Version:** 2.0 (Recovery Build)  
**Next Review Date:** 2026-04-21  
**Maintained By:** Recovery Build Automation
