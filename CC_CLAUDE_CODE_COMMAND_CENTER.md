# Tiger Claw Command Center — Complete Native Build

## What exists
A FastAPI Hub at `~/hermes-hub/server.py` (port 9000, URL: https://workspace.hermestigerclaw.com via Cloudflare tunnel). It has:
- `/command` route serving a basic 7-tab iframe shell at `~/hermes-hub/www/command.html`
- WebSocket `/ws` broadcasting real-time service status every 15s
- 60+ API endpoints for auth, vault, notebook, security, agents, TTS
- A Tauri macOS app at `~/hermes-apps/macos/` (10MB .app, DMG at `~/Desktop/Tiger_Claw_1.0.0.dmg`)
- A Capacitor iOS project at `~/hermes-apps/ios/`

The current `/command` page is a placeholder — a handful of iframes loading Hub pages under different tabs. The Jarvis HUD has already been edited with Kato's permission to support iPhone detection, live service dots, and agent status panels. Build on top of all of this — nothing is off-limits.

## Your job
Build a truly integrated command center (`command.html`) that replaces the iframe shell with NATIVE panels. Every tab is a real live dashboard, not a page load. Use the Hub's existing API endpoints and WebSocket. Add new API endpoints as needed. All data must be live and real-time via WebSocket.

## Tabs & what each needs

### Tab 1: 📊 Dashboard (home)
- Live service status dots for ALL 20+ services (ports 3002, 65001, 8000, 8080, 8081, 5678, 9119, 4000, 11434, 27226, 9000, 3003, 3847, 8765, 1234, 18789, etc.)
- Real-time WebSocket updates — green pulse when up, red when down
- Agent roster: hermes-cloud, hermes-local, rexxie, nemobot, claus, elena, victor, nova, riggs, marcus, datarex, n8n-worker, comfyui — live status
- Quick stats: clients active today, pending authorizations, open tasks, system uptime
- Alert feed: security scan results, service failures, auth expirations

### Tab 2: 📋 Kanban / Task Manager
- Board with columns: Backlog | Today | In Progress | Done | Blocked
- Tasks have: title, assignee (Kato/Vlad/agent), priority, deadline, tags
- Drag-to-move between columns
- Backed by a new DB table or JSON file at `~/hermes-hub/tasks.json`
- API: GET/POST/PUT/DELETE `/api/kanban/tasks`
- Filter by assignee, priority, tag
- WebSocket push when tasks change

### Tab 3: 📧 Email
- Show inbox from `atigerclawai@gmail.com` (Gmail API — credentials at `~/Desktop/REX/google_credentials.json`, token at `~/.rex_google_token.json`)
- Compose, reply, forward
- Quick actions: "Send to Rexxie", "Create task from email"
- Filter: unread, flagged, GOJ-related, BBG-related
- API: GET `/api/email/inbox`, POST `/api/email/send`, GET `/api/email/read/{id}`

### Tab 4: 👥 Clients & Employees
- Client roster from `auth_tracker.db` (`~/Documents/goj files/dashboard/auth_tracker.db`) — 426+ clients
- Authorization status: ACTIVE / EXPIRED / PENDING RENEWAL — color-coded
- Employee list with medical + inservice compliance tracking
- **WiFi-based time tracking:** When an employee's phone joins the office WiFi, log arrival time. When it disconnects, log departure. Use ARP table monitoring or the office router's DHCP leases.
- Today's attendance: who's here, who's late, who's absent
- API: GET `/api/clients`, GET `/api/employees`, GET `/api/attendance`, POST `/api/attendance/checkin`

### Tab 5: 🤖 Agents
- Full agent list from Hub's agent registry
- Each agent: name, status, port, last seen, uptime, description
- Start/stop/restart agents (where possible via launchctl)
- Agent log tails — last 20 lines from each agent's log
- Memory usage per agent (ps aux)
- API: GET `/api/hub/agents` (exists), POST `/api/agents/{name}/restart`

### Tab 6: 💻 Terminal
- Web terminal connected to local shell (the existing `/terminal` page works — embed or recreate)
- Command history
- Quick commands: health check, restart hub, status, backup

### Tab 7: 🔐 Vault
- Rexxie vault entries (existing API: `/api/rexxie/vault/*`)
- Add/edit/delete/search entries
- Category filters
- Pin/unlock flow

### Tab 8: 🛡 Security
- Ecosystem scan trigger + results (existing: POST `/api/rexxie/scan`)
- Audit log view (GET `/api/hub/security/audit`)
- Integrity check results
- Malware scan trigger
- Red team/blue team scan results from `~/Desktop/REX/rex_red_team.py` and `rex_blue_team.py`

### Tab 9: 🔄 Workflows (n8n)
- List all 6 live n8n workflows with status, last run, next run
- Trigger manual workflow runs
- Workflow execution history
- API: GET `/api/hub/n8n` (exists), POST `/api/n8n/trigger/{id}`

### Tab 10: 📅 Calendar / Schedule
- GOJ daily schedule: 7:30 AM morning report, 10:30 AM kitchen sheets, 3:15 PM signin sheets, 9 PM drop-off
- Client schedule view — who's scheduled today, who called sick
- 7-System Schedule Change Cascade status: Calendar → Attendance → Driver → Kitchen → Distribution → Sign-in → Menu
- Pending schedule changes from `auth_tracker.db.pending_schedule_changes`

### Tab 11: 🤖 AI / Models
- All available models from DeepSeek, Anthropic, Google, xAI, OpenAI, Mistral, Groq, Ollama, LM Studio
- Quick chat interface to any model
- Model status: online/offline, token usage
- API: GET `/api/hub/models` (exists)

### Tab 12: 📓 NotebookLM
- Existing notebook at `/notebook` — embed or recreate
- Upload documents (PDF, DOCX, TXT)
- List, read, delete, search
- Sync to Obsidian (API exists: `/api/notebook/obsidian/save`)
- Link to Google NotebookLM vault docs

### Tab 13: 🎨 Design Studio
- **Antigravity** — native Mac app at `/Applications/Antigravity.app`. Show status, recent projects from `~/.gemini/antigravity-cli/brain/`, "Open in Antigravity" button. Goal: eventually connect via MCP so Hermes can pipe designs directly.
- **Image generation** — prompt input → FAL/ComfyUI image gen (existing `image_generate` tool)
- **Excalidraw** — create/open diagrams (existing Excalidraw skill)
- **Architecture diagrams** — dark-themed SVG cloud/infra diagrams
- If Antigravity gets MCP'd, add a "Send to Antigravity" button on every design output

## Architecture rules
- **Native panels ONLY.** No iframes loading existing pages. Build each tab directly in `command.html` using the Hub's JSON API endpoints.
- **WebSocket for all real-time data.** Service status, agent updates, task changes, new emails — push, don't poll.
- **Single HTML file.** `~/hermes-hub/www/command.html` — both Tauri and Capacitor load this same file. Keep it self-contained or with a small CSS/JS companion if needed.
- **Mobile-first responsive.** Must work on iPhone Safari, iPad, macOS, and inside the Tauri app.
- **Design system:** Dark theme matching GOJ Dashboard: bg `#0f1923`, surface `#1a2535`, border `#2a3a4a`, text `#c8d8e8`, gold accent `#c9a84c`, success `#2ecc71`, danger `#e74c3c`. Font: -apple-system sans-serif.
- **Add API endpoints to `server.py`** for anything the frontend needs that doesn't exist yet. Keep endpoints RESTful, JSON, same auth pattern (Depends(require_auth)).
- **Feel free to improve or refactor any existing page** — `/jarvis`, `/terminal`, `/notebook`, `/command` — Kato has approved edits to all of them. Nothing is off-limits.
- **The Hub must restart cleanly** after adding new endpoints.

## WiFi time tracking implementation
For employee attendance via WiFi:
- Monitor the office network for known employee device MAC addresses
- Options: (a) poll `arp -a` every 60s and check against a MAC registry, (b) query the router's DHCP lease table if accessible, (c) use `ping` sweeps
- Log arrival when a known MAC appears, departure when it disappears for 5+ minutes
- Store in a new SQLite table or JSON file
- Expose via GET `/api/attendance` and GET `/api/attendance/today`
- Show on the Clients tab as "Who's Here Now"

## Email implementation
- Use Google Gmail API with existing credentials at `~/Desktop/REX/google_credentials.json`
- Read-only scope initially, compose added later
- Fetch last 50 inbox messages, show unread count
- Store cursor/tokens in the existing `~/.rex_google_token.json`

## After building
1. Restart the Hub: `kill $(lsof -ti :9000)` then `cd ~/hermes-hub && python3 server.py &`
2. Verify `/command` loads from both `http://127.0.0.1:9000/command` and `https://workspace.hermestigerclaw.com/command`
3. Verify WebSocket `/ws` broadcasts correctly
4. Rebuild the Tauri app: `cd ~/hermes-apps/macos && npx tauri build`
5. Create a fresh DMG from the new .app bundle
6. Test on iPhone Safari

## Files to modify
- `~/hermes-hub/server.py` — add new API endpoints, improve existing ones as needed
- `~/hermes-hub/www/command.html` — COMPLETE REWRITE as described above
- `~/hermes-hub/www/jarvis.html` — feel free to enhance or merge into command center
- `~/hermes-apps/macos/src-tauri/tauri.conf.json` — ensure `devUrl` points to `/command`
- `~/hermes-apps/ios/capacitor.config.json` — ensure iOS loads `/command`

## Files to reference (read, don't modify)
- `~/Desktop/REX/CC_HERMES_KNOWLEDGE.md` — full ecosystem knowledge
- `~/Desktop/REX/CC_HUB_MASTER_REFERENCE.md` — Hub API reference
- `~/Desktop/REX/CLAUDE.md` — governing rules
- `~/Documents/goj files/dashboard/auth_tracker.db` — client/employee data
- `~/Desktop/REX/google_credentials.json` — Gmail auth

## What NOT to do
- Do NOT remove existing API endpoints that are in use
- Do NOT change the auth flow (PIN/WebAuthn)
- Do NOT break the Cloudflare tunnel
- Do NOT expose PHI to cloud