---
tags: [tool-registry, hermes, ghs, reference]
last_updated: 2026-06-04
version: "1.0"
author: Hermes
source: CC_HERMES_KNOWLEDGE.md, CC_stats_api.py, CC_stats_api_INSTALL.md, backend/main.py (live recon 2026-06-04)
---

# GHS Tool Registry
## Gold Health Systems · Complete Weapons Inventory · v1.0 · June 4 2026
## Every agent reads this to know what it has at its disposal.

> **How to use this file:** Every section is an inventory of available tools.  
> `[FILL IN FROM: source]` placeholders mean the value exists but must be pulled from that source at setup time.  
> Cross-references use `[[wikilinks]]` to other sections of this vault.  
> Source of truth for the whole stack: `[[BRAIN/MASTER.md]]`

---

## Table of Contents

1. [[#AI Models & Providers]]
2. [[#Voice & Telephony]]
3. [[#Telegram Bots]]
4. [[#APIs & Integrations]]
5. [[#MCP Tools Connected to Hermes]]
6. [[#Internal APIs (Self-Hosted)]]
7. [[#Automation & Orchestration]]
8. [[#Databases]]
9. [[#Hardware]]
10. [[#Security & Encryption]]
11. [[#Design & Media]]
12. [[#Open Items & Known Gaps]]

---

## AI Models & Providers

### Routing Logic (Hermes Cloud Gateway · Port 3002)

| Priority | Model | Provider | Use Case |
|----------|-------|----------|----------|
| **Primary** | `deepseek-v4-pro` | DeepSeek direct (`api.deepseek.com/v1`) | All general tasks. NEVER route via OpenRouter. |
| **Fallback 1** | `claude-sonnet-4-6` | Anthropic | Multi-step agents, orchestration, Cowork mode |
| **Fallback 2** | `gemini-2.0-flash` | Google | Speed-first tasks |
| **Fallback 3** | `moonshotai/kimi-k2.6:free` | OpenRouter | 262K context, long-horizon coding (non-DeepSeek routing only) |
| **High-stakes** | `claude-opus-4-6` | Anthropic | Critical decisions, HIPAA-adjacent reasoning |
| **Cheap/fast** | `grok-3-mini` | xAI | Cheap cloud reasoning, quick classification |

**⚠️ DeepSeek Rule:** Always `provider: deepseek` + `base_url: https://api.deepseek.com/v1`. Never OpenRouter for DeepSeek.

---

### Anthropic

| Model | String | Notes |
|-------|--------|-------|
| Claude Opus 4.6 | `claude-opus-4-6` | High-stakes only. Expensive. |
| Claude Sonnet 4.6 | `claude-sonnet-4-6` | Orchestration, Cowork, fallback 1 |
| Claude Haiku 4.5 | `claude-haiku-4-5-20251001` | Fast/cheap Anthropic option |

API key location: `~/.hermes/profiles/cloud/.env` → `ANTHROPIC_API_KEY`

---

### DeepSeek

| Model | String | Notes |
|-------|--------|-------|
| DeepSeek v4 Pro | `deepseek-v4-pro` | **Primary gateway model.** Direct subscription. |
| DeepSeek v4 Flash | `deepseek-v4-flash` | Faster, cheaper variant |

- **Base URL:** `https://api.deepseek.com/v1`
- **Provider string:** `deepseek`
- API key: `~/.hermes/profiles/cloud/.env` → `DEEPSEEK_API_KEY`
- ⚠️ Known issue: 402 errors → check `provider=deepseek` is set in `config.yaml`, not `openrouter`

---

### Google

| Model | String | Notes |
|-------|--------|-------|
| Gemini 2.0 Flash | `gemini-2.0-flash` | Gateway fallback 2 |
| Gemini 2.5 Flash | `gemini-2.5-flash` | Available |
| Gemini 2.5 Pro | `gemini-2.5-pro` | Available |

API key: `~/.hermes/profiles/cloud/.env` → `GOOGLE_API_KEY`

---

### xAI

| Model | String | Notes |
|-------|--------|-------|
| Grok 4.3 | `grok-4.3` | Available |
| Grok 4.20 Reasoning | `grok-4.20-reasoning` | Reasoning mode |
| Grok 3 Mini | `grok-3-mini` | **Cheap cloud reasoning.** Fast. |

---

### Perplexity

| Model | String | Notes |
|-------|--------|-------|
| Sonar Pro | `sonar-pro` | Online search model — live web results |
| Sonar Reasoning Pro | `sonar-reasoning-pro` | Reasoning + search |

Use for: live data lookups, current events, web-grounded answers.

---

### OpenAI

| Model | String | Notes |
|-------|--------|-------|
| GPT-4o | `gpt-4o` | Available |
| GPT-4o Mini | `gpt-4o-mini` | Fast/cheap |
| o1 | `o1` | Reasoning |
| o3-mini | `o3-mini` | Fast reasoning |

---

### Mistral

| Model | String | Notes |
|-------|--------|-------|
| Mistral Large | `mistral-large-latest` | Available via Mistral provider |

---

### Groq (Fast Inference)

| Model | String | Notes |
|-------|--------|-------|
| Qwen3 32B | `qwen3-32b` | Via Groq |
| LLaMA 3.3 70B | `llama-3.3-70b` | Via Groq |

---

### Ollama Local (Port 11434)

| Model | String | Notes |
|-------|--------|-------|
| Mistral Hermie | `mistral-hermie` | **Default Hermie model.** 128K context. No thinking mode. |
| Qwen 2.5 Coder | `qwen2.5-coder:7b` | Code tasks |
| Qwen 3 14B Hermie | `qwen3:14b-hermie` | In Hermes profile config |
| LLaMA 3.2 | `llama3.2` | Available |

- API base: `http://127.0.0.1:11434/v1`
- API key: `ollama` (no real auth)
- Manager: local process

---

### LM Studio (Port 1234)

| Model | Notes |
|-------|-------|
| `qwen3.5-9b` (MLX) | **Primary LM Studio model.** Optimized for M4. |
| `nvidia-nemotron-3-nano-30b` | Available |
| `gemma-3-4b` | Available |
| `nomic-embed-text-v1.5` | **Embeddings model** |

- Base URL: `http://localhost:1234/v1`
- Use for: local inference, embedding generation

---

### OG 33 (Multi-Model Deliberation)

Multi-model deliberation system integrated into GOJ Dashboard and standalone portal. All available models participate by default. Chairman (Kato) controls composition. **⚠️ GOJ client data NEVER in OG 33 prompts.**

---

## Voice & Telephony

### ElevenLabs

ElevenLabs is wired for voice generation (primarily BBG/Masha persona).

| Item | Value |
|------|-------|
| Default Voice ID | `pNInz6obpgDQGcFmaJgB` (Adam — placeholder, not production) |
| TTS Model | `eleven_multilingual_v2` |
| API Key | `[FILL IN FROM: elevenlabs.io/profile/api-key or macOS Keychain]` |
| Victoria Voice ID | `[FILL IN FROM: elevenlabs.io/voices — search "Lily"]` |
| Masha Voice ID | `[FILL IN FROM: elevenlabs.io/voices — search "Billy"]` |
| All Voice IDs | `[FILL IN FROM: elevenlabs.io/voices — list full account voices]` |

**Usage note:** ElevenLabs is for BBG (internet assumed). Do NOT use for REX or Rexxie — Rexxie's private lane is local-only, no cloud TTS.

**Fallback TTS:** Microsoft Edge TTS (free, no API key, lower quality).

---

### Piper TTS (Local · MIT License)

Recommended local TTS engine — runs entirely on-device, no cloud, no API key. Neural VITS voices.

| Item | Value |
|------|-------|
| Status | **Recommended but not yet installed** |
| Install | `brew install piper-tts` or ARM64 binary from github.com/rhasspy/piper/releases |
| REX voice | `en_US-ryan-high` (male) |
| Rexxie voice | `en_US-amy-medium` or `en_US-kathleen-low` (female) |
| Integration point | Add `GET /api/tts?voice=rex&text=...` to REX FastAPI `:8000` |
| Python package | `pip install piper-tts` |

---

### Retell AI (Voice Agents)

| Agent | Persona | Phone Number | Transfer | Status |
|-------|---------|-------------|----------|--------|
| **Victoria (Viktoriya)** | GOJ M12 confirmation calls | `[FILL IN FROM: retell dashboard]` | 347-587-9913 | ⚠️ API 404 — likely expired key |
| **Masha** | BBG persona | `[FILL IN FROM: retell dashboard]` | `[FILL IN FROM: retell dashboard]` | ⚠️ Same 404 issue |

- API Key: `[FILL IN FROM: retell.ai dashboard → API Keys]` — **needs renewal**
- Both agents currently quiet (404 on API calls)
- Action required: log into retell.ai, check/renew API key, re-register agents

---

### Twilio

| Item | Value |
|------|-------|
| Phone Numbers | `[FILL IN FROM: console.twilio.com → Phone Numbers → Manage]` |
| Account SID | `[FILL IN FROM: console.twilio.com → Dashboard]` |
| Auth Token | `[FILL IN FROM: console.twilio.com → Dashboard]` |
| Use case | SMS/call fallback, Patter alerting (planned), staff notifications |

**Patter** (planned): Agent phone number for alerting Kato via call/SMS when Telegram might be missed. Not yet configured.

---

### Voice Routing Summary

```
GOJ confirmation calls → Victoria (Retell AI) → 11labs voice
BBG persona calls      → Masha (Retell AI) → 11labs voice
REX local voice        → Piper TTS (planned) → en_US-ryan-high
Rexxie local voice     → Piper TTS (planned) → en_US-amy-medium
BBG content TTS        → ElevenLabs → eleven_multilingual_v2
Fallback               → Microsoft Edge TTS (free)
Current Command Center → window.speechSynthesis (system, fragile — replace with Piper)
```

---

## Telegram Bots

| Bot | Handle | Purpose | Chat ID / Token | Status |
|-----|--------|---------|-----------------|--------|
| **Hermes** | `@Hermes_Cloud_May_bot` | Main Hermes gateway chat | Kato chat_id: `5587703834` | ✅ Active |
| **Rexxie** | `@goldhealth_rexxie_bot` | Private confidant — Kato only. Local-only, never cloud. 4 lanes, 1 token. | Private lane — token in `~/Desktop/REX/rex_rexxie_telegram_config.json` | ✅ Running |
| **Hermie** | `@HermieChatt_bot` | Hermie local (Ollama port 65001) | — | ⚠️ Repairing |
| **GOJ Ops** | `@RexOfGold_bot` | GOJ business operations | Token may need renewal | ✅ Active |
| **Receipts** | `@GOJReceipts_bot` | Billing / bookkeeping uploads | — | ✅ Active |
| **Attendance** | `@GojAttendance_bot` | Attendance statistics | — | ✅ Active |

**Zombie — NEVER enable:** `com.hermes.rexxie-bot` plist. It crashes and steals the Rexxie token.

**Daily automation bot:** All GOJ daily jobs run through `@goldhealth_rexxie_bot`:

| Time | Job |
|------|-----|
| 7:30 AM | Morning report |
| 10:30 AM | Kitchen + distribution PDFs |
| 3:15 PM | Sign-in + driver sheets |
| 8:30 PM (Fri) | Missing menus alert |
| 9:00 PM | Drop-off rundown |
| 9:00 PM (Fri) | Weekly email summary |

---

## APIs & Integrations

### Google APIs

All via shared OAuth token. Credentials: `~/Desktop/REX/google_credentials.json` (symlinked from `~/.rex_google_credentials.json`). Token: `~/.rex_google_token.json`.

| API | Scope | Status | Notes |
|-----|-------|--------|-------|
| **Gmail API** | Read, send, label, search | ✅ Active | Powers `rex_gmail.py`. Re-auth: `python backend/rex_gmail.py --setup` |
| **Drive API** | Upload, list, sync | ✅ Active | Powers `rex_gdrive.py`. Shares token with Gmail. |
| **Sheets API** | Read-only | ✅ Available | Scope granted |
| **YouTube API** | — | ❌ Scope not yet added | Add when needed |

**Drive folders of note:** Claude Session PDFs · GOJBot · Hermes Backups · remittance (835 ERA files) · `templates/` (LOCKED OCR library — do not move or rename) · Tigerclaw_AI · NotebookLM GHS Vault doc

**⚠️ When Gmail OAuth token expires:** All 9 GOJ pipeline JSONs go stale → Claus Watchman RED. Fix: run `python backend/rex_gmail.py --setup`.

---

### Cloudflare Tunnel

| Item | Value |
|------|-------|
| Config file | `~/.cloudflared/hermestigerclaw.yml` |
| Status | ✅ Running |
| Domain | `*.hermestigerclaw.com` + `goldhealthsys.com` |
| Routes | `hermestigerclaw.com` → Hermes Portal (:3847) · `rex.hermestigerclaw.com` → REX FastAPI (:8000) · `ui.hermestigerclaw.com` → Open WebUI (:3000) · `chat.hermestigerclaw.com` → LibreChat (:3080) · `workspace.hermestigerclaw.com` → Hermes AI Hub (:3003) |
| Notes | Kato can also add `:3005` auth proxy in front of `:3002` for external access |

---

### Tailscale VPN

| Item | Value |
|------|-------|
| Mac Mini IP | `100.98.90.26` |
| iPhone | Connected |
| Use case | Secure remote access to local services without Cloudflare exposure |

---

### Clover POS

| Item | Value |
|------|-------|
| Device | C051UQ41540458 |
| Business | Boardwalk Beer Garden (BBG) |
| Status | ✅ Active |
| Import script | `clover_ufc328_import.py` (UFC 328 menu — 39 items, 19 modifiers) |
| Integration | Existing integration in REX stack |

---

### QuickBooks

| Item | Value |
|------|-------|
| Status | Sole financial system for GHS |
| Notes | Bookkeeper left May 31. QuickBooks export pending. Being replaced by REX financial layer (Plaid + receipt OCR) — long-term. |

---

### Obsidian Vault

| Item | Value |
|------|-------|
| Path | `~/Documents/GHS-Vault` |
| MCP tools | `find_note`, `search_vault`, `read_note`, `list_directory` |
| Integration | Connected via `obsidian` MCP |
| Nightly digest | Obsidian Nightly Digest n8n workflow runs 10 PM |

---

### NotebookLM Bridge

One-directional: Vault → Google Doc → NotebookLM. Nothing feeds back.

| Notebook | Size |
|----------|------|
| `ghs-strategy` | ~268K chars |
| `goj-ops` | ~1.27M chars |

---

### Instagram (BBG)

| Item | Value |
|------|-------|
| Account | `@boardwalkbeergarden` |
| Account ID | `27923669980556036` |
| Tokens | Linked in Hermes (`instagram` MCP) |
| Auto-post | **NEVER.** Kato approves every post before it goes live. |

---

### Fireflies

| Item | Value |
|------|-------|
| Status | Wired but drifted inactive |
| Use case | Meeting transcription → Obsidian |
| API Key | `[FILL IN FROM: macOS Keychain — search "Fireflies"]` |
| Action needed | Verify key, wire transcript → Obsidian pipeline |

---

### n8n

| Item | Value |
|------|-------|
| Manager | `com.goj.n8n.plist` |
| Status | ✅ 6 live workflows |
| Access | Local only |

See [[#Automation & Orchestration]] for full workflow list.

---

## MCP Tools Connected to Hermes

11 MCP servers confirmed active (from CC_HERMES_KNOWLEDGE.md §9):

| MCP Server | Tools Available | Notes |
|------------|----------------|-------|
| `filesystem` | File read/write/list on local paths | Core file access |
| `fireflies` | Meeting transcription | Wired, inactive — needs reactivation |
| `gdrive` | Upload, list, sync Google Drive | `atigerclawai@gmail.com` |
| `github` | Repo read/write, PR, issues | Connected |
| `instagram` | Post, schedule, read (BBG) | No auto-post — Chairman approval required |
| `n8n` | Trigger workflows, webhook management | 6 live workflows |
| `notebooklm-bridge` | Push content to NotebookLM notebooks | One-directional only |
| `obsidian` | `find_note`, `search_vault`, `read_note`, `list_directory` | Vault at `~/Documents/GHS-Vault` |
| `retell` | Voice agent management | ⚠️ API 404 — key likely expired |
| `sqlite` | Direct query of local SQLite DBs | Used for auth_tracker.db, rexxie.db |
| `telegram` | Send/receive Telegram messages | All bots route through this |

**Camofox (browser engine):** NOT a separate MCP. Built-in Hermes browser engine at `tools/browser_camofox.py`. Config: `config.yaml §browser.camofox`. Used for web scraping.

---

## Internal APIs (Self-Hosted)

### REX FastAPI Backend — Port 8000

> Public URL: `rex.hermestigerclaw.com`  
> Auth: Desktop Mode (localhost = always trusted, no token). JWT for iPhone pairing.  
> Source: `~/Desktop/REX/backend/main.py` (3,976 lines)  
> Start dev: `source ~/debate-chamber/.venv/bin/activate && cd ~/Desktop/REX && uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload`  
> Start prod: `launchctl load ~/Library/LaunchAgents/com.rex.backend.plist`

**Core Endpoints:**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Basic health check |
| GET | `/api/health` | Extended health with services |
| GET | `/api/models` | Available model list |
| GET | `/api/settings` | Current settings |
| POST | `/api/settings/secure-mode` | Toggle secure (PHI) mode |
| POST | `/api/keys` | Set/update API keys |
| GET | `/api/keys/status` | Check key availability |
| POST | `/api/chat` | Main chat endpoint (GOJ dashboard widget) |
| POST | `/api/staff/chat` | Staff-tiered chat |
| WS | `/ws/chat` | WebSocket — desktop + iPhone streaming chat |
| GET | `/api/memory` | Read memory facts |
| POST | `/api/memory` | Write memory fact |
| DELETE | `/api/memory` | Delete memory fact |
| GET | `/api/memory/sessions` | Session history |
| GET | `/api/journeys` | Journey records |
| GET | `/api/audit` | Audit trail entries |
| GET | `/api/devices` | Paired devices |
| POST | `/api/agent/send` | Send message to agent bus |
| POST | `/api/agent/receive` | Receive from agent bus |
| GET | `/api/pairing/init` | Start iPhone pairing |
| POST | `/api/pairing/complete` | Complete iPhone pairing |

**Gmail Endpoints:**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/gmail/status` | OAuth token status |
| GET | `/api/gmail/summary` | Inbox digest |
| GET | `/api/gmail/search` | Search Gmail |
| POST | `/api/gmail/autolabel` | Auto-label emails |
| GET | `/api/gmail/rules` | Label rules |
| POST | `/api/gmail/rules` | Create label rule |

**Auth / Users:**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/auth/login` | Login |
| POST | `/api/auth/logout` | Logout |
| GET | `/api/auth/me` | Current user info |
| POST | `/api/auth/create-user` | Create user |
| GET | `/api/auth/users` | List users |
| GET | `/api/auth/users/{id}/permissions` | Get user permissions |
| PUT | `/api/auth/users/{id}/permissions` | Update permissions |
| DELETE | `/api/auth/users/{id}` | Delete user |
| POST | `/api/auth/set-admin-password` | Set admin password |

**Documents & Files:**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/upload` | Upload file |
| GET | `/api/uploads` | List uploads |
| GET | `/api/uploads/{filename}` | Serve upload |
| DELETE | `/api/uploads/{filename}` | Delete upload |
| POST | `/api/upload-training` | Upload training data |
| GET | `/api/training-queue` | Training queue |
| POST | `/api/documents/route` | Auto-route document by type |
| GET | `/api/documents` | List documents |
| GET | `/api/documents/serve/{category}/{filename}` | Serve document |

**Google Drive:**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/drive/sync` | Sync files to Drive |
| GET | `/api/drive/files` | List Drive files |

**Telegram:**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/telegram/config` | Get bot config |
| POST | `/api/telegram/config` | Update bot config |
| POST | `/api/telegram/fetch` | Fetch messages |
| GET | `/api/telegram/messages` | Recent messages |
| GET | `/api/telegram/schedule` | Schedule context |

**Chairman Events:**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/chairman/events` | List events |
| POST | `/api/chairman/events` | Create event |
| DELETE | `/api/chairman/events/{id}` | Delete event |
| GET | `/api/chairman/reminders/pending` | Pending reminders |
| POST | `/api/chairman/reminders/{id}/mark-sent` | Mark sent |
| POST | `/api/chairman/pdf-prompt` | PDF AI prompt |
| GET | `/api/chairman/pending-pdfs` | Pending PDFs |
| POST | `/api/chairman/extract-pdf` | Extract PDF data |

**GOJ Operations:**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/goj/stats` | GOJ aggregate stats |
| GET | `/api/goj/members` | Member list |
| GET | `/api/goj/roster/{day_shift}` | Roster by day+shift |
| GET | `/api/day-summary` | Daily summary report |
| GET | `/api/month-summary` | Monthly summary report |
| GET | `/api/attendance` | Attendance data |
| GET | `/api/clients` | Full client list |
| GET | `/api/clients/{name}` | Client detail |
| GET | `/api/authorizations` | Auth documents |
| GET | `/api/menus/master` | Master menu data |
| GET | `/api/attendance/history/{name}` | Client attendance history |
| GET | `/api/dashboard/summary` | Dashboard widget summary |

**Staff / Compliance:**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/staff/compliance` | Staff compliance records |
| GET | `/api/staff/medical` | Staff medical records |
| GET | `/api/members/portfolios` | Member portfolios |
| POST | `/api/members/upload` | Upload member file |
| GET | `/api/members/serve/{folder}/{file}` | Serve member file |

**EDI (Billing):**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/edi/upload` | Upload EDI file |
| GET | `/api/edi/claims` | EDI claims list |
| GET | `/api/edi/remittances` | ERA remittances |
| GET | `/api/edi/summary` | Billing summary |
| POST | `/api/edi/match` | Match claims to remittances |
| GET | `/api/edi/file/{id}` | Serve EDI file |

**Misc:**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/phone-unlock-callback` | Phone unlock callback |
| GET | `/api/phone-unlock/status` | Phone unlock status |
| GET | `/api/backup/status` | Backup health |

---

### GOJ Dashboard (Flask) — Port 8080

> LIVE source: `~/.hermes-cloud/home/goj-pipeline/datarex/app.py`  
> ⚠️ NOT `~/Documents/goj files/dashboard/app.py` (that file is NOT running)  
> Manager: `com.goj.datarex.plist`  
> DB: `pipeline.db` in same directory structure

Data inputs: 9 daily JSON pipeline files in `~/.hermes-cloud/home/goj-pipeline/data/` — written by automation scripts, read by dashboard. Stale if Gmail token expired.

Nav bar: Dashboard | Clients | Authorizations | Billing | 🤖 OG 33 | System | Users | Sign out

---

### CC Stats API — Port 8001

> Source: `~/Desktop/REX/CC_stats_api.py`  
> Manager: `~/Desktop/REX/com.ghs.cc-stats-api.plist` (**NOT YET INSTALLED** as of 2026-06-04)  
> Auth: Localhost only, no token (Desktop Mode)  
> Built: 2026-06-04

All endpoints are GET unless noted. Base: `http://localhost:8001`

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Health check + DB availability |
| GET | `/api/snapshot` | **Recommended.** All key metrics in one call (clients, attendance, clock-in, pipeline health) |
| GET | `/api/stats/clients` | Client auth breakdown — total, active, ACTIVE/EXPIRED/PENDING counts, expiring in 30d |
| GET | `/api/stats/attendance?days_back=7` | Today's attendance + N-day trend |
| GET | `/api/stats/roster` | Today's roster by shift |
| GET | `/api/stats/expiring?days=30` | Clients with auths expiring within N days |
| GET | `/api/stats/employees` | Employee list (sparse — main data in `GOJ_Staff_Compliance_Apr2026.xlsx`) |
| GET | `/api/clockin/status` | Who is clocked in today |
| POST | `/api/clockin/{employee_name}` | Record clock-in |
| POST | `/api/clockout/{employee_name}` | Record clock-out |
| GET | `/api/clockin/history?days_back=7` | Clock records for last N days |
| GET | `/api/goj/pipeline` | Status of 9 pipeline JSON files — flags stale (>25h) |
| GET | `/api/files/recent` | Recently modified REX files |

Clock data: `~/Desktop/REX/CC_clock_records.json`  
DB used: `auth_tracker.db` (read-only)

**Install when ready:** See `~/Desktop/REX/CC_stats_api_INSTALL.md`

---

### Tiger Claw API — Port 27226

| Item | Value |
|------|-------|
| Manager | `com.tigerclaw.api.plist` |
| Status | ✅ Running |
| Purpose | M01–M24 stats endpoints — Jarvis HUD reads from here |
| Public URL | `hermestigerclaw.com` (Cloudflare tunnel) |

---

### Open WebUI — Port 3000

| Item | Value |
|------|-------|
| Manager | `ai.openwebui.hermes.plist` (Docker) |
| Status | ✅ Running (PID 72079) |
| URL | `ui.hermestigerclaw.com` |
| DB | `webui.db` |
| Use | Frontend for Ollama models |

---

### Hermes AI Hub — Port 3003

| Item | Value |
|------|-------|
| Manager | Docker |
| URL | `workspace.hermestigerclaw.com` |
| Status | — (see CLAUDE.md) |

---

### Hermes Kanban — Port 9119

| Item | Value |
|------|-------|
| Manager | launchd |
| Status | See current `launchctl list` |

---

### Hermes Portal — Port 3847

| Item | Value |
|------|-------|
| URL | `hermestigerclaw.com` (landing page) |
| Manager | launchd |

---

### Phone Unlock Service — Port 8765

| Item | Value |
|------|-------|
| Manager | launchd |
| Purpose | iPhone unlock callback integration |

---

### Kapso WhatsApp — Port 18789

| Item | Value |
|------|-------|
| Manager | `com.hermes.kapso-whatsapp.plist` |
| Status | See current `launchctl list` |

---

### LibreChat — Port 3080

| Item | Value |
|------|-------|
| Manager | Docker |
| URL | `chat.hermestigerclaw.com` |
| Status | ❌ NOT RUNNING |
| Files | `~/Documents/LibreChat/` |

---

## Automation & Orchestration

### n8n Workflows (6 Live)

Manager: `com.goj.n8n.plist` | Status: ✅ All verified active May 31 2026

| Workflow | ID / Schedule | Notes |
|----------|--------------|-------|
| ShellCore Health Watchdog | Every 5 minutes | Service health monitoring |
| Morning System Report | 8:00 AM daily | System status report |
| GOJ Daily Delivery | `dw5HxFEOLs0QNUHX` · 2:00 PM daily | Kitchen, distribution, documents |
| GOJ Nightly Handoff | 9:00 PM weekdays | End-of-day summary + handoff |
| Obsidian Nightly Digest | 10:00 PM daily | Push activity digest to Obsidian vault |
| GOJ Kitchen Correction | Manual trigger | Ad-hoc kitchen list correction |

---

### Claus Watchman

| Item | Value |
|------|-------|
| Manager | `com.hermes.claus-watchman.plist` |
| Status | ✅ Running (PID confirmed) |
| Purpose | GOJ pipeline monitor — watches 9 daily JSON files. Goes RED when Gmail token expires or any file goes stale. |

---

### LaunchAgents (All Active Plists)

Run `launchctl list | grep -E "hermes|rex|goj|ghs|tiger|claus|n8n"` on the Mac Mini to get current PID/status.

| Plist | Service | Status |
|-------|---------|--------|
| `ai.hermes.gateway-cloud.plist` | Hermes cloud gateway (:3002) | ✅ Primary |
| `ai.hermes.gateway.plist` | Hermes local gateway (:65001) | ⚠️ Repairing |
| `ai.openwebui.hermes.plist` | Open WebUI (:3000, Docker) | ✅ |
| `com.rex.backend.plist` | REX FastAPI (:8000) | ✅ |
| `com.goj.datarex.plist` | GOJ Dashboard (:8080) | ✅ LIVE |
| `com.goj.n8n.plist` | n8n workflows | ✅ 6 live |
| `com.goj.transition-agent.plist` | TransitionAgent (Drive monitoring) | ✅ Loaded (Drive hook NOT built) |
| `com.tigerclaw.api.plist` | Tiger Claw API (:27226) | ✅ |
| `com.tigerclaw.hudsite.plist` | Tiger Claw HUD site | — |
| `com.tigerclaw.screensaver.plist` | Tiger Claw Screensaver | ✅ (updated May 29) |
| `com.hermes.claus-watchman.plist` | Claus Watchman | ✅ |
| `com.hermes.kapso-whatsapp.plist` | Kapso WhatsApp (:18789) | — |
| `com.ghs.cc-stats-api.plist` | CC Stats API (:8001) | ❌ Not yet installed |
| `com.hermes.rexxie-bot.plist` | **ZOMBIE — NEVER ENABLE** | ❌ Keep disabled |

**Restart pattern (any Hermes gateway):**
```bash
launchctl unload <plist>
pkill -f "hermes_cli.main.*gateway"
sleep 8
launchctl load <plist>
```

---

### GOJ 7-System Schedule Change Cascade

**ATOMIC — all 7 update or none.** When any client changes day, calls sick, or won't attend:

1. Calendar
2. Attendance records
3. Driver's list
4. Kitchen's list
5. Distribution logs
6. Sign-in sheets
7. Client's individual menu

---

## Databases

### auth_tracker.db (GOJ Primary DB)

| Item | Value |
|------|-------|
| Path | `~/Documents/goj files/dashboard/auth_tracker.db` |
| Type | SQLite (NOT yet SQLCipher encrypted — top HIPAA gap) |
| Access | Never in cloud. Presidio runs on all outbound. |

| Table | Rows | Key Columns | Notes |
|-------|------|-------------|-------|
| `clients` | ~426 | `id`, `name`, `active`, `shift`, `day_X_actual` | Full client roster |
| `authorization` | — | `service_end_date` (=expiry), `status` | ACTIVE / EXPIRED / PENDING RENEWAL |
| `menus` | — | `week_start` | PDF registry. NULL-patched April 2026. |
| `client_menus` | 1,661+ | `main` (NOT `main_dish`!), `confidence` | Per client+day. OCR score 0–1. |
| `employees` | 15 | — | Staff. May be sparse — main data in `GOJ_Staff_Compliance_Apr2026.xlsx` |
| `pending_schedule_changes` | — | — | Schedule mods awaiting confirmation |
| `attendance_log` | — | `log_date`, `shift`, `client_name`, `status` | Used by CC Stats API |
| `auth_documents` | — | `expiration_date`, `status`, `client_name` | Used by expiring endpoint |

**⚠️ Critical column name:** `main` NOT `main_dish` in `client_menus` table.

---

### rexxie.db (Kato's Private Confidant DB)

| Item | Value |
|------|-------|
| Path | `~/Desktop/REX/rexxie.db` |
| Access | Kato only. Private lane. Local-only. **Zero GOJ data. Zero crossover. Enforced always.** |
| Encryption | AES-256-GCM. Triple-encrypted. |

---

### rex_journeys.db

| Item | Value |
|------|-------|
| Path | `~/.rex/rex_journeys.db` |
| Purpose | Real memory tables — journey/session history |

---

### rex_memory.db / rex_user_model.db

| Item | Value |
|------|-------|
| Status | ⚠️ Both 0KB (broken) |
| Fix | One-line fix in `~/Desktop/REX/backend/memory.py` |
| Impact | Rexxie starts cold every session — no persistent user model |

---

### palace_main.db / palace_cloud.db (MemPalace)

| Item | Value |
|------|-------|
| Path | `/Volumes/cartoons/palace_main.db` (144KB) + `/Volumes/cartoons/palace_cloud.db` (24KB) |
| Status | ⚠️ Never wired. Dormant. Kato owns these. |
| System | MemPalace — 29 MCP tools, wings/rooms/drawers memory architecture |
| Action | Tier 1 install: `uv tool install mempalace` |

---

### webui.db

| Item | Value |
|------|-------|
| Path | Open WebUI data directory (Docker volume) |
| Purpose | Open WebUI user data, chat history |

---

## Hardware

### Mac Mini M4 — Primary Server

| Item | Value |
|------|-------|
| User | `mainsobhelper` |
| RAM | 24GB unified memory |
| Chip | Apple M4 |
| Role | **All production services run here** |
| Ollama | mistral-hermie, qwen2.5-coder:7b |
| LM Studio | qwen3.5-9b MLX, nvidia-nemotron-3-nano-30b, gemma-3-4b, nomic-embed-text-v1.5 |
| External Drive | `/Volumes/cartoons/` — nightly Hermes backups 2AM (7-day rolling), palace DBs |

---

### Alienware Aurora R8 — IRONWALL Node (Planned)

| Item | Value |
|------|-------|
| RAM | 32GB |
| GPU | RTX 2070 |
| OS | Pop!_OS (home) |
| Status | Planned. Not yet integrated. |
| Role | Heavy GPU inference, training, ECC autoresearch |

---

### Office Mac — Air-Gapped Work Gateway (Planned)

| Item | Value |
|------|-------|
| RAM | 16GB |
| Status | Planned. Not yet set up. |
| Rule | **Air-gapped from GOJ data and financials.** |

---

### Paperless-ngx (Office)

| Item | Value |
|------|-------|
| Operator | Misha (office admin) |
| Address | `100.99.86.60:8000` (Tailscale) |
| Role | Document scanning + OCR at GOJ office |
| Pipeline | One of 4 OCR engines: Tesseract + Google Drive Vision + **Paperless-ngx** + Claude Vision |

---

### ZK Biometric Devices (PLANNED)

| Item | Value |
|------|-------|
| Status | Not yet purchased |
| Plan | Fingerprint/face recognition at GOJ entrance for attendance automation |

---

## Security & Encryption

| Layer | Implementation | Status |
|-------|---------------|--------|
| Outbound PHI | Presidio de-identification (all 18 HIPAA Safe Harbor identifiers) | ✅ Active |
| Rexxie messages | AES-256-GCM | ✅ Active |
| SQLCipher vault | `rex_sqlcipher_vault.py` | ✅ For Rexxie |
| Large blobs | ChaCha20 | ✅ Active |
| Master keys | macOS Keychain: `rex-sovereign`, `rexxie-2fa-secret` | ✅ Active |
| RBAC | `rex_permissions.py` — 4 tiers: Chairman / admin / staff / restricted | ✅ Active |
| TOTP | RFC example value `JBSWY3DPEHPK3PXP` | ⚠️ MUST ROTATE — zero real security |
| auth_tracker.db | SQLite, unencrypted | ❌ Top HIPAA gap |
| PHI Gate 1 | `akc_tokenizer.py` | ❌ Skeleton only — blocks all cloud PHI until complete |
| Audit trail | Every write to auth_tracker.db gets audit entry | ✅ Active |
| Soft deletes | All deletes are soft | ✅ Enforced |
| Agent bus comms | AES-256-GCM, per-agent HKDF key `rex-agent-bus-{agent_id}` | ✅ Active |

**PAE Engine (Propose → Approve → Execute):** No real-world action without Chairman authorization. Running at REX FastAPI :8000. No exceptions for production actions.

**RBAC Tiers:**

| Tier | Access |
|------|--------|
| Chairman (Kato) | Everything |
| Vlad | Financial view only |
| FrontDesk | Demographics + auth only |
| Kitchen | PDF handoffs only |
| Driver | Route sheets only |
| Restricted | Read-only, no PHI |

---

## Design & Media

### GHS Design System

| Element | Value |
|---------|-------|
| Background | `#0f1923` |
| Surface | `#1a2535` |
| Border | `#2a3a4a` |
| Text | `#c8d8e8` |
| Gold | `#c9a84c` |
| Success | `#2ecc71` |
| Warning | `#f39c12` |
| Danger | `#e74c3c` |
| Font | `-apple-system` sans-serif |
| GHS Logo | Black triangle — `~/Documents/goj files/static/ghs_logo.png` |
| GOJ Logo | Flower, navy+red — `~/Documents/goj files/static/img/goj_logo.png` |

**Role badge colors:** Chairman=gold · Vlad=`#3498db` · FrontDesk=green · Kitchen=purple · Driver=orange

**Antigravity:** `com.google.antigravity` native Mac app. All GHS/BBG outputs can route through Antigravity for visual polish. Connected via Hermes MCP. `agent-skills` repo (addyosmani) IS the Antigravity design system repo (tagged "antigravity").

---

### Video Generation Stack (BBG)

5-tier fallback for BBG social video:

| Tier | Tool | Status |
|------|------|--------|
| 1 | Open-Generative-AI | ✅ macOS arm64 DMG on disk. 200+ models. Tier 1 for BBG video. |
| 2 | Flux Schnell via ComfyUI Cloud | ✅ PRIME. `COMFY_CLOUD_API_KEY` confirmed. 8 keyframes, 1080×1920. ARM64 OOM workaround: PNG→JPEG before encode. |
| 3 | PIL/ffmpeg | ✅ Pure Python fallback |
| 4 | Seedance (ByteDance) | ❌ 402 — credits depleted |
| 5 | FAL | ❌ Dead/404 — do not use |
| — | Manim | Math animations only — not BBG content |

**Hyperframes** (v0.5.3, `~/.hyperframes/config.json`): Installed but NOT operational. 1 command ever run. Original BBG video choice, replaced by Open-Generative-AI.

---

## Open Items & Known Gaps

See [[CC_PHASE_STATUS]] for full phase breakdown. Highest priority items:

| # | Item | Priority | Notes |
|---|------|----------|-------|
| 1 | TransitionAgent Drive hook | 🔴 URGENT | NOT built. Bookkeeper left May 31. ~June 7 deadline. |
| 2 | QuickBooks handoff | 🔴 URGENT | New bookkeeper taking over. ~June 7 deadline. |
| 3 | TOTP rotation | 🔴 CRITICAL | RFC example value in prod = zero security |
| 4 | auth_tracker.db SQLCipher | 🔴 HIPAA | Unencrypted PHI DB |
| 5 | akc_tokenizer.py Gate 1 | 🔴 HIPAA | Skeleton only — PHI cloud block depends on this |
| 6 | CC Stats API install | 🟡 Ready | File built, plist ready, not yet loaded |
| 7 | Retell API key renewal | 🟡 | Victoria + Masha both 404 |
| 8 | rex_memory.db / rex_user_model.db | 🟡 | 0KB — one-line fix in backend/memory.py |
| 9 | Jarvis Phase 19 | 🟡 | Plists exist, not running |
| 10 | MemPalace wiring | 🟠 | palace_main.db on disk, never connected |
| 11 | ECC install | 🟠 | Kato's #1 repo priority — `bash install.sh` |
| 12 | hermes-dreaming plugin | 🟠 | `hermes plugins install asimons81/hermes-dreaming --enable` |
| 13 | Piper TTS install | 🟠 | Replace browser speechSynthesis with local neural TTS |
| 14 | iMessage watcher | 🟠 | iPad-Mac Mini connection — chat names still need Kato input |
| 15 | Fireflies reactivation | 🟢 | Verify Keychain key, wire → Obsidian |
| 16 | Zombie plist | ⛔ | `com.hermes.rexxie-bot.plist` — NEVER ENABLE |

---

*This file is machine-paired with `[[CC_TOOL_REGISTRY.json]]` for programmatic agent access.*  
*Source of truth: `[[BRAIN/MASTER.md]]` · Governing doc: `[[CLAUDE.md]]`*
