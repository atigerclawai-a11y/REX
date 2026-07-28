# Tiger Claw — Gap Analysis & Master Build Review

## Context
Kato (Alejandro) has built a massive ecosystem over the past year. A lot exists. A lot is planned. Before building anything new, audit everything and answer four questions.

## What's already built (Hermes built this with Kato)

### Running services (all live on Mac Mini M4, 24GB)
```
Port 9000  — Tiger Claw Hub (FastAPI, 60+ endpoints, WebSocket /ws, Cloudflare tunnel)
Port 3002  — Hermes Cloud Gateway (DeepSeek V4 Pro, Telegram @Hermes_Cloud_May_bot)
Port 65001 — Hermes Local Gateway (Ollama mistral-hermie, @HermieChatt_bot)
Port 8000  — REX FastAPI / Nemobot (LiteLLM router, PAE engine)
Port 8080  — GOJ DataRex Dashboard (Flask, LIVE, auth_tracker.db)
Port 8081  — Open WebUI
Port 9119  — Hermes Dashboard/Kanban
Port 4000  — Hermes Deck
Port 3847  — Hermes Portal (landing page)
Port 3003  — Hermes AI Hub (Docker)
Port 5678  — n8n automation (6 live workflows)
Port 11434 — Ollama (mistral-hermie, qwen2.5-coder:7b)
Port 1234  — LM Studio (qwen3.5-9b, nemotron-30b, gemma-3-4b)
Port 27226 — Tiger Claw API (M01–M24 stats for Jarvis HUD)
```
Plus 10+ launchd-managed processes (Claus Watchman, Screensaver, HUD site, Signal bridge, Rexxie bot, Kapso WhatsApp, Hub dev, Cloudflare tunnel, Phone unlock).

### Web pages (all at :9000, auth-protected unless noted)
- `/login` — PIN + WebAuthn login
- `/jarvis` — JARVIS HUD with iPhone detection, live service dots, agent status
- `/jarvis-iphone` — Mobile-optimized HUD
- `/terminal` — Web terminal (basic shell)
- `/notebook` — Local NotebookLM (upload docs, list, read, delete, Obsidian sync)
- `/command` — Tabbed command center shell (7 iframe tabs — PLACEHOLDER, needs real panels)
- `/docs` — Swagger API docs (no auth)
- `/health` — Health check (no auth)

### Native apps
- **macOS Tauri app** at `~/hermes-apps/macos/` — 10MB .app, DMG at `~/Desktop/Tiger_Claw_1.0.0.dmg`
- **iOS Capacitor app** at `~/hermes-apps/ios/` — loads Hub via WKWebView
- Both are thin wrappers — they load the Hub's web UI

### Agents (verified running)
```
hermes-cloud, hermes-local, rexxie (@goldhealth_rexxie_bot),
nemobot (:8000), claus (watchman), @RexOfGold_bot,
@GOJReceipts_bot, @GojAttendance_bot
```

### GOJ business (425 clients, Brooklyn adult day care, HIPAA)
- Daily automation: 7:30 AM report, 10:30 AM kitchen PDFs, 3:15 PM signin sheets, 9 PM drop-off
- n8n workflows: Health Watchdog, Morning Report, Daily Delivery, Nightly Handoff, Obsidian Digest, Kitchen Correction
- `auth_tracker.db` — 426 clients, 15 employees, menus, authorizations, schedules (NOT yet encrypted)
- 7-System Schedule Change Cascade (atomic: Calendar → Attendance → Driver → Kitchen → Distribution → Sign-in → Menu)
- Menu pipeline: Russian 2-page forms, 4-engine OCR consensus

### Security
- AES-256-GCM for Rexxie messages, SQLCipher vault, ChaCha20 streaming
- Presidio de-id on all outbound data
- Red team (`rex_red_team.py`) + Blue team (`rex_blue_team.py`) built
- Fortress scanner integrated into Hub
- Audit logging on all DB writes

### Cron jobs (active)
- Health check loop: every 15 min
- Daily backup: 2 AM, 14-day retention
- Health changelog: auto-appends on state changes

### Integrations
- Cloudflare Tunnel: `*.hermestigerclaw.com` + `goldhealthsys.com`
- Google Drive: `atigerclawai@gmail.com`, templates folder (OCR library)
- Gmail: `allen@gardenofjoybrooklyn.com` → `atigerclawai@gmail.com`
- Obsidian vault: `~/Documents/GHS-Vault`
- NotebookLM bridge: vault → Google Doc → NotebookLM (one-directional)
- ElevenLabs TTS, Kokoro local TTS
- Instagram: @boardwalkbeergarden
- Retell AI voice agents (Victoria/Masha — currently quiet, API key likely expired)

## What was proposed (Hermes suggested building)
A 12-tab native command center (`command.html`) replacing the iframe shell:
1. Dashboard — all services, agents, stats
2. Kanban — task board with drag-and-drop
3. Email — Gmail inbox, compose, reply
4. Clients — roster, auth statuses, WiFi attendance tracking
5. Agents — start/stop/restart, logs, memory usage
6. Terminal — live shell
7. Vault — Rexxie entries
8. Security — scans, audit log, red/blue team
9. Workflows — n8n control panel
10. Calendar — GOJ schedule + 7-system cascade
11. AI Models — all providers, quick chat
12. NotebookLM — document manager

## Question 1: What's missing?
Read the full knowledge base at `~/Desktop/REX/CC_HERMES_KNOWLEDGE.md`, the Hub reference at `~/Desktop/REX/CC_HUB_MASTER_REFERENCE.md`, and inspect the live system. Then tell Kato:

- **What capability gaps exist** that neither the current build nor the 12-tab proposal covers?
- **What's redundant?** Does anything already exist elsewhere that the 12-tab plan would duplicate?
- **What's the priority order?** If we can't build all 12 tabs at once, what should come first?
- **What dependencies exist?** Does tab X need tab Y built first?

Specifically check:
- Is there already a Kanban at port 9119 (Hermes Dashboard)? Does it conflict?
- Does the existing `/jarvis` page already cover what the Dashboard tab would do?
- Is the WiFi attendance tracking feasible from the Mac Mini (it's not on the office WiFi — it's at Kato's home)?
- Does the 7-System Schedule Change Cascade need its own tab, or should it be part of Calendar?

## Question 2: Can this be one master build?
- Is it sensible to build all 12 tabs into a single `command.html` file?
- Or should some tabs stay as separate pages and the command center link to them?
- What are the performance implications of 12 live panels in one page on an iPhone?
- Should the Tauri macOS app and iOS app use the same HTML, or should they have platform-specific versions?
- Is there a better architecture? (e.g., micro-frontends, web components, separate pages with a shared shell)

## Question 3: DropTop integration
Kato uses **DropTop** — a macOS menu bar customization app. He wants:
- **Rex accessible from the menu bar** — quick commands, status, maybe a mini chat
- **Rexxie accessible from the menu bar** — personal assistant in a dropdown

Questions for Claude:
- What's the best way to integrate DropTop with the Hub? (API calls from DropTop widgets? A separate menu bar app? A Tauri system tray?)
- Can we build DropTop widgets that call the Hub's API endpoints?
- What's the minimal viable menu bar integration we can build in a day?
- Should this be part of the Tauri app (system tray) or separate?

## Question 3.5: Antigravity integration
Kato uses **Google Antigravity** (`/Applications/Antigravity.app`) as his design partner — it's his go-to for visual builds, UI polish, and creative work. Currently:

**What exists:**
- Native Mac app installed at `/Applications/Antigravity.app`
- CLI at `~/.gemini/antigravity-cli/` with brain, conversations, knowledge, log
- State at `~/.gemini/antigravity/antigravity_state.pbtxt`
- The `agent-skills` repo (addyosmani, tagged "antigravity") IS the Antigravity design system
- Trusted workspace: `~/Downloads/hermie-skills-bundle`

**What's MISSING:**
- NO MCP server entry in Hermes config.yaml (there's no MCP section at all — not for Antigravity, Obsidian, n8n, or anything)
- No API endpoints in the Hub for Antigravity
- No link/widget in the command center
- Hermes can't talk to Antigravity at all

**Questions for Claude:**
- Can Antigravity be connected via MCP? (It's a Google product — does it have an MCP server, a REST API, or a CLI bridge?)
- What's the minimum viable Antigravity widget for the command center? (Status? Recent projects? "Open in Antigravity" button?)
- Should there be a "Design" tab that bundles Antigravity + agent-skills + image generation + Excalidraw?
- Can we use `~/.gemini/antigravity-cli/` to pipe designs between Hermes and Antigravity?
- What other design tools exist in the ecosystem that should be grouped with Antigravity? (ComfyUI, image_generate, Excalidraw, arch-diagrams)

## Question 4: The "I don't like this" workflow
Kato wants a simple process for requesting changes:

- If he opens the command center and something looks wrong, what does he do?
- If an agent does something unexpected, what's the escalation?
- How should he communicate design changes? (Telegram to Hermes? Direct to Claude Code? GitHub issue?)
- Is there a way to "freeze" a working version and experiment on a copy?
- How do we track what was changed and why, so we can roll back?

Propose a lightweight change management workflow that works for a solo operator who moves fast. No JIRA. No sprints. Just: "I saw this, I want that, make it happen, don't break anything else."

## Rules
- Read before building. Read `CC_HERMES_KNOWLEDGE.md` in full first.
- Nothing is off-limits. Kato has approved edits to all pages.
- Be honest. If something in the 12-tab plan doesn't make sense, say so.
- Propose before building. Answer the four questions, get Kato's approval, then build.
- User is `mainsobhelper`. Home is `/Users/mainsobhelper`. Everything runs on this Mac Mini M4.
