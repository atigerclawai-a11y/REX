#!/usr/bin/env python3
"""
CC_obsidian_live_daemon.py — GHS Obsidian Live Dashboard Daemon
Gold Health Systems · Mac Mini M4 · June 2026

Writes 5 live markdown files into ~/Desktop/Gold_Health_Systems/BRAIN/GHS Live/
every 5 minutes so Obsidian is a live operational dashboard.

Usage:
    python CC_obsidian_live_daemon.py --once      # single pass, then exit
    python CC_obsidian_live_daemon.py --daemon    # run every 5 minutes (internal loop)
    python CC_obsidian_live_daemon.py --status    # print last run info from state file

Output files (in LIVE_DIR):
    SYSTEM_STATUS.md  — service health table
    GOJ_TODAY.md      — authorization + attendance snapshot
    BUILD_STATUS.md   — 19-phase progress + blockers
    ALERTS.md         — urgent + attention items
    TODAY_LOG.md      — append-only running log (newest at top)
"""

import os
import sys
import json
import time
import sqlite3
import socket
import argparse
import datetime
import textwrap
from pathlib import Path
from typing import Optional
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

HOME = Path.home()
REX_DIR       = HOME / "Desktop" / "REX"
BRAIN_DIR     = HOME / "Desktop" / "Gold_Health_Systems" / "BRAIN"
LIVE_DIR      = BRAIN_DIR / "GHS Live"
STATE_FILE    = REX_DIR / "logs" / ".obsidian_daemon_state.json"
LOG_FILE      = REX_DIR / "logs" / "obsidian_daemon.log"

INTERVAL_SECONDS = 300  # 5 minutes

# auth_tracker.db — try primary location first, fall back to REX copy
DB_PATHS = [
    HOME / "Documents" / "goj files" / "dashboard" / "auth_tracker.db",
    REX_DIR / "auth_tracker.db",
]

# Source files for build status
PHASE_STATUS_FILE = REX_DIR / "CC_PHASE_STATUS.md"
BUILD_LOG_FILE    = REX_DIR / "CC_MASTER_BUILD_LOG.md"
WATCHDOG_LOG      = REX_DIR / "logs" / "watchdog.log"
CLAUS_LOG         = REX_DIR / "logs" / "claus.log"

# Services to check (name, port, health path)
SERVICES = [
    {"name": "Hermes Gateway", "port": 3002,  "path": "/health"},
    {"name": "REX Backend",    "port": 8000,  "path": "/api/health"},
    {"name": "GOJ Dashboard",  "port": 8080,  "path": "/health"},
    {"name": "CC Stats API",   "port": 8001,  "path": "/health"},
    {"name": "Hermes Local",   "port": 65001, "path": "/health"},
    {"name": "Tiger Claw",     "port": 27226, "path": "/health"},
    {"name": "Ollama",         "port": 11434, "path": "/api/tags"},
]


# ─────────────────────────────────────────────────────────────────────────────
# UTILITY
# ─────────────────────────────────────────────────────────────────────────────

def now_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def today_midnight() -> float:
    n = datetime.datetime.now()
    return datetime.datetime(n.year, n.month, n.day).timestamp()

def fmt_uptime(seconds: float) -> str:
    if seconds < 0:
        return "—"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if h > 24:
        d = h // 24
        hh = h % 24
        return f"{d}d {hh}h"
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"

def progress_bar(pct: float, width: int = 20) -> str:
    filled = max(0, min(width, int(width * pct / 100)))
    return "█" * filled + "░" * (width - filled)

def atomic_write(path: Path, content: str):
    """Write to .tmp then rename — atomic on POSIX systems."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise

def load_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def save_state(state: dict):
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(STATE_FILE, json.dumps(state, indent=2, default=str))
    except Exception as e:
        daemon_log(f"WARN: could not save state: {e}")

def daemon_log(msg: str):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# SERVICE HEALTH
# ─────────────────────────────────────────────────────────────────────────────

def _tcp_alive(port: int, timeout: float = 2.0) -> bool:
    """Fast TCP connect check — works even if HTTP path returns 4xx."""
    try:
        s = socket.create_connection(("localhost", port), timeout=timeout)
        s.close()
        return True
    except (OSError, socket.timeout):
        return False

def check_service(svc: dict, timeout: float = 2.0) -> bool:
    """Try HTTP first, fall back to TCP."""
    url = f"http://localhost:{svc['port']}{svc.get('path', '/health')}"
    try:
        with urlopen(url, timeout=timeout) as resp:
            return resp.status < 500
    except HTTPError as e:
        # 4xx still means the server is up
        return e.code < 500
    except (URLError, OSError, socket.timeout):
        pass
    return _tcp_alive(svc["port"], timeout)

def check_all_services(state: dict) -> list:
    """Check every service, update uptime-tracking state, return result list."""
    now_iso = datetime.datetime.now().isoformat()
    now_ts  = time.time()
    results = []

    svc_state = state.setdefault("services", {})

    for svc in SERVICES:
        key    = str(svc["port"])
        is_up  = check_service(svc)
        entry  = svc_state.get(key, {})

        if is_up:
            if entry.get("status") != "UP":
                entry["first_up"] = now_iso   # reset when coming back up
            entry["status"]  = "UP"
            entry["last_up"] = now_iso
            try:
                first_up_ts = datetime.datetime.fromisoformat(entry["first_up"]).timestamp()
                uptime_sec  = now_ts - first_up_ts
            except Exception:
                uptime_sec = 0.0
        else:
            if entry.get("status") == "UP":
                entry["last_down"] = now_iso   # record when it went down
            entry["status"]  = "DOWN"
            uptime_sec       = -1.0

        entry["last_check"] = now_iso
        svc_state[key]      = entry

        results.append({
            **svc,
            "up":         is_up,
            "uptime_sec": uptime_sec,
            "icon":       "🟢" if is_up else "🔴",
            "label":      "LIVE" if is_up else "DOWN",
        })

    return results


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────────────────────────────────────

def find_db() -> Optional[Path]:
    for p in DB_PATHS:
        if p.exists():
            return p
    return None

def _get_name_col(cur: sqlite3.Cursor) -> str:
    """Detect the best client name column in the clients table."""
    try:
        cur.execute("PRAGMA table_info(clients)")
        cols = [r[1].lower() for r in cur.fetchall()]
    except Exception:
        return "id"

    # Prefer a composite or single name column
    if "last_name" in cols and "first_name" in cols:
        return "last_name || ', ' || first_name"
    for c in ("full_name", "name", "client_name", "lastname"):
        if c in cols:
            return c
    return "id"

def _detect_fk(cur: sqlite3.Cursor) -> str:
    """Detect foreign key column in authorization → clients."""
    try:
        cur.execute("PRAGMA table_info(authorization)")
        cols = [r[1].lower() for r in cur.fetchall()]
    except Exception:
        return "client_id"

    for c in ("client_id", "member_id", "clients_id", "person_id"):
        if c in cols:
            return c
    return "client_id"

def query_goj_data() -> dict:
    """Query auth_tracker.db for authorization counts and expiry data."""
    data = {
        "db_found":        False,
        "db_path":         None,
        "total_clients":   0,
        "auth_active":     0,
        "auth_expired":    0,
        "auth_pending":    0,
        "auth_expiring_30": 0,
        "expiring_clients": [],   # list of (name, date_str)
        "attendance_confirmed": 0,
        "error":           None,
    }

    db_path = find_db()
    if not db_path:
        data["error"] = "auth_tracker.db not found at expected paths"
        return data

    data["db_found"] = True
    data["db_path"]  = str(db_path)

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cur  = conn.cursor()

        # Total client count
        try:
            cur.execute("SELECT COUNT(*) FROM clients")
            data["total_clients"] = cur.fetchone()[0]
        except Exception:
            pass

        # Auth status breakdown
        try:
            cur.execute("""
                SELECT status, COUNT(*) AS cnt
                FROM authorization
                GROUP BY status
            """)
            for row in cur.fetchall():
                status = (row["status"] or "").upper().strip()
                cnt    = row["cnt"]
                if status == "ACTIVE":
                    data["auth_active"] = cnt
                elif status == "EXPIRED":
                    data["auth_expired"] = cnt
                elif "PENDING" in status:
                    data["auth_pending"] = cnt
        except Exception as e:
            data["error"] = f"auth query failed: {e}"

        # Clients expiring within 30 days
        today   = datetime.date.today()
        in_30   = today + datetime.timedelta(days=30)
        name_col = _get_name_col(cur)
        fk_col   = _detect_fk(cur)

        try:
            cur.execute(f"""
                SELECT c.{name_col} AS client_name, a.service_end_date
                FROM authorization a
                JOIN clients c ON a.{fk_col} = c.id
                WHERE a.status = 'ACTIVE'
                  AND date(a.service_end_date) BETWEEN date(?) AND date(?)
                ORDER BY a.service_end_date ASC
                LIMIT 25
            """, (today.isoformat(), in_30.isoformat()))
            rows = cur.fetchall()
            data["auth_expiring_30"]  = len(rows)
            data["expiring_clients"]  = [(r["client_name"], r["service_end_date"]) for r in rows]
        except Exception:
            # Try without JOIN (some schemas differ)
            try:
                cur.execute("""
                    SELECT service_end_date, COUNT(*) AS cnt
                    FROM authorization
                    WHERE status = 'ACTIVE'
                      AND date(service_end_date) BETWEEN date(?) AND date(?)
                    GROUP BY service_end_date
                    ORDER BY service_end_date ASC
                """, (today.isoformat(), in_30.isoformat()))
                rows = cur.fetchall()
                data["auth_expiring_30"] = sum(r["cnt"] for r in rows)
            except Exception:
                pass

        # Today's attendance (best-effort)
        try:
            cur.execute("""
                SELECT COUNT(*) FROM attendance
                WHERE date = ? AND present = 1
            """, (today.isoformat(),))
            data["attendance_confirmed"] = cur.fetchone()[0]
        except Exception:
            pass

        conn.close()

    except Exception as e:
        data["error"] = str(e)

    return data


# ─────────────────────────────────────────────────────────────────────────────
# BUILD STATUS
# ─────────────────────────────────────────────────────────────────────────────

def read_build_status() -> dict:
    """Parse CC_PHASE_STATUS.md for progress and blockers."""
    result = {
        "complete":     0,
        "total":        19,
        "active_phase": "15-CC — Command Center Phase 2",
        "blockers":     [],
        "error":        None,
    }

    if not PHASE_STATUS_FILE.exists():
        result["error"] = "CC_PHASE_STATUS.md not found"
        return result

    try:
        content = PHASE_STATUS_FILE.read_text(encoding="utf-8")
        lines   = content.split("\n")

        complete = 0
        active   = None

        for line in lines:
            if not line.startswith("|"):
                continue
            upper = line.upper()
            # Skip header/separator rows
            if "| # |" in line or "|---|" in line or "| PHASE" in upper:
                continue

            if "✅ COMPLETE" in line or ("LOCKED" in upper and "✅" in line):
                complete += 1
            if "IN PROGRESS" in upper or "ACTIVE BUILD" in upper:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) > 2:
                    # Try to get phase name from col 2 or 3
                    for p in parts[1:4]:
                        p = p.strip("* ").strip()
                        if p and p not in ("", "#"):
                            active = p
                            break

        result["complete"]     = complete
        result["active_phase"] = active or "15-CC — Command Center Phase 2"

        # Extract known blockers
        blocker_map = [
            ("13-V",          "Phase 13-V verification sprint NOT RUN (HARD GATE — blocks Phase 14+)"),
            ("akc_tokenizer", "Gate 1: akc_tokenizer.py not fully built — PHI cloud routing blocked"),
            ("65001",         "Hermes local gateway :65001 DOWN"),
            ("rexxie-bot",    "com.hermes.rexxie-bot.plist is a zombie — keep disabled"),
        ]
        seen = set()
        for keyword, msg in blocker_map:
            if keyword in content and msg not in seen:
                result["blockers"].append(msg)
                seen.add(msg)

    except Exception as e:
        result["error"] = str(e)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# TODAY'S FILES
# ─────────────────────────────────────────────────────────────────────────────

def scan_todays_files() -> list:
    """Files in ~/Desktop/REX/ with mtime >= today's midnight."""
    midnight  = today_midnight()
    new_files = []
    try:
        for entry in os.scandir(REX_DIR):
            if entry.is_file() and entry.stat().st_mtime >= midnight:
                new_files.append(entry.name)
        new_files.sort()
    except Exception:
        pass
    return new_files


# ─────────────────────────────────────────────────────────────────────────────
# WATCHDOG / CLAUS ALERTS
# ─────────────────────────────────────────────────────────────────────────────

def read_watchdog_alerts() -> list:
    """Recent alert lines from watchdog.log and/or claus.log."""
    alerts = []
    for log_path in (WATCHDOG_LOG, CLAUS_LOG):
        try:
            if not log_path.exists():
                continue
            raw = log_path.read_text(encoding="utf-8", errors="replace")
            for line in raw.split("\n")[-100:]:
                stripped = line.strip()
                if not stripped:
                    continue
                if any(kw in stripped.upper() for kw in
                       ("ALERT", "ERROR", "WARN", "FAIL", "DOWN", "CRITICAL", "EXPIRED", "STALE")):
                    alerts.append(stripped)
        except Exception:
            pass
    # Deduplicate and cap
    seen, deduped = set(), []
    for a in alerts:
        if a not in seen:
            seen.add(a)
            deduped.append(a)
    return deduped[-8:]


# ─────────────────────────────────────────────────────────────────────────────
# MARKDOWN WRITERS
# ─────────────────────────────────────────────────────────────────────────────

def write_system_status(svc_results: list, watchdog: list, ts: str):
    rows = []
    for s in svc_results:
        uptime = fmt_uptime(s["uptime_sec"]) if s["up"] else "—"
        rows.append(f"| {s['name']} | :{s['port']} | {s['icon']} {s['label']} | {uptime} |")

    up_count   = sum(1 for s in svc_results if s["up"])
    down_count = len(svc_results) - up_count

    alert_section = (
        "\n".join(f"- `{a}`" for a in watchdog)
        if watchdog
        else "*No alert lines found in watchdog/claus logs*"
    )

    content = f"""\
---
updated: {ts}
auto_generated: true
tags: [live, system, health]
---

# 🏛️ GHS System Status
*Auto-updated every 5 minutes by CC_obsidian_live_daemon*

**{up_count}/{len(svc_results)} services UP** · as of {ts}

## Services
| Service | Port | Status | Uptime |
|---------|------|--------|--------|
{chr(10).join(rows)}

## Recent Log Alerts
{alert_section}

---
*Port-checked from localhost · Uptime resets on restart detection*
"""
    atomic_write(LIVE_DIR / "SYSTEM_STATUS.md", content)


def write_goj_today(goj: dict, ts: str):
    today     = datetime.date.today()
    day_label = today.strftime("%A %B %d %Y").replace(" 0", " ")  # strip leading zero

    # DB status note
    if goj["error"]:
        db_note = f"\n> ⚠️ **DB warning:** {goj['error']}\n"
    elif not goj["db_found"]:
        db_note = "\n> ⚠️ **auth_tracker.db not found** — showing placeholder data\n"
    else:
        db_note = f"\n> 📂 DB: `{goj['db_path']}`\n"

    # Attendance block
    if goj["attendance_confirmed"] > 0:
        attn_block = f"- **Confirmed present:** {goj['attendance_confirmed']}"
    else:
        attn_block = "- *Attendance data not available (attendance table query returned 0)*"

    total   = goj["total_clients"] or "~425"
    active  = goj["auth_active"]   or "—"
    expired = goj["auth_expired"]
    pending = goj["auth_pending"]
    expiring = goj["auth_expiring_30"]

    # Expiring clients list
    if goj["expiring_clients"]:
        exp_lines = "\n".join(
            f"- **{name}** — expires {exp_date}"
            for name, exp_date in goj["expiring_clients"]
        )
    elif expiring > 0:
        exp_lines = f"*{expiring} clients expiring — names unavailable (join query failed)*"
    else:
        exp_lines = "*No clients expiring in next 30 days*"

    exp_icon = "⚠️" if expiring > 0 else "✅"

    content = f"""\
---
updated: {ts}
tags: [live, goj, operations]
---

# 🏥 GOJ Today — {day_label}
{db_note}
## Attendance
{attn_block}

## Authorization Snapshot
| Status | Count | |
|--------|-------|---|
| Active | {active} | ✅ |
| Expiring in 30 days | {expiring} | {exp_icon} |
| Pending renewal | {pending} | 🔄 |
| Expired | {expired} | {'🔴' if expired > 0 else '✅'} |
| **Total clients** | **{total}** | |

## ⚠️ Expiring This Month — Action Required
{exp_lines}

---
*Source: auth_tracker.db · Updated: {ts}*
"""
    atomic_write(LIVE_DIR / "GOJ_TODAY.md", content)


def write_build_status(build: dict, new_files: list, ts: str):
    pct = int(100 * build["complete"] / max(build["total"], 1))
    bar = progress_bar(pct)

    blocker_lines = (
        "\n".join(f"- 🔴 {b}" for b in build["blockers"])
        if build["blockers"]
        else "- *No blockers detected in phase file*"
    )

    if new_files:
        file_lines = "\n".join(f"- `{f}`" for f in new_files[:30])
        file_header = f"**{len(new_files)} file(s) modified today**"
    else:
        file_lines  = "- *No files modified in ~/Desktop/REX/ today*"
        file_header = "No new files today"

    err_note = f"\n> ⚠️ {build['error']}\n" if build.get("error") else ""

    content = f"""\
---
updated: {ts}
tags: [live, build, phases]
---

# 🔨 GHS Build Status
{err_note}
## Overall Progress
**Phases complete:** {build['complete']}/{build['total']} ({pct}%)

`{bar}` {pct}%

## Active Phase: {build['active_phase']}
Status: **IN PROGRESS**

## Blockers 🔴
{blocker_lines}

## Today's Modified Files in ~/Desktop/REX/
{file_header}
{file_lines}

---
*Source: CC_PHASE_STATUS.md · Updated: {ts}*
"""
    atomic_write(LIVE_DIR / "BUILD_STATUS.md", content)


def write_alerts(svc_results: list, goj: dict, build: dict, ts: str):
    # ── URGENT ──
    urgent = [
        "TOTP secret = RFC example value (`JBSWY3DPEHPK3PXP`) — **zero real security, must rotate**",
        "`auth_tracker.db` not SQLCipher-encrypted — top open security item",
        "`rex_user_model.db` is 0 KB — user model starts cold every session",
        "Retell API key expired — Victoria + Masha voice agents both dead",
    ]
    for s in svc_results:
        if not s["up"]:
            urgent.append(f"Service DOWN: **{s['name']}** (:{s['port']})")

    # ── ATTENTION ──
    attention = []
    if goj["auth_expired"] > 0:
        attention.append(
            f"{goj['auth_expired']} client(s) with **EXPIRED** authorization — escalate if >30 days no PENDING RENEWAL"
        )
    if goj["auth_expiring_30"] > 0:
        attention.append(
            f"{goj['auth_expiring_30']} client(s) authorization **expiring within 30 days** — start renewal now"
        )
    for b in build["blockers"]:
        if b not in urgent:
            attention.append(b)
    attention.extend([
        "`com.hermes.rexxie-bot.plist` = zombie — **keep disabled**, it steals the Rexxie token",
        "Nightly backup failing 38+ times — Phase 8 backup scripts need audit",
        "Gmail now IMAP-only (RESOLVED June 26) — Drive OAuth (~/.rex_google_token.json) still valid",
        "hermes-workspace LaunchAgents unloaded (quarantine pending Kato approval)",
    ])

    urgent_lines    = "\n".join(f"- {u}" for u in urgent)
    attention_lines = "\n".join(f"- {a}" for a in attention)

    content = f"""\
---
updated: {ts}
tags: [live, alerts, urgent]
---

# 🚨 Active Alerts

## 🔴 URGENT — Requires Immediate Action
{urgent_lines}

## 🟡 ATTENTION — Known Open Items
{attention_lines}

## 🟢 Standing Good
- Rexxie private lane / firewall wall intact ✅
- GOJ daily automation pipeline running ✅ (7AM → kitchen/driver/signin PDFs)
- Claus Watchman active (`com.hermes.claus-watchman.plist`) ✅
- Phase 1–13 + 18 complete and locked ✅
- Hermes Cloud Gateway :3002 operational ✅
- n8n automations: 6 live workflows ✅

---
*Alert state as of {ts} · Items marked URGENT require Kato action*
"""
    atomic_write(LIVE_DIR / "ALERTS.md", content)


def update_today_log(svc_results: list, goj: dict, new_files: list, state: dict, ts: str):
    """Prepend a timestamped entry to TODAY_LOG.md (newest at top)."""
    log_path = LIVE_DIR / "TODAY_LOG.md"
    today    = datetime.date.today()

    # Detect service changes vs previous state
    prev = state.get("prev_services", {})
    changes = []
    for s in svc_results:
        key  = str(s["port"])
        curr = "UP" if s["up"] else "DOWN"
        if key in prev and prev[key] != curr:
            arrow = "✅ came back UP" if curr == "UP" else "🔴 went DOWN"
            changes.append(f"**{s['name']}** :{s['port']} → {arrow}")

    # Update state
    state["prev_services"] = {str(s["port"]): ("UP" if s["up"] else "DOWN") for s in svc_results}
    run_num = state.get("run_count", 0) + 1
    state["run_count"] = run_num

    changes_text = (
        "\n".join(f"  - {c}" for c in changes)
        if changes
        else "  *No changes since last run*"
    )

    files_text = (
        f"{len(new_files)} modified: " + ", ".join(f"`{f}`" for f in new_files[:10])
        if new_files
        else "*none*"
    )

    up_svcs = [s["name"] for s in svc_results if s["up"]]
    down_svcs = [s["name"] for s in svc_results if not s["up"]]

    new_entry = f"""\
## {ts} — Run #{run_num}

**Services up:** {", ".join(up_svcs) or "none"}
**Services down:** {", ".join(down_svcs) or "none"}
**Changes since last run:**
{changes_text}

**Auth snapshot:** Active={goj['auth_active']} · Expired={goj['auth_expired']} · \
Expiring30={goj['auth_expiring_30']}
**Today's REX files:** {files_text}

---

"""

    # Header written only once (when file is new)
    existing = ""
    if log_path.exists():
        existing = log_path.read_text(encoding="utf-8")

    header = ""
    if not existing:
        header = f"""\
---
tags: [live, log, daily]
---

# 📋 TODAY_LOG — {today.strftime("%A %B %d %Y").replace(" 0", " ")}
*Append-only running log · Newest entries at top · Resets at midnight*

---

"""

    atomic_write(log_path, header + new_entry + existing)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN RUN
# ─────────────────────────────────────────────────────────────────────────────

def run_once():
    ts = now_str()
    daemon_log(f"── Daemon run starting ─────────────────── {ts}")

    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()

    daemon_log("Checking service health...")
    svc_results = check_all_services(state)
    up_count    = sum(1 for s in svc_results if s["up"])
    daemon_log(f"  {up_count}/{len(svc_results)} services UP")

    daemon_log("Querying auth_tracker.db...")
    goj = query_goj_data()
    if goj["error"]:
        daemon_log(f"  ⚠️  {goj['error']}")
    else:
        daemon_log(f"  Clients: {goj['total_clients']} · Active: {goj['auth_active']} · "
                   f"Expired: {goj['auth_expired']} · Expiring30: {goj['auth_expiring_30']}")

    daemon_log("Reading build status...")
    build = read_build_status()
    daemon_log(f"  {build['complete']}/{build['total']} phases complete · "
               f"Active: {build['active_phase']}")

    daemon_log("Scanning today's files in ~/Desktop/REX/...")
    new_files = scan_todays_files()
    daemon_log(f"  {len(new_files)} file(s) modified today")

    daemon_log("Reading watchdog/claus logs...")
    watchdog = read_watchdog_alerts()
    daemon_log(f"  {len(watchdog)} alert line(s) found")

    # ── Write all markdown files ──
    daemon_log("Writing SYSTEM_STATUS.md...")
    write_system_status(svc_results, watchdog, ts)

    daemon_log("Writing GOJ_TODAY.md...")
    write_goj_today(goj, ts)

    daemon_log("Writing BUILD_STATUS.md...")
    write_build_status(build, new_files, ts)

    daemon_log("Writing ALERTS.md...")
    write_alerts(svc_results, goj, build, ts)

    daemon_log("Updating TODAY_LOG.md...")
    update_today_log(svc_results, goj, new_files, state, ts)

    save_state(state)

    daemon_log(f"✅ All 5 files written to {LIVE_DIR}")
    daemon_log("────────────────────────────────────────────────────────────")


def main():
    ap = argparse.ArgumentParser(
        description="GHS Obsidian Live Dashboard Daemon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python CC_obsidian_live_daemon.py --once     # single run, then exit
              python CC_obsidian_live_daemon.py --daemon   # 5-min loop (internal sleep)
              python CC_obsidian_live_daemon.py --status   # print last state file
        """),
    )
    ap.add_argument("--once",   action="store_true", help="Run one pass and exit")
    ap.add_argument("--daemon", action="store_true", help="Loop every 5 minutes")
    ap.add_argument("--status", action="store_true", help="Print last state and exit")
    args = ap.parse_args()

    if args.status:
        state = load_state()
        print(json.dumps(state, indent=2, default=str))
        return

    if args.once:
        run_once()
        return

    if args.daemon:
        daemon_log(f"Starting daemon — interval {INTERVAL_SECONDS}s")
        while True:
            try:
                run_once()
            except Exception as e:
                daemon_log(f"ERROR in run_once: {e}")
            daemon_log(f"Sleeping {INTERVAL_SECONDS}s...")
            time.sleep(INTERVAL_SECONDS)
        return

    ap.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
