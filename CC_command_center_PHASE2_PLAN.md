# GHS Command Center — Phase 2 Plan
**Gold Health Systems · Hermes-built · June 2026**

---

## Phase 1 Delivered (Complete)

The Phase 1 web app at `~/Desktop/REX/CC_command_center.html` contains:

- Sacred geometry screensaver via Three.js (Flower of Life + Metatron's Cube, 19 circles, additive blending glow, star field, breathing animation, color cycling purple–teal–cyan)
- PIN unlock system with SHA-256 hash in localStorage, default 1234, keyboard + numpad support
- Synapse visualization — 10 skill nodes (Canvas 2D, bezier connections, particle flow, glow halos, click for skill info)
- Hermes Center — WebSocket to ws://localhost:3002/ws, HTTP POST fallback, typing indicator, message history, auto-reconnect
- Weather widget — wttr.in JSON API, Brooklyn NY, current conditions + 3-day forecast, no API key needed
- Tiger Claw panel — large Orbitron clock, alarm management with localStorage, Web Speech API alerts
- Widget Center — system health (3002/8000/8080), GOJ bot status, calendar day view, bills placeholder, compound center
- Top bar — live clock, service health dots with real ping, weather badge
- Taskbar — 7 app shortcuts (Dashboard, Gmail, Calendar, WebUI, Tiger Claw, Hermes, Home)
- Voice — Rex (male) and Rexxie (female) toggles via Web Speech API
- Auto-dim at 3 min, screensaver at 5 min, activity resets on any input

---

## Phase 2 Priorities

### P2-A: Electron Wrapper (OS-Level Screensaver)

**Why:** Browser tab can't be a true OS screensaver. Electron gives native window control.

**What to build:**
- `electron-main.js` — BrowserWindow in fullscreen, frameless, always-on-top
- `electron-preload.js` — bridge for system APIs (power save blocker, system idle time via `powerMonitor.getSystemIdleTime()`)
- Replace JS inactivity timer with `powerMonitor.on('user-did-resign-active')` for true OS-level screensaver trigger
- Register as Login Item via `app.setLoginItemSettings()`
- Build `.dmg` installer via `electron-builder`
- Add tray icon: right-click → Open, Lock, Quit

**Files to add:**
```
~/Desktop/REX/CC_electron/
  package.json
  electron-main.js
  electron-preload.js
  electron-builder.config.js
```

### P2-B: Real Bill Tracking Integration

**Why:** Kato needs a native bills/finance view without switching apps.

**Options to evaluate:**
1. **Plaid API** — read-only bank/credit card transaction feed (requires OAuth, needs PII caution)
2. **Manual CSV import** — Kato pastes statement CSVs, parsed by the app
3. **Local bills.json** — structured bill registry with due dates, amounts, paid status

**Recommended start:** bills.json + manual entry (privacy-first, no cloud PII). Expand to Plaid in Phase 3.

**Widget to build:**
- Bills list with category, due date, amount, status (Paid / Due / Overdue)
- Monthly total due vs. paid summary
- Color-coded: green = paid, gold = due soon, red = overdue
- Quick-add form
- Data stored in `~/Desktop/REX/bills.json` (local, not in cloud)

### P2-C: Voice App Integration (Replace Web Speech API)

**Why:** Web Speech API is browser-dependent and low quality. Rex/Rexxie deserve better voices.

**Options:**
1. **ElevenLabs** — premium, cloned voices. Requires API key, cloud call. Gate behind `akc_tokenizer.py` Gate 1 if sending any PII.
2. **Piper TTS** — local, fast, good quality. Can run on Mac Mini M4. No cloud.
3. **Coqui TTS** — local, high quality. Heavier compute.
4. **Hermes TTS endpoint** — route through REX `/api/tts` which handles voice selection and queues locally.

**Recommended:** Piper TTS local model, wired through REX API. Hermes calls `/api/tts?voice=rex&text=...` and returns audio blob.

### P2-D: Live Skill Execution Visualization via Hermes WebSocket Events

**Why:** The synapse visualization should react to actual Hermes events, not guesses.

**What to build:**
- Hermes gateway emits structured WebSocket events: `{ type: "skill_activated", skill: "ocr", task_id: "..." }`
- Command center receives these and maps `skill` → synapse node ID
- Node lights up gold for duration of skill execution, dims to active-cyan when complete
- Connection particles travel faster during active execution
- Task completion sends `{ type: "skill_complete", skill: "ocr", duration_ms: 1234 }`
- Side panel shows last 5 skill executions with timing

**Hermes gateway change:** Add event emitter to `hermes-agent/src/` that broadcasts structured events on the WS connection alongside normal chat responses.

### P2-E: Tiger Claw — Full TTS + Hermes Integration

**Current:** Web Speech API announcement only.
**Phase 2:**
- Tiger Claw sends alarm trigger to REX `/api/notify` → REX uses Piper TTS for announcement
- Alarm tones: pick from local `.wav` files (or generate via Tone.js in-browser)
- Recurring alarms (daily, weekday, weekly)
- Alarm history log in `~/Desktop/REX/logs/alarms.log`
- GOJ automation schedule displayed read-only (7:30 AM, 10:30 AM, 3:15 PM, etc.) — these fire via n8n but are shown in Tiger Claw for visibility

### P2-F: Google Calendar Sync

**Why:** Calendar widget is a placeholder today.

**What to build:**
- OAuth2 flow for Google Calendar (shares token with Gmail/Drive: `~/.rex_google_token.json`)
- REX endpoint: `GET /api/calendar/today` → returns today's events
- REX endpoint: `GET /api/calendar/upcoming?days=7` → next 7 days
- Command center polls every 5 min
- Events displayed in Calendar widget with time, title, color-coded by calendar
- Clicking event shows details popover
- "Add event" quick-entry form (text → Hermes parses → creates via Calendar API)

### P2-G: Obsidian Plugin / Vault Integration

**Why:** Kato uses Obsidian for notes. Command center should surface relevant notes.

**What to build:**
- REX watches `~/Desktop/REX/` or vault folder for `.md` file changes
- "Recent notes" widget: last 5 modified, click to open in Obsidian
- Search box in widget → searches vault content → returns matches
- Hermes can write notes to vault (`[[YYYY-MM-DD]] note content`)
- Use Obsidian URI protocol: `obsidian://open?vault=REX&file=filename`

### P2-H: Bills — Full Integration (Phase 3 scope)

Full Plaid integration with transaction categorization, monthly spend analysis, bill reminders, budget tracking. Scope to Phase 3 after Gate 1 (akc_tokenizer.py) is complete.

---

## Architecture Notes for Phase 2

**Data flows that must remain local:**
- `auth_tracker.db` — no cloud sync, ever (Gate 1 rule)
- `rexxie.db` — local only, private lane
- `bills.json` — local only
- Any patient names, SSNs, DOBs from GOJ — Presidio de-id before any cloud call

**New files (following CC_ prefix rule):**
```
~/Desktop/REX/
  CC_command_center_electron/     — Electron wrapper
  CC_bills.json                   — Bill registry
  CC_alarm_history.log            — Tiger Claw alarm log
  CC_calendar_cache.json          — Cached calendar events
```

**REX API endpoints to add:**
```
GET  /api/calendar/today
GET  /api/calendar/upcoming
GET  /api/notes/recent
POST /api/notes/create
GET  /api/bills
POST /api/bills
POST /api/tts
POST /api/notify
```

---

## Phase 2 Execution Order

1. P2-B (Bills JSON) — quickest win, no external deps, very useful
2. P2-F (Calendar Sync) — token already exists, moderate effort
3. P2-C (TTS) — replace Web Speech API with Piper local model
4. P2-D (Live Skill Events) — requires Hermes gateway change
5. P2-E (Tiger Claw full) — depends on P2-C
6. P2-A (Electron wrapper) — larger scope, do last
7. P2-G (Obsidian) — nice-to-have, when vault structure is settled

---

*Maintained by Hermes · Gold Health Systems*
*Source of truth: ~/Desktop/Gold_Health_Systems/BRAIN/MASTER.md*
