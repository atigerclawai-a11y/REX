# REX Command Center — Dashboard Rebuild Brief
**Owner:** Kato / Gold Health Systems, Brooklyn NYC  
**Prepared:** 2026-04-16  
**Purpose:** Complete specification for rebuilding index.html to a presentable, functional state  
**Status of current build:** NOT PRESENTABLE — see issues below

---

## WHAT THIS BRIEF IS FOR

The current dashboard (`index.html`) has structural problems that make it unsuitable for presentation. This document is the complete spec to fix it — use it to start a fresh Claude session and give it to the AI exactly as written.

---

## PASTE THIS INTO YOUR NEXT CLAUDE SESSION

---

You are helping Kato, Chairman of Gold Health Systems (GHS), rebuild the REX Command Center dashboard (`index.html`). This is a single-file HTML/CSS/JS dashboard that runs locally in a browser. It does NOT use React, Node, or any build step. The following is the complete specification — follow it exactly.

### WHO YOU'RE BUILDING FOR

- **Company**: Gold Health Systems (GHS) — Medicaid home health care agency, Brooklyn NYC
- **Facility**: Garden of Joy (GOJ) — Adult Day Care Center
- **Population served**: 423 active Russian-speaking elderly members
- **Chairman / sole authority**: Kato
- **System name**: REX (the AI operating system)
- **Deployed website**: goldhealthsys.com / goldhealthsys.pages.dev

### CORE FILES TO READ BEFORE WRITING ANYTHING

Read all of these files before touching index.html:

1. `/REX/GOJ_PACKET_B_MASTER_PROMPT.md` — System laws, phase definitions, what is locked
2. `/REX/PACKET_B_FULL_PLAN.md` — Full 17-tab dashboard spec
3. `/REX/agent_registry.json` — All 13 real agents (IDs, models, roles)
4. `/REX/master_list.json` — Master component registry and north star principles
5. `/REX/GHS_MASTER_PROMPT.md` — 423 members, real attendance stats, data structure
6. `/REX/GOJ_Master_Routes.json` — Real route data (drivers: Alisher, Vadik, etc.)
7. `/REX/parsed_clients.json` — Real client menu selections (Russian food items, weekly)
8. `/REX/ghs_manifest.json` — GHS brand, colors (#1a2742 navy, #C9A84C gold), website structure
9. `/REX/website/components/GoldEgg.jsx` — THE REAL BRAND MARK — use this exact SVG
10. `/REX/website/components/Nav.jsx` — How the real Gold Egg logo is rendered in nav
11. `/REX/ACTIVE_SYSTEM_MANIFEST.json` — Current system version (v3.2-phase16)
12. `/REX/REX_PHASE16_STATUS.md` — Security audit, 3 CRITICAL issues, carry-forward items

### THE 7 PROBLEMS TO FIX (in priority order)

---

#### PROBLEM 1 — LOGO IS WRONG (Fix first, it affects presentation immediately)

The current logo in the dashboard header is a made-up SVG triangle labeled "GHS". That is NOT the GHS brand.

**The real brand mark is the Gold Egg** — a cracked-open golden egg with an orange glow, hatching crack lines, and a warm golden gradient. This is used on:
- The live website (goldhealthsys.com) in the nav and hero
- The GoldEgg.jsx component in `/REX/website/components/GoldEgg.jsx`
- All official GHS/REX materials

**Fix**: Replace the fake triangle SVG in the dashboard header with the cracked Gold Egg SVG extracted from `GoldEgg.jsx`. The header should show the Gold Egg mark followed by the text "REX" in gold, on the dark navy background.

The correct SVG path for the egg body:
```
M50 6 C22 6 5 36 5 66 C5 96 25 118 50 118 C75 118 95 96 95 66 C95 36 78 6 50 6 Z
```
Gradient: `#FFF8C0` → `#F5C830` → `#C08A00` → `#5A3600`  
Crack color: `#FFD000` with glow  
Brand colors: navy `#1a2742`, gold `#C9A84C`

---

#### PROBLEM 2 — REX EGG ORB IS JUST A TOAST POPUP

The Rex Egg (bottom-right fixed orb) currently shows a toast message "REX is watching 🦖" when clicked. This is useless.

**What it must do**: Open a **full chat panel** — a slide-in drawer or modal that is a back-and-forth AI chat interface. This is the primary way the Chairman talks to Rex/Rexxie.

**Requirements for the Rex Chat Panel**:
- Opens from the egg orb at bottom-right
- Shows a chat history area (scrollable)
- Has an input field at the bottom + send button
- On send: makes a `fetch()` call to `http://localhost:11434/api/chat` (Ollama API)
  - Model: `qwen3.5:9b`
  - System prompt: "You are Rexxie, the private AI assistant for Kato, Chairman of Gold Health Systems. You have access to GOJ operations context. Be direct, accurate, and Chairman-focused."
  - Streams the response using `ReadableStream` / `response.body.getReader()`
- Shows streaming text in real time as Rex responds
- Has a close button
- Remembers conversation history within the session (array of `{role, content}`)
- The egg orb itself should pulse/glow gold when the chat is open
- Error state: if Ollama is offline, show "Rex is offline — start Ollama and try again" in the chat area

---

#### PROBLEM 3 — WEBREX IS DECORATIVE, NOT FUNCTIONAL

The current WebRex panel shows a circular node diagram of agents. It looks like a logo, not a tool. It does nothing when you click it.

**What it must be**: Two separate views in the WebRex tab:

**View A — Agent Network** (what's currently there, made functional):
- Each node is clickable
- Clicking a node shows a sidebar with: agent ID, model, role, status, last seen, tags
- Edge lines show actual dependencies from `agent_registry.json`
- Node color: green = running, orange = idle, red = error/offline
- Data loaded from `agent_registry.json` (13 real agents)

**View B — Integration Dependency Map** (NEW — this is what Kato actually needs):
- A hierarchical flowchart showing HOW every component connects to every other
- Nodes represent: REX backend, Ollama API, LM Studio, Telegram Bot, GOJ Scheduler, OCR Engine, Queue Processor, LibreChat, pgvector CIME, Gmail watcher, FastAPI server, SQLite/vault, Cloudflare tunnel
- Directed edges show data flow direction (e.g., "Menu PDF → OCR → GOJ Scheduler → Telegram Bot → Chairman")
- Each edge is labeled with what data flows through it
- Each node has a status dot (green/orange/red) that can be clicked to see the component's current state
- THIS IS THE AUDIT TRAIL MAP — if something breaks, you trace the edge backwards to find the source
- Rendered as an SVG with zoom/pan capability
- A "trace path" tool: click any two nodes → highlights the path between them

Toggle between View A and View B with a button in the WebRex panel header.

---

#### PROBLEM 4 — BUSINESS CONTEXT SWITCHER DOES NOTHING

The top navigation has tabs: GOJ, Sports Bar, Web Design, Social Media. Clicking them just shows the tab as "active" with no real behavior change.

**What must happen when you switch context**:
- The entire dashboard recolors slightly (GOJ = teal accent, Sports Bar = orange accent, Web Design = blue accent, Social Media = purple accent)
- The Home panel headline and subtitle change to reflect the business
- The Operations panel shows different data/placeholder relevant to that business
- The footer "Context: GOJ" label updates
- A persistent banner at the top shows which context is active (to prevent confusion)
- GOJ is the default and has the most real data
- The other 3 contexts are clearly marked "Coming Soon — Phase 19" with a placeholder card explaining what will be here

**Critical rule**: Business data NEVER crosses contexts. The switcher must make it visually obvious which context you're in.

---

#### PROBLEM 5 — NO REAL DATA ANYWHERE

The dashboard shows fake placeholder data. Real data exists in the REX folder and must be loaded.

**What to load and where**:

| Data Source | File | Panel | What to Show |
|-------------|------|--------|------|
| Member count | GHS_MASTER_PROMPT.md (423 members) | Home stats | "423 Active Members" counter |
| Daily attendance | GHS_MASTER_PROMPT.md (per-day table) | Operations | Real Mon-Fri shift attendance numbers |
| Route data | GOJ_Master_Routes.json | Operations | Real driver names: Alisher, Vadik, car_service clients |
| Client menus | parsed_clients.json | Operations | Real client name list with menu selections |
| Calendar | Copy of Calendar 2026 - Apr (1).csv | Home / Operations | Current month calendar with real entries |
| Agent registry | agent_registry.json | Agents panel | All 13 real agents with real IDs/models/roles |
| Staff list | /staff/ folder contents | Employee panel | Real staff members from folder names |

Since this is a local HTML file, the real data should be **embedded directly** as JavaScript constants at the top of the `<script>` section. Do NOT use fetch() to load JSON files — embed the data inline so the dashboard works by opening the HTML file directly.

Extract and embed:
- All 13 agents from `agent_registry.json`
- The attendance table from the master prompt
- Driver names and route counts from `GOJ_Master_Routes.json`
- Staff names from the `/staff/` folder: Alisher, Allen Khiger, Andriy Sheremet, Gennadi Gugilov, Inna Klimova, Liudmila Zhuk, Natalie Altman, Oleg Tikhonov, Olena Sturovska, Ravil Aleev, Svitlana Rozmetanyuk, Vadim Kononenko, Valerian, Vladimir Khiger
- Plan distribution from the master prompt: CPHL(208), Eld Serve(85), Anthem(46), VCM(29), SWH(24), VNS(20)

---

#### PROBLEM 6 — NO EMPLOYEE MANAGEMENT SECTION

There is no way to view, add, or manage employees from the dashboard.

**Add a dedicated "Staff" tab** (or integrate into the existing Profiles/Hiring tabs) with:

**Staff Directory view**:
- Table showing all 14 staff members (from the /staff/ folder)
- Columns: Name, Role, Status, Contact (placeholder), Days Active
- Pre-populated with real names from /staff/ folder: Alisher, Allen Khiger, Andriy Sheremet, Gennadi Gugilov, Inna Klimova, Liudmila Zhuk, Natalie Altman, Oleg Tikhonov, Olena Sturovska, Ravil Aleev, Svitlana Rozmetanyuk, Vadim Kononenko, Valerian, Vladimir Khiger
- Mark drivers (Alisher, Vadik/Vadim Kononenko, Andriy Sheremet) with a "Driver" badge

**Add New Employee form**:
- Fields: Full Name, Role (dropdown: Driver, Care Aide, Administrator, Kitchen, Other), Phone, Start Date, Notes
- On submit: shows a confirmation toast "Employee added to queue — Kato must approve"
- MSU required to actually commit any changes

**Documents section per employee**:
- Shows whether Medical, Inservice, and Compliance docs are on file (from GOJ_Staff_Compliance_Apr2026.xlsx status)
- Red badge if expired or missing, green if current

---

#### PROBLEM 7 — FILE UPLOAD (Calendar, Sign-in, Authorizations)

Add a document upload area to the OCR Intake tab:

- Drag-and-drop zone accepting PDF and image files
- Quick-access buttons: "Upload Calendar", "Upload Sign-in Sheet", "Upload Authorization Form"
- Each uploaded file shows: filename, size, upload timestamp, status (Queued → Processing → Complete)
- Since we're in a local HTML file: use the browser File API to read the file and display its metadata
- Show a "Send to OCR Queue" button that calls the local OCR endpoint: `http://localhost:8000/api/ocr/intake`
- If the API is offline, show: "OCR engine offline — file saved locally, will process when REX backend starts"
- The real document templates live in `/REX/TEMPLATE_signin.pdf`, `/REX/TEMPLATE_driver.pdf`, `/REX/TEMPLATE_distribution.pdf`, `/REX/TEMPLATE_menu_personalized_sample.pdf`, `/REX/GOJ_Weekly_Menu_Form.pdf`

---

### DESIGN RULES — NON-NEGOTIABLE

**Colors** (locked, do not change):
- Background dark: `#0D1B2A`
- Card/panel: `#1A2B35`
- Teal accent: `#0D7377`
- Gold accent: `#C9A84C`
- Parchment/light: `#F0EAD6`
- Green status: `#52C882`
- Red: `#dc2626`
- Orange: `#F5A623`

**Brand**: The Gold Egg is the brand mark. It appears in the header nav AND as the Rex chat orb. Both should use the same egg SVG — different sizes.

**Tabs**: Keep all 17 tabs. Don't remove any. Add Staff as a sub-tab under Profiles or as a standalone tab.

**Phase labels**: Tabs for features not yet built (pgvector CIME, Voice, etc.) should be visible but show a "Phase XX — Coming Soon" placeholder with a brief description of what will be here.

**MSU gate**: Finance tab and Settings key management are still behind MSU (code: CHAIRMAN or 1234). Don't remove this gate.

**Rex/Rexxie separation**: Rex (green T-Rex identity, public-facing) is displayed in the dashboard. Rexxie (turtle/shell, private Chairman-only) is the chat voice behind the egg. Both identities are distinct. Never merge them.

---

### TECHNICAL CONSTRAINTS

- Single HTML file — no build step, no npm, no server required to open
- Must work by double-clicking the file in Finder
- All CSS inline in `<style>` tags
- All JS inline in `<script>` tags
- External CDN OK for fonts only (Google Fonts)
- Real data embedded as JS constants (not fetched)
- The Rex chat DOES need internet/Ollama to work, but the rest of the dashboard must work offline
- File size: keep under 300KB
- Write in chunks — do not write more than 200 lines at once without confirming

---

### PHASE 17 (WebRex Spider) — ALREADY PLANNED

Phase 17 is the WebRex phase. The dependency map (Problem 3 above) IS Phase 17. When implementing it, note:
- The spider crawls the local system to detect running services (check localhost:11434, localhost:3000, localhost:8000, localhost:1234)
- Real-time status dots update every 30 seconds using `setInterval`
- The map is drawn in SVG, not Canvas
- Node positions are fixed (not force-directed layout) for predictability
- Phase 17 spec is in `PACKET_B_FULL_PLAN.md`

---

### SYSTEM STATUS AT TIME OF THIS BRIEF

| Item | Status |
|------|--------|
| Phase | 16 (current) |
| REX Version | 1.0.16 |
| Ollama | localhost:11434 · native (NOT Docker) |
| Rexxie model | qwen3.5:9b |
| Cline build agent | qwen2.5-coder:7b |
| LM Studio | localhost:1234 · nomic-embed-text-v1.5 (embeddings only) |
| Active agents | 13 (see agent_registry.json) |
| Active enforcer | rex_policy_enforcer.py |
| Unified enforcer | rex_unified_enforcer.py (written, not yet activated) |
| Security issues | 3 CRITICAL open — see REX_PHASE16_STATUS.md |
| Dashboard | index.html in /REX/ — currently NOT presentable |
| Website | goldhealthsys.com (Next.js, Cloudflare Pages) |

---

### VERIFICATION CHECKLIST (run before calling it done)

Before saying the dashboard is complete, check:
- [ ] Gold Egg appears in header (not a triangle)
- [ ] Clicking the egg orb opens a chat panel (not a toast)
- [ ] Chat panel successfully calls Ollama at localhost:11434 (or shows offline error gracefully)
- [ ] All 13 agents from agent_registry.json are shown with real IDs and models
- [ ] Real attendance numbers (Mon 153, Tue 146, Wed 170, Thu 164, Fri 197, Sun 73) shown
- [ ] Real driver names (Alisher, Vadik) appear in routes
- [ ] Real staff names appear in Staff section (14 names from /staff/ folder)
- [ ] Switching to Sports Bar context shows a different visual and "Coming Soon" content
- [ ] WebRex has both Agent Network view and Integration Dependency Map view
- [ ] File upload area exists in OCR Intake tab and accepts PDF drop
- [ ] Finance tab still requires MSU
- [ ] No JS console errors
- [ ] File opens correctly by double-clicking in Finder (no server needed)

---

*Generated from full REX system audit · 2026-04-16 · Kato / Gold Health Systems*
