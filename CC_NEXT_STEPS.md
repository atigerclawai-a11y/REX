# Tiger Claw — Step-by-Step Next Move Plan
# Compiled: June 7, 2026

────────────────────────────────────────────────────────────
PHASE 0: AUDIT — Send Claude the audit prompt (TODAY)
────────────────────────────────────────────────────────────

File: ~/Desktop/REX/CC_CLAUDE_AUDIT.md

Drop this into Claude Code FIRST. He'll give you an honest inventory
of everything he built, what's actually running, and what's placeholder.
Do this before anything else — it prevents both AIs from building
duplicates or contradicting each other.

After Claude responds, compare his list against this URL audit:

  SERVICES UP (13):
  ✅ Hub :9000, Cloudflare tunnel, GHS site
  ✅ REX :8000, DataRex :8080, OpenWebUI :8081
  ✅ n8n :5678, Ollama :11434, LM Studio :1234
  ✅ Hermes Dash :9119, Deck :4000, AI Hub :3003

  NEEDS CHECK (4):
  ⚠️ TigerClaw API :27226 — 404 at root, endpoint may be at different path
  ⚠️ Cloud GW :3002 — 404 at root, likely alive
  ⚠️ Local GW :65001 — 404 at root, likely alive
  ⚠️ Phone Unlock :8765 — 404 at root

  DOWN (2):
  ❌ Portal :3847 — connection refused
  ❌ LibreChat :3080 — connection refused

  All Hub pages working: /login, /jarvis, /command, /terminal, /notebook, /docs

────────────────────────────────────────────────────────────
PHASE 1: GAP ANALYSIS — Send Claude the gap analysis (TODAY)
────────────────────────────────────────────────────────────

File: ~/Desktop/REX/CC_CLAUDE_GAP_ANALYSIS.md

After the audit, drop this. Claude will answer:
- What's missing from the 18-page plan?
- Can everything be one master build on Railway?
- How to integrate DropTop and Antigravity?
- What's the change workflow when you don't like something?

────────────────────────────────────────────────────────────
PHASE 2: BUILD — Send Claude the Railway build spec
────────────────────────────────────────────────────────────

File: ~/Desktop/REX/CC_CLAUDE_RAILWAY_BUILD.md

Only after Claude's audit + gap analysis answers. This builds:

  18-PAGE RAILWAY APP:
   1. /dashboard    — Customizable widget editor (12 widget types)
   2. /modules      — 34 GHS modules (16 built, 18 pending)
   3. /clients      — 426 clients, auth statuses
   4. /employees    — WiFi attendance tracking
   5. /schedule     — GOJ calendar, 7-system cascade
   6. /billing      — Claims, QuickBooks handoff
   7. /kitchen      — Menu pipeline, OCR
   8. /transport    — Routes, GPS placeholder
   9. /security     — Scans, audit, HIPAA
  10. /agents       — Agent controls, logs
  11. /bbg          — Beer Garden operations
  12. /design       — Antigravity, image gen, Excalidraw
  13. /tools        — Spotlight-style command palette (11 categories)
  14. /documents    — Unified doc storage center
  15. /og33         — 33-model deliberation chamber
  16. /vault        — Rexxie (PHI-safe, read-only)
  17. /voice        — Voice commands, TTS, "Jarvis I'm leaving"
  18. /settings     — Preferences, toggles

────────────────────────────────────────────────────────────
PHASE 3: TOOLBOX — Best libraries and extensions found
────────────────────────────────────────────────────────────

For the widget dashboard (/):
  → Gridstack.js v12.6.0 (gridstackjs.com)
    - Pure Typescript, zero dependencies
    - Drag, resize, responsive, mobile support
    - Save/restore layouts, nested grids
    - Works with any framework
    - npm install gridstack + 3 lines of code
    - Used by VMware, Node-RED, and others

For the command palette (/tools):
  → Pattern after macOS Spotlight / VS Code Command Palette
    - Fuzzy search filter
    - Category tabs
    - Keyboard shortcuts
    - "Launch" opens pre-configured modal
    - No heavy library needed — 200 lines of vanilla JS

For the OG 33 chamber (/og33):
  → Multi-model parallel API calls + collapsible response cards
    - Color-code by provider (DeepSeek=orange, Claude=purple, etc.)
    - Synthesize with one "chairman" model
    - Vote aggregation

Available skills to leverage in the tools catalog:

  HERMES (cloud profile): ~/.hermes/profiles/cloud/skills/
    78 SKILL.md files — 76 active+2 pending
    Used by: Hermes agent directly (web_search, terminal, image_generate, etc.)

  CLAUDE / ECC: ~/.claude/skills/
    195 SKILL.md files — 63 agents, 249 skills, 79 commands
    Used by: Claude Code CLI for code generation, review, testing

  ECC REPO: ~/Desktop/REX/ecc/skills/
    348 files (skills + supporting docs)
    Used by: full ECC harness — 60-agent, 232-skill system

  TOTAL ECOSYSTEM: ~270 unique skills across both platforms
    (accounting for overlap between Claude and ECC repo)

  The /tools page must catalog ALL of them — not just the 76 Hermes ones.
  Every skill from both systems, organized by category, with "which platform
  supports this" badges (Hermes ✓, Claude ✓, ECC ✓).

  NOT YET INSTALLED — Recommended additions:
  - Graphify (github.com/safishamsi/graphify) — knowledge graph skill ✅ INSTALLED
    v0.8.35, 61K stars, YC S26. Maps entire project into queryable graph.
    Installed to: ~/.hermes/skills/graphify/ (root) + cloud profile
    Also supports: Antigravity, Claude Code, Codex, OpenCode, Cursor, Gemini
    Use: /graphify . in any AI assistant → knowledge graph of your project

────────────────────────────────────────────────────────────
PHASE 4: FIXES — What needs repair (order matters)
────────────────────────────────────────────────────────────

  1. Restart Portal :3847 — connection refused
     → check: launchctl list | grep portal
     → fix: launchctl load ~/Library/LaunchAgents/com.hermes.portal.plist

  2. Restart LibreChat :3080 — connection refused (Docker)
     → check: docker ps | grep librechat
     → fix: docker start librechat or docker-compose up

  3. Fix TigerClaw API :27226 — returns 404 at root
     → check what endpoint it expects
     → curl http://127.0.0.1:27226/api/health or similar

  4. Fix Cloud GW :3002 + Local GW :65001 health endpoints
     → Gateway health may be at /api/status not root
     → These are likely alive but returning 404 for root query

  5. Fix /api/hub/models — 404 (endpoint may have moved)
     → Check server.py for correct route

  6. Fix cloud .env permissions (HIGH security)
     → sudo chmod 600 ~/.hermes/profiles/cloud/.env (ACL blocked — needs sudo)

  7. Encrypt auth_tracker.db with SQLCipher (CRITICAL HIPAA)

────────────────────────────────────────────────────────────
PHASE 5: DEPLOY — Push to Railway
────────────────────────────────────────────────────────────

After Claude builds the app:
  1. cd ~/workspace/jarvis-deploy
  2. railway link (connect to existing project)
  3. railway up (deploy)
  4. Set custom domain: command.hermestigerclaw.com
  5. Verify all 18 pages load
  6. Rebuild Tauri macOS app with new Railway URL
  7. Rebuild Capacitor iOS app with new Railway URL

────────────────────────────────────────────────────────────
QUICK COMMANDS
────────────────────────────────────────────────────────────

  Check all services:  curl http://127.0.0.1:9000/api/hub/summary (auth)
  Restart Hub:         kill $(lsof -ti :9000); cd ~/hermes-hub; python3 server.py &
  Health check:        curl http://127.0.0.1:9000/health
  Tunnel check:        curl https://workspace.hermestigerclaw.com/health
  Rebuild macOS app:   cd ~/hermes-apps/macos; npx tauri build
  Create DMG:          create-dmg --volname "Tiger Claw" ... Tiger Claw.dmg ./App.app/

────────────────────────────────────────────────────────────
PRIORITY ORDER
────────────────────────────────────────────────────────────

  1. Send CC_CLAUDE_AUDIT.md to Claude → get honest inventory
  2. Compare audit against this document → find gaps
  3. Send CC_CLAUDE_GAP_ANALYSIS.md → resolve architecture
  4. Fix DOWN services (Portal, LibreChat)
  5. Send CC_CLAUDE_RAILWAY_BUILD.md → build the app
  6. Deploy to Railway → test all 18 pages
  7. Rebuild native apps → DMG + iOS TestFlight
  8. Fix HIPAA gap (SQLCipher encrypt auth_tracker.db)
