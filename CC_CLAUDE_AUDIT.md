# Claude — Full Build Audit: What did you build?

## Context
Hermes and I have been building the Tiger Claw command center. Hermes keeps suggesting things, but I'm not sure what YOU already built in our previous sessions. Before we build anything more, I need a complete inventory.

## What I need from you

### 1. List everything you've built
Every file, every page, every endpoint, every script. With paths. Don't summarize — list every artifact.

Specifically I need to know about:
- The Railway command center (I see a 4,983-line index.html at `~/Desktop/REX/CC_railway_deploy/index.html` — is that yours?)
- The Jarvis HUD pages
- The Tiger Claw Screensaver and how it activates
- Any voice/TTS work you did
- The agent pages
- The 34 GHS modules — which ones actually have code behind them?
- Anything related to employee WiFi attendance
- Email integration work
- The Kanban/task board
- DropTop menu bar integration
- Antigravity connection
- The Hub server.py — what endpoints did you build vs Hermes?
- n8n workflow work
- Security scanning pages

### 2. What's running vs what's placeholder?
For everything you built, tell me honestly:
- ✅ Working and tested
- ⚠️ Built but not tested / may have bugs
- 🚧 Started but incomplete
- 📋 Planned but not started

No sugarcoating. If something's just a static page with no backend, say so.

### 3. What's the real architecture?
Hermes proposed:
- A Railway FastAPI app with 16 pages (dashboard, modules, clients, employees, schedule, billing, kitchen, transport, security, agents, BBG, design, tools, vault, voice, settings)
- Mac Mini as backend (Hub :9000, REX :8000, DataRex :8080)
- Railway talks to Mac Mini via API bridge
- PHI stays local
- Cloudflare tunnel for internal access only

Is this what you had in mind? What would you change?

### 4. What's missing that I should ask for?
What should I be asking both you AND Hermes to build that neither of you have mentioned yet? What capability gaps do you see?

### 5. How does the screensaver activate when I leave the house?
Hermes mentioned a `com.tigerclaw.screensaver.plist` with idle-monitor + hotcorner. But I want:
- "Jarvis, I'm leaving" voice command → screensaver on, security armed
- A button on the iPhone app
- Geofence: when my iPhone leaves home WiFi → auto-activate
- When I come back → auto-deactivate

What's the actual state of this? Is there an API endpoint?

### 6. Voice — what's real?
- ElevenLabs voices (REX, Rexxie) — configured and working?
- Kokoro local TTS — installed and working?
- Victoria/Masha Retell agents — any signs of life?
- "Hey Jarvis" wake word — ever built?
- Voice chat mode — exists?

## Files to check
- `~/Desktop/REX/CC_railway_deploy/` — the v2 command center
- `~/hermes-hub/server.py` — the Hub
- `~/hermes-hub/www/` — all web pages
- `~/hermes-apps/` — Tauri + Capacitor apps
- `~/.claude/projects/` — your session data
- `~/.hermes/profiles/cloud/` — Hermes config
- `~/Desktop/REX/CC_HERMES_KNOWLEDGE.md` — what Hermes thinks exists

## Rules
- Be honest about what's working and what's not
- Use real file paths — I need to be able to verify
- If something was planned but never built, say so clearly
- Don't match Hermes' assumptions just to be consistent — correct him if he's wrong
