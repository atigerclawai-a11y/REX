# CC_SESSION_LOG_2026-05-31.md
# GHS/GOJ — Full Session Capture
# Date: May 31, 2026
# Purpose: Permanent capture of all new information, decisions, and discoveries from this session.
# This file is the safety net. MASTER.md is the source of truth. SOUL.md derives from MASTER.md.

---

## SOURCE OF TRUTH ARCHITECTURE (Decision Made This Session)

**BRAIN/MASTER.md** = the ONE unequivocal source of truth. All other documents derive from it.

| Document | Role | Updates |
|----------|------|---------|
| `BRAIN/MASTER.md` | Source of truth — what IS true right now | Kato maintains |
| `SOUL.md` | Hermes identity core — generated FROM MASTER.md, installed into Hermes | Regenerate when MASTER.md changes |
| `CLAUDE.md` | Claude/Cowork working context — derived from MASTER.md | Keep in sync |
| `MEMORY.md` | Hermes session-to-session operational notes | Short-term, NOT source of truth |
| `Obsidian vault` | Long-form documentation, meeting notes, deep dives | Reference material only |
| `GOJ_WORKING_DOC.md` | Active work log | Ephemeral |
| Auto-memory | Claude Cowork session-to-session recall | Persists across Cowork conversations |

**The cycle that was breaking things:** Multiple competing "truth" documents drifting out of sync.
**The fix:** Update MASTER.md → regenerate SOUL.md → install → verify. One update, one direction.

---

## DOMAINS OWNED

| Domain | Status | Purpose |
|--------|--------|---------|
| `hermestigerclaw.com` | Live | Primary Hermes/REX infrastructure. All services via Cloudflare tunnel (`*.hermestigerclaw.com`). |
| `goldhealthsys.com` | Live | GHS marketing site + employee login portal. "The Gold Standard in Medical Collaboration." 34 modules, REX at center. Sign-in modal for employees links to internal dashboard. |

**goldhealthsys.com is hosted via Railway or Tiger Claw** (exact host TBD — confirm with Kato).

---

## GHS PRODUCT — goldhealthsys.com

**Live marketing landing page** for Gold Health Systems. Not a placeholder — it's fully built and publicly accessible. Features REX AI prominently.

**Employee login:** Sign-in modal at top of page. Employees enter via this portal into the dashboard (authorizations, billing, 837/835 files, etc.).

**34 Modules with current status as listed on site:**

| Module | Status |
|--------|--------|
| REX AI Workspace | CORE |
| Rexxie Private AI | CORE |
| Command Dashboard | LIVE |
| Custom Permissions | LIVE |
| Document Center | LIVE |
| Menu & Nutrition | LIVE |
| Staff Management | LIVE |
| Attendance Engine | LIVE |
| Route Generator | LIVE |
| Client Profiles | LIVE |
| Insurance Analytics | LIVE |
| Sign-In Sheet PDFs | LIVE |
| PIN-Gated Access | LIVE |
| Mobile PWA | LIVE |
| Telegram Bots | LIVE |
| Compliance Monitor | LIVE |
| Report Generator | LIVE |
| Kitchen Operations | LIVE |
| Daily Curriculum | LIVE |
| Security Red/Blue Team | LIVE |
| Encrypted Backups | LIVE |
| Theme Engine | LIVE |
| Claims 837 Engine | LIVE |
| Payments 835 | LIVE |
| Driver Scheduler | LIVE |
| Live Fleet Tracker | NEW |
| Auth Reader AI | NEW |
| Email PDF Watcher | NEW |
| iOS Native App | NEW |
| REX Messaging | SOON |
| Widget Marketplace | SOON |
| Training Tracker | SOON |
| Meeting Scheduler | SOON |

**IMPORTANT NOTE:** "LIVE" on the marketing site ≠ fully operational end-to-end. Kato to verify which modules are truly working vs. aspirational. This distinction must be maintained in MASTER.md.

---

## EMAIL INTAKE FLOW

| Address | Purpose |
|---------|---------|
| `atigerclawai@gmail.com` | PRIMARY. Receives everything: scans from Allen, bills, project communications, all external intake. OAuth account for Gmail/Google Drive. |
| `allen@gardenofjoybrooklyn.com` | WORK EMAIL. Used to send all document scans to atigerclawai@gmail.com. |

**Scan workflow:**
1. Physical documents scanned at facility
2. Scanner sends PDF to `allen@gardenofjoybrooklyn.com`
3. Allen manually forwards/sends to `atigerclawai@gmail.com` with labeled subject line when possible
4. Scanned PDFs have auto-generated long numeric filenames (no human-readable labels on the file itself)
5. Gmail scanner watches atigerclawai@gmail.com, routes inbound docs
6. OCR identifies unlabeled PDFs by matching against templates in Google Drive

**Goal:** Automate so scans route directly from scanner to Gmail — no manual forwarding step. Not yet live.

**OCR identification logic:** All form templates are stored in Google Drive `templates/` folder. The OCR pipeline pattern-matches incoming unlabeled PDFs against these templates to identify document type (auth form, menu form, billing form, etc.).

---

## GOOGLE DRIVE STRUCTURE

**Account:** atigerclawai@gmail.com
**OAuth credentials:** `~/Desktop/REX/google_credentials.json` → `~/.rex_google_credentials.json`
**Token:** `~/.rex_google_token.json`

**Top-level folders (confirmed from screenshot, May 31 2026):**

| Folder | Last Modified | Purpose |
|--------|--------------|---------|
| `Claude Session PDFs` | Tue 4:41PM | PDFs generated during Claude/Cowork working sessions |
| `GOJBot` | Mar 11 | GOJ Telegram bot related files |
| `Hermes Backups` | Wed 10:16PM | Hermes configuration and data backups — disaster recovery |
| `march 9 menu` | Mar 8 | Menu file (shared, specific date) |
| `remittance` | Mar 18 | 835 ERA files (Electronic Remittance Advice from insurance payers) |
| `templates` | May 7 | **CRITICAL OCR DEPENDENCY** — form templates used to identify unlabeled scan PDFs |
| `Tigerclaw_AI` | Wed 9:37AM | Tiger Claw related files and assets |
| `[NotebookLM] GHS Vault — Ful...` | — | Google Doc used for NotebookLM one-directional sync |

**LOCKED DEPENDENCY:** `templates/` folder in Google Drive is required for OCR pipeline operation. If this folder is moved, renamed, or its contents changed without updating the OCR pattern-matching config, document identification breaks.

**NotebookLM bridge (one-directional):**
- ghs-strategy sync: ~268K chars
- goj-ops sync: ~1.27M chars
- Nothing from NotebookLM feeds back into Hermes

---

## HR / EMPLOYEE FILING SYSTEM

**Current state:** MANUAL. Kato manually tracks when employee items need updating (medicals, trainings, inservices, certifications, renewals).

**Planned system:** Structured central filing environment where:
- All employee files are uploaded to one central location
- System tracks expiration dates for: medical exams, training certifications, inservice completions, any compliance items
- Auto-alerts when items are approaching expiration
- This is the **Training Tracker** module listed as SOON on goldhealthsys.com

**This was discussed in depth in previous sessions.** The requirement exists, the spec exists somewhere, the module is planned.

**Related DB:** `employees` table in `auth_tracker.db` has some medical + inservice compliance tracking — but Kato wants a full standalone HR filing system, not just DB rows.

---

## BILLING SYSTEM

**Current:** Carecenta — a care management SaaS platform used by adult day care centers. Handles authorizations, billing, scheduling, 837/835 EDI processing.

**Plan:** Build own in-house billing system to completely replace Carecenta and bring all billing in-house under REX.

**Required capabilities:**
- Authorization management
- EDI 837 — electronic claim submission to Medicaid/Medicare/insurance
- EDI 835 — electronic remittance advice (parsing payment explanations from payers)
- Client files with full assessments
- Full billing workflow (invoice generation, submission, reconciliation)

**Related modules on goldhealthsys.com:**
- Automated Billing (LIVE)
- Claims 837 Engine (LIVE)
- Payments 835 (LIVE)

**Note:** These are listed as LIVE on the marketing site. Verify actual operational status.

---

## DRIVER TRACKING SYSTEM

**Status: PLANNED — NOT YET BUILT.**
**Replacing:** GeoTab (commercial GPS/fleet tracking platform)

Kato has spoken about this at length in previous sessions. The goal is to build an in-house GPS driver tracking system rather than pay for GeoTab. This connects to:
- Live Fleet Tracker module (NEW on goldhealthsys.com)
- Driver Scheduler module (LIVE on goldhealthsys.com)
- Real-time GPS for every van — ETAs, routes, capacity

---

## REPOS TO EVALUATE / INTEGRATE

| Repo | Status | Notes |
|------|--------|-------|
| **LibreChat** | LIVE in stack | Port 3080, chat.hermestigerclaw.com, Docker. Already running. |
| **Open Higgsfield AI** | To evaluate | Open-source video generation. Relevant to BBG video pipeline (current prime: ComfyUI Cloud). Could replace or strengthen Flux Schnell layer. |
| **Open-LLM-VTuber** | To evaluate | Open-source LLM-powered virtual AI characters. Possible connection to Jarvis (Phase 19, video-chat + Luna sandbox). |
| **Claude Ads** | To evaluate | Purpose unclear — possibly Claude-powered ad creation for BBG social. Clarify with Kato. |
| **Agentic Inbox** | To evaluate | Agentic email processing system. Directly relevant to email intake automation (Allen scans → Gmail → OCR pipeline). |
| **Camofox** (`jo-inc/camofox-browser`) | To evaluate | Stealth headless browser for AI agents. Bypasses Cloudflare/bot detection. Drop-in Puppeteer/Playwright replacement. Candidate engine for REX Browser Shield module and insurance/auth portal automation. |
| **Hyperframes** | OWNED | Kato already has this. Purpose not yet clarified — follow up. |

**Timing:** Evaluate and integrate AFTER MASTER.md is complete and SOUL.md is installed and verified. These repos may contain systems that need to be documented in MASTER.md — confirm with Kato before evaluation session.

---

## PORT CHAOS CONCERN

Kato raised this explicitly: ports have been assigned ad hoc throughout the build. He doesn't have a clear picture of what's running on what port and doesn't know if things are conflicting.

**Current known port map:**

| Port | Service | Status |
|------|---------|--------|
| 3000 | Open WebUI (Docker) | Live |
| 3001 | Hermes local gateway | BROKEN — crashes on start |
| 3002 | Hermes cloud gateway | Live |
| 3003 | Hermes AI Hub (Docker) | Live |
| 3080 | LibreChat (Docker) | Live |
| 3847 | Hermes Portal/Landing | Live |
| 8000 | REX FastAPI (Nemobot) | Live |
| 8080 | GOJ Dashboard (Flask) | Live |
| 8081 | ShellCore FastAPI | Likely defunct/unused |
| 8765 | Phone Unlock | Live |
| 9119 | Hermes Kanban | Live |
| 18789 | Kapso WhatsApp bridge | Live |
| 27226 | Tiger Claw API | Live |
| 11434 | Ollama | Live |
| 1234 | LM Studio | Live |

**Action needed:** Full port audit — verify what's actually running on each port, what conflicts exist, what's defunct, and establish a port assignment map so nothing gets accidentally broken.

---

## LOCKED LUCY — FOUNDING MANDATE

*(This needs stronger framing in SOUL.md — not just a SaaS replacement item)*

From `gold_health_unified_gameplan.docx` (April 2026):

> **"Build a fully local, privacy-first multi-agent system for Gold Health Systems, starting with Garden of Joy adult day care (425 clients, the current 'guinea pig' customer). Required elements: deterministic Policy Enforcer; per-agent encrypted SQLCipher vaults; secrecy levels (never_share, owner_only, restricted); TOTP 2FA on sensitive disclosures; no unnecessary cloud dependencies; local hot-folder watcher + Tesseract + PaddleOCR + EasyOCR consensus; strict HIPAA-aligned treatment of PHI-adjacent data; and future scalability under full Gold Health Systems control."**

This is the non-negotiable founding mandate. Everything else — every service, every module, every agent — must be evaluated against this. It's not a project goal. It's a constitution.

Kato's words: "I picture this as a big project that will change my life."

---

## STALE ENTRIES IN BRAIN/MASTER.md (as of May 31, 2026)

These need to be corrected in MASTER.md:
- `deepseek-chat` → should be `deepseek-v4-pro`
- `claude-opus-4-7` → should be `claude-opus-4-6`
- Missing: goldhealthsys.com domain
- Missing: Email intake flow
- Missing: Google Drive structure
- Missing: HR system (planned)
- Missing: Carecenta (current billing)
- Missing: Driver tracking (planned, replacing GeoTab)
- Missing: Repos to evaluate
- Missing: Source of truth hierarchy
- Missing: Port audit note

---

## ROUND 8 — PENDING

Kato has answers from Round 8 Hermes self-assessment. These have NOT yet been sent and reviewed. After MASTER.md is updated and files are written, receive Round 8 answers, incorporate any corrections into SOUL.md v5.2, then proceed to install.

---

## OPEN QUESTIONS (Need Kato's Answers)

1. **goldhealthsys.com host** — Railway or Tiger Claw? Confirm exact host.
2. **Templates folder contents** — What types of templates live there? Auth forms? Menu forms? Billing forms? All?
3. **Tigerclaw_AI Drive folder** — What's in it?
4. **Claude Ads repo** — What is it for?
5. **Hyperframes** — What does it do?
6. **Which LIVE modules on goldhealthsys.com are actually operational** — vs. aspirational
7. **Other domains?** — Any beyond hermestigerclaw.com and goldhealthsys.com?
8. **Other repos** — Are there additional repos beyond the 7 listed?
9. **ShellCore identity** — Kato believes ShellCore = early Jarvis prototype. Needs Round 8 verification with Hermes.

---

---

## REPO ANALYSIS — FULL TIER BREAKDOWN (May 31, 2026)

Kato sent 10+ repos for evaluation. Analysis below. All findings also reflected in MASTER.md Repos section.

### TIER 1 — Integrate now. The real deal.

**MemPalace** (49K stars)
- THIS IS Kato's palace system. palace_main.db (144KB) + palace_cloud.db (24KB) on external drive = exactly this.
- Local-first, no API key needed. 96.6% R@5 recall accuracy on LongMemEval. 29 MCP tools. Wings/rooms/drawers architecture.
- Has `integrations/openclaw` folder — openclaw is its designated companion/retrieval layer.
- Claude Code auto-save hooks built in.
- Gap: Owned, not yet connected/operational.

**agent-skills** by Addy Osmani (43K stars)
- By Google Chrome VP Engineering. 23 production-grade skills for Claude Code, Cursor, Gemini CLI, Windsurf, Kiro.
- **Key finding:** Repo is tagged "antigravity" and "antigravity-ide" — direct connection to Kato's design partner Antigravity.
- Specialist agent personas: code-reviewer, test-engineer, security-auditor.
- Evaluate connection with Antigravity before integrating.

### TIER 2 — Strong candidates. Evaluate after SOUL.md installed.

**Agentic Inbox** — Direct answer to email intake gap. Allen scans → manual forward → atigerclawai@gmail.com is the problem. This is the solution. Evaluate when closing that flow.

**awesome-llm-apps** (110K stars, Shubhamsaboo) — 100+ runnable templates. Medical imaging agent + insurance claim voice agent both directly GOJ-relevant.

**PilotDeck** (OpenBMB/Tsinghua, 17 stars) — Task-oriented agent OS. White-box traceable memory (edit/delete/rollback what agents remember), smart routing (70% cost reduction shown), always-on background execution. Uses deepseek-v4-pro same as Kato. Open-sourced May 28, 2026 — only 3 days old. Too new for production trust. ⚠️ PORT CONFLICT: defaults to 3001, same as Kato's broken local Hermes gateway.

**awesome-claude-code** (45K stars) — Curated skills/hooks/orchestrators. README is placeholder while being reorganized. Good reference to check monthly.

**Open Higgsfield AI** — Video generation. BBG pipeline.
**Open-LLM-VTuber** — Virtual AI characters. Jarvis/Luna Phase 19.
**Camofox** — Stealth headless browser. REX Browser Shield + insurance portal automation.

### TIER 3 — Future/specialized. Real repos, not GOJ/GHS ops.

**autoresearch** (84K stars, karpathy) — Autonomous LLM training experiments, overnight GPU runs. Needs H100 ideally. Alienware Aurora RTX 2070 is adjacent. Not operational yet.

**nanochat** (53K stars, karpathy) — Full GPT-2 training pipeline for ~$48. Has `.claude/skills/read-arxiv-paper` skill. Learning tool.

**Karpathy repos generally** — nanoGPT (54K), llm.c (29K), rendergit (render any git repo as HTML for LLMs — immediately useful), reader3, llm-council (multiple LLMs solving hard questions together).

**qlib** (Microsoft) — Quant investment ML. Only relevant if building financial trading layer.

### TIER 4 — Need more information.

**openclaw** — Too large to read inline. MemPalace's designated companion. Read properly before integrating.
**Claude Ads** — Purpose unknown. Clarify with Kato.
**Hyperframes** — Owned by Kato. Purpose unknown. Clarify with Kato.

---

*End of session capture — May 31, 2026*
*All items above must be reflected in BRAIN/MASTER.md update.*
