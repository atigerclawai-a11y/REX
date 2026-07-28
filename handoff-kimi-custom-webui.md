# Build Handoff: Unified GHS Custom Web UI + Chat Interface
> **Target:** Kimi K3
> **From:** Hermes (post-troubleshooting session 2026-07-26)
> **Priority:** HIGH — Kato wants a web UI he can be proud of

---

## What Kato Wants

A **real custom web UI / chat interface** that:
- Looks professional, not like a generic OpenWebUI skin
- Incorporates ALL local builds AND cloud models in one unified interface
- Shares conversation memory across all platforms (Telegram bots, WebUI, etc.)
- Is something Kato would be proud to show

---

## Current Architecture

### Running Bots (Telegram)

| Bot | Token | Model | Status | Notes |
|-----|-------|-------|--------|-------|
| **@Rexxie_Assists_bot** | `8980921667:AAE4iYE3Lo6F-Ai9hz2QQDYUMsCD_I3LzTo` | `llama3.2-heretic:3b` (think) + `tinyllama:latest` (fast) | ✅ Running via launchd | Main bot, Kato's personal assistant |
| **@HermieChatt_bot** | `8702536335:AAEcM4aTLuvtgKfCpHrY6esmb3GXUJ7wXnM` | `llama3.2-heretic:3b` | ✅ Running via launchd | Secondary bot |
| **@goldhealth_rexxie_bot** | ~~`8657319466:***`~~ | — | ❌ Deleted | Bot removed from Telegram, can't recover |
| **Attendance bot** | (separate token) | — | ✅ Running | GOJ attendance tracking |

### Local Models (Ollama :11434)

```
llama3.2-heretic:3b    — 2.0GB, abliterated (uncensored), PRIMARY model
tinyllama:latest       — 637MB, fast fallback
llama3.2:3b            — 2.0GB, vanilla (not heretic, can be replaced)
gemma3:4b              — 3.3GB, available
nomic-embed-text       — 274MB, embeddings
```

### Office Mac Models (unreachable — tunnel :11435 dead)

```
rexxie:12b             — 8.5GB, Gemma4 12B abliterated (was working)
gemma3:12b-abliterated — 7.3GB (blob incomplete)
gemma3:12b             — 8.1GB
jikepjikep_16HEX/gemma-4-12b-nightshift-heretic-uncensored-qat-q4 — 7.4GB (broken template)
```

Office Mac is on Tailscale (`100.99.86.60`, `alejandros-mac-mini.tail992494.ts.net`) but unreachable — SSH times out, all ports down, although Tailscale shows "active" with 0 bytes received. **When it comes back**, the `rexxie:12b` model should be the primary again.

### SSH Tunnel
- Autossh + launchd (`com.ssh.office-tunnel`) forwarding `localhost:11435` → Office Mac `:11434`
- Port 8010 forward was removed (nothing on other end, was flooding error logs)
- Stray manual tunnel was killed (was fighting autossh)

### OpenWebUI (:3000)
- Running, titled "GHS"
- Configured with `OLLAMA_BASE_URLS="http://127.0.0.1:11434;http://127.0.0.1:11435"` 
- Currently only shows local models (Office Mac down)
- Requires login authentication

### Bot Code Location
- `~/Desktop/REX/CC_rexxie_assists_bot.py` — Main Rexxie bot (uses `/api/generate` with plain text prompt format)
- `~/Desktop/REX/CC_hermiechat_telegram_bot.py` — HermieChatt bot (also `/api/generate`)
- `~/Desktop/REX/CC_rexxie_assists_bot_new.py` — Stale copy, can be cleaned up
- Conversation memory: `~/.rexxie_conversations.json`
- State/offset: `~/.rexxie_assists_state.json`
- Logs: `~/Desktop/REX/logs/rexxie_assists.log`

### Bot Token (stored in script directly)
- Token: `8980921667:AAE4iYE3Lo6F-Ai9hz2QQDYUMsCD_I3LzTo`
- @BotFather bot name: `@Rexxie_Assists_bot`

---

## Key Issues Uncovered This Session

1. **Office Mac unreachable** — SSH and all ports time out over Tailscale. Tailscale shows "active; relay nyc, tx 1896336 rx 0" — we're sending data but getting 0 bytes back. Needs someone on the same network to restart Tailscale or check firewall.

2. **Model template corruption** — The `jikepjikep_16HEX/gemma-4-12b-nightshift-heretic-uncensored-qat-q4` GGUF had a broken template (just `{{ .Prompt }}`), causing `/v1/chat/completions` to return empty. Fixed by creating `rexxie:12b` from raw GGUF blob with proper Gemma4 template, but bot now uses `/api/generate` instead to be template-agnostic.

3. **Dual Ollama instances on Office Mac** — Both Homebrew and App bundle `ollama serve` were running, fighting for port 11434. Fixed by unloading Homebrew's launch agent.

4. **TCC blocking file writes** — macOS TCC prevents overwriting files in `~/Desktop/REX/` from background contexts. Workaround: write to `_new.py` files or use the full path.

5. **Local Mac critically low on memory** — Sometimes as low as 56MB free. `tinyllama` (637MB) and `llama3.2-heretic:3b` (2GB) work via swap but slowly.

---

## What the Custom UI Needs

### Core Requirements

1. **Unified chat interface** that works with ALL models:
   - Local Ollama (`:11434`) — `llama3.2-heretic:3b`, `tinyllama`, `gemma3:4b`
   - Office Mac (`:11435` or direct Tailscale) — `rexxie:12b`, `gemma3:12b-abliterated`
   - Cloud providers (DeepSeek, etc.) via API

2. **Professional design** — Not OpenWebUI's generic look. Dark theme, clean, fast. Kato wants to be **proud** of it.

3. **Cross-platform conversation memory** — Chat history shared between:
   - Telegram bots (@Rexxie_Assists_bot, @HermieChatt_bot)
   - This new WebUI
   - (Optional) Future mobile apps

4. **Perpetual memory integration** — Read/write to `~/GHS-Vault/Jarvis Perpetual Memory.md` and vault index

5. **Model selection** — Dropdown/menu to switch between:
   - Local heretic models
   - Office Mac 12B when available
   - Cloud models (DeepSeek, etc.)
   - Auto-fallback when Office Mac is down

### Technical Constraints

- **NO OAuth for Google** — Service account only (`~/.rex_drive_service_account.json`)
- **NO Facebook/Instagram posting** — View/search only
- **Local-first** — Cloud is fallback, not primary
- **HIPAA-aware** — PHI stays local (`auth_tracker.db` never reaches cloud)
- **TCC issues** — `~/Desktop/REX/` is TCC-protected for writes from background processes
- **Run via launchd** for persistence (use `launchctl submit`)

### Design Preferences (from Kato)

- Dark theme
- Fast and responsive
- Clean, professional — think Linear, Stripe-level UI
- Shows active model name always
- No silent model fallback
- Hard-isolate chats per model

---

## Files the UI Should Incorporate

### Bot & Chat
- `~/Desktop/REX/CC_rexxie_assists_bot.py` — Bot code (reference for API usage)
- `~/.rexxie_conversations.json` — Conversation history format
- `~/GHS-Vault/Jarvis Perpetual Memory.md` — Perpetual memory

### Ollama API Endpoints
- `POST /api/generate` — Generate completion (`model`, `prompt`, `system`, `stream`, `options`)
- `GET /api/tags` — List available models
- `GET /api/ps` — Check loaded models
- `POST /api/chat` — Alternative chat endpoint

### Existing Web Services
- OpenWebUI: `http://localhost:3000`
- REX Backend: `http://localhost:8000`
- JARVIS Hub: `http://localhost:9000`
- Rexxie Portal: (PID 1761, `CC_rexxie_portal.py`)

---

## Current Bot Prompt Format (for reference)

The bot uses **plain text prompt formatting** for model-agnostic compatibility:

```
POST /api/generate
{
  "model": "llama3.2-heretic:3b",
  "prompt": "User: [message]\nAssistant: ",
  "system": "[system prompt with perpetual memory]",
  "stream": false,
  "options": {"num_ctx": 8192, "num_predict": 1024}
}
```

---

## What Kato Specifically Asked For

From this session:
- "all my telegram bots working" ✓ (fixed)
- "my custom web ui" — needs build
- "telegram tunnel route to 12b but give me a choice" — model selector
- "shared memory across platforms" — already exists via vault
- "a heretic model to replace llama3.2" ✓ (llama3.2-heretic:3b downloaded)
- A UI he can be "proud of" — **this is the main ask**

---

## Build Order

1. **Design the UI** — Dark theme, model selector, chat pane, perpetual memory panel
2. **Build the backend** — FastAPI/Node serving the chat API, connecting to Ollama + cloud
3. **Connect to Telegram** — Sync conversation history across platforms
4. **Deploy** — Run via launchd, survive reboots
5. **Office Mac integration** — When tunnel is up, 12B model auto-available

---

*Handoff prepared 2026-07-26 by Hermes. Send this to Kimi K3.*
