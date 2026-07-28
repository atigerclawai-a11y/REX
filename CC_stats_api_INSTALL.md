# CC Stats API — Install Guide
**GHS Command Center Stats API · Port 8001 · Built 2026-06-04**

---

## What This Is

A lightweight FastAPI service that exposes live GOJ operations data to the
Gold Health Systems Command Center dashboard. Runs on port 8001 (separate
from the main REX backend on port 8000). Localhost-only. No auth tokens
required — Desktop Mode applies.

**Files created:**
- `~/Desktop/REX/CC_stats_api.py` — the API
- `~/Desktop/REX/com.ghs.cc-stats-api.plist` — LaunchAgent (not installed yet)
- `~/Desktop/REX/CC_clock_records.json` — clock-in/out store
- `~/Desktop/REX/CC_stats_api_INSTALL.md` — this file

---

## Prerequisites

FastAPI and uvicorn must be available in `.rex-venv`. Test first:

```bash
source ~/.rex-venv/bin/activate
python -c "import fastapi, uvicorn; print('OK')"
```

If missing:
```bash
source ~/.rex-venv/bin/activate
pip install fastapi uvicorn
```

---

## Quick Start (Manual / Dev)

```bash
source ~/.rex-venv/bin/activate
cd ~/Desktop/REX
python CC_stats_api.py
```

Or via uvicorn directly:
```bash
source ~/.rex-venv/bin/activate
uvicorn CC_stats_api:app --host 127.0.0.1 --port 8001 --reload
```

Confirm it's running:
```bash
curl -s http://localhost:8001/health | python3 -m json.tool
```

---

## Install as LaunchAgent (Persistent / Auto-start)

> **Do not install until you've tested the manual start above.**

### Step 1 — Ensure logs directory exists
```bash
mkdir -p ~/Desktop/REX/logs
```

### Step 2 — Copy plist to LaunchAgents
```bash
cp ~/Desktop/REX/com.ghs.cc-stats-api.plist \
   ~/Library/LaunchAgents/com.ghs.cc-stats-api.plist
```

### Step 3 — Load it
```bash
launchctl load ~/Library/LaunchAgents/com.ghs.cc-stats-api.plist
```

### Step 4 — Confirm running
```bash
launchctl list | grep cc-stats
curl -s http://localhost:8001/health
```

### To restart:
```bash
launchctl unload ~/Library/LaunchAgents/com.ghs.cc-stats-api.plist
sleep 3
launchctl load  ~/Library/LaunchAgents/com.ghs.cc-stats-api.plist
```

### To stop permanently:
```bash
launchctl unload ~/Library/LaunchAgents/com.ghs.cc-stats-api.plist
rm ~/Library/LaunchAgents/com.ghs.cc-stats-api.plist
```

### Log tails:
```bash
tail -f ~/Desktop/REX/logs/cc-stats-api.log
tail -f ~/Desktop/REX/logs/cc-stats-api-err.log
```

---

## Endpoint Reference

All endpoints are GET unless noted. Base URL: `http://localhost:8001`

### `GET /health`
Basic health check. Returns DB availability status.
```json
{
  "status": "ok",
  "service": "cc-stats-api",
  "port": 8001,
  "db_available": true,
  "timestamp": "2026-06-04T10:00:00"
}
```

---

### `GET /api/snapshot`
**Recommended for the command center widget.** Single call returns all key
metrics — clients, today's attendance, clock-in status, pipeline health.
```bash
curl -s http://localhost:8001/api/snapshot | python3 -m json.tool
```

---

### `GET /api/stats/clients`
Client authorization breakdown.
- `total_clients` — all rows in `clients` table
- `active_clients` — where `active = 1`
- `auth_breakdown` — count per auth status (ACTIVE / EXPIRED / PENDING RENEWAL)
- `expiring_soon_30d` — active auths expiring within 30 days
- `expired_count` — expired authorization count
- `pending_renewal_count` — pending renewal count

```bash
curl -s http://localhost:8001/api/stats/clients | python3 -m json.tool
```

---

### `GET /api/stats/attendance?days_back=7`
Today's attendance + 7-day trend.
- `today_scheduled` — clients on the log today (any status)
- `today_confirmed` — clients marked present/attended/confirmed
- `trend` — array of `{date, scheduled, confirmed}` for last N days

```bash
curl -s "http://localhost:8001/api/stats/attendance?days_back=14" | python3 -m json.tool
```

---

### `GET /api/stats/roster`
Today's roster by shift.
- Primary source: `attendance_log` for today's date
- Fallback: `clients.day_X_actual` schedule (if no log entries yet)
- Returns shift-grouped client names with status

```bash
curl -s http://localhost:8001/api/stats/roster | python3 -m json.tool
```

---

### `GET /api/stats/expiring?days=30`
Clients with authorizations expiring within N days, sorted most urgent first.
- `expiring` — array of `{client_name, expiration_date, status, days_remaining}`
- `count` — total matching

```bash
curl -s "http://localhost:8001/api/stats/expiring?days=14" | python3 -m json.tool
```

---

### `GET /api/stats/employees`
Employee list from `auth_tracker.db` (if `employees` table exists).
Note: as of June 2026, staff compliance data lives in
`GOJ_Staff_Compliance_Apr2026.xlsx` — the DB employees table may be sparse.

```bash
curl -s http://localhost:8001/api/stats/employees | python3 -m json.tool
```

---

### `GET /api/clockin/status`
Who is currently clocked in today, plus full today's log.
```json
{
  "date": "2026-06-04",
  "clocked_in": [{"employee": "Maria", "clocked_in_since": "08:32:10"}],
  "count_in": 1,
  "today_log": [...]
}
```

### `POST /api/clockin/{employee_name}`
Record a clock-in.
```bash
curl -s -X POST http://localhost:8001/api/clockin/Maria | python3 -m json.tool
```

### `POST /api/clockout/{employee_name}`
Record a clock-out.
```bash
curl -s -X POST http://localhost:8001/api/clockout/Maria | python3 -m json.tool
```

### `GET /api/clockin/history?days_back=7`
Clock records for the last N days.

Clock data is stored in `~/Desktop/REX/CC_clock_records.json`.

---

### `GET /api/goj/pipeline`
Status of GOJ pipeline data files in `~/.hermes-cloud/home/goj-pipeline/data/`.
Flags any file not updated in >25 hours as `stale: true`.

```bash
curl -s http://localhost:8001/api/goj/pipeline | python3 -m json.tool
```

---

### `GET /api/files/recent`
Recently modified files in `~/Desktop/REX/` (py, command, json, md, plist).
Useful for the command center to show recent build/script activity.

```bash
curl -s http://localhost:8001/api/files/recent | python3 -m json.tool
```

---

## Database Tables Used

| Table | Used By | Notes |
|-------|---------|-------|
| `clients` | `/api/stats/clients`, `/api/stats/roster` | `active`, `day_X_actual`, `shift`, `name` |
| `auth_documents` | `/api/stats/clients`, `/api/stats/expiring` | `expiration_date`, `status`, `client_name` |
| `authorization` | `/api/stats/clients` (fallback) | `service_end_date`, `status` |
| `attendance_log` | `/api/stats/attendance`, `/api/stats/roster` | `log_date`, `shift`, `client_name`, `status` |
| `employees` | `/api/stats/employees` | Optional — may not exist |

All access is **read-only**. Clock records never touch `auth_tracker.db`.

---

## Security Notes

- Binds to `127.0.0.1` only — not reachable from the network
- No auth tokens required (Desktop Mode: localhost = chairman)
- `auth_tracker.db` is never read from cloud context
- PHI never leaves this machine via this service
- CORS is wide-open (`*`) because network binding is the access control

---

## Phase 2 Plans

- Add `clock_records` table to `auth_tracker.db` (soft-delete safe, encrypted)
- Add `GET /api/stats/menus` — menu submission rates for current week
- Add `GET /api/stats/schedule-changes` — pending schedule change queue
- Wire `/api/snapshot` into the Command Center frontend auto-refresh (60s interval)
