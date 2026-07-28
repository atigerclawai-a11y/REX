# TIGER CLAW HUB — Master Reference
# Compiled: June 7, 2026 · Built by Hermes (DeepSeek V4 Pro)
# Every line verified against live system state

---

## 1. ECOSYSTEM MAP — Live Services

| Service | Port | PID | Manager | Status |
|---------|------|-----|---------|--------|
| **Tiger Claw Hub** | 9000 | 49808 | `com.goj.hub` | ✅ LIVE |
| Hermes Cloud Gateway | 3002 | 1557 | `ai.hermes.gateway-cloud` | ✅ |
| Hermes Local Gateway | 65001 | 1591 | `ai.hermes.gateway` | ✅ |
| REX FastAPI (Nemobot) | 8000 | 1607 | `com.rex.backend` | ✅ |
| GOJ DataRex Dashboard | 8080 | 1567 | `com.goj.datarex` | ✅ |
| Tiger Claw API | 27226 | 1569 | `com.tigerclaw.api` | ✅ |
| Open WebUI | 8081 | 1575 | `ai.openwebui.hermes` | ✅ (was 3000, moved) |
| Hermes Dashboard | 9119 | 1558 | `ai.hermes.dashboard` | ✅ |
| Hermes Landing | 3003 | 1582 | `com.hermes.landing` | ✅ |
| Hermes Deck | 4000 | 1559 | `com.hermes.deck` | ✅ |
| Hermes Portal | 3847 | 1604 | `com.hermes.portal` | ✅ |
| Hermes Show | — | 1556 | `com.hermes.show` | ✅ |
| n8n Automation | 5678 | 1595 | `com.goj.n8n` | ✅ |
| Ollama | 11434 | 1591 | `com.ollama.ollama` | ✅ |
| LM Studio | 1234 | 1617 | manual | ✅ |
| Cloudflare Tunnel | — | 1562 | `com.cloudflare.hermestigerclaw` | ✅ |
| Tiger Claw HUD Site | — | 1552 | `com.tigerclaw.hudsite` | ✅ |
| Hotcorner / Screensaver | — | 1596 | `com.tigerclaw.hotcorner` | ✅ |
| Hub Dev (staging) | — | 1608 | `com.goj.hub-dev` | ✅ |
| Signal Bridge | — | 1553 | `ai.hermes.signal` | ✅ |
| Rexxie Bot | — | 1565 | `com.rex.rexxie-bot` | ✅ |

**DOWN:** Obsidian REST API (:27124), LibreChat (:3080), ComfyUI (:8188), Open WebUI Docker (:3000), Kapso WhatsApp (:18789)

---

## 2. HUB PAGES & API

### Web Pages (`http://127.0.0.1:9000`)
| Path | Page | Auth |
|------|------|------|
| `/` | Index / Landing | ✅ |
| `/jarvis` | JARVIS HUD (main dashboard) | ✅ |
| `/jarvis-iphone` | Mobile-optimized HUD | ✅ |
| `/terminal` | Hermes Web Terminal | ✅ |
| `/notebook` | Local NotebookLM | ✅ |
| `/login` | PIN / WebAuthn login | — |
| `/webrex` | WebRex (pending) | — |
| `/docs` | Swagger API docs | — |

### API Endpoints (60+ total)

**Auth:**
- `POST /api/hub/auth/pin` — PIN login
- `POST /api/hub/auth/pin/set` — Change PIN (requires auth)
- `GET /api/hub/auth/check` — Session check
- `POST /api/hub/auth/webauthn/*` — Face ID / Touch ID

**Vault (`/api/rexxie/vault/*`):**
- `GET /status` — `{"unlocked": false}` (needs master password)
- `GET /entries` — List entries
- `POST /entry` — Add entry
- `GET /entry/{id}` — Get entry
- `PUT /entry/{id}` — Update entry
- `DELETE /entry/{id}` — Delete entry
- `GET /search?q=` — Search vault

**Notebook (`/api/notebook/*`):**
- `POST /upload` — Upload document (multipart)
- `GET /docs` — List documents
- `GET /doc/{filename}` — Read document
- `DELETE /doc/{filename}` — Delete document
- `GET /obsidian/notes` — List Obsidian notes
- `POST /obsidian/save` — Save note to Obsidian

**Security:**
- `GET /api/hub/security/audit` — Audit log
- `POST /api/hub/security/malware-scan` — Trigger malware scan
- `GET /api/hub/security/integrity` — File integrity check
- `POST /api/rexxie/scan` — Fortress ecosystem scan
- `POST /api/rexxie/scan/path` — Scan specific path

**System:**
- `GET /api/hub/summary` — Full ecosystem health (all services)
- `GET /api/hub/agents` — Agent roster (33 agents)
- `GET /api/hub/rexxie` — Rexxie status
- `GET /api/hub/gateway` — Gateway status
- `GET /api/hub/datarex` — DataRex status
- `GET /api/hub/ghs` — GHS platform (34 modules)
- `GET /api/hub/keys` — API key inventory
- `GET /api/hub/n8n` — n8n workflows
- `GET /api/hub/models` — Model listing
- `GET /api/models` — AI models
- `GET /api/memory/*` — Memory search/write
- `POST /api/jarvis/ask` — Jarvis Q&A
- `POST /api/jarvis/speak` — TTS
- `GET /api/hub/ollama` — Ollama models
- `GET /api/hub/lmstudio` — LM Studio models
- `GET /health` — Health check (no auth)

**WebSocket:** `ws://127.0.0.1:9000/ws/secure`

---

## 3. CONFIG FILES — What Lives Where

| File | Purpose | Last Modified |
|------|---------|---------------|
| `~/.hermes/config.yaml` | Main Hermes config (MCP, delegation, toolsets) | Jun 7 05:55 |
| `~/.hermes/.env` | All API keys, tokens, secrets | Jun 6 09:05 |
| `~/.hermes/profiles/cloud/config.yaml` | Cloud profile (DeepSeek provider, 24 lines) | Jun 6 08:32 |
| `~/.hermes/profiles/cloud/.env` | Cloud profile env (subset of main) | Jun 6 08:19 |
| `~/hermes-hub/server.py` | Hub backend (4,423 lines, FastAPI) | Jun 7 06:07 |
| `~/hermes-hub/pin.json` | Hub PIN hash (pbkdf2_sha256) | Jun 7 04:50 |
| `~/hermes-hub/auth.json` | Hub password/auth | May 22 |
| `~/.hermes/rexxie_vault/pin.hash` | Rexxie vault PIN | Jun 7 04:50 |
| `~/hermes-hub/vault/vault.db` | Encrypted vault (SQLite, AES-256-GCM) | Jun 7 05:09 |
| `~/.hermes/notebook/` | NotebookLM document storage | Jun 7 06:07 |
| `~/.hermes/config.yaml.bak_mcp_20260607` | Config backup (pre-MCP changes) | Jun 7 |

### Config Highlights

**Delegation** (in `~/.hermes/config.yaml`):
```yaml
delegation:
  max_spawn_depth: 2        # was 1
  max_concurrent_children: 4 # was 3
  max_iterations: 60         # was 50
  default_toolsets: [terminal, file, web, browser, skills, memory, session_search, vision, todo]
```

**MCP Servers** (in `~/.hermes/config.yaml`):
- `filesystem` — npx @modelcontextprotocol/server-filesystem ✅
- `fireflies` — api.fireflies.ai ✅
- `gdrive` — Google Drive MCP ✅
- `github` — @modelcontextprotocol/server-github ✅
- `obsidian` — https://127.0.0.1:27124 ✅ (needs Obsidian running)
- `n8n` — http://localhost:5678/mcp ✅ (needs MCP trigger workflow)
- `mempalace` — python3 -m mempalace.mcp_server ⚠️ (needs pip install)

---

## 4. API KEYS — What's Configured

| Service | Key Present | In .env |
|---------|------------|---------|
| DeepSeek | ✅ | `DEEPSEEK_API_KEY` |
| Anthropic | ✅ | `ANTHROPIC_API_KEY` |
| OpenAI | ✅ | `OPENAI_API_KEY` |
| Google AI | ✅ | `GOOGLE_API_KEY` |
| xAI / Grok | ✅ | `XAI_API_KEY` |
| Perplexity | ✅ | `PERPLEXITY_API_KEY` |
| Groq | ✅ | `GROQ_API_KEY` |
| Mistral | ✅ | `MISTRAL_API_KEY` |
| OpenRouter | ✅ | `OPENROUTER_API_KEY` |
| ElevenLabs | ✅ | `ELEVENLABS_API_KEY` |
| Retell AI | ✅ | `RETELL_API_KEY` |
| FAL (image gen) | ✅ | `FAL_KEY` |
| Comfy Cloud | ✅ | `COMFY_CLOUD_API_KEY` |
| Obsidian | ✅ | `OBSIDIAN_API_KEY` |
| n8n | ✅ | `N8N_API_KEY` |
| Tavily (search) | ✅ | `TAVILY_API_KEY` |
| Twilio | ✅ | `TWILIO_*` |
| Telegram | ✅ | `TELEGRAM_BOT_TOKEN` |
| GitHub | ✅ | `GITHUB_TOKEN` |
| Lead Connector | ❌ | — |
| Cloudflare | ❌ | — |

**PIN:** Set to user-provided code. Hash at `~/.hermes/rexxie_vault/pin.hash` + `~/hermes-hub/pin.json`.

---

## 5. AGENT ROSTER — Production

| Agent | Launchctl | Status | Note |
|-------|-----------|--------|------|
| Nemobot / REX API | `com.rex.backend` | ✅ :8000 | LiteLLM router, PAE engine |
| Rexxie Bot | `com.rex.rexxie-bot` | ✅ | Telegram bot |
| Rexxie Daily | `com.goj.rexxiedaily` | ⚠️ Exited | Daily automation |
| Claus Watchman | `com.hermes.claus-watchman` | ⚠️ Exited | Phase 18 |
| TransitionAgent | `com.goj.transition-agent` | ⚠️ Exited | Drive hook NOT built |
| Tiger Claw API | `com.tigerclaw.api` | ✅ :27226 | M01–M24 stats |
| DataRex Dashboard | `com.goj.datarex` | ✅ :8080 | GOJ LIVE dashboard |
| Hermie Local | `ai.hermes.gateway` | ✅ :65001 | Ollama mistral-hermie |
| Hermes Cloud | `ai.hermes.gateway-cloud` | ✅ :3002 | This is you |
| n8n | `com.goj.n8n` | ✅ :5678 | 6 workflows |
| Open WebUI | `ai.openwebui.hermes` | ✅ :8081 | Open WebUI |
| Kapso WhatsApp | `com.hermes.kapso-whatsapp` | ❌ Exit 1 | Kapso bridge |
| Jarvis HUB | `com.goj.hub` | ✅ :9000 | This server |

**13-Agent Planned:** Claus, Sentinel, TechGuard, Chronicler, Officer Riggs, IntegrityGuard, Horizon, Archivist, PostMaster, Spark, OCR Engineer, Jarvis, Luna — NOT YET BUILT.

---

## 6. NOTEBOOK LM — Local Module

**Storage:** `~/.hermes/notebook/`
**Page:** `http://127.0.0.1:9000/notebook`
**External:** https://notebooklm.google.com (linked from header)

**Features:**
- Upload: `.md`, `.txt`, `.pdf`, `.json`, `.yaml`, `.py`, `.html`, `.js`, `.ts`
- PDF extraction: pdftotext fallback (needs poppler: `brew install poppler`)
- Text files: direct read (50K char cap)
- Obsidian sync: save notes to vault, list notes
- Full CRUD: upload, list, read, delete

**Missing for full PDF support:** `pip install pymupdf` or `brew install poppler`

---

## 7. HERMES TERMINAL

**TUI:** `~/.hermes/hermes-agent/ui-tui/` (hermes-tui v0.0.1, Ink/React)
**Backend:** `tui_gateway/` (Python JSON-RPC)
**Launch:** `hermes --tui`
**Web Terminal:** `http://127.0.0.1:9000/terminal`

---

## 8. BLOCKERS & OPEN ITEMS

| # | Item | Severity | Status |
|---|------|----------|--------|
| 1 | `auth_tracker.db` NOT SQLCipher encrypted | 🔴 CRITICAL | HIPAA — top priority |
| 2 | TransitionAgent Drive hook NOT built | 🔴 URGENT | Deadline ~Jun 7 |
| 3 | Jarvis Phase 19 plists NOT running | 🟠 HIGH | Phase 19 incomplete |
| 4 | iMessage watcher NOT built | 🟠 HIGH | Required for schedule cascade |
| 5 | Obsidian REST API (:27124) DOWN | 🟠 HIGH | Blocks MCP + sync |
| 6 | MemPalace NOT installed | 🟡 MEDIUM | `pip install mempalace` needed |
| 7 | Vault locked (needs master password) | 🟡 MEDIUM | Vault DB exists but empty |
| 8 | Audit chain BROKEN at entry 1 | 🟡 MEDIUM | Hash mismatch |
| 9 | Gatekeeper disabled | 🟡 LOW | Security hardening |
| 10 | Firewall disabled | 🟡 LOW | Security hardening |
| 11 | Kapso WhatsApp bridge DOWN | 🟡 LOW | Exit code 1 |
| 12 | LibreChat DOWN (:3080) | 🟢 LOW | Not needed currently |
| 13 | `com.hermes.rexxie-bot.plist` ZOMBIE | 🔴 NEVER ENABLE | Crashes, steals token |

---

## 9. BACKUP LOCATIONS

| Backup | Path | Date |
|--------|------|------|
| Pre-migration full | `~/Desktop/REX_Backups/CC_pre_migration_20260607_044516/` | Jun 7 04:45 |
| **Daily auto (cron)** | `~/Desktop/REX_Backups/CC_daily_*/` | Every 2 AM |
| Config pre-MCP | `~/.hermes/config.yaml.bak_mcp_20260607` | Jun 7 05:55 |
| REX daily (stale) | `~/Desktop/REX_Backups/` | Apr 20 |
| Encrypted backup | `/Volumes/cartoons/` (external) | Varies |

**Cron job:** `f12d0922ddf9` — `CC_daily_backup.sh` runs daily at 2 AM, 14-day rolling, local delivery (no Telegram spam).

---

## 10. QUICK COMMANDS

```bash
# Restart Hub
launchctl kickstart -k gui/$(id -u)/com.goj.hub

# PIN login (2563)
curl -s -c /tmp/cookies http://127.0.0.1:9000/api/hub/auth/pin \
  -H "Content-Type: application/json" -d '{"pin":"2563"}'

# Full health check
curl -s -b /tmp/cookies http://127.0.0.1:9000/api/hub/summary | python3 -m json.tool

# Agent roster
curl -s -b /tmp/cookies http://127.0.0.1:9000/api/hub/agents

# Fortress scan
curl -s -X POST -b /tmp/cookies http://127.0.0.1:9000/api/rexxie/scan

# List notebook docs
curl -s -b /tmp/cookies http://127.0.0.1:9000/api/notebook/docs

# Vault entries
curl -s -b /tmp/cookies http://127.0.0.1:9000/api/rexxie/vault/entries

# Restart cloud gateway
launchctl unload ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist
pkill -f "hermes_cli.main.*gateway"
sleep 8
launchctl load ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist
```
