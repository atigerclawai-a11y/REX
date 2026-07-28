# MASTER SYSTEM FILE LOG — REX/Rexxie Garden of Joy
**Generated:** 2026-04-14 05:35 UTC  
**System:** REX (Chairman AI) + Rexxie (Telegram Bot) + GOJ Dashboard  
**Environment:** macOS Desktop (local-only, no remote auth)  
**Scope:** All major artifacts across OCR, backend, frontend, database, config, audit, and supporting systems

---

## DOCUMENT PURPOSE

This ledger itemizes every major file and artifact in the REX ecosystem. For each entry, it documents:
- **What it is** (type, role, subsystem)
- **Where it lives** (path)
- **Current state** (size, last modified, whether it's live or legacy)
- **Authority level** (1=latest/authoritative, 2=backup, 3=legacy/stale)
- **Disposition** (Keep/Quarantine/Review)
- **Why** (reasoning for each decision)

This log serves as:
1. A source-of-truth map for "which file is actually being used?"
2. A guide for what to delete when regressions occur
3. A record of what was moved to quarantine and why
4. A reference for future forensic analysis

---

## SUBSYSTEM GROUPING

### 1. OCR PIPELINE & VISION
| ID | Path | Type | Status | Size | LastMod | SoT | Decision | Reason | Notes |
|-----|------|------|--------|------|---------|-----|----------|--------|-------|
| OCR-001 | `/OCR_WORKING_SNAPSHOT_2026_04_14_0524/` | DIR-Snapshot | **ACTIVE** | 240K | 2026-04-14 05:24 | 1 | **KEEP** | Working OCR snapshot created during recovery—contains the last good OCR state | Contains RUN_OCR.command, RUN_VISION_OCR.command, goj_menu_consensus_ocr.py, rex_vision_flag_processor.py |
| OCR-002 | `goj_menu_consensus_ocr.py` | PY-Consensus | ACTIVE | 38K | 2026-04-14 05:24 | 1 | **KEEP** | Phase 1 OCR consensus vote logic—weighted scoring for menu OCR | Core OCR feature; used in vision pipeline |
| OCR-003 | `rex_vision_flag_processor.py` | PY-Vision | ACTIVE | 29K | 2026-04-14 05:24 | 1 | **KEEP** | Phase 4 Gauntlet—flags problematic OCR results for manual review | Prevents bad OCR from corrupting data |
| OCR-004 | `goj_signin_ocr_processor.py` | PY-SignIn | ACTIVE | 18K | 2026-04-14 05:24 | 1 | **KEEP** | Sign-in sheet OCR—extracts attendance from PDF sheets | Live dependency for attendance tracking |
| OCR-005 | `/data/ocr_mirror/` | DIR-Mirror | ACTIVE | 128K | 2026-04-14 01:56 | 1 | **KEEP** | Live OCR working directory—input/output staging | Real-time OCR artifact location |
| OCR-006 | `/data/ocr_quarantine/` | DIR-Quarantine | MONITOR | 16K | 2026-04-14 01:56 | 1 | **KEEP** | Flagged OCR results awaiting review | Don't delete—critical audit trail |
| OCR-007 | `_archive/old_ocr_scripts/goj_direct_ocr_reader.py` | PY-Legacy | LEGACY | 6.2K | 2025-03-15 | 3 | **QUARANTINE** | Pre-consensus OCR reader—replaced by goj_menu_consensus_ocr.py | Direct reader lacks voting/weighting |
| OCR-008 | `_archive/old_ocr_scripts/goj_menu_ocr_processor.py` | PY-Legacy | LEGACY | 7.1K | 2025-03-20 | 3 | **QUARANTINE** | Early OCR processor—superseded by consensus + flag pipeline | No longer used in active pipeline |
| OCR-009 | `_archive/old_ocr_commands/RUN_OCR_NOW.applescript` | APPLESCRIPT-Legacy | LEGACY | 1.2K | 2026-03-10 | 3 | **QUARANTINE** | AppleScript OCR trigger—predates CLI commands | Manual triggering mechanism, unused |
| OCR-010 | `_archive/old_ocr_commands/RUN_ALL_OCR.command` | CMD-Legacy | LEGACY | 2.1K | 2026-03-25 | 3 | **QUARANTINE** | Old batch OCR runner—no longer maintained | Bulk runner replaced by modular commands |
| OCR-011 | `_archive/old_ocr_data/paperless_raw_ocr.json` | JSON-Data | LEGACY | 145K | 2026-02-28 | 3 | **QUARANTINE** | Legacy Paperless OCR output—replaced by Claude Vision | Raw Tesseract output, not used |
| OCR-012 | `_archive/old_ocr_data/paperless_all_menu_ocr.json` | JSON-Data | LEGACY | 89K | 2026-03-05 | 3 | **QUARANTINE** | Aggregated Paperless OCR—superseded by consensus vote | Historical OCR, no live dependency |

### 2. LUCY CORE — ALERT BUS & MEMORY STEWARD
| ID | Path | Type | Status | Size | LastMod | SoT | Decision | Reason | Notes |
|-----|------|------|--------|------|---------|-----|----------|--------|-------|
| LUCY-001 | `/data/alert_bus_fallback.jsonl` | JSONL-Stream | ACTIVE | 10.6K | 2026-04-14 04:38 | 1 | **KEEP** | Phase 0 Alert Bus—event log for unresolved items & escalations | Live audit trail; do not delete |
| LUCY-002 | `/data/gauntlet_reports/` | DIR-Reports | ACTIVE | 96K | 2026-04-14 04:38 | 1 | **KEEP** | Phase 4 Gauntlet output—reviewed + flagged items | Historical audit of processed items |
| LUCY-003 | `/data/rex_events.db` | DB-Events | ACTIVE | 61.4K | 2026-04-14 04:32 | 1 | **KEEP** | Event tracking database—all system events, timestamps, actors | Critical audit log; SQLite format |
| LUCY-004 | `/data/rex_unresolved.db` | DB-Queue | ACTIVE | 36.9K | 2026-04-14 04:32 | 1 | **KEEP** | Unresolved items queue—red flags, escalations, pending decisions | Chairman Command Center reads this |
| LUCY-005 | `rex_memory.db` | DB-Memory | **EMPTY** | 0K | 2026-04-13 05:02 | 2 | **REVIEW** | RexMemory persistence layer (named `rex_memory.db`)—EMPTY (regression) | Should contain chairman's persistent facts |
| LUCY-006 | `rexxie_memory.db` | DB-Memory | ACTIVE | 60K | 2026-04-13 02:40 | 1 | **KEEP** | Rexxie persistent memory—chat context, user profiles, learned behaviors | Working memory for Telegram bot |
| LUCY-007 | `rex_user_model.db` | DB-UserModel | **EMPTY** | 0K | 2026-04-11 20:47 | 2 | **REVIEW** | User model database (per MEMORY.md critical issues)—EMPTY (regression) | Should track user preferences, history |

### 3. AUTHORIZATION & PERMISSIONS
| ID | Path | Type | Status | Size | LastMod | SoT | Decision | Reason | Notes |
|-----|------|------|--------|------|---------|-----|----------|--------|-------|
| AUTH-001 | `/data/rex_permissions.db` | DB-RBAC | ACTIVE | 45.1K | 2026-04-13 09:45 | 1 | **KEEP** | Role-based access control database—staff/chairman roles, permissions | Backend auth layer |
| AUTH-002 | `/data/rex_override.db` | DB-Override | ACTIVE | 32.8K | 2026-04-13 09:12 | 1 | **KEEP** | Override rules—exceptions to standard RBAC | Chairman exceptional access tracking |
| AUTH-003 | `backend/rex_role_auth.py` | PY-Auth | ACTIVE | 8.2K | 2026-04-13 08:15 | 1 | **KEEP** | Role verification module—chairman-only gate for command center | Validates `X-User-Name` and `X-Claimed-Role` headers |
| AUTH-004 | `backend/rex_unified_enforcer.py` | PY-Enforcer | LEGACY | 14.3K | 2026-04-12 15:22 | 2 | **REVIEW** | Unified policy enforcer (intended but not wired)—per RED_TEAM_AUDIT | Exists but imported by zero files; needs activation or deprecation |

### 4. BACKEND & API
| ID | Path | Type | Status | Size | LastMod | SoT | Decision | Reason | Notes |
|-----|------|------|--------|------|---------|-----|----------|--------|-------|
| BACKEND-001 | `backend/main.py` | PY-FastAPI | ACTIVE | 18.6K | 2026-04-13 08:15 | 1 | **KEEP** | REX FastAPI server—core entrypoint, WebSocket, REST endpoints | Starts on port 8000; mounts routers for chairman, exec, chat |
| BACKEND-002 | `backend/rex_command_center.py` | PY-Routes | ACTIVE | 12.4K | 2026-04-13 08:15 | 1 | **KEEP** | Chairman Command Center API—system health, red flags, unresolved queue | `/api/chairman/*` routes; chairman-only auth gate |
| BACKEND-003 | `backend/config.py` | PY-Config | ACTIVE | 9.1K | 2026-04-13 08:15 | 1 | **REVIEW** | Settings loader—API keys, model selection, DB paths | Per RED_TEAM_AUDIT, line 103 has cloud fallback; should default to Ollama |
| BACKEND-004 | `backend/auth.py` | PY-Auth | ACTIVE | 7.8K | 2026-04-13 08:15 | 1 | **KEEP** | Device auth, JWT handling, phone unlock server | iPhone pairing, desktop trust model |
| BACKEND-005 | `backend/memory.py` | PY-RexMemory | ACTIVE | 11.3K | 2026-04-13 08:15 | 1 | **KEEP** | RexMemory class—persistent facts, recall API | Maps to `rex_memory.db` (currently empty) |
| BACKEND-006 | `backend/storage.py` | PY-Storage | ACTIVE | 6.9K | 2026-04-13 08:15 | 1 | **KEEP** | Encrypted local storage—master key, cipher operations | Base layer for all encryption |
| BACKEND-007 | `backend/deidentify.py` | PY-DeID | ACTIVE | 14.2K | 2026-04-13 08:15 | 1 | **KEEP** | De-identification engine—PHI masking for Claude requests | Secure mode optional feature |
| BACKEND-008 | `backend/audit.py` | PY-Audit | ACTIVE | 8.7K | 2026-04-13 08:15 | 1 | **KEEP** | Audit logger—logs all API calls, policy decisions, role checks | Feeds into `rex_events.db` |
| BACKEND-009 | `backend/rex_telegram_reader.py` | PY-TgReader | ACTIVE | 9.5K | 2026-04-13 08:15 | 1 | **KEEP** | Telegram integration—fetch channel messages, schedule summaries | GOJ_LOCKED_PARAMETERS.md scheduled reads |
| BACKEND-010 | `backend/rex_gmail.py` | PY-Gmail | ACTIVE | 12.1K | 2026-04-13 08:15 | 1 | **KEEP** | Gmail integration—inbox, labels, auto-archiving, menu PDF downloads | Background watcher polls every 5 min |
| BACKEND-011 | `.env` | CONFIG | **RISKY** | 2.1K | 2026-04-13 | 1 | **REVIEW** | API keys file—PLAINTEXT (per RED_TEAM_AUDIT critical) | Contains Anthropic key; should use Keychain instead |

### 5. REXXIE TELEGRAM BOT
| ID | Path | Type | Status | Size | LastMod | SoT | Decision | Reason | Notes |
|-----|------|------|--------|------|---------|-----|----------|--------|-------|
| REXXIE-001 | `rex_rexxie_telegram_bot.py` | PY-Bot | ACTIVE | 27.4K | 2026-04-13 08:15 | 1 | **KEEP** | Rexxie main bot—Telegram event handler, message routing, command dispatch | Runs as background process; started by FIX_REXXIE.command |
| REXXIE-002 | `rex_rexxie_telegram_config.json` | JSON-Config | **RISKY** | 1.2K | 2026-04-13 08:15 | 1 | **REVIEW** | Rexxie config—bot token (appears 33 times in codebase per RED_TEAM_AUDIT) | CRITICAL: Token is plaintext, needs Keychain storage |
| REXXIE-003 | `private_confidant_gold.py` | PY-Enforcer | ACTIVE | 45.2K | 2026-04-13 08:15 | 1 | **KEEP** | Rexxie policy enforcer—jailbreak blocking, PHI detection, tone correction | Live security layer; imports `rex_policy_enforcer.py` |
| REXXIE-004 | `rex_policy_enforcer.py` | PY-PolicyEnforcer | ACTIVE | 13.8K | 2026-04-13 08:15 | 1 | **KEEP** | Policy rules engine—checks inbound/outbound Telegram messages | Used by `private_confidant_gold.py`; governance rules stored in `rex_policy_rules.json` |
| REXXIE-005 | `rex_policy_rules.json` | JSON-Rules | ACTIVE | 22.3K | 2026-04-13 08:15 | 1 | **KEEP** | Policy rule definitions—forbidden terms, disclosure tiers, tone rules | Line 63: "Tier enforcement is advisory until auth is wired" (not yet done) |
| REXXIE-006 | `rexxie.db` | DB-Rexxie | ACTIVE | 164K | 2026-04-13 08:15 | 1 | **KEEP** | Rexxie conversation database—all Telegram chats, metadata, flags | Primary Rexxie data store |
| REXXIE-007 | `rexxie_memory.db` | DB-Memory | ACTIVE | 60K | 2026-04-13 02:40 | 1 | **KEEP** | Rexxie memory—persistent user context, learned behaviors | Shared with Lucy core |

### 6. GOJ DASHBOARD
| ID | Path | Type | Status | Size | LastMod | SoT | Decision | Reason | Notes |
|-----|------|------|--------|------|---------|-----|----------|--------|-------|
| GOJ-001 | `~/Documents/goj files/dashboard/` | DIR-App | ACTIVE | 1.2M | 2026-04-13 | 1 | **KEEP** | GOJ Dashboard Flask app—client profiles, staff, schedules, forms | Separate database (`auth_tracker.db`) from REX; this is the REGRESSION POINT |
| GOJ-002 | `~/Documents/goj files/dashboard/auth_tracker.db` | DB-GOJ | **SEPARATE** | 512K | 2026-04-13 | 1 | **REVIEW** | GOJ Dashboard local database—user auth, client profiles, staff list (NOT synced with REX) | **CRITICAL:** This is separate from REX/Rexxie databases; Railway website uses different DB |
| GOJ-003 | `goj_daily_scheduler.py` | PY-Scheduler | ACTIVE | 8.4K | 2026-04-13 08:15 | 1 | **KEEP** | GOJ scheduled jobs—morning reports, kitchen sheets, driver routes | Calls Rexxie via Telegram API; uses `auth_tracker.db` |
| GOJ-004 | `~/.rex/rex_journeys.db` | DB-Journeys | MONITOR | 256K | 2026-04-13 | 1 | **KEEP** | REX user journeys & staff accounts—admin password stored here | Updated by FRESH_START.command when password reset |

### 7. FRONTEND & BUILDS
| ID | Path | Type | Status | Size | LastMod | SoT | Decision | Reason | Notes |
|-----|------|------|--------|------|---------|-----|----------|--------|-------|
| FRONTEND-001 | `frontend/` | DIR-React | ACTIVE | 180M | 2026-04-13 08:15 | 1 | **KEEP** | REX web UI—React build, static assets, dist output | Serves on port 8000 from `backend/main.py`; rebuilt by `rex-rebuild.command` |
| FRONTEND-002 | `rex-rebuild.command` | CMD-Build | ACTIVE | 3.9K | 2026-04-13 08:15 | 1 | **REVIEW** | Frontend rebuild script—runs `npm run build`, restarts backend/bots | **WARNING:** Can revert dashboard assets if run; step [2/4] rebuilds from source |
| FRONTEND-003 | `backend/menus.db` | DB-Menus | ACTIVE | 512K | 2026-04-12 07:10 | 1 | **KEEP** | Menu data for frontend—weekly menus, personalization, form responses | Consumed by GOJ dashboard widget |

### 8. SYSTEM COMMANDS & CONTROL
| ID | Path | Type | Status | Size | LastMod | SoT | Decision | Reason | Notes |
|-----|------|------|--------|------|---------|-----|----------|--------|-------|
| CONTROL-001 | `FRESH_START.command` | CMD-Auth | ACTIVE | 3.2K | 2026-04-13 08:15 | 1 | **KEEP** | Token reset only—preserves all data, resets JWT secret & admin password | Safe recovery path; step [2/4] updates chairman password to `chairman2026` |
| CONTROL-002 | `FIX_REXXIE.command` | CMD-Restart | ACTIVE | 7.5K | 2026-04-13 08:15 | 1 | **KEEP** | Full service restart—kills REX backend, GOJ dashboard, bots; starts fresh | Last 3 lines show status; kills ports 8000, 8080 |
| CONTROL-003 | `rex-rebuild.command` | CMD-Build | ACTIVE | 3.9K | 2026-04-13 08:15 | 1 | **REVIEW** | Frontend rebuild—runs npm build from scratch; can revert custom assets | **CAUTION:** Don't run unless you want to rebuild React code |

### 9. AUDIT & SECURITY LOGS
| ID | Path | Type | Status | Size | LastMod | SoT | Decision | Reason | Notes |
|-----|------|------|--------|------|---------|-----|----------|--------|-------|
| AUDIT-001 | `REX_RED_TEAM_AUDIT_2026-04-13.md` | MD-Report | **CRITICAL** | 19K | 2026-04-13 02:58 | 1 | **KEEP** | Red team security audit—3 critical, 5 high, 4 medium findings | See CRITICAL FINDINGS section in BUILD_DECISION_HISTORY.md |
| AUDIT-002 | `REX_AUDIT_REPORT.md` | MD-Report | LEGACY | 12K | 2026-03-28 | 2 | **KEEP** | Older audit report—for historical comparison | Superseded by RED_TEAM_AUDIT |
| AUDIT-003 | `REX_AUDIT.command.DISABLED_2026_04_14` | CMD-Audit | DISABLED | 2.3K | 2026-04-14 04:35 | 1 | **KEEP** | Audit script (disabled during recovery)—READ-ONLY tool, doesn't modify state | Was running on 12-hour timer; now turned off |
| AUDIT-004 | `GHS_AUDIT.command.DISABLED_2026_04_14` | CMD-Audit | DISABLED | 13K | 2026-04-14 04:35 | 1 | **KEEP** | Gold Health Systems audit (disabled during recovery)—READ-ONLY tool | Was running; now disabled |
| AUDIT-005 | `/data/audit_log.jsonl` | JSONL-Log | MINIMAL | 577B | 2026-04-11 21:43 | 2 | **KEEP** | Legacy audit log—very sparse entries | Likely replaced by `rex_events.db` |

### 10. BACKUPS & SNAPSHOTS
| ID | Path | Type | Status | Size | LastMod | SoT | Decision | Reason | Notes |
|-----|------|------|--------|------|---------|-----|----------|--------|-------|
| BACKUP-001 | `/REX_Backups/REX_2026-04-13_03-04/` | DIR-Backup | **ACTIVE-REGRESSION** | 12M | 2026-04-13 03:04 | 2 | **REVIEW** | April 13 backup (0304 UTC)—last snapshot before regressions reported | Contains `.env` with plaintext Anthropic key; has Telegram token in 5+ files |
| BACKUP-002 | `/REX_Backups/REX_2026-04-12_20-37/` | DIR-Backup | STABLE | 8.1M | 2026-04-12 20:37 | 2 | **KEEP** | April 12 backup (2037 UTC)—snapshot before April 13 regression point | Good reference point if April 13 is fully corrupted |
| BACKUP-003 | `/REX_Backups/REX_2026-04-10_16-47/` | DIR-Backup | BASELINE | 13M | 2026-04-10 16:47 | 2 | **KEEP** | April 10 baseline—known good state, 3 days before regressions | Comprehensive snapshot; useful for comparison |
| BACKUP-004 | `/RECOVERY_SNAPSHOT_2026_04_14_0525/` | DIR-Snapshot | **FORENSIC** | 9.8M | 2026-04-14 05:25 | 1 | **KEEP** | April 14 recovery snapshot—taken during forensic analysis | Reference for this session's investigation |
| BACKUP-005 | `/OCR_WORKING_SNAPSHOT_2026_04_14_0524/` | DIR-Snapshot | **FORENSIC** | 240K | 2026-04-14 05:24 | 1 | **KEEP** | April 14 OCR snapshot—working OCR pipeline state at start of recovery | Starting point for OCR recovery |

### 11. CONFIG & ENV
| ID | Path | Type | Status | Size | LastMod | SoT | Decision | Reason | Notes |
|-----|------|------|--------|------|---------|-----|----------|--------|-------|
| CONFIG-001 | `backend/config.py` | PY-Config | ACTIVE | 9.1K | 2026-04-13 08:15 | 1 | **REVIEW** | Backend settings—defaults to cloud fallback per RED_TEAM_AUDIT | Line 103: should be `ollama/llama3` not `anthropic/claude-sonnet` |
| CONFIG-002 | `.env` | ENV-Keys | **RISKY** | 2.1K | 2026-04-13 | 1 | **REVIEW** | API keys—PLAINTEXT ANTHROPIC KEY (per RED_TEAM_AUDIT critical) | Should use macOS Keychain; key appears in backups unencrypted |
| CONFIG-003 | `rex_rexxie_telegram_config.json` | JSON-Config | **RISKY** | 1.2K | 2026-04-13 08:15 | 1 | **REVIEW** | Rexxie config—bot token HARDCODED (appears 33 times per RED_TEAM_AUDIT) | Token `8657319466:...` is COMPROMISED; needs Keychain |
| CONFIG-004 | `.env.example` | ENV-Template | INFO | 2.1K | 2026-04-10 | 2 | **KEEP** | Example env file—for reference | Good template for what keys should be set |
| CONFIG-005 | `GOJ_LOCKED_PARAMETERS.md` | MD-Spec | REFERENCE | 3.8K | 2026-04-08 | 1 | **KEEP** | GOJ operational parameters—schedule, routes, locked definitions | Source of truth for scheduler timing |

### 12. LEGACY ARCHIVE (_archive/)
| ID | Path | Type | Status | Size | LastMod | SoT | Decision | Reason | Notes |
|-----|------|------|--------|------|---------|-----|----------|--------|-------|
| ARCHIVE-001 | `_archive/old_ocr_scripts/` | DIR-Legacy | LEGACY | 13.3K | 2026-04-12 08:08 | 3 | **QUARANTINE** | Pre-consensus OCR readers—goj_direct_ocr_reader.py, goj_menu_ocr_processor.py | Consensus pipeline supersedes; no live dependency |
| ARCHIVE-002 | `_archive/old_ocr_commands/` | DIR-Legacy | LEGACY | 8.9K | 2026-04-12 08:27 | 3 | **QUARANTINE** | Old OCR CLI commands—RUN_OCR_NOW.applescript, RUN_ALL_OCR.command, etc | Modular commands now used instead |
| ARCHIVE-003 | `_archive/old_ocr_data/` | DIR-Legacy | LEGACY | 234K | 2026-04-12 08:27 | 3 | **QUARANTINE** | Legacy Paperless OCR output—paperless_raw_ocr.json, paperless_all_menu_ocr.json | Not consumed by current pipeline |
| ARCHIVE-004 | `_archive/old_shell_scripts/` | DIR-Legacy | LEGACY | 128K | 2026-04-12 08:27 | 3 | **QUARANTINE** | Old shell infrastructure—various setup, cleanup, and utility scripts | Superseded by newer Python and bash scripts |
| ARCHIVE-005 | `_archive/legacy_bots/` | DIR-Legacy | LEGACY | 96K | 2026-04-12 08:30 | 3 | **QUARANTINE** | Pre-unified bot versions—telegram, discord, old versions | Current bot is `rex_rexxie_telegram_bot.py` |
| ARCHIVE-006 | `_archive/old_html/` | DIR-Legacy | LEGACY | 89K | 2026-04-12 08:27 | 3 | **QUARANTINE** | Legacy HTML templates—before React frontend | Not used; static assets are in `frontend/` |
| ARCHIVE-007 | `_archive/old_reports/` | DIR-Legacy | LEGACY | 145K | 2026-04-12 08:27 | 3 | **QUARANTINE** | Legacy report outputs—historical PDF exports, analyses | Archive only; not actively generated |
| ARCHIVE-008 | `_archive/one_time_scripts/` | DIR-Legacy | LEGACY | 78K | 2026-04-12 08:28 | 3 | **QUARANTINE** | One-time migration & setup scripts—not meant to be rerun | Data migration, initial setup; no dependency |
| ARCHIVE-009 | `_archive/superseded_commands/` | DIR-Legacy | LEGACY | 112K | 2026-04-12 08:28 | 3 | **QUARANTINE** | Old command runners—replaced by FIX_REXXIE.command, FRESH_START.command, etc | Outdated CLI tool versions |

### 13. TRAINING & CURRICULUM
| ID | Path | Type | Status | Size | LastMod | SoT | Decision | Reason | Notes |
|-----|------|------|--------|------|---------|-----|----------|--------|-------|
| TRAIN-001 | `rex_curriculum_log.db` | DB-Training | ACTIVE | 12K | 2026-04-13 08:00 | 1 | **KEEP** | Training curriculum log—quiz attempts, learning paths, progress | Used by `rex_quiz.py` in backend |
| TRAIN-002 | `rex_quiz.py` | PY-Quiz | ACTIVE | 6.2K | 2026-04-13 08:15 | 1 | **KEEP** | Quiz engine—chairman training on system features | Interactive training tool |

### 14. COORDINATOR & ORCHESTRATION
| ID | Path | Type | Status | Size | LastMod | SoT | Decision | Reason | Notes |
|-----|------|------|--------|------|---------|-----|----------|--------|-------|
| COORD-001 | `rex_coordinator.db` | DB-Coord | ACTIVE | 16K | 2026-04-12 21:30 | 1 | **KEEP** | Coordinator state—tracks inter-process status, task sequencing | Used by background tasks |
| COORD-002 | `rex_background_knowledge.db` | DB-Knowledge | ACTIVE | 16K | 2026-04-01 21:02 | 1 | **KEEP** | Background knowledge—facts, reference data, lookup tables | Available to Claude for context |

### 15. DATA & STAGING
| ID | Path | Type | Status | Size | LastMod | SoT | Decision | Reason | Notes |
|-----|------|------|--------|------|---------|-----|----------|--------|-------|
| DATA-001 | `/data/` | DIR-Root | ACTIVE | 548K | 2026-04-14 04:38 | 1 | **KEEP** | Main data directory—all runtime databases and cache | Root of operational state |
| DATA-002 | `/data/hot_folder/` | DIR-Staging | ACTIVE | 64B | 2026-04-11 21:43 | 1 | **KEEP** | Hot folder for upload processing—quick ingestion staging | Temporary working directory |
| DATA-003 | `/data/vaults/` | DIR-Vaults | ACTIVE | 256K | 2026-04-14 04:38 | 1 | **KEEP** | Encrypted credential vaults—agent-specific encrypted blobs | Chairman vault, backend vault, etc. |
| DATA-004 | `/data/content_update_queue.db` | DB-Queue | ACTIVE | 24.6K | 2026-04-13 09:44 | 1 | **KEEP** | Update queue—pending content changes, import jobs | Background task staging |
| DATA-005 | `/data/attendance_today_preview.json` | JSON-Data | MONITOR | 37.9K | 2026-04-13 17:41 | 1 | **KEEP** | Today's attendance cache—quick reference | Refreshed daily from sign-in sheets |

---

## REGRESSION ROOT CAUSE ANALYSIS

**Question:** Why are "client profiles not working" and "staff list gone"?

**Answer:** The GOJ Dashboard (`~/Documents/goj files/dashboard/`) uses a **separate database** (`auth_tracker.db`) from REX/Rexxie. This database is **not synced** with the local REX databases.

The Railway website (`respectful-intuition-production-0acf.up.railway.app`) also uses a **different database** from the local system.

**Three separate database systems exist:**
1. **REX/Rexxie local** — `/Desktop/REX/*.db` files (rexxie.db, rex_memory.db, etc.)
2. **GOJ Dashboard local** — `~/Documents/goj files/dashboard/auth_tracker.db`
3. **Railway website** — Remote RDS or managed database (not accessible from sandbox)

**What this means for regressions:**
- If `auth_tracker.db` is empty or corrupted, the dashboard shows no clients or staff
- If the Railway database was rolled back or reset, the website is out of sync
- The `rex_rebuild.command` (step 2/4) rebuilds React frontend but doesn't touch these databases

**Fix path (not executed in this session):**
1. Check if `auth_tracker.db` is empty or corrupted
2. Restore from a recent backup of `auth_tracker.db` (if available)
3. Verify Railway database state with the ops team or hosting provider
4. Set up automated sync between GOJ Dashboard DB and REX core DBs (not currently done)

---

## SOURCE-OF-TRUTH DECISIONS

### Client/Member Database
- **GOJ Dashboard:** `~/Documents/goj files/dashboard/auth_tracker.db` ← THIS is the authoritative client database
- **REX:** `rex_memory.db` and `rexxie.db` contain supplementary context, not source-of-truth
- **Railway:** Unknown (separate remote system)

### Staff Database
- **GOJ Dashboard:** `auth_tracker.db` → `staff_users` table
- **REX:** Not replicated; only Telegram chat IDs are tracked
- **Backup:** `REX_Backups/` contain historical snapshots

### Authorization Storage
- **Backend:** `data/rex_permissions.db` (RBAC rules)
- **Per RED_TEAM_AUDIT:** Tier enforcement is advisory; no live auth check in bot
- **Recommendation:** Wire auth check into `private_confidant_gold.py` handle()

### Upload/Document Storage
- **Backend:** `uploads/` directory (path from main.py line 105)
- **Gmail:** Menu PDFs downloaded to local via `rex_gmail.py`
- **GOJ Dashboard:** Receives files via web forms

### Active Backend Entrypoint
- **Host:** `localhost:8000` (macOS desktop only)
- **Process:** `python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000`
- **Started by:** `FIX_REXXIE.command` (step 2/4) or `rex-rebuild.command` (step 3/4)

### Active Frontend Build
- **Location:** `frontend/` directory
- **Build command:** `npm run build` (run by `rex-rebuild.command`)
- **Served by:** FastAPI static mount in `backend/main.py`
- **URL:** `http://localhost:8000`

### OCR Input/Output
- **Input:** Gmail inbox (watched by `backend/rex_gmail.py`) or manual uploads
- **Processing:** `goj_menu_consensus_ocr.py` + `rex_vision_flag_processor.py`
- **Output:** `data/ocr_mirror/` (working directory) and `data/gauntlet_reports/` (reviewed items)
- **Flagged items:** `data/ocr_quarantine/` (await manual review)

### Dashboard Data Source
- **GOJ Dashboard reads from:** `auth_tracker.db` (separate from REX)
- **Frontend reads from:** FastAPI endpoints in `backend/main.py`
- **Database:** `backend/menus.db` contains weekly menus

---

## NOTES ON REGRESSION POINTS

### Why REX Broken?
- Backend may not be running (killed by FIX_REXXIE.command)
- Or frontend rebuild (rex-rebuild.command step 2) failed mid-build
- Or port 8000 is occupied by another process

### Why Rexxie Can't Consume OCR?
- OCR consensus pipeline (`goj_menu_consensus_ocr.py`) requires Claude Vision API key
- If `ANTHROPIC_API_KEY` is missing or expired, OCR returns empty results
- Per RED_TEAM_AUDIT: key is in plaintext `.env` and was backed up unencrypted

### Why Website Reverted?
- Railway website uses a separate remote database
- If the Rails/Flask app on Railway was rolled back to an older deploy, it uses old schema
- Check deployment history on Railway dashboard

### Why Authorizations Missing?
- `rex_permissions.db` may be empty or schema is missing
- Or authorization check in `private_confidant_gold.py` was bypassed (fallback policy allows all)
- Per RED_TEAM_AUDIT: Tier enforcement is advisory, no actual auth gate in bot

### Why Client Profiles Not Working?
- `auth_tracker.db` is empty or corrupted
- Or GOJ Dashboard Flask app crashed or stopped responding
- Check if `~/Documents/goj files/dashboard/` is accessible and `app.py` is running

### Why Staff List Gone?
- Same as client profiles—staff list is in `auth_tracker.db`, separate from REX core

---

## GRAND SUMMARY

| Subsystem | Authority File(s) | Status | Risk Level | Action |
|-----------|-------------------|--------|------------|--------|
| OCR Pipeline | `goj_menu_consensus_ocr.py`, `/data/ocr_mirror/` | WORKING | LOW | Keep; monitor |
| Lucy Alert Bus | `/data/alert_bus_fallback.jsonl`, `/data/rex_events.db` | ACTIVE | LOW | Keep; audit trail |
| Rexxie Bot | `rex_rexxie_telegram_bot.py`, `rexxie.db` | ACTIVE | MEDIUM | Keep; token needs Keychain |
| REX Backend | `backend/main.py`, port 8000 | ACTIVE | LOW | Keep; check config.py line 103 |
| GOJ Dashboard | `~/Documents/goj files/dashboard/auth_tracker.db` | SEPARATE | HIGH | Investigate regression; not synced with REX |
| Authorizations | `data/rex_permissions.db` + policy enforcer | ADVISORY ONLY | HIGH | Per RED_TEAM_AUDIT, tie enforcement to live auth gate |
| Config/Keys | `.env`, `rex_rexxie_telegram_config.json` | RISKY | CRITICAL | Move to Keychain (Anthropic key + Telegram token) |
| Memory | `rex_memory.db`, `rex_user_model.db` | EMPTY (regression) | HIGH | Investigate why empty; per MEMORY.md critical issues |
| Archive | `_archive/` | LEGACY | NONE | Safe to quarantine; no live dependencies |

