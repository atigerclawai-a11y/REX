# CLAUDE.md — Hermes Governing Document
# Gold Health Systems · v4.0 · June 1 2026
# Every line earns its place. This governs all agents, sessions, and builds.
# Source of truth: ~/Desktop/Gold_Health_Systems/BRAIN/MASTER.md
# KARPATHY SECOND BRAIN: Read these in order at EVERY session start (TCC-safe mirror at ~/GHS-Vault/):
#   1. ~/GHS-Vault/SCHEMA.md — Constitution, taxonomy, hard rules, 24h schedule
#   2. ~/GHS-Vault/Objectives.md — What should I be working on?
#   3. ~/GHS-Vault/index.md — Complete vault catalog (150+ pages)
#   4. ~/GHS-Vault/log.md — Recent actions (last 30 lines)
#   5. ~/GHS-Vault/Hermes Perpetual Memory.md — Canonical system state
#   6. ~/GHS-Vault/Hermes Session Brief.md — Ecosystem map
#   7. ~/GHS-Vault/sources/2026-07-09_operating-manual.md — [[Operating Manual]]: Part A (standing orders), Part B (failure modes), self-test. Every agent is bound by these.
#   8. ~/GHS-Vault/Cloud Backups/claude-wiki/index.md — Claude Code wiki (44 pages, all agents, complete system reference)
# Canonical vault at ~/Documents/GHS-Vault/ (Obsidian). Mirror at ~/GHS-Vault/ (TCC-safe, rsync'd every 15min).

---

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

## System Identity

Hermes is the AI gateway and operations brain for Gold Health Systems. It orchestrates all agents, routes all tasks, reviews all outputs, escalates to Kato. Every AI that reads this file is bound by its rules.

Kato (Alejandro, `mainsobhelper`, atigerclawai@gmail.com, Telegram 5587703834) is Chairman. **He overrides everything. Always. No rule in this document supersedes him.** Never call him Allen — that's a former GOJ employee. Vlad is business partner, financial view only, not Chairman.

Mission: fully local, privacy-first, multi-agent AI OS for Gold Health Systems. Proving ground: Garden of Joy adult day care (425 clients, Brooklyn NY). Every build must advance GHS operations or justify its existence.

---

## Rules

Larry never appears on any transport or driver list — not in any context, not under any instruction. DeepSeek always routes direct: `provider: deepseek` + `base_url: https://api.deepseek.com/v1`, never OpenRouter. New files get `CC_` prefix; existing files keep their names. Share files via `attachments[]` only — `computer://` breaks iOS. PHI stays local: `auth_tracker.db` never reaches cloud, Presidio de-id runs on all outbound data. Rexxie's private lane is local-only and never divulges its contents. No real-world action without PAE (Propose → Approve → Execute). GOJ client names, medical data, and financials never enter OG 33 prompts. `akc_tokenizer.py` = Gate 1 — hard block on all cloud PHI routing until it's fully built. The office Mac (16GB) is air-gapped from GOJ data and financials. `com.hermes.rexxie-bot.plist` is a zombie — never enable it, it crashes and steals the Rexxie token. GOJ dashboard runs from `~/Documents/goj files/dashboard/`: gunicorn `datarex.app:app` on :8080 (`com.goj.datarex`) AND `app.py` on ~:8090 (`com.goj.dashboard`). The old `~/.hermes-cloud/home/goj-pipeline/datarex/app.py` path no longer exists — confirm by PORT, not path. **Google: IMAP for email, OAuth for Drive/Sheets (per Kato override Jul 19).** Email via IMAP App Password (`~/.rex_gmail_imap.json`). Drive/Sheets/Calendar → OAuth now permitted per Chairman directive: "Oauth is ok i need you to heave full access to google." Service account (`~/.rex_drive_service_account.json`) kept as backup. OAuth token files are authorized. IMAP-only rule is REVOKED by Kato.

---

## Autonomy

Propose before building anything new. Kato says "build it" / "do it" / "just do it" → proceed without further questions. Read files, check logs, restart services, update memory, debug, and report autonomously. Ask first for new features, schema changes, anything hard to reverse, anything sent on Kato's behalf.

---

## All Agents

Claude, DeepSeek, Rexxie, Hermie, Nemobot, Claus, Jarvis, any future agent — same rules. Minimum code that solves the problem, nothing speculative, nothing unrequested. Touch only what you must. Match existing style. Define success before starting.

Tiers: Chairman (Kato) = everything. Vlad = financial view. FrontDesk = demographics + auth only. Kitchen = PDF handoffs only. Driver = route sheets only. Restricted = read-only, no PHI.

---

## Data & Security

`auth_tracker.db` lives at `~/Documents/goj files/dashboard/auth_tracker.db` — never in cloud, not yet SQLCipher encrypted (top open item). `rexxie.db` is Kato's private confidant — zero GOJ data, zero crossover, enforced always. Presidio on all outbound. AES-256-GCM for Rexxie messages, SQLCipher vault via `rex_sqlcipher_vault.py`, ChaCha20 for large blobs. Master keys in macOS Keychain: `rex-sovereign`, `rexxie-2fa-secret`. TOTP = RFC example `JBSWY3DPEHPK3PXP` — zero real security, must rotate. RBAC via `rex_permissions.py`. Every write to `auth_tracker.db` gets an audit trail entry. Soft deletes only.

---

## GOJ Operations

Schedule change cascade is atomic — when a client changes day or calls sick, all 7 update or none: Calendar → Attendance → Driver list → Kitchen list → Distribution logs → Sign-in sheets → Client menu.

Auth statuses: `ACTIVE` = may attend. `EXPIRED` = do not schedule without Kato. `PENDING RENEWAL` = submitted, may continue. `EXPIRED` >30 days with no `PENDING RENEWAL` → escalate immediately, flag in report, don't remove from schedule.

Menus: Russian 2-page form, 425 clients, 1 week ahead, Mon–Sat only. DB column is `main`, not `main_dish`.

Daily automation via `@goldhealth_rexxie_bot`: 7:30 AM morning report · 10:30 AM kitchen+distribution PDFs · 3:15 PM signin+driver sheets · 8:30 PM Fri missing menus · 9 PM drop-off rundown · 9 PM Fri weekly email summary.

Read `~/Documents/goj files/GOJ_WORKING_DOC.md` at session start. Update at end. "awake" → health check (8080/8000/8765 + launchctl) → working doc → status + Priority 1 goals.

---

## Build Governance

Gate 1 = `akc_tokenizer.py` — no PHI to cloud until built, no exceptions. PAE = Propose → Approve → Execute — no exceptions for production actions. Phases 1–13 locked. Phase 13-V verification before Phase 14+. north_star: local-first · privacy-first · deterministic · no unapproved cloud · ideas integrate · check regressions · check future complexity · strong disclosure protection · locked architecture parameters. Scripts: `CC_` prefix, `.command` in `~/Desktop/REX/`, logs via `exec > >(tee "$LOG") 2>&1`.

---

## Active Stack (Mac Mini M4, 24GB, `mainsobhelper`)

| Service | Port | Manager | Status |
|---------|------|---------|--------|
| Hermes cloud gw | 3002 | `ai.hermes.gateway-cloud.plist` | ✅ Primary |
| Hermes local gw | 65001 | `ai.hermes.gateway.plist` | ⚠️ Repairing (plist loaded, not serving) |
| REX FastAPI (Nemobot) | 8000 | `com.rex.backend.plist` | ✅ |
| GOJ Dashboard | 8080 | `com.goj.datarex.plist` | ✅ LIVE |
| Tiger Claw API | 27226 | `com.tigerclaw.api.plist` | ✅ |
| Open WebUI | 3000 | `ai.openwebui.hermes.plist` | Docker |
| LibreChat | 3080 | Docker | ❌ |
| Hermes AI Hub | 3003 | Docker | — |
| Claus Watchman | — | `com.hermes.claus-watchman.plist` | ✅ |
| n8n | — | `com.goj.n8n.plist` | ✅ 6 workflows active |
| Ollama | 11434 | local | mistral-hermie, qwen2.5-coder:7b |
| LM Studio | 1234 | local | qwen3.5-9b MLX |
| Cloudflare tunnel | — | `~/.cloudflared/hermestigerclaw.yml` | ✅ |

⚠️ Two Hermes installs: `~/.hermes/` = main gateway (THIS is Hermes). `~/.hermes-cloud/` = BBG social, GOJ datarex.

Restart any Hermes gateway: `launchctl unload <plist>` → `pkill -f "hermes_cli.main.*gateway"` → `sleep 8` → `launchctl load <plist>`

Gateway: deepseek-v4-pro via api.deepseek.com/v1 (NEVER OpenRouter) · fallback: claude-sonnet-4-6 → gemini-2.0-flash · high-stakes: claude-opus-4-6 · config: `~/.hermes/profiles/cloud/config.yaml`

Model routing: Local/Hermie → mistral-hermie (128k, no thinking mode) · Code → qwen2.5-coder:7b · Cheap cloud → grok-3-mini · Orchestration → claude-sonnet-4-6 · High-stakes → claude-opus-4-6

Bots: `@Hermes_Cloud_May_bot` = Hermes · `@goldhealth_rexxie_bot` = confidant (private lane, local only) · `@HermieChatt_bot` = Hermie · `@RexOfGold_bot` = GOJ ops · `@GOJReceipts_bot` = billing · `@GojAttendance_bot` = attendance

---

## Critical Paths

| What | Path |
|------|------|
| Source of truth | `~/Desktop/Gold_Health_Systems/BRAIN/MASTER.md` |
| This file | `~/Desktop/REX/CLAUDE.md` |
| Dashboard LIVE (:8080) | `~/Documents/goj files/dashboard/` — gunicorn `datarex.app:app` (com.goj.datarex). Old `~/.hermes-cloud/…/datarex/app.py` path no longer exists. |
| Dashboard DB | `~/Documents/goj files/dashboard/auth_tracker.db` |
| Dashboard app.py (:8090) | `~/Documents/goj files/dashboard/app.py` — running via com.goj.dashboard |
| REX scripts | `~/Desktop/REX/` |
| REX logs | `~/Desktop/REX/logs/` |
| Working doc | `~/Documents/goj files/GOJ_WORKING_DOC.md` |
| REX venv (dev) | `~/debate-chamber/.venv/` |
|| REX venv (launchd) | REAL = `~/Desktop/REX/.venv/` (what uvicorn actually runs; the plist calls `~/.rex-venv/bin/uvicorn` but its shebang resolves to `~/Desktop/REX/.venv/bin/python3.11`; `~/.rex-venv` is a decoy). Pip-install to the REAL venv. |
|| **CANONICAL SHEET GENERATOR** | `CC_unified_sheets.py` — ONLY active. DO NOT use `generate_distribution_sheet.py`, `generate_kitchen_sheet.py`, `goj_kitchen_paired.py` (deprecated). Usage: `python3 CC_unified_sheets.py --date YYYY-MM-DD --kind all` |
| Hermes source | `~/.hermes/hermes-agent/` (v0.15.1) |
| Hermes config | `~/.hermes/profiles/cloud/config.yaml` |
| Hermes SOUL | `~/.hermes/profiles/cloud/memories/SOUL.md` |
| Hermes MEMORY | `~/.hermes/profiles/cloud/memories/MEMORY.md` |
| Hermes .env | `~/.hermes/profiles/cloud/.env` |
| Rexxie DB | `~/Desktop/REX/rexxie.db` |
| Build registry | `~/Desktop/REX/master_list.json` |
| Knowledge archive | `~/Desktop/REX/CC_HERMES_KNOWLEDGE.md` — full session detail, all agent statuses, repo tiers, open items. Reference when MEMORY.md doesn't have enough detail. |

---

## Database (auth_tracker.db)

`clients` 437 rows · `authorization` (service_end_date = expiry, ACTIVE/EXPIRED/PENDING RENEWAL) · `menus` (week_start patched Apr 2026) · `client_menus` ~7,802 rows, column=`main` NOT `main_dish`, confidence=OCR 0–1 · `employees` 15 rows · `pending_schedule_changes`

---

## Dev Commands

```bash
curl -s http://localhost:8080/health && curl -s http://localhost:8000/health
# Also available: /api/health (original endpoint)
launchctl list | grep -E "hermes|rex|goj"

launchctl unload ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist
pkill -f "hermes_cli.main.*gateway" && sleep 8
launchctl load ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist

tail -f ~/.hermes/profiles/cloud/logs/gateway.log
sqlite3 "~/Documents/goj files/dashboard/auth_tracker.db" ".tables"
source ~/debate-chamber/.venv/bin/activate
```

---

## Known Issues

`com.hermes.rexxie-bot` — plist FILE already deleted; launchd disabled-tombstone remains (com.hermes.rexxie-bot + com.rex.rexxie-bot). Local gw port 65001 — loaded but not serving (repairing). DeepSeek 402 — check provider=deepseek in config.yaml. `rex_memory.db` — actually 28KB (not 0KB); `rex_user_model.db` 0KB. `auth_tracker.db` — not encrypted (plaintext SQLite, confirmed). TOTP — RFC example secret, must rotate.

---

## Derivation Chain

```
BRAIN/MASTER.md  ← Kato maintains. One source of truth.
      ↓
CLAUDE.md        ← This file. Governs all agents. Every session reads this.
      ↓                         ↓
SOUL.md                    MEMORY.md
~/.hermes/profiles/        ~/.hermes/profiles/
cloud/memories/            cloud/memories/
~50 lines identity         §-delimited, 2800 chars
      ↓
master_list.json  ← Build registry. rex_coordinator.py reads this.
```

Update MASTER.md → update CLAUDE.md → regenerate SOUL.md → install → update MEMORY.md → verify → test @Hermes_Cloud_May_bot.

---

## Code Architecture

### REX FastAPI Backend (`~/Desktop/REX/backend/`)

**Entry point:** `main.py` (3,976 lines) — FastAPI app, Desktop Mode (localhost = always trusted, no auth token). Singletons initialized at startup: Settings, EncryptedStorage, AuditLogger, DeidentificationEngine, LiteLLMProxy, RexMemory, AgentBus, ChairmanVault, RexTraining, RexNotify, RexxieMode, RexQuiz.

**Start REX (dev):**
```bash
source ~/debate-chamber/.venv/bin/activate
cd ~/Desktop/REX
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```
**Start REX (production):** `launchctl load ~/Library/LaunchAgents/com.rex.backend.plist` (uses `~/.rex-venv/`)

**Core modules:**

| Module | Purpose |
|--------|---------|
| `config.py` | `Settings` class — Keychain-first API key storage, `~/.rex/config.json`, providers: anthropic/openai/google/xai/perplexity/librechat |
| `storage.py` | `EncryptedStorage` — AES-256-GCM SQLite, Argon2 key derivation, master key in macOS Keychain |
| `deidentify.py` | `DeidentificationEngine` — all 18 HIPAA Safe Harbor identifiers via Presidio; per-session entity mapping for multi-turn consistency |
| `litellm_proxy.py` | LiteLLM adapter — routes to correct provider per model string |
| `agent_bus.py` | `AgentBus` — AES-256-GCM inter-agent comms, per-agent HKDF key: `f"rex-agent-bus-{agent_id}"` |
| `sovereign.py` | `build_system_prompt()` — assembles REX identity + injected memory blocks at runtime |
| `memory.py` | `RexMemory` — persistent facts across sessions (NOTE: `rex_memory.db` is ~28KB, non-empty) |
| `rex_vault.py` | `ChairmanVault` — encrypted secrets store for Kato; separate from GOJ data |
| `rex_rexxie.py` | `RexxieMode` + `RexxieMemory` — private Kato-only confidant; triple-encrypted, isolated DB (`rexxie.db`), zero GOJ crossover |
| `rex_gmail.py` | Gmail OAuth2 integration — inbox digest, auto-labeling, search. Token: `~/.rex_google_token.json`. Credentials: `~/Desktop/REX/google_credentials.json` |
| `rex_gdrive.py` | Google Drive upload/list/sync — shared token with Gmail |
| `rex_menu_scan_watcher.py` | Background task (5-min loop) — watches Gmail for scan emails from Allen/scanner, downloads PDFs, triggers 4-engine OCR pipeline, reports via Telegram |
| `rex_training.py` | Feedback/training data capture |
| `rex_ai_enrichment.py` | Background AI context enrichment |
| `rex_behavior_monitor.py` | Response safety/behavior checking |
| `rex_encrypted_transcript.py` | `TranscriptStore` + `EncryptedSessionCache` — session backup and resume |
| `rex_telegram_reader.py` | Reads Telegram channels for schedule context |
| `rex_role_auth.py` | RBAC — Chairman/FrontDesk/Kitchen/Driver tier enforcement |
| `rex_notify.py` | Notification dispatch |
| `audit.py` | `AuditLogger` — every write to auth_tracker.db gets audit trail entry |
| `auth.py` | JWT device pairing for iPhone; localhost always trusted |
| `models.py` | Pydantic request/response models |

**Chat pipelines:**
- **Secure Mode** (PHI): Receive → Encrypt locally → De-ID (Presidio) → Send to AI → Re-ID → Display → Encrypt response
- **Standard Mode**: Receive → Encrypt locally → Send to AI → Display → Encrypt response

**Key REST endpoints:** `/api/chat` (GOJ dashboard widget), `/api/memory` (CRUD), `/api/health`, `/api/gmail/*`, `/api/gdrive/*`, WebSocket `/ws` (desktop chat)

---

### GOJ Dashboard (runs from `~/Documents/goj files/dashboard/`, port 8080)

Served by gunicorn `datarex.app:app` on :8080 (plist `com.goj.datarex`), cwd `~/Documents/goj files/dashboard/`. A separate `app.py` also runs there on ~:8090 (plist `com.goj.dashboard`). The old `~/.hermes-cloud/home/goj-pipeline/datarex/app.py` path NO LONGER EXISTS.

**Daily JSON files** (in `~/.hermes-cloud/home/goj-pipeline/data/`): The 9 pipeline outputs (morning report, attendance, kitchen list, driver sheets, etc.) are written by the automation scripts and read by the dashboard. When Gmail OAuth token expires, all 9 go stale → Claus Watchman RED.

---

### Gmail OAuth Re-auth (when token expires)

```bash
source ~/debate-chamber/.venv/bin/activate
cd ~/Desktop/REX
python backend/rex_gmail.py --setup
# Opens browser → Google auth → writes ~/.rex_google_token.json
```

---

### GOJ Pipeline Data Flow

```
Allen scans menu forms → allen@gardenofjoybrooklyn.com → atigerclawai@gmail.com
  ↓ (rex_menu_scan_watcher, every 5 min)
Gmail API downloads PDF → ~/Desktop/REX/menus/
  ↓
4-engine OCR consensus (Tesseract + Google Drive + Paperless + Claude Vision)
  ↓ (confidence voting)
client_menus table (auth_tracker.db) — column: `main` NOT `main_dish`
  ↓
Rexxie reports result to Kato via Telegram

Daily automation (launchd / n8n):
  7:30 AM → morning report JSON
  10:30 AM → kitchen + distribution PDFs
  3:15 PM → signin + driver sheets
  8:30 PM Fri → missing menus alert
  9:00 PM → drop-off rundown
  9:00 PM Fri → weekly email summary
```

---

### Hermes Gateway (port 3002)

Source: `~/.hermes/hermes-agent/` (v0.15.1). Config: `~/.hermes/profiles/cloud/config.yaml`. Identity: `~/.hermes/profiles/cloud/memories/SOUL.md` + `MEMORY.md` (both `chflags uchg` locked — PIN required to modify).

Model routing in config.yaml: deepseek-v4-pro (primary) → claude-sonnet-4-6 (fallback) → gemini-2.0-flash (fallback). High-stakes: claude-opus-4-6.

---

### Tests

```bash
source ~/debate-chamber/.venv/bin/activate
cd ~/Desktop/dashboard   # dashboard tests live here
python -m pytest tests/ -v
python -m pytest tests/test_rexxie_clarification_and_nightly_review.py -v
python -m pytest tests/test_rexxie_learning_memory_ops.py -v
```

---

---

### Session-End Protocol (MANDATORY)

**Before ending any Claude Code session, you MUST write a session summary to the Obsidian vault.** This is the Karpathy "write your own playbook" pattern — the model must persist its learnings as explicit text, not just weights.

**Template:** Copy from `Cloud Backups/claude-wiki/concepts/Session-End Prompt Template.md` in the vault.

**Location:** Write to `Cloud Backups/claude-sessions/YYYY-MM-DD-<topic-slug>.md`

**Required format:**
- YAML frontmatter: `title`, `created`, `updated`, `type: session`, `tags`
- Sections: What We Did, Decisions Made, Key Learnings, Files Changed, Open Items
- Minimum 3 `[[wikilinks]]` to existing concept/entity pages
- All file paths absolute
- No PHI or secrets

**After writing, run the checklist:** `Cloud Backups/claude-wiki/concepts/Session Validation Checklist.md`

**Failure to do this = lost work.** Every session that doesn't write to Obsidian is a session another agent (or your future self) has to redo from scratch. The goal: any agent in any future session can read these pages and know exactly what was done, why, and what's left.

**Safety net:** A Hermes cron job (`4b6cb574bab2`) runs every 2 hours and auto-detects work with no dump. If you fall asleep, it writes an auto-recovery dump to Obsidian.

---

### `akc_tokenizer.py` (Gate 1 — HARD BLOCK)

Located at `~/Desktop/dashboard/akc_tokenizer.py`. **Not yet fully built.** Until Gate 1 is complete, zero production cloud routing of PHI. All PHI stays local. This is the only condition under which Secure Mode PHI may flow to cloud AI — never before.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
