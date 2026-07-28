# CC_OBSIDIAN_DASHBOARD_GUIDE.md
## GHS Obsidian Live Dashboard — Setup & Usage
### Gold Health Systems · June 2026

---

## What This Is

The GHS Obsidian Live Dashboard turns your BRAIN vault into a real-time operational display.
A Python daemon (`CC_obsidian_live_daemon.py`) runs every 5 minutes and overwrites 5 markdown
files in `~/Desktop/Gold_Health_Systems/BRAIN/GHS Live/`. Open `GHS_DASHBOARD.canvas` in
Obsidian and you get a live, auto-refreshing command center.

---

## Quick Start

### 1 — Run manually (test it)

```bash
source ~/debate-chamber/.venv/bin/activate
cd ~/Desktop/REX
python CC_obsidian_live_daemon.py --once
```

You should see output like:
```
[2026-06-04 09:15:32] ── Daemon run starting ─────────── 2026-06-04 09:15:32
[2026-06-04 09:15:32] Checking service health...
[2026-06-04 09:15:34]   5/7 services UP
...
[2026-06-04 09:15:36] ✅ All 5 files written to ~/Desktop/Gold_Health_Systems/BRAIN/GHS Live/
```

### 2 — Open the canvas in Obsidian

1. Open Obsidian
2. Set vault to `~/Desktop/Gold_Health_Systems/BRAIN/` (if not already)
3. In the file explorer, navigate to **GHS Live** → open `GHS_DASHBOARD.canvas`
4. You'll see a 2×2 grid of live panels + the running log

### 3 — Enable auto-refresh in Obsidian

Obsidian doesn't auto-reload open files by default. Solutions:

**Option A — Community plugin: "Auto Refresh"**
Install it from Settings → Community Plugins → search "Auto Refresh" or "File Refresh".
Set refresh interval to 60 seconds.

**Option B — Close and reopen canvas periodically**
Hit `Ctrl+W` then reopen. The canvas always reads the current file on open.

**Option C — Live Preview mode**
The canvas nodes use `type: "file"` — they render the live file contents each time
the canvas is opened or refreshed.

---

## Install the LaunchAgent (for automatic 5-min runs)

The plist is at `~/Desktop/REX/com.ghs.obsidian-daemon.plist`. It is **not installed by default** —
Kato must approve.

```bash
# Install
cp ~/Desktop/REX/com.ghs.obsidian-daemon.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.ghs.obsidian-daemon.plist

# Verify it loaded
launchctl list | grep obsidian
# → you should see com.ghs.obsidian-daemon with PID 0 (waiting) or a PID (running)

# Check logs
tail -f ~/Desktop/REX/logs/obsidian_daemon.log

# Stop
launchctl unload ~/Library/LaunchAgents/com.ghs.obsidian-daemon.plist

# Check status
python ~/Desktop/REX/CC_obsidian_live_daemon.py --status
```

**Note:** The plist uses `--once` with `StartInterval 300`. This means launchd calls the script
every 5 minutes, the script runs one pass and exits cleanly. This is more reliable than the
script's internal `--daemon` loop.

---

## What Each Panel Shows

### SYSTEM_STATUS.md
Live port-check table for all 7 GHS services. Uptime is tracked from when each service
was last seen coming back up. Also shows the last 8 alert lines from watchdog.log / claus.log.

### GOJ_TODAY.md
Snapshot from `auth_tracker.db`:
- Authorization counts (Active / Expiring30 / Pending / Expired)
- List of clients whose authorization expires in the next 30 days
- Today's attendance (if the attendance table has today's data)

> Requires auth_tracker.db to be at `~/Documents/goj files/dashboard/auth_tracker.db` or
> `~/Desktop/REX/auth_tracker.db` (falls back to whichever exists).

### BUILD_STATUS.md
Progress bar and phase count extracted from `CC_PHASE_STATUS.md`.
Shows the active phase, known blockers, and every file modified today in `~/Desktop/REX/`.

### ALERTS.md
Two-tier alert board:
- 🔴 **URGENT** — security issues, downed services, broken data (requires Kato action)
- 🟡 **ATTENTION** — known open items, things to schedule
- 🟢 **Standing Good** — confirmed healthy systems

### TODAY_LOG.md (right panel / running log)
Append-only. Each 5-minute run prepends an entry showing: which services changed state,
new files built, auth snapshot. Oldest entries scroll down — it's a full audit trail of
the day.

---

## Pin GHS_DASHBOARD.canvas as the Obsidian Startup File

1. Settings → Options → **Files & Links**
2. Set **Default new note location** to `GHS Live`
3. Settings → **Appearance** → scroll to **Show inline title** — enable for clean look

For startup: install the **Obsidian Homepage** community plugin, set homepage to
`GHS Live/GHS_DASHBOARD` (no extension). Every time Obsidian opens, the canvas loads.

---

## Adding New Data Sources

The daemon is modular. To add a new data source:

**1 — Add a new query function** (follow the `query_goj_data()` pattern):
```python
def query_bbg_pos() -> dict:
    """Query Boardwalk Beer Garden POS data."""
    # ...read from wherever BBG data lives
    return {"total_sales": 0, "covers": 0, "error": None}
```

**2 — Add a new writer function** (follow the `write_goj_today()` pattern):
```python
def write_bbg_today(bbg: dict, ts: str):
    content = f"""..."""
    atomic_write(LIVE_DIR / "BBG_TODAY.md", content)
```

**3 — Call both from `run_once()`**:
```python
bbg = query_bbg_pos()
write_bbg_today(bbg, ts)
```

**4 — Add a node to GHS_DASHBOARD.canvas**:
```json
{
  "id": "bbg_today",
  "type": "file",
  "file": "GHS Live/BBG_TODAY.md",
  "x": 500, "y": 150, "width": 400, "height": 300
}
```

---

## Dataview Plugin Queries

If you have the **Dataview** community plugin installed, you can add dynamic queries
directly inside your markdown files. Add this block to `GOJ_TODAY.md`:

````markdown
```dataview
TABLE authorization_status, service_end_date AS "Expires"
FROM ""
WHERE file.name = "GOJ_TODAY"
```
````

For a more useful cross-file count (requires structured frontmatter in your client notes):
````markdown
```dataview
LIST
FROM "GHS Live"
WHERE contains(tags, "live")
SORT file.mtime DESC
```
````

> Note: Dataview works on Obsidian note files within the vault. For live DB data, the daemon's
> direct SQLite queries are faster and more reliable.

---

## Troubleshooting

**Files aren't updating**
- Check if the daemon is running: `launchctl list | grep obsidian`
- Run manually: `python ~/Desktop/REX/CC_obsidian_live_daemon.py --once`
- Check logs: `tail -40 ~/Desktop/REX/logs/obsidian_daemon.log`

**GOJ_TODAY.md shows no data**
- The daemon couldn't find or query auth_tracker.db
- Confirm: `ls ~/Documents/goj\ files/dashboard/auth_tracker.db`
- Check error line at top of GOJ_TODAY.md

**Canvas nodes show "File not found"**
- Obsidian vault must be set to `~/Desktop/Gold_Health_Systems/BRAIN/`
- The canvas uses vault-relative paths like `GHS Live/SYSTEM_STATUS.md`

**Daemon crashes on startup**
- Confirm venv: `source ~/debate-chamber/.venv/bin/activate && python --version`
- Confirm script path: `ls ~/Desktop/REX/CC_obsidian_live_daemon.py`

---

## File Index

| File | Location | Purpose |
|------|----------|---------|
| `CC_obsidian_live_daemon.py` | `~/Desktop/REX/` | The daemon script |
| `com.ghs.obsidian-daemon.plist` | `~/Desktop/REX/` | LaunchAgent (not installed) |
| `CC_OBSIDIAN_DASHBOARD_GUIDE.md` | `~/Desktop/REX/` | This file |
| `GHS_DASHBOARD.canvas` | `BRAIN/GHS Live/` | Obsidian canvas layout |
| `SYSTEM_STATUS.md` | `BRAIN/GHS Live/` | Live service health |
| `GOJ_TODAY.md` | `BRAIN/GHS Live/` | Live GOJ operations |
| `BUILD_STATUS.md` | `BRAIN/GHS Live/` | Live build phase tracker |
| `ALERTS.md` | `BRAIN/GHS Live/` | Live alert board |
| `TODAY_LOG.md` | `BRAIN/GHS Live/` | Append-only daily log |
| `.obsidian_daemon_state.json` | `~/Desktop/REX/logs/` | Uptime + run-count state |
| `obsidian_daemon.log` | `~/Desktop/REX/logs/` | Daemon run log |

---

*Built by Hermes (Claude) for Gold Health Systems · June 2026*
