# CC_CLAUS_ORCHESTRATION_BRIEF.md
## Claus — GHS Build Orchestrator · v2.0
### Gold Health Systems · June 4, 2026
### Maintained by: Hermes

---

## What Claus Is

Claus is the system that never sleeps. He is the operational intelligence layer for Gold Health Systems — monitoring all running services, guarding the build registry, briefing Kato every morning, and making sure nothing goes silently wrong.

Claus began as a simple GOJ pipeline watchman that ran three times a day and turned RED when Gmail OAuth expired. Claus v2 expands that into the full GHS build orchestrator: six monitoring modules, a persistent state file, dynamic morning briefings drawn from the live phase documents, a PAE proposal system, and an hourly build digest.

Claus uses the **Hermes bot** (`@Hermes_Cloud_May_bot`) for all messages. He never touches the Rexxie bot (`@goldhealth_rexxie_bot`) — that is Kato's private confidant and operates on a completely separate lane.

---

## File Locations

| File | Purpose |
|------|---------|
| `~/Desktop/REX/CC_claus_orchestrator.py` | The script — Claus v2 main |
| `~/Desktop/REX/CC_claus_state.json` | Persistent state (uptime stats, last brief date, digest queue, PAE proposals) |
| `~/.hermes/claus/watchman.log` | Rolling log file |
| `~/Library/LaunchAgents/com.hermes.claus-watchman.plist` | LaunchAgent (existing, unchanged until Kato approves plist update) |

---

## How to Run Claus

```bash
# Single snapshot (same as what the plist triggers 3x daily)
python3 ~/Desktop/REX/CC_claus_orchestrator.py --telegram

# Manually trigger the morning briefing right now
python3 ~/Desktop/REX/CC_claus_orchestrator.py --brief

# Print current status to stdout (no Telegram, no token needed)
python3 ~/Desktop/REX/CC_claus_orchestrator.py --status

# Continuous monitoring loop (run manually for 24/7 coverage)
python3 ~/Desktop/REX/CC_claus_orchestrator.py --loop
```

---

## Plist Update (PAE — Awaiting Kato Approval)

The existing plist (`com.hermes.claus-watchman.plist`) currently points to:
```
/Users/mainsobhelper/.hermes/bin/claus_watchman.py
```

To switch to Claus v2, change **one line** in the plist:

**Before:**
```xml
<string>/Users/mainsobhelper/.hermes/bin/claus_watchman.py</string>
```

**After:**
```xml
<string>/Users/mainsobhelper/Desktop/REX/CC_claus_orchestrator.py</string>
```

Then reload:
```bash
launchctl unload ~/Library/LaunchAgents/com.hermes.claus-watchman.plist
launchctl load   ~/Library/LaunchAgents/com.hermes.claus-watchman.plist
```

**Backward compatibility:** The new script handles `--telegram` identically to the old watchman — runs once, alerts if RED, exits. No behavior change until you use `--loop` mode.

**For 24/7 continuous monitoring (optional future upgrade):** Change the plist's `StartCalendarInterval` to `KeepAlive + RunAtLoad` and point to `--loop`. This gives sub-60-second response to any service failure instead of the current 3x-daily window.

---

## Six Monitoring Modules

### Module 1: Service Health Monitor

Checks all 9 GHS services concurrently using asyncio + thread pool. Each check does a TCP connection probe followed by an HTTP GET, with a 5-second timeout. HTTP 4xx responses count as "alive" — a 404 means the service is running, even if the health route isn't wired.

**Services monitored:**

| Service | Port | Path |
|---------|------|------|
| Hermes Cloud GW | 3002 | /health |
| REX FastAPI | 8000 | /api/health |
| GOJ Dashboard | 8080 | / |
| Tiger Claw API | 27226 | /health |
| CC Stats API | 8001 | /health |
| Ollama | 11434 | /api/tags |
| LM Studio | 1234 | /v1/models |
| Open WebUI | 3000 | / |
| Hermie Local GW | 65001 | /v1/models |

**State tracked per service:** total checks, up count, consecutive failures, last status. Uptime percentage appears in the morning brief.

**To add a new service:** add an entry to the `SERVICES` list at the top of `CC_claus_orchestrator.py`:
```python
{
    "name":    "My New Service",
    "port":    9999,
    "path":    "/health",
    "emoji":   "🔧",
    "restart": "launchctl load ~/Library/LaunchAgents/com.myservice.plist",
},
```


### Module 2: Daily Orchestration Briefing

Sent to Kato every day at 9 AM (triggered by the 8 AM plist invocation). The brief is generated dynamically — Claus reads `CC_PHASE_STATUS.md` and `CC_MASTER_BUILD_LOG.md` at send time, so it always reflects current build state.

**Brief format:**
```
🏛️ GHS Morning Brief — [Day, Date]
══════════════════════════════════

📊 SYSTEM STATUS — N/9 services UP
✅ 🧠 Hermes Cloud GW :3002 (99.2% uptime)
✅ 🦖 REX FastAPI :8000 (100.0% uptime)
❌ 🤖 Hermie Local GW :65001 [5× down]
...

🔨 BUILD STATUS (19-phase plan)
✅ Ph1: Foundation — Local AI Setup
✅ Ph2: Rexxie Core — Private AI Id...
🔨 Ph15-CC: Command Center Phase 2
🔴 Ph13-V: ⛔ VERIFICATION SPRINT
...

📋 OPEN ITEMS
• Fix @goldhealth_rexxie_bot 401 loop → unblocks Phase 13-V
• Approve + Execute PAE-1 Gemma 4 switch
...

🔧 TODAY'S BUILD ACTIVITY
• Hermes Gateway Config Revert (~12:47 PM)
• Dock Autohide Fix (Permanent)
  CC_ files modified today: 3

📋 Pending PAEs (from CC_PHASE_STATUS.md):
  📋 PAE-1: Switch Hermie to Gemma 4 28B
  📋 PAE-2: Install hermes-dreaming Plugin

══════════════════════════════════
Claus v2 · 08:02 · Gold Health Systems
```

**Briefing schedule:** 9 AM daily (8–10 AM window). If `last_brief_date` in state matches today's date, the brief is skipped for the rest of the day even if Claus runs again.


### Module 3: Build Registry Guardian

Runs every 10 minutes. Compares all `CC_*.py` files in `~/Desktop/REX/` against the `known_cc_files` list in state. When a new file appears, Claus sends a Telegram message with a proposed `master_list.json` entry:

```json
{
  "name": "Claus Orchestrator",
  "description": "Auto-detected: CC_claus_orchestrator.py",
  "category": "auto-detected",
  "milestone": "unassigned",
  "status": "building",
  "stage_percent": 10,
  "stage_label": "New"
}
```

Kato reviews and adds manually — Claus never modifies `master_list.json` directly.

**Core file tamper detection:** Claus tracks `mtime` for four core files:
- `backend/main.py`
- `master_list.json`
- `CC_MASTER_BUILD_LOG.md`
- `CC_PHASE_STATUS.md`

If any of these change unexpectedly between checks, Claus sends a warning.


### Module 4: Agent Completion Monitor

Scans for `CC_*` files modified in the last 65 minutes. Queues them and sends an **hourly digest** instead of per-file notifications. This keeps Telegram quiet while still giving Kato visibility into what each session produced.

**Digest example:**
```
🔧 Claus Build Digest — 14:00
4 CC_ files created/modified in the last hour:

• CC_claus_orchestrator.py
• CC_CLAUS_ORCHESTRATION_BRIEF.md
• CC_gateway_auth_proxy.py
• CC_fix_telegram_conflict.command
```

Files are tracked in `digest_queue` and `digest_sent` in the state file. Once sent, they move to `digest_sent` (bounded to 200 entries) and won't re-appear in future digests.


### Module 5: PAE Escalation System

Claus can send **Propose → Approve → Execute** proposals to Kato through Telegram with inline Yes/No buttons. This is for operational decisions that need Chairman approval before any action is taken.

**Critical rule: Claus NEVER auto-executes approved commands.** When Kato presses APPROVE, Claus logs the approval and sends the commands back as copy-paste text. Kato runs them manually.

**Sending a PAE from code:**
```python
queue_pae(
    state,
    title="Restart Hermie Local Gateway",
    description="Port 65001 has been down for 3+ hours. Suggested restart sequence.",
    commands=(
        "launchctl unload ~/Library/LaunchAgents/ai.hermes.gateway.plist\n"
        "pkill -f 'hermes_cli.main.*gateway'\n"
        "sleep 8\n"
        "launchctl load ~/Library/LaunchAgents/ai.hermes.gateway.plist"
    ),
    bot_token=bot_token,
)
```

**Callback handling:** Inline button presses (callback_query) are processed only in `--loop` mode, where Claus polls `getUpdates` every 60 seconds. In snapshot mode (`--telegram`), the buttons are displayed but not acted on until the next loop invocation.

**PAE IDs:** Claus-generated proposals use the `PAE-C##` prefix (e.g., PAE-C01) to distinguish them from Hermes-proposed PAEs (`PAE-1`, `PAE-2`, `PAE-3`) that live in `CC_PHASE_STATUS.md`.

**Viewing pending PAEs:**
```bash
python3 ~/Desktop/REX/CC_claus_orchestrator.py --status
```


### Module 6: GOJ Pipeline Monitor

Preserves and extends the original Claus watchman behavior. Runs on every snapshot invocation, rate-limited to one alert per hour to avoid spam.

**Checks:**

1. **Pipeline data freshness** — scans `~/.hermes-cloud/home/goj-pipeline/data/` for JSON/TXT files older than 26 hours. Stale files mean the daily automation hasn't run or Gmail OAuth has expired.

2. **7:30 AM morning report** — between 8 AM and 1 PM, checks for a morning report file modified today. Alerts if missing.

3. **Attendance anomaly detection** — queries `auth_tracker.db` for today's `PRESENT` count. Alerts if:
   - Count > 500: data error (GOJ has ~425 clients max)
   - Count < 50 on a weekday: pipeline failure or data not written yet

4. **Gmail OAuth token** — checks `~/.rex_google_token.json` exists and hasn't expired. If missing or expired: `python backend/rex_gmail.py --setup`. This is the original "turns RED" trigger from Claus v1.

---

## Alert Escalation Matrix

| Level | Trigger | What Claus sends | Response |
|-------|---------|-----------------|----------|
| **INFO** | Normal operation | Nothing (quiet days stay quiet) | — |
| **WARNING** | Service down for the first time | ⚠️ service name, port, error, restart command | Investigate |
| **URGENT** | 3+ consecutive failures | 🚨 URGENT with restart command | Restart immediately |
| **CRITICAL** | GOJ pipeline stale + Gmail expired together | 🏥 GOJ Pipeline Alert with remediation steps | Re-auth Gmail token |
| **TAMPER** | Core file unexpectedly modified | ⚠️ filename + timestamp | Verify intentional |

Claus sends a **WARNING** on the first failure and escalates to **URGENT** after 3 consecutive failures of the same service. This avoids false alarms from transient restarts while catching genuine outages quickly.

---

## State File Reference

`~/Desktop/REX/CC_claus_state.json` is a plain JSON file. Claus reads it on every invocation and writes it back before exiting. You can inspect or edit it manually.

Key fields:

```json
{
  "service_stats": {
    "Hermes Cloud GW": {
      "up": 42, "total": 45,
      "consecutive_fail": 0, "last_up": true
    }
  },
  "last_brief_date":     "2026-06-04",
  "last_registry_check": "2026-06-04T14:02:11",
  "last_digest_ts":      "2026-06-04T14:00:00",
  "known_cc_files":      ["CC_claus_orchestrator.py", "..."],
  "digest_queue":        [],
  "digest_sent":         ["CC_gateway_watchdog.py", "..."],
  "pae_queue":           [
    {
      "id": "PAE-C01",
      "title": "Restart Hermie Local Gateway",
      "status": "pending",
      "sent_ts": "2026-06-04T08:02:00"
    }
  ],
  "core_file_mtimes":    {"main.py": 1748990400.0, "...": "..."},
  "tg_update_offset":    0
}
```

To reset uptime stats for a single service (e.g., after an intentional rebuild):
```bash
python3 -c "
import json; p = open('$HOME/Desktop/REX/CC_claus_state.json')
s = json.load(p); p.close()
s['service_stats'].pop('Hermie Local GW', None)
open('$HOME/Desktop/REX/CC_claus_state.json','w').write(json.dumps(s, indent=2))
"
```

---

## Integration Points

| Agent / System | How Claus integrates |
|----------------|----------------------|
| **Hermes** | Receives morning brief and all alerts via Telegram |
| **rex_coordinator.py** | Claus reads `master_list.json` that rex_coordinator manages |
| **goj_daily_scheduler.py** | Claus monitors the output files that the scheduler produces |
| **CC_gateway_watchdog.py** | Watchdog handles auto-restarts for Hermes GW; Claus monitors all other services |
| **CC_PHASE_STATUS.md** | Claus parses this at brief-time for dynamic phase summary |
| **CC_MASTER_BUILD_LOG.md** | Claus parses TODAY'S CHANGES section for the build activity block |
| **auth_tracker.db** | Claus queries for attendance anomaly detection (read-only, no writes) |

---

## Adding New Monitoring Targets

**New service (HTTP endpoint):** Add an entry to the `SERVICES` list in `CC_claus_orchestrator.py`:
```python
{
    "name":    "My Service",
    "port":    PORT,
    "path":    "/health",
    "emoji":   "EMOJI",
    "restart": "launchctl load ~/Library/LaunchAgents/com.myservice.plist",
},
```

**New file staleness check:** Add a path to the `_check_pipeline_files()` logic in Module 6.

**New PAE type:** Call `queue_pae(state, title, description, commands, bot_token)` from anywhere in the script.

**New core file to watch for tampering:** Add a `Path` to the `_CORE_FILES` list in Module 3.

---

## Known Limitations (v2.0)

- PAE button callbacks only work in `--loop` mode. In `--telegram` mode (plist default), buttons are cosmetic.
- The `--loop` mode isn't yet managed by a plist with `KeepAlive`. Run it manually in a terminal session if you want continuous < 60-second response time.
- Attendance check requires the `attendance` table in `auth_tracker.db`. If the schema differs (e.g., column names change), the check silently skips and logs a debug message.
- LM Studio on port 1234 may appear DOWN when the app is open but the server isn't started. That's a cosmetic false negative — Claus can't distinguish "LM Studio not open" from "LM Studio open but server off."

---

## Derivation

```
CLAUDE.md (governs all agents)
    ↓
CC_claus_orchestrator.py   ← The script
CC_claus_state.json        ← Live state
CC_CLAUS_ORCHESTRATION_BRIEF.md  ← This document
    ↓
com.hermes.claus-watchman.plist  ← LaunchAgent (plist update PAE pending)
```

---

*Claus v2 · Gold Health Systems · June 4, 2026*
*Maintained by: Hermes*
