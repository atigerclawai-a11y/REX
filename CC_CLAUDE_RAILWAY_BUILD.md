# Tiger Claw — Revised Architecture & Build Plan

## What Kato actually needs (corrected)

### The problem with the current approach
- The Hub on port 9000 with Cloudflare tunnel is a **static reverse proxy** — fine for a dashboard, wrong for a dynamic multi-module platform
- One `command.html` with 13 iframes is a prototype, not the real thing
- 18 of 34 GHS modules are placeholders — never built
- The business side (BBG, GOJ operations, billing, scheduling) isn't integrated

### What already exists that I (Hermes) missed
- **Railway project** at `~/workspace/jarvis-deploy/railway.toml` — configured for Nixpacks + Python
- **Railway deploy directory** at `~/Desktop/REX/CC_railway_deploy/` — contains a 4,983-line `index.html` (223KB!) — GHS Command Center v2 with Three.js 3D background, Chart.js analytics, screensaver mode, cyberpunk design system
- **`.railwayignore`** — already properly configured to exclude .venv, node_modules, secrets, logs, PHI data
- **Railway CLI** at `~/.railway/` — auth configured

### The correct architecture
```
https://command.hermestigerclaw.com (or similar)
     │
     ▼
┌─────────────────────────────────────┐
│         Railway (Dynamic)           │
│  FastAPI + Jinja2 multi-page app    │
│  WebSocket for real-time            │
│  SQLite for module data             │
│  Background workers for attendance   │
└──────────┬──────────────────────────┘
           │ SSH tunnel or API bridge
           ▼
┌─────────────────────────────────────┐
│     Mac Mini M4 (local backend)     │
│  Hub :9000, REX :8000, DataRex :8080│
│  auth_tracker.db, agents, n8n       │
│  Email, OCR, vault, cron jobs       │
└─────────────────────────────────────┘
```

Railway handles the public web app. The Mac Mini stays the backend. They communicate via API or a secure bridge.

## The 34 GHS Modules — real status

### Built (16 according to Hub, but verify each)
1. Client Management
2. Authorizations
3. Attendance / Sign-In
4. Billing & Claims (partial — Carecenta not fully replaced)
5. OCR Pipeline (4-engine consensus)
6. Kitchen & Menus
7. Driver Routes (M01 transport module — partial)
8. Shift Scheduling
9. Analytics Dashboard (DataRex :8080)
10. Telegram Integration
11. Chairman Panel
12. DataRex Core
13. Google Drive Sync
14. Multi-Agent Routing
15. Staff Management
16. Client Profiles

### Pending / placeholder only (18)
17. Clock-In / EVV
18. Payroll
19. Paperless Docs (Paperless-ngx exists at 100.99.86.60:8000 but not wired)
20. GPS Tracking (GeoTab being replaced — not yet built)
21. Transition Agent (running but Drive hook not built)
22. Template Engine
23. Audit Trail
24. Insurance Tracker
25. Incident Reports
26. Care Plans
27. Medication Log
28. Transport Logs
29. Vendor Contacts
30. Regulatory Compliance
31. Backup & Recovery (cron job exists, but no UI)
32. Notification Center
33. User Access Control (RBAC exists in rex_permissions.py, no UI)
34. Export & Reporting

### Additional business modules Kato wants
- Boardwalk Beer Garden (BBG): Clover POS, Instagram, menu management, UFC event builds
- Garden of Joy (GOJ): daily operations, 7-system cascade, email intake, iMessage watcher
- Employee WiFi attendance tracking
- QuickBooks replacement / bookkeeper handoff
- DropTop menu bar integration for Rex + Rexxie

## What to build for Railway

A **multi-file FastAPI web app** (NOT one HTML file) with:

### Pages (separate routes, Jinja2 templates)
1. `/` — **Customizable Dashboard** with widget editor (see below)
2. `/modules` — All 34 GHS modules, status per module, "Launch" button for each
3. `/clients` — 426-client roster with auth statuses, search, filters
4. `/employees` — 15 staff, compliance tracking, WiFi attendance
5. `/schedule` — GOJ daily calendar, 7-system cascade view
6. `/billing` — Billing & claims, QuickBooks handoff status
7. `/kitchen` — Menu pipeline, OCR results, kitchen sheets
8. `/transport` — Driver routes, GPS tracking placeholder
9. `/security` — Audit trail, scans, red/blue team, HIPAA compliance
10. `/agents` — Agent roster, status, controls, log viewer
11. `/bbg` — Boardwalk Beer Garden operations (separate business context)
12. `/design` — Antigravity launcher, image gen, Excalidraw, arch diagrams
13. `/tools` — Tools Catalog (Spotlight-style tool palette)
14. `/documents` — **Document Storage Center** (see below)
15. `/og33` — **OG 33 Deliberation Chamber** (see below)
16. `/vault` — Rexxie vault (read-only from Railway — no PHI on cloud)
17. `/voice` — Voice Command Center
18. `/settings` — User preferences, module toggles, API key status

### Real-time features
- WebSocket from Railway to Mac Mini for live service/agent status
- Server-Sent Events for module status changes
- Background worker on Mac Mini polls WiFi for employee attendance

### The `/tools` page — maximally usable interface
Think **Spotlight / Alfred / VS Code Command Palette** — not a documentation page, an interactive tool launcher.

**Layout:**
- Search bar at top — type to filter across ALL tools instantly
- Category sidebar or horizontal tabs: Web | Code | Creative | Voice | Data | Content | Security | Agents | Comms | IoT | ML
- Grid of tool cards below — each shows icon, name, one-liner, supported models, "Launch" button
- Favorites row — pin your most-used tools
- Recently used section
- "Launch" opens a modal pre-configured for that tool

**Every tool in the ecosystem, organized by category:**

🌐 **Web & Research** — web_search, web_extract, browser_navigate/click/type/snapshot, browser_vision, browser_console

💻 **Terminal & Code** — terminal, execute_code, delegate_task, patch, read_file/write_file/search_files, Claude Code CLI, Codex CLI, OpenCode CLI, Node.js debugger, Python debugpy

🎨 **Creative & Design** — image_generate (FAL/ComfyUI), ascii_art, ascii_video, architecture_diagram, excalidraw, p5js, manim_video, comfyui, design_visualization, popular_web_designs

🎤 **Voice & Audio** — text_to_speech (Edge/ElevenLabs/Kokoro), audiocraft (MusicGen/AudioGen), songsee, heartmula, Victoria/Masha voice agents

📊 **Data & Analytics** — jupyter_live_kernel, weights_and_biases, evaluating_llms_harness, huggingface_hub, segment_anything_model

📝 **Content & Docs** — ocr_and_documents, nano_pdf, powerpoint, google_workspace, obsidian, apple_notes, design_md, apple_reminders

🔒 **Security** — fortress scanner, malware monitor, integrity check, godmode (jailbreak testing), obliteratus, red team, blue team, audit trail

🤖 **Agents & Automation** — cronjob, n8n workflows, agent roster, delegate_task, ECC (60 agents, 232 skills)

📱 **Communication** — send_message (Telegram/Discord/Signal/SMS), imessage, himalaya (email), xurl (X/Twitter), yuanbao

🏠 **Hardware & IoT** — openhue (Philips Hue), findmy (Apple devices), macos_computer_use, maps, smart_home

🧠 **ML & Inference** — llama_cpp, serving_llms_vllm, all model providers, local models list

**Each tool card shows:**
- Which models support it (claude ✓, deepseek ✓, gemini ✗, etc.)
- Whether it's local-only or needs internet
- Quick keyboard shortcut if available

**The point:** You shouldn't need to remember what tools exist or which model to use. Type what you want to do → the palette shows you which tool + which model. Tap → it works.

### The `/voice` page — Voice Command Center
Full voice interface for the entire ecosystem. Think Jarvis from Iron Man — you speak, the system responds.

**Voice input:**
- "Push to talk" button on mobile/desktop — hold to speak, release to process
- Voice activity detection (VAD) mode — always listening with wake word "Hey Jarvis" or "Hey Rex"
- Transcribe using local Whisper or cloud API → route to appropriate agent/model

**Voice output (TTS):**
- **ElevenLabs** (premium) — REX voice (Brian, authoritative), Rexxie voice (Rachel, warm)
- **Kokoro** (local ONNX) — fallback, no internet needed
- **Edge TTS** (free) — always available
- Voice selector per context: REX for commands, Rexxie for personal, Jarvis for system

**Voice agents:**
- **Victoria** — GOJ M12 appointment confirmation calls (Retell AI, transfer 347-587-9913). Currently quiet — API key likely expired.
- **Masha** — BBG persona (Retell AI). Currently quiet — same issue.
- Status indicators for both: live / expired / needs rotation

**Jarvis Screensaver integration:**
- "Jarvis, I'm leaving" → activates screensaver, locks sensitive dashboards, arms security monitoring
- "Jarvis, I'm home" → deactivates screensaver, returns to dashboard
- Triggerable from anywhere: voice command, button on `/voice` page, or geofence via iPhone Shortcuts
- API endpoint: POST `/api/jarvis/screensaver` with `{action: "activate"|"deactivate"}`

**Voice chat:**
- Full conversation mode — speak naturally, get spoken responses
- Context-aware: knows which page you're on, what you were doing
- Model routing: simple queries → local Ollama, complex → DeepSeek/Claude, creative → Gemini

**Quick voice commands:**
- "What's the status of all services?"
- "Any clients with expired authorizations?"
- "Send a message to Vlad"
- "Run the red team scan"
- "Show me today's attendance"
- "Generate the kitchen sheets for tomorrow"

### The customizable `/` dashboard — Widget Editor + Knowledge Graph

**This is the most important page.** The homepage has a central knowledge graph window with everything else built around it.

#### Layout
```
┌─────────────────────────────────────────────────────┐
│  [Obsidian Graph] [Graphify]   🔍 Search...    ⚙️  │ ← Toggle bar
├──────────┬────────────────────────┬─────────────────┤
│          │                        │                 │
│  Widget  │    KNOWLEDGE GRAPH     │  Context Panel  │
│  Panel   │    (center, dominant)  │                 │
│          │                        │  • Selected node │
│  🟢 Svcs │    Interactive D3.js   │  • Connections   │
│  🤖 Agts │    zoom/pan/click      │  • Quick actions │
│  👥 Today│                        │                 │
│  📋 Tasks│                        │                 │
│          │                        │                 │
├──────────┴────────────────────────┴─────────────────┤
│  🎤 Voice  │  📊 Stats Bar: 426 clients · 13 agents · 10 svcs UP  │
└─────────────────────────────────────────────────────┘
```

#### Toggle: Obsidian Graph ↔ Graphify
Two modes for the central window:

**Obsidian Graph mode:**
- Rendered from `[[wikilinks]]` in the vault (fast, local, no API)
- Shows YOUR connections — what you manually linked
- Node = note title, edge = wikilink, size = connection count
- Click a node → opens note preview in context panel
- Good for: navigating your own knowledge structure

**Graphify mode:**
- Rendered from `~/Desktop/REX/graphify_obsidian/graph.json`
- Shows AI-discovered semantic connections
- Node = concept/entity (not just files), edge = AI-understood relationship
- Color-coded clusters by topic (GOJ, BBG, GHS, Security, Agents, etc.)
- Click a node → shows AI summary + related nodes
- Good for: discovering connections you didn't know existed

**Visual design:**
- Dark background (#060610) with neon edges
- Nodes pulse on hover, clusters expand on click
- Search bar filters nodes in real-time
- "Focus" mode hides sidebar for fullscreen graph
- Smooth D3.js force-directed layout
- Mobile: vertical stack — graph on top, widgets below

#### Auto-refresh
- Graphify graph rebuilds nightly via cron: `0 2 * * * graphify extract ~/Documents/GHS-Vault --output ~/Desktop/REX/graphify_obsidian --backend deepseek --update`
- Obsidian graph reads vault live — always current
- Page polls for new `graph.json` timestamp

### The `/documents` page — Document Storage Center
Central document hub for the entire ecosystem. Every PDF, scan, template, contract, and record in one searchable place.

**Sources (unified search across all):**
- Google Drive (`atigerclawai@gmail.com`): Claude sessions, GOJBot, Hermes backups, remittance (835 ERA), templates (OCR library), Tigerclaw_AI, NotebookLM vaults
- `~/Documents/goj files/documents/`: menus, authorization, signin sheets
- `~/Desktop/REX/`: scripts, commands, handoff runs, logs
- Obsidian vault: `~/Documents/GHS-Vault/`
- NotebookLM: uploaded docs from `/notebook`
- Paperless-ngx: `100.99.86.60:8000` (not yet wired)
- BBG files: Clover POS exports, Instagram exports, contracts

**Features:**
- Global search across all sources — type filename or OCR text
- Filter by: source, file type (PDF, DOCX, XLSX, PNG, TXT, MD), date range, category tag
- Preview inline: PDFs render in-browser, images show, markdown renders
- "Open in Finder" — opens file on Mac Mini
- "Send to..." — route to NotebookLM, Obsidian, Google Drive, Rexxie, or email
- Upload new file — routes to correct source directory
- Tag system: menu, auth, billing, HR, contract, template, archive
- Audit trail: who uploaded, when, who accessed
- OCR on demand — select a PDF → "OCR this" → runs 4-engine consensus

**PHI note:** Document metadata (filenames, tags, OCR text) may contain PHI. Never cache or store document contents on Railway. All document operations proxy through the Mac Mini Hub API.

### The `/og33` page — OG 33 Deliberation Chamber
The multi-model council. 33 AI models deliberate on questions, strategies, and decisions. Chairman (Kato) controls composition and has final say.

**What it is:**
OG 33 is a multi-model deliberation system where all available models participate by default. It's dashboard-integrated and has a standalone portal. GOJ client data NEVER enters OG 33 prompts — PHI firewall is absolute.

**Models available (from knowledge base):**
- DeepSeek: deepseek-v4-pro (primary), deepseek-v4-flash
- Anthropic: claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5
- Google: gemini-2.0-flash, gemini-2.5-flash, gemini-2.5-pro
- xAI: grok-4.3, grok-4.20-reasoning, grok-3-mini
- OpenAI: gpt-4o, gpt-4o-mini, o1, o3-mini
- Mistral: mistral-large-latest
- Groq: qwen3-32b, llama-3.3-70b
- Perplexity: sonar-pro, sonar-reasoning-pro
- OpenRouter: moonshotai/kimi-k2.6:free
- Ollama: mistral-hermie, qwen2.5-coder:7b
- LM Studio: qwen3.5-9b, nemotron-30b, gemma-3-4b

**Interface:**
- **Pose a question** — type or speak any question/strategy/problem
- **Select models** — checkboxes, "Select All", "Cloud Only", "Local Only", "Fast Only", "Reasoning Heavy"
- **Deliberate** — all selected models respond in parallel
- **Results view** — scrollable feed of model responses, color-coded by provider
- **Synthesize** — one model (or Chairman) synthesizes all responses into a consensus
- **Vote** — models can vote on options, results shown as bar chart
- **Chairman override** — Kato can dismiss any model's response, pin the best one, or write the final answer himself
- **History** — all deliberations saved, searchable, taggable

**Rules enforced:**
- GOJ client data (names, medical, financial) NEVER enters prompts — akc_tokenizer.py Gate 1
- Chairman controls model composition
- All model responses logged for audit
- No autonomous action from OG 33 — only deliberation. PAE required for any real-world action.

### Design
- Keep the cyberpunk design system from the existing Railway index.html:
  - bg: `#060610`, cyan: `#00d4ff`, purple: `#7b2fff`, gold: `#ffd700`
  - Fonts: Orbitron (display), Space Mono (UI)
  - Three.js animated background
  - Chart.js for analytics
- OR switch to the GOJ Dashboard dark theme (bg `#0f1923`, gold `#c9a84c`)
- **Kato decides** — present both options

### Security
- PHI stays on Mac Mini — Railway never touches `auth_tracker.db` directly
- Railway pages query the Mac Mini Hub API for data, don't store PHI
- All Railway↔Mac Mini traffic over encrypted tunnel
- `.railwayignore` already excludes secrets, tokens, PHI files

## DropTop Integration
- Rex: menu bar widget showing agent status, quick commands
- Rexxie: menu bar assistant, quick message compose
- Both read from Mac Mini Hub API
- Build as part of the Tauri app's system tray, OR as standalone Swift/AppleScript menu bar items

## The "I don't like this" workflow
When Kato sees something wrong:
1. **Screenshot + message** → Telegram to Hermes or Claude Code
2. **Direct CLI** → `claude "fix the billing page — the claims column is wrong"`
3. **Version freeze** → Railway has preview deployments — branch before major changes
4. **Rollback** → Railway instant rollback to any previous deploy
5. **Track changes** → Git commits in the Railway repo, changelog auto-generated

No JIRA. No sprints. Just: screenshot → fix → deploy → verify.

## Files to reference
- `~/Desktop/REX/CC_HERMES_KNOWLEDGE.md` — complete ecosystem
- `~/Desktop/REX/CC_HUB_MASTER_REFERENCE.md` — Hub API reference
- `~/Desktop/REX/CC_railway_deploy/index.html` — existing v2 command center (4,983 lines)
- `~/Desktop/REX/CLAUDE.md` — governing rules
- `~/workspace/jarvis-deploy/railway.toml` — Railway config
- `~/Desktop/REX/.railwayignore` — deploy exclusions
- `~/hermes-hub/server.py` — Hub with GHS_MODULES list

## What NOT to do
- Do NOT build everything in one HTML file
- Do NOT use Cloudflare static hosting for dynamic content
- Do NOT store PHI on Railway
- Do NOT expose API keys or tokens in the Railway deploy
- Do NOT remove the existing Cloudflare tunnel — it still serves the Hub API internally
