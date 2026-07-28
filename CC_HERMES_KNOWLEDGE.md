# HERMES KNOWLEDGE BASE
# Gold Health Systems — Complete Operational Reference
# Compiled: June 1 2026 · From all Q&A rounds + verified system state
# Source of truth: BRAIN/MASTER.md. Install: ~/.hermes/profiles/cloud/memories/MEMORY.md

---

## 1. WHO KATO IS

Full name: Alejandro. Never "Allen" — Allen Khiger is a former GOJ employee, different person.
Username: `mainsobhelper`. Email: `atigerclawai@gmail.com`. Telegram ID: `5587703834`.
Vlad = business partner, delegated financial view only (not full access).
Larry = permanently off all transport/driver lists, no exceptions ever.

---

## 2. THE BUSINESSES

**Gold Health Systems (GHS)** — parent company (AKC Managing C-Corp).
- `hermestigerclaw.com` — REX/Hermes platform. Cloudflare tunnel: `*.hermestigerclaw.com`.
- `goldhealthsys.com` — marketing site + employee login portal. 34 modules. Host: Railway (not Tiger Claw). **"LIVE" on site ≠ actually functional** — most modules have glitches. Verify each independently.

**Garden of Joy (GOJ)** — adult day care, Brooklyn NY. ~425 active clients. Russian-speaking population. HIPAA-covered.
- Staff: Kato (full), Vlad (full), FrontDesk (demographics+auth only), Kitchen (PDF handoffs only), Misha (office Mac admin, Paperless-ngx at 100.99.86.60:8000).
- Auth statuses: `ACTIVE` / `EXPIRED` / `PENDING RENEWAL`. Never schedule without ACTIVE auth.
- `EXPIRED >30 days with no PENDING RENEWAL` → escalate immediately to Kato.
- When auth is expired/pending, do not remove from schedule — flag in next report and wait for Kato's decision.

**Boardwalk Beer Garden (BBG)** — Brighton Beach. Adults-only after 8PM. No DJ until summer. Clover POS: C051UQ41540458.
- Instagram: @boardwalkbeergarden (account ID: 27923669980556036). Tokens linked in Hermes.
- No auto-posting — Kato approves every post before it goes live.
- UFC 328 was the main build: 39 menu items, 19 modifiers. One-time import script: `clover_ufc328_import.py`.

---

## 3. FULL ACTIVE STACK (Mac Mini M4, 24GB, `mainsobhelper`)

| Service | Port | Manager | Notes |
|---------|------|---------|-------|
| Hermes cloud gw | 3002 | `ai.hermes.gateway-cloud.plist` | **This is Hermes. You are this.** |
| Hermes local gw | 65001 | `ai.hermes.gateway.plist` | Under repair — switching to mistral-hermie. Context floor fixed. |
| TigerClaw API | 27226 | `com.tigerclaw.api.plist` | M01–M24 stats endpoint — Jarvis HUD reads from here |
| REX FastAPI (Nemobot) | 8000 | `com.rex.backend.plist` | `rex.hermestigerclaw.com`. LiteLLM router. PAE Engine. |
| GOJ Dashboard (Flask) | 8080 | `com.goj.datarex.plist` | LIVE at `~/.hermes-cloud/home/goj-pipeline/datarex/app.py` |
| Open WebUI | 3000 | `ai.openwebui.hermes.plist` | Docker. `ui.hermestigerclaw.com`. PID 72079. Has webui.db. |
| LibreChat | 3080 | Docker | `chat.hermestigerclaw.com`. Files at `~/Documents/LibreChat/`. **NOT RUNNING.** |
| Hermes AI Hub | 3003 | Docker | `workspace.hermestigerclaw.com` |
| Hermes Kanban | 9119 | launchd | — |
| Hermes Portal | 3847 | launchd | `hermestigerclaw.com` landing |
| Tiger Claw HUD | — | `com.tigerclaw.hudsite.plist` | — |
| Tiger Claw Screensaver | — | `com.tigerclaw.screensaver.plist` | idle-monitor + hotcorner (May 29 update) |
| Claus Watchman | — | `com.hermes.claus-watchman.plist` | ✅ Running (PID confirmed) |
| n8n | — | `com.goj.n8n.plist` | 6 live workflows (see §8) |
| Kapso WhatsApp | 18789 | `com.hermes.kapso-whatsapp.plist` | — |
| Phone Unlock | 8765 | launchd | — |
| Ollama | 11434 | local | mistral-hermie (default), qwen2.5-coder:7b |
| LM Studio | 1234 | local | qwen3.5-9b primary (MLX), nvidia-nemotron-3-nano-30b, gemma-3-4b, nomic-embed-text-v1.5 (embeddings) |
| Cloudflare tunnel | — | `~/.cloudflared/hermestigerclaw.yml` | `*.hermestigerclaw.com` + `goldhealthsys.com` |

**⚠️ Two Hermes installs:**
- `~/.hermes/` — main gateway source, cloud profile (this is you). Other profiles: builder, sage, scribe, trader, hermie-local.
- `~/.hermes-cloud/` — BBG social pipeline, multi-model profiles (gemini, grok, deepseek, groq-fast, perplexity, qwen-local, hermie-local, mistral). GOJ Dashboard lives here at `home/goj-pipeline/datarex/`.

**Restart pattern (any Hermes gateway):**
```
launchctl unload <plist>
pkill -f "hermes_cli.main.*gateway"
sleep 8
launchctl load <plist>
```
Always pkill — `launchctl unload` alone is not fast enough, causes Telegram token conflicts.

---

## 4. MODEL ROUTING

**Primary:** `deepseek-v4-pro` via `https://api.deepseek.com/v1` — direct subscription. NEVER OpenRouter.
**Fallback 1:** `claude-sonnet-4-6` (Anthropic) — multi-step agents, orchestration.
**Fallback 2:** `gemini-2.0-flash` (Google).
**Fallback 3:** `moonshotai/kimi-k2.6:free` (OpenRouter — 262K context, free tier, long-horizon coding).
**High-stakes:** `claude-opus-4-6` (Anthropic).
**Cheap cloud reasoning:** `grok-3-mini`.

**All available providers:**

| Provider | Models |
|----------|--------|
| DeepSeek (direct) | deepseek-v4-pro (primary), deepseek-v4-flash |
| Anthropic | claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5-20251001 |
| Google | gemini-2.0-flash, gemini-2.5-flash, gemini-2.5-pro |
| xAI | grok-4.3, grok-4.20-reasoning, grok-3-mini |
| Perplexity | sonar-pro, sonar-reasoning-pro |
| OpenAI | gpt-4o, gpt-4o-mini, o1, o3-mini |
| Mistral | mistral-large-latest |
| Groq | qwen3-32b, llama-3.3-70b |
| OpenRouter | moonshotai/kimi-k2.6:free (non-DeepSeek routing only) |
| Ollama :11434 | mistral-hermie (default Hermie), qwen2.5-coder:7b |
| LM Studio :1234 | qwen3.5-9b (primary), nvidia-nemotron-3-nano-30b, gemma-3-4b |

**OG 33:** All models participate by default. Chairman controls composition. GOJ client data NEVER in OG 33 prompts.

---

## 5. AGENTS — REAL STATUS

| Agent | Status | What it actually is |
|-------|--------|---------------------|
| **Nemobot** | ✅ Running | REX FastAPI :8000. LiteLLM router to all models. PAE engine. |
| **Rexxie** (@goldhealth_rexxie_bot) | ✅ Running | 4 lanes, 1 token. Lane 2 = private/personal (local ONLY — never cloud, never divulges). `rexxie.db` isolated. |
| **Claus** Phase 18 | ✅ Running | `com.hermes.claus-watchman.plist` active. Hermes IS Claus realized. Phase 18 = completing that vision. |
| **Jarvis** Phase 19 | ❌ Not running | Real-time HUD. Reads TigerClaw :27226. Plists exist but not running (exited clean). |
| **TransitionAgent** | ✅ Running | `com.goj.transition-agent.plist` loaded May 28. Google Drive monitoring hook NOT built. Deadline ~June 7. |
| **Hermie** (@HermieChatt_bot) | ⚠️ Repairing | Local Ollama port 65001. Switching to mistral-hermie. Was broken (context floor bug). |
| **Victoria (Viktoriya)** | ⚠️ Quiet | Retell AI, GOJ M12 confirmation calls. Phone assigned. Transfer: 347-587-9913. API 404 — likely expired. |
| **Masha** | ⚠️ Quiet | Retell AI, BBG persona. Phone assigned. Same 404 issue as Victoria. |
| **OG 33** | ✅ Available | Dashboard-integrated + standalone portal. Multi-model deliberation. |
| **Red Team** | ✅ Built | `rex_red_team.py`. 60% random probe sample → Rexxie Telegram. |
| **Blue Team** | ✅ Built | `rex_blue_team.py`. Self-evolving. Audits Red Team, auto-generates new probes. |
| **@RexOfGold_bot** | ✅ Active | Business ops |
| **@GOJReceipts_bot** | ✅ Active | Billing/bookkeeping uploads |
| **@GojAttendance_bot** | ✅ Active | Attendance stats |

**ShellCore** (IMPORTANT DISTINCTION): NOT the 13-agent planned system. Separate EARLIER prototype — 5-agent spine, FastAPI port 8081, Ed25519-signed governance, Tauri console. Phase 1 complete, then SHELVED as "too early." Code at `dashboard/console/src-tauri/`. Vision carried to Jarvis Phase 19.

**OpenClaw** (`~/openclaw-skills/hello_memory/`): Even EARLIER precursor to Hermes. FastAPI :8000, Telegram v11.5, PAE engine. Hardcoded DeepSeek block. Built for GOJ doc automation + full sovereignty. Largely superseded. Not ShellCore.

**13-Agent Planned System** (NOT YET BUILT): Claus (Chief of Staff), Sentinel (Egress Firewall), TechGuard (IT Integrity), The Chronicler (Scribe+Sage), Officer Riggs (Red-Team), IntegrityGuard, Horizon, The Archivist, PostMaster, Spark, OCR Vision Engineer, Jarvis (Video-Chat), Luna (Child Companion — LAST TO ACTIVATE, highest stakes). Activation order locked: Riggs → Archivist → Horizon → PostMaster → Spark → OCR → Jarvis → Luna.

---

## 6. GOJ DAILY OPERATIONS

**Daily automation (all via @goldhealth_rexxie_bot):**

| Time | Job |
|------|-----|
| 7:30 AM | Morning report |
| 10:30 AM | Kitchen + distribution sheets (2-page PDFs) |
| 3:15 PM | Sign-in + driver sheets |
| 8:30 PM (Fri) | Missing menus alert |
| 9:00 PM | Drop-off rundown — target: "no decisions necessary" |
| 9:00 PM (Fri) | Weekly email summary |

**n8n Workflows (6 live, all verified active May 31):**

| Workflow | Schedule |
|----------|----------|
| ShellCore Health Watchdog | Every 5m |
| Morning System Report | 8am |
| GOJ Daily Delivery (ID: dw5HxFEOLs0QNUHX) | 2pm |
| GOJ Nightly Handoff | 9pm weekdays |
| Obsidian Nightly Digest | 10pm |
| GOJ Kitchen Correction | Manual trigger |

**7-System Schedule Change Cascade (ATOMIC — all 7 or nothing):**
When anyone changes day / calls sick / won't be there:
1. Calendar · 2. Attendance records · 3. Driver's list · 4. Kitchen's list · 5. Distribution logs · 6. Sign-in sheets · 7. Client's individual menu

**Menu pipeline:** Russian 2-page form, 425 clients, submitted 1 week ahead, Mon–Sat only. 4-engine OCR consensus: Tesseract + Google Drive Vision + Paperless-ngx + Claude Vision. Low-confidence entries → Rexxie flag.

**iMessage watcher:** NOT YET BUILT. Monitors 3 GOJ group chats on Kato's personal iMessage. Mechanism: iPad physically connected to Mac mini; watcher reads through that iPad connection. Specific chat names still need Kato input.

**Email intake:** `allen@gardenofjoybrooklyn.com` → `atigerclawai@gmail.com`. Allen manually forwards scanned PDFs. Gmail scanner auto-routes to Google Drive. OCR identifies doc type by matching against `templates/` folder in Drive. Templates folder = LOCKED OCR DEPENDENCY — do not move or rename.

---

## 7. CRITICAL FILE PATHS (LOCKED — DO NOT CHANGE)

| What | Path |
|------|------|
| Dashboard app (LIVE) | `~/.hermes-cloud/home/goj-pipeline/datarex/app.py` |
| Dashboard DB | `~/Documents/goj files/dashboard/auth_tracker.db` |
| Dashboard (NOT live) | `~/Documents/goj files/dashboard/app.py` |
| REX scripts | `~/Desktop/REX/` |
| REX logs | `~/Desktop/REX/logs/` |
| REX Python venv | `~/debate-chamber/.venv/` |
| Menu PDFs | `~/Documents/goj files/documents/menus/` |
| Authorization docs | `~/Documents/goj files/documents/authorization/` |
| Sign-in sheets | `~/Documents/goj files/documents/signin/` |
| Working doc | `~/Documents/goj files/GOJ_WORKING_DOC.md` (read at session start, update at end) |
| Locked specs | `~/Documents/goj files/GOJ_LOCKED_PARAMETERS.md` |
| Hermes agent source | `~/.hermes/hermes-agent/` (v0.15.1) |
| Hermes cloud config | `~/.hermes/profiles/cloud/config.yaml` |
| Hermes cloud memory | `~/.hermes/profiles/cloud/memories/MEMORY.md` |
| Hermes cloud logs | `~/.hermes/profiles/cloud/logs/gateway.log` |
| Hermes cloud .env | `~/.hermes/profiles/cloud/.env` |
| GOJ Master Routes | `~/Desktop/Gold_Health_Systems/GOJ_Master_Routes (1).json` |
| Google credentials | `~/Desktop/REX/google_credentials.json` → symlinked from `~/.rex_google_credentials.json` |
| Gmail OAuth token | `~/.rex_google_token.json` |
| Rexxie config | `~/Desktop/REX/rex_rexxie_telegram_config.json` |
| Rexxie DB (isolated) | `~/Desktop/REX/rexxie.db` (no GOJ data) |
| External drive | `/Volumes/cartoons/` (palace_main.db + palace_cloud.db here) |
| BRAIN source of truth | `~/Desktop/Gold_Health_Systems/BRAIN/MASTER.md` |
| GHS logo | `~/Documents/goj files/static/ghs_logo.png` (black triangle) |
| GOJ logo | `~/Documents/goj files/static/img/goj_logo.png` (flower, navy+red) |

---

## 8. DATABASE TABLES (auth_tracker.db)

| Table | Key facts |
|-------|-----------|
| `clients` | ~426 rows. Primary key `id`. Full client roster. |
| `authorization` | `service_end_date` = expiry. Status: ACTIVE / EXPIRED / PENDING RENEWAL. |
| `menus` | PDF registry. `week_start` = NULL-patched April 2026. |
| `client_menus` | 1,661+ rows. Per client+day. Column is `main` (NOT `main_dish`). `confidence` = OCR score 0–1. |
| `employees` | 15 staff. Medical + inservice compliance tracked here. |
| `pending_schedule_changes` | Schedule mods awaiting confirmation. |

`auth_tracker.db` is SQLite, NOT yet SQLCipher encrypted. Top HIPAA gap.
`rexxie.db` = 100% isolated. No client data. Zero GOJ crossover.
`rex_memory.db` = 0KB broken. `rex_user_model.db` = 0KB broken. One-line fix in `backend/memory.py`.
`palace_main.db` (144KB) + `palace_cloud.db` (24KB) on external drive = MemPalace databases. NOT wired. Dormant.
Railway DB exists and is NOT synced to local `auth_tracker.db` — known regression.

---

## 9. MCPs + INTEGRATIONS (11 connected)

`filesystem`, `fireflies`, `gdrive`, `github`, `instagram`, `n8n`, `notebooklm-bridge`, `obsidian`, `retell`, `sqlite`, `telegram`

- **Google Drive:** account `atigerclawai@gmail.com`. Credentials at `~/Desktop/REX/google_credentials.json`. Token: `~/.rex_google_token.json`.
- **Google Drive folders:** Claude Session PDFs, GOJBot, Hermes Backups, remittance (835 ERA files), `templates/` (LOCKED OCR library), Tigerclaw_AI, NotebookLM GHS Vault doc.
- **NotebookLM bridge:** One-directional — vault → Google Doc → NotebookLM. Nothing feeds back. ghs-strategy: ~268K chars. goj-ops: ~1.27M chars.
- **Fireflies:** Wired but drifted inactive. Use case: meeting transcription → Obsidian. API key likely in macOS Keychain. No active pipeline.
- **Obsidian vault:** `~/Documents/GHS-Vault`. 4 tools: find_note, search_vault, read_note, list_directory.
- **Camofox:** NOT a separate project. Built-in Hermes browser engine at `tools/browser_camofox.py`. Used for web scraping. Config: `config.yaml §browser.camofox`.

---

## 10. SECURITY + KEYS

- **HIPAA:** Presidio library on all outbound data. `auth_tracker.db` PHI never reaches cloud.
- **Encryption:** AES-256-GCM for Rexxie. SQLCipher vault via `rex_sqlcipher_vault.py` + ChaCha20 streaming.
- **Master keys:** macOS Keychain — `rex-sovereign`, `rexxie-2fa-secret`.
- **⚠️ TOTP secret = RFC example value `JBSWY3DPEHPK3PXP`.** MSU provides ZERO real security. Must rotate.
- **RBAC:** `rex_permissions.py` — 4 tiers: chairman, admin, staff, restricted.
- **PHI firewall:** 5 layers — tokenizer (Gate 1), classifier, context strip, output scan, audit log.
- **`akc_tokenizer.py` Gate 1 = skeleton only.** Zero cloud PHI routing until built.
- **Disclosure tier = no auth gate.** Any Telegram user can request sensitive data. Must be gated.
- **API keys in `~/.hermes/profiles/cloud/.env`:** DEEPSEEK_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY, COMFY_CLOUD_API_KEY confirmed.

---

## 11. VOICE + VIDEO STACK

**Retell voice agents:**
- **Victoria (Viktoriya)** — GOJ M12 appointment confirmation calls. Transfer: 347-587-9913. Voice: 11labs-Lily (placeholder, pending bilingual test). Currently quiet — likely Retell API key expired.
- **Masha** — BBG persona. Voice: 11labs-Billy (placeholder). Currently quiet same reason.
ElevenLabs default voice ID: `pNInz6obpgDQGcFmaJgB` (Adam). Default TTS fallback: Microsoft Edge (free).

**Video generation (5-tier fallback for BBG):**
1. FAL — dead/404. Do not use.
2. Flux Schnell via ComfyUI Cloud — PRIME. `COMFY_CLOUD_API_KEY` confirmed. 8 keyframes, 1080×1920. ARM64 OOM workaround: PNG→JPEG before encode.
3. PIL/ffmpeg — pure Python fallback.
4. Seedance (ByteDance) — 402, credits depleted.
5. Manim — math animations only, not BBG content.

**Hyperframes:** Installed (v0.5.3, `~/.hyperframes/config.json`). 1 command ever run. NOT operational. Original choice for BBG video, largely replaced by Open-Generative-AI.
**Krea.ai:** NOT found on disk. Not live.
**Open-Generative-AI:** Tier 1 for BBG video pipeline. 200+ models, macOS arm64 DMG.
**Patter:** Planned agent phone number for alerting Kato via call/SMS when Telegram might be missed. Not yet configured.

---

## 12. INTELLIGENCE ARCHITECTURE

**9-Step Growth Loop (every message):**
signal detection → memory retrieval → user model build → policy check → plan → respond → log exchange → update user model → periodic reflection (every 20 exchanges)

**Key modules:**
- `rex_planner.py` — 19 IntentTypes. Classify → Plan → Validate → Enrich → Route → Audit.
- `rex_user_model.py` — 4 tiers: Session, Short-term (21d), Long-term, Reflection.
- `rex_reflection.py` — 5 growth signals. Writes Tier 4 every 20 exchanges.
- `rex_human_behavior.py` — strips AI filler from Rexxie responses.
- `rex_policy_enforcer.py` — production. `rex_unified_enforcer.py` = Phase 16 planned replacement (858 lines, not yet active).
- `rex_coordinator.py` — Build Coordinator. Reads `master_list.json`, fuzzy-matches ideas.

**CLS v3 (Phase 9):** Tier A = automatic pattern scoring (no MemorySteward writes). Tier B = 3+ observations + 2+ days → Telegram approval required → MemorySteward write. Both disabled by `GAUNTLET_ENV`.

**PAE Engine:** Propose → Approve → Execute. No real-world action without Chairman authorization. Completed Phase 2B.5. Runs at REX FastAPI :8000.

**14 Architecture Rules:**
R1=DB is truth · R2=Audit trail every write · R3=Tenant isolation · R4=Idempotency · R5=Human review gates · R6=Soft delete only · R7=Job standards · R8=Chairman authority · R9=Staging required · R10=Encrypted backups · R11=Private repo · R12=NDAs first · R13=EVV native · R14=Incident auto-alert

---

## 13. HARDWARE TOPOLOGY

| Node | Status | Role |
|------|--------|------|
| Mac Mini M4, 24GB, `mainsobhelper` | ✅ Current primary | All production services run here |
| Alienware Aurora R8, **32GB** RAM, RTX 2070, home | Planned | IRONWALL node. Pop!_OS. Not yet integrated. |
| Office Mac, 16GB | Planned | Work gateway. Air-gapped from GOJ data. Not set up. |
| External drive `/Volumes/cartoons/` | Active | Nightly Hermes backups 2AM, 7-day rolling. palace_main.db + palace_cloud.db here. |

---

## 14. DESIGN SYSTEM

**GOJ Dashboard colors:**
Background `#0f1923` · Surface `#1a2535` · Border `#2a3a4a` · Text `#c8d8e8` · Gold `#c9a84c` · Success `#2ecc71` · Warning `#f39c12` · Danger `#e74c3c` · Font: -apple-system sans-serif

**Role badges:** Chairman=gold · Vlad=blue #3498db · FrontDesk=green · Kitchen=purple · Driver=orange

**Logo placement:** GHS (black triangle) top-left all templates. GOJ (flower, navy+red) top-right. Both hot-swappable via file replacement.

**Nav bar:** Dashboard | Clients | Authorizations | Billing | 🤖 OG 33 | System | Users | Sign out

**Antigravity:** Kato's design partner (`com.google.antigravity` native Mac app, connected via Hermes MCP). All GHS/BBG outputs can route through Antigravity for visual polish. agent-skills repo (addyosmani) tagged "antigravity" — IS the Antigravity design system repo.

**Tiger Claw Screensaver:** Active (May 29 update). idle-monitor + hotcorner → triggers. HUD website likely the screensaver display. Connected to Jarvis data feed.

---

## 15. REPO EVALUATION (May 31 2026)

### TIER 1 — Install Now

| Repo | Stars | Purpose | Install |
|------|-------|---------|---------|
| **ECC** (affaan-m/ECC) | 187K | Agent harness — 60 agents, 232 skills, Hermes operator story built in (`docs/HERMES-SETUP.md`). AgentShield security. **Kato's #1 priority.** | `bash install.sh` or `npx ecc-universal install` |
| **hermes-dreaming** (asimons81) | 9 | Staged self-improvement for Hermes — scans DREAM: markers, proposes memory/skill changes, holds for review. Direct Hermes plugin. **Most important plugin to what Kato is building.** | `hermes plugins install asimons81/hermes-dreaming --enable` |
| **MemPalace** | 52K | Local-first AI memory: wings/rooms/drawers, 96.6% R@5, 29 MCP tools, ChromaDB+SQLite, Claude Code auto-save. Kato owns palace_main.db + palace_cloud.db on external drive. **Dormant — never wired.** | `uv tool install mempalace` |
| **agent-skills** (addyosmani) | 43K | 23 production engineering skills for Claude Code/Cursor. Tagged "antigravity" — this IS the Antigravity repo. | `/plugin marketplace add addyosmani/agent-skills` |
| **Open-Generative-AI** | 17.7K | Self-hosted video studio, 200+ models, text-to-video. macOS arm64 DMG. Replaces Hyperframes for BBG. | Desktop DMG or npm setup |

### TIER 2 — Evaluate After Tier 1

| Repo | Stars | Notes |
|------|-------|-------|
| **PilotDeck** (OpenBMB) | 17 | Agent OS from Tsinghua. Smart model routing (70% cost savings). Uses deepseek-v4-pro. **⚠️ Port 3001 conflict** — change before running. |
| **Agentic Inbox** (Cloudflare) | 9 | AI email client on Cloudflare Workers. Direct answer to allen@gardenofjoybrooklyn.com intake gap. |
| **awesome-llm-apps** (Shubhamsaboo) | 110K | 100+ runnable templates. Medical imaging + insurance claim voice agents are GOJ-relevant. |
| **Open-LLM-VTuber** | 6.1K | AI character with voice. Luna/Jarvis candidate. Hold until v2.0 stable. |
| **awesome-claude-code** (hesreallyhim) | 45K | Canonical Claude Code discovery index. Read before installing anything. |
| **Langflow** | — | Visual LangChain builder. No deep research done yet. |
| **Camofox** | — | Already built in! `tools/browser_camofox.py` in hermes-agent. Not a separate install. |

### TIER 3 — Future / GPU

ECC autoresearch (84K, Karpathy) — H100/Alienware. nanochat (53K) — GPU-dependent. rendergit — renders repo as HTML for LLMs, low priority but handy now. qlib (Microsoft) — quant only.

### KATO-OWNED
openclaw (`~/openclaw-skills/`) — Hermes precursor. Superseded.
Hyperframes (`~/.hyperframes/`) — installed v0.5.3, not operational.

---

## 16. SaaS BEING REPLACED

| Replacing | With | Status |
|-----------|------|--------|
| Carecenta (billing) | REX in-house: EDI 837+835 + client assessments | Planned |
| GeoTab (GPS/fleet) | In-house Live Fleet Tracker (TigerClaw) | Planned |
| QuickBooks | REX financial layer (Plaid + receipt OCR) | Bookkeeper left May 31 — QuickBooks export pending |
| External bookkeeper | REX P&L automation + Vlad delegated view | In progress |
| Manual route planning | TigerClaw M01 transport module | Partial |

---

## 17. CURRENT OPEN ITEMS (PRIORITY ORDER)

| # | Item | Status |
|---|------|--------|
| 1 | **TransitionAgent Drive hook** — NOT built. Bookkeeper left May 31 | **URGENT · ~June 7 deadline** |
| 2 | **QuickBooks handoff** — new bookkeeper taking over; capture workflow | **URGENT · ~June 7** |
| 3 | **Jarvis Phase 19** — plists not running | Critical open item |
| 4 | **Victoria/Masha (Retell)** — 404, likely expired API key | Need Retell key check + re-reg |
| 5 | **auth_tracker.db** — NOT SQLCipher encrypted | Top HIPAA priority |
| 6 | **akc_tokenizer.py Gate 1** — skeleton only | Block cloud PHI routing until built |
| 7 | **iMessage watcher** — NOT built | Needed for 7-System Cascade trigger; uses iPad-Mac Mini connection |
| 8 | **MemPalace** — never wired | palace_main.db + palace_cloud.db on cartoons drive; Tier 1 owned system |
| 9 | **hermes-dreaming plugin** — not yet installed | Most important Hermes plugin: `hermes plugins install asimons81/hermes-dreaming --enable` |
| 10 | **ECC install** — not yet installed | Kato's #1 repo priority: `bash install.sh` |
| 11 | **Fireflies** — wired but inactive | Check Keychain for key; wire transcript → Obsidian flow |
| 12 | **TOTP secret rotation** — RFC example value = zero security | Must rotate immediately |
| 13 | **rex_memory.db + rex_user_model.db both 0KB** — one-line fix in `backend/memory.py` | Rexxie starts cold every session |
| 14 | **BBG posting automation** — status unverified | No auto-post; manual approval gate always on |
| 15 | **Zombie plist `com.hermes.rexxie-bot`** — keep disabled forever | — |
| 16 | **Port audit** — ports assigned ad hoc | Verify all active, document conflicts, deprecate defunct |

---

## 18. BUILD PIPELINE PHASES

Phases 1–13: LOCKED. Foundation through CommandCenter UI. No reopening without explicit reason.
Phase 13-V: Verification sprint — must complete before ANY Phase 14+ work begins.
Phase 14: MultiContext_Ventures (4 business contexts: GOJ, sports_bar, web_design, social_media)
Phase 15: AgentForge
Phase 16: Claus/Manager-General completion — activates `rex_unified_enforcer.py`
Phase 17: WebRex_Topology
Phase 18: Claus (watchman running ✅)
Phase 19: Jarvis HUD (not running ❌)
Phase 20+: Full 13-agent system build

**Planned 13-agent architecture tech stack:** LangGraph · Ollama · Docker Compose (one container per agent) · Tauri (Command Console UI, Locker Room) · Tailscale (3-node WireGuard mesh) · SQLite WAL (Scribe ledger, hash-chained, encrypted)

---

## SECURITY HARDENING — Personal-Assistant Stack (red/blue team, June 27 2026)

Surgical red-team → blue-team pass on Kato's private assistant stack. Baseline never broke
(backend `/api/health` stayed `ok`/Presidio, `rexxie.db` intact, no live service touched).
Pre-pass snapshot: `~/Desktop/REX/CC_session_snapshots/20260627_024133`.

**`CC_rexxie_signal.py`** — Rexxie's private Signal brain (fully local, never cloud):
- CRITICAL: sender auth was suffix-match → a foreign number ending in Kato's digits could impersonate him. Fixed to exact full-E.164 equality on `sourceNumber`.
- CRITICAL: no reply-loop guard. Fixed — only `dataMessage` envelopes, skip own number, dedup by `timestamp`, exponential backoff.
- HIGH: Kato's phone was in the system prompt (PII) → removed. HIGH: LLM endpoint now hard-refuses at import unless localhost + rejects cloud model names (gpt/claude/gemini/deepseek). This is the architectural control that lets `CC_REXXIE_BUILD_KNOWLEDGE.md` stay complete — it physically can't leave the Mac.
- MED: memory recall fixed to use new `RexxieMemory.get_recent(n)` (was silently empty); `signal-cli` send now checks returncode + truncates to 3500 chars.

**`CC_chairman_assistant.py`** — Kato's personal SMS assistant (Twilio :8110):
- CRITICAL: webhook had no `X-Twilio-Signature` validation → now validated **fail-closed** (rejects all if `TWILIO_AUTH_TOKEN`/`CHAIRMAN_WEBHOOK_URL`/twilio lib missing).
- CRITICAL: PIN prompt now bound to originating number + 5-min expiry + 3-strike → 15-min lockout.
- HIGH: session file now atomic write, `0o600`. HIGH: Gate-1 PHI-block vs import failure split so PHI never leaks on a swallowed exception. MED: full-E.164 sender match; session stores matched keyword, not raw body.

**Installers** (`CC_install_rexxie_signal.command`, `CC_install_chairman_notify.command`): `chmod 600` on generated plists. Both are Kato-run only (harness blocks agent from persisting launchd). Rexxie always-on needs `signal-cli link` first.

Open items for Hermes to track: rotate the RFC-example TOTP secret; `auth_tracker.db` still plaintext (SQLCipher pending); `CHAIRMAN_PIN`/`TWILIO_AUTH_TOKEN`/`CHAIRMAN_WEBHOOK_URL` must be set in `~/.hermes/.env` before the Chairman webhook will accept any request.

---
# END CC_HERMES_KNOWLEDGE.md
# This file is MEMORY.md — install at: ~/.hermes/profiles/cloud/memories/MEMORY.md
