# Memory Correction Proposal — 2026-06-25
**Status:** ✅ APPLIED 2026-06-25 after Blue=APPROVE + Red=CHANGES-REQUIRED(B1/B2 incorporated). All edits surgical/additive; verified no true info lost (PKCE + all Victoria/Masha detail + MEMORY.md Retell/Masha facts preserved). Revert: restore from CC_memory_backups/20260625_181835/.
**Backup:** `~/Desktop/REX/CC_memory_backups/20260625_181835/` (9 files + SHA-256 manifest)

## Governing principle (the audit's job)
Every change below must **correct a verified-wrong fact** or **add a verified-true fact**.
**No correct information may be deleted.** Where text is removed, the proposal states the
evidence that it was wrong. Auditors must reject any change that deletes/alters something
that is actually true, or that asserts a "correction" not backed by live evidence.

Each item: **OLD → NEW**, **EVIDENCE**, **CLASS** = `FIX` (wrong→right) / `ADD` (new true info) / `FLAG` (mark uncertain, delete nothing).

---

## FILE 1 — `~/Documents/GHS-Vault/Hermes Perpetual Memory.md` (canon)

### 1.1 Google OAuth Token — CLASS: FIX + ADD (preserve the caution note)
OLD:
```
- **Canonical:** `~/.rex_google_token.json` — REAL FILE (NO symlinks)
- **Cron:** `bf672b2eb75f` refreshes every 30 minutes
- **Email:** IMAP via `~/.rex_gmail_imap.json` — separate from OAuth, NOT a Drive token
- **⚠️ Symlinks are destructive.** Always write real files to both ...
```
NEW:
```
- **Path:** `~/.rex_google_token.json` is currently a SYMLINK → `~/.hermes/shared/google_token.json` (the real file). [OPEN ITEM — see Flag G]
- **Scopes (verified 2026-06-25):** gmail.readonly, gmail.modify, drive.readonly, drive.metadata.readonly, **drive (full)**. ONE token serves BOTH Gmail and Drive.
- **IMAP** (`~/.rex_gmail_imap.json`, app-password, same account atigerclawai@gmail.com) is an ADDITIONAL email path — it is NOT "separate from / unrelated to Drive"; the OAuth token IS the Drive (and Gmail) token.
- **⚠️ Historical caution (preserved):** a prior incident flagged symlinks as risky for this token. Current state is a symlink (see Flag G) — do not assume both paths are independent real files.
- **Refresh:** no `com.rex.google-refresh` launchd job exists; refresh log last updated 2026-06-24. Mechanism unconfirmed — verify it is actually scheduled.
```
EVIDENCE: `ls -la` shows symlink (Jun 21) → shared file. `json scopes` = 5 scopes incl full `drive`. `~/.rex_gmail_imap.json` keys = email/app_password/imap_host/imap_port, user=atigerclawai@gmail.com. `bf672b2eb75f` not found in any scheduler (see 1.3). No `com.rex.google-refresh` in launchctl.
> NOTE: the cron ID line is REMOVED here only because it is moved/corrected in §1.3; the "30-minute refresh" intent is preserved there as an open gap. Nothing true is lost.

### 1.2 Infrastructure — Docker ports + local gw — CLASS: FIX
OLD:
```
- **Docker ports:** Dify :80, Chatwoot :3008, DocuSeal :3007, Metabase :3005, Flowise :3006, LibreChat :3080, Open WebUI :8081, BBG :4173
- **Local gateway:** :65001 (LM Studio :1234, qwen3.5:9b)
```
NEW:
```
- **Docker (verified live 2026-06-25):** UP = Dify :80, Flowise :3006. DOWN/absent = DocuSeal :3007, Metabase :3005, Chatwoot :3008, LibreChat :3080, Open WebUI :8081, BBG :4173. (Open WebUI actually runs on :3000 via launchd `ai.openwebui.hermes`, not Docker :8081.) [These remain valid *intended* services — listed as not-currently-running, not deleted.]
- **Local gateway :65001:** plist `ai.hermes.gateway` loaded but NOT serving (repairing). LM Studio :1234 (qwen3.5-9b) verified up.
```
EVIDENCE: `lsof -iTCP:<port> -sTCP:LISTEN` for each; only :80, :3006, :3000, :1234 listening. :65001 not listening; plist loaded.

### 1.3 NEW SECTION "## Scheduled Automation (verified 2026-06-25)" — CLASS: ADD + FIX
Replaces the scattered phantom cron IDs (`bf672b…`, `a33563…`, `ef3bd1…`, `75f4fd…`, `0b2991…`, `d6cd2c…`) which back NO live job. The *functions* are preserved by mapping each to the real scheduler (or flagging it as a genuine gap — nothing dropped silently).
NEW:
```
## Scheduled Automation (verified 2026-06-25)
The previously-cited cron IDs (bf672b…, a33563…, ef3bd1…, 75f4fd…, 0b2991…, d6cd2c…) are DEAD — found in no live scheduler. Real schedulers:
- **launchd (loaded):** com.goj.victoria-caller, com.goj.victoria-webhook, com.tigerclaw.notebooklm-handoff, com.goj.scheduler.{morning_report 7:30, kitchen_sheets 10:30, signin_driver_sheets 15:00, changes_routes 15:15, missing_menus_fri 20:30, weekly_email_fri 21:00}, com.rex.evening-report 21:00
- **Hermes cron (~/.hermes/cron/jobs.json, 6):** Rexxie-watch-Claus, Claus-watchman, REX-daily-backup 4:30, GOJ-Signature-Learning 13:00, Resource-Governor 5min, memory-consolidation 480m
- **n8n (6 active):** GOJ Daily Delivery 2pm, GOJ Nightly Handoff 9pm, ShellCore Health Watchdog, Morning System Report 8am, GOJ Kitchen Correction (manual), Obsidian Nightly Digest 10pm
- **Function map for the old IDs:** OAuth-refresh → NO live job (gap). NotebookLM reauth → com.tigerclaw.notebooklm-handoff (runs). owner.com poller → NO launchd job (gap; CC_owner_reservation_poller.py present but unscheduled). Victoria daily caller → com.goj.victoria-caller (runs). META token refresh → unverified.
```
EVIDENCE: grep of 6 IDs across ~/.hermes, ~/Desktop/REX, ~/.n8n = not found. `~/.hermes/cron/jobs.json` = 6 listed jobs. n8n `database.sqlite workflow_entity` = 6 active. launchctl confirms victoria-caller/webhook/notebooklm-handoff loaded; no google-refresh/owner-poller.

### 1.4 GOJ Pipeline — menu source path — CLASS: FIX
OLD: `- **Menu source:** \`goj_proprietary.db\` → \`client_menus\``
NEW: `- **Menu source:** \`~/Documents/goj files/proprietary/goj_proprietary.db\` → \`client_menus\` (2.3MB, populated). ⚠️ \`~/Desktop/REX/goj_proprietary.db\` is a 0-byte EMPTY STUB — never read it.`
EVIDENCE: REX-root copy = 0 bytes/0 tables; Documents/.../proprietary copy = 2.3MB with client_menus, victoria_calls, clients; goj_victoria_caller.py uses the Documents path.

### 1.5 Masha & Victoria — agent IDs — CLASS: FIX + FLAG
OLD: `- **Victoria (GOJ):** agent \`agent_26e3746829ae6e174f4a012bbd\` ...` and Masha `voice=cartesia-Elena, dedicated phone number`
NEW:
```
- **Victoria (GOJ) — CANONICAL: `agent_26e3746829ae6e174f4a012bbd`** (Kato-confirmed 2026-06-25: "the one Masha isn't using"). The deprecated **`agent_8a326510567e7dc3e2dc5221df`** ("Victoria-GOJ-v2") is entangled in a routing bug — the Retell number +164…3781 has a hardcoded outbound_agent forcing calls to v2. ⚠️ The live dialer `goj_victoria_caller.py` still hardcodes the v2 ID (8a3265) — NEEDS a code fix to 26e3 (separate from this memory edit).
- **Masha (BBG):** agent `agent_305ba9fdc34276c523766cd096`. ⚠️ Voice config conflicts across files (cartesia-Elena vs 11labs-Billy) and phone status conflicts ("dedicated" vs "NONE/deregistered +164…3781") — FLAG for Kato, not resolved here.
```
EVIDENCE: grep — 26e3 in .env/integration/batch_caller; 8a3265 in goj_victoria_caller.py + bbg_lana_analysis.md (documents the +164…3781 hardcoded-outbound-agent routing bug); 305ba9 in staff/masha daemon. Kato verbally confirmed Victoria = the non-Masha one (26e3).

---

## FILE 2 — `~/.hermes/profiles/cloud/memories/SOUL.md` AND `~/Documents/GHS-Vault/soul.md` (both, kept in sync) — Hard Rule #12 — CLASS: FIX (safety-critical)
OLD:
```
12. Two dashboards exist. LIVE: `~/.hermes-cloud/home/goj-pipeline/datarex/app.py` (port 8080). NOT LIVE: `~/Documents/goj files/dashboard/app.py`. Always confirm which.
```
NEW:
```
12. GOJ dashboard runs from `~/Documents/goj files/dashboard/`: gunicorn `datarex.app:app` on :8080 (plist com.goj.datarex) AND `app.py` on ~:8090 (plist com.goj.dashboard). The old `~/.hermes-cloud/home/goj-pipeline/datarex/app.py` path NO LONGER EXISTS. Confirm by PORT, not path.
```
EVIDENCE: `~/.hermes-cloud/...datarex/` dir does not exist (ls→absent). :8080 served by gunicorn datarex.app:app, cwd=goj files/dashboard (PID 999, com.goj.datarex). app.py running PID 1032 (com.goj.dashboard, ~:8090). This is a SAFETY rule inversion — top priority.

---

## FILE 3 — `~/.hermes/profiles/cloud/memories/MEMORY.md` — canonical pointer — CLASS: FIX
OLD (first § line): `§ Canonical perpetual memory: ~/.hermes/memories/USER.md. ...`
NEW (first § line): `§ Canonical perpetual memory: ~/Documents/GHS-Vault/Hermes Perpetual Memory.md (curated, read at session start, wins on conflict). Auto-capture feeder: ~/.hermes/memories/USER.md (LOOP-style cron) — merged upward, not treated as truth. ...`
EVIDENCE: new ~/.claude/CLAUDE.md + SOUL.md both name the vault file as canon; USER.md is auto-written and diverged (17 vs 6 sections). Kato decision 2026-06-25: vault = canon, USER.md = feeder. (Rest of MEMORY.md content UNCHANGED.)

---

## FILE 4 — `~/Desktop/REX/CLAUDE.md` (project governing doc) — CLASS: FIX (batch)
- Dashboard paths (Rules, Critical Paths, Code Architecture) → same correction as SOUL #12 (path no longer exists; both apps run from `goj files/dashboard`).
- venv: `~/.rex-venv/ (copy — TCC blocks Desktop)` → `REAL = ~/Desktop/REX/.venv (what uvicorn runs; plist calls ~/.rex-venv/bin/uvicorn but its shebang resolves to ~/Desktop/REX/.venv/bin/python3.11; ~/.rex-venv is a decoy). Pip-install to the REAL venv.`
- `clients ~426 rows` → `437`; `client_menus 1661+ rows` → `~7,802`.
- `rex_memory.db currently 0KB` → `28KB (non-empty)`.
- n8n `✅ 6 live` → `6 workflows active: GOJ Daily Delivery 2pm, Nightly Handoff 9pm, ShellCore Health Watchdog, Morning Report 8am, Kitchen Correction, Obsidian Digest 10pm`.
- Local gw :65001 `⚠️ Repairing` → keep "Repairing" but add `(plist loaded, not serving)`.
- `com.hermes.rexxie-bot.plist — zombie, keep disabled` → `plist FILE already deleted; launchd disabled-tombstone remains (com.hermes.rexxie-bot + com.rex.rexxie-bot). Intent satisfied.`
EVIDENCE: per FILE 2 + the three audit agents' verified results (dashboard PID trace, DB counts via sqlite COUNT, ls sizes, n8n workflow_entity, launchctl).
> All other CLAUDE.md content (Active Stack table rows that ARE correct: :3002/:8000/:8080/:27226, model routing, DeepSeek-direct, paths that exist) is PRESERVED unchanged.

---

## FILE 5 — `~/Desktop/REX/master_list.json` (chmod +w first; values only, structure unchanged) — CLASS: FIX
- `Policy Enforcer`: status `planned`→`building`, stage_percent `20`→`35`, +note "PHI fail-closed gate live in main.py (secure cloud chat 503s if de-id engine degraded)".
- `Secrecy and Disclosure Control`: status `planned`→`building`, stage_percent `20`→`30`, +note "Presidio de-id repaired (was silently regex); Gate 1 v1 (text) built; TOTP still RFC-example — rotate".
EVIDENCE: this session's verified work (live /api/health deid_engine=Presidio; main.py gate; akc_tokenizer.py v1). No other components changed.

---

## OPEN ITEMS (FLAG — delete nothing, decide later)
- **Flag G — Google token symlink:** still a symlink → shared file (Jun 21). Kato said "I fixed that" but structure unchanged (scopes were what changed). Document as symlink + open question: intended, or restore real files at both paths?
- **Victoria dialer code fix:** goj_victoria_caller.py uses deprecated 8a3265 → should change to 26e3 (code change, not this proposal).
- **owner.com poller gap:** CC_owner_reservation_poller.py has no launchd job → BBG reservations may not be polled.
- **+164…3781 routing bug:** hardcoded outbound_agent on the Retell number.

## WHAT WE ARE NOT TOUCHING (preserved verified-correct)
Cloud gw :3002 + DeepSeek-direct + model routing; REX :8000 / dashboard :8080 / TigerClaw :27226; REAL venv layout; auth_tracker.db location + plaintext status + `main` column; hub PBKDF2 auth; SOUL.md hard rules #1–#11; the Straschnow/Olympus/HHA business sections (NOT system-verifiable — left as-is, flagged NEEDS-KATO, not edited); all of USER.md (feeder, cron-owned).
