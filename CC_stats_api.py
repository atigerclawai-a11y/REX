#!/usr/bin/env python3
"""
CC_stats_api.py — GHS Command Center Stats API
Port 8001 · localhost only · PHI stays local
Built: 2026-06-04

Provides live GOJ operations data to the Gold Health Systems Command Center.
Reads auth_tracker.db directly — never sends data to cloud.

Existing REX endpoints this complements (port 8000):
  /api/attendance         — per-date attendance log
  /api/goj/stats          — GOJ stats (requires auth token)
  /api/clients            — client list (requires auth token)
  /api/authorizations     — auth docs (requires auth token)
  /api/staff/compliance   — staff compliance xlsx (chairman only)

This API (port 8001) is for the command center dashboard widget only.
No auth token required — localhost access is implicitly trusted per Desktop Mode.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import sqlite3
import json
import os
import glob
import socket
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

app = FastAPI(title="GHS Command Center Stats API", version="1.0.0")

# CORS: allow all origins (access is gated at network level — localhost only)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Paths ─────────────────────────────────────────────────────────────────────

DB_PATH = str(Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db")
GOJ_DATA_DIR = str(Path.home() / ".hermes-cloud" / "home" / "goj-pipeline" / "data")
REX_DIR = str(Path.home() / "Desktop" / "REX")
CLOCK_FILE = str(Path.home() / "Desktop" / "REX" / "CC_clock_records.json")
COMPLIANCE_XLSX = str(Path.home() / "Desktop" / "REX" / "backend" / ".." /
                      "GOJ_Staff_Compliance_Apr2026.xlsx")


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    """Return a WAL-mode connection to auth_tracker.db."""
    if not os.path.exists(DB_PATH):
        raise HTTPException(503, f"auth_tracker.db not found at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA query_only=ON")   # read-only guard
    return conn


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return bool(row and row[0])


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Basic health check — confirms the service is running."""
    db_ok = os.path.exists(DB_PATH)
    return {
        "status": "ok",
        "service": "cc-stats-api",
        "port": 8001,
        "db_available": db_ok,
        "db_path": DB_PATH,
        "timestamp": datetime.now().isoformat(),
    }


# ── Client Stats ──────────────────────────────────────────────────────────────

@app.get("/api/stats/clients")
def client_stats():
    """
    Client authorization breakdown for the command center.
    Returns total clients, auth status counts, expiring-soon count.

    Tables used: clients, auth_documents
    """
    conn = get_db()
    try:
        result = {
            "total_clients": 0,
            "active_clients": 0,
            "auth_breakdown": [],
            "expiring_soon_30d": 0,
            "expired_count": 0,
            "pending_renewal_count": 0,
            "last_updated": datetime.now().isoformat(),
        }

        # Client counts
        result["total_clients"] = conn.execute(
            "SELECT COUNT(*) FROM clients"
        ).fetchone()[0]

        result["active_clients"] = conn.execute(
            "SELECT COUNT(*) FROM clients WHERE active = 1"
        ).fetchone()[0]

        # Auth document breakdown
        if table_exists(conn, "auth_documents"):
            auth_rows = conn.execute("""
                SELECT status, COUNT(*) as count
                FROM auth_documents
                GROUP BY status
                ORDER BY count DESC
            """).fetchall()
            result["auth_breakdown"] = [dict(r) for r in auth_rows]

            # Expiring soon (next 30 days) — active authorizations
            today = date.today().isoformat()
            cutoff = (date.today() + timedelta(days=30)).isoformat()
            result["expiring_soon_30d"] = conn.execute("""
                SELECT COUNT(*) FROM auth_documents
                WHERE expiration_date BETWEEN ? AND ?
                AND LOWER(status) = 'active'
            """, (today, cutoff)).fetchone()[0]

            result["expired_count"] = conn.execute("""
                SELECT COUNT(*) FROM auth_documents
                WHERE LOWER(status) = 'expired'
            """).fetchone()[0]

            result["pending_renewal_count"] = conn.execute("""
                SELECT COUNT(*) FROM auth_documents
                WHERE LOWER(status) LIKE 'pending%'
            """).fetchone()[0]

        elif table_exists(conn, "authorization"):
            # Fallback: older schema uses 'authorization' table
            auth_rows = conn.execute("""
                SELECT status, COUNT(*) as count
                FROM authorization
                GROUP BY status
            """).fetchall()
            result["auth_breakdown"] = [dict(r) for r in auth_rows]

            today = date.today().isoformat()
            cutoff = (date.today() + timedelta(days=30)).isoformat()
            result["expiring_soon_30d"] = conn.execute("""
                SELECT COUNT(*) FROM authorization
                WHERE service_end_date BETWEEN ? AND ?
                AND status = 'ACTIVE'
            """, (today, cutoff)).fetchone()[0]

        return result
    finally:
        conn.close()


# ── Attendance Stats ──────────────────────────────────────────────────────────

@app.get("/api/stats/attendance")
def attendance_stats(days_back: int = 7):
    """
    Today's attendance and recent trend.
    Returns today's count and a per-day breakdown for the last N days.

    Table used: attendance_log
    """
    conn = get_db()
    try:
        result = {
            "today": date.today().isoformat(),
            "today_count": 0,
            "today_scheduled": 0,
            "today_confirmed": 0,
            "trend": [],
            "source": "attendance_log",
        }

        if not table_exists(conn, "attendance_log"):
            result["source"] = "no_table"
            return result

        today_str = date.today().isoformat()

        # Today's counts
        today_rows = conn.execute("""
            SELECT status, COUNT(*) as cnt
            FROM attendance_log
            WHERE log_date = ?
            GROUP BY status
        """, (today_str,)).fetchall()

        present_statuses = {"present", "attended", "confirmed"}
        scheduled_statuses = {"scheduled", "present", "attended", "confirmed"}
        for r in today_rows:
            s = (r["status"] or "").lower()
            if s in scheduled_statuses:
                result["today_scheduled"] += r["cnt"]
            if s in present_statuses:
                result["today_confirmed"] += r["cnt"]
        result["today_count"] = result["today_scheduled"]

        # N-day trend
        trend = []
        for i in range(days_back - 1, -1, -1):
            d = (date.today() - timedelta(days=i)).isoformat()
            row = conn.execute("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN LOWER(status) IN ('present','attended','confirmed') THEN 1 ELSE 0 END) as confirmed
                FROM attendance_log
                WHERE log_date = ?
            """, (d,)).fetchone()
            trend.append({
                "date": d,
                "scheduled": row["total"] or 0,
                "confirmed": row["confirmed"] or 0,
            })
        result["trend"] = trend

        return result
    finally:
        conn.close()


# ── Today's Roster Summary ────────────────────────────────────────────────────

@app.get("/api/stats/roster")
def roster_summary():
    """
    Today's scheduled roster by shift — counts and names.
    Uses attendance_log or falls back to clients active-day schedule.
    """
    conn = get_db()
    try:
        today_str = date.today().isoformat()
        shifts = {}

        if table_exists(conn, "attendance_log"):
            rows = conn.execute("""
                SELECT shift, client_name, status, source
                FROM attendance_log
                WHERE log_date = ?
                ORDER BY shift, client_name
            """, (today_str,)).fetchall()

            for r in rows:
                k = str(r["shift"] or "1")
                shifts.setdefault(k, {"shift": k, "clients": [], "count": 0, "confirmed": 0})
                shifts[k]["clients"].append({
                    "name": r["client_name"],
                    "status": r["status"],
                    "source": r["source"],
                })
                shifts[k]["count"] += 1
                if (r["status"] or "").lower() in {"present", "attended", "confirmed"}:
                    shifts[k]["confirmed"] += 1

        # If attendance_log has no entries today, fall back to clients schedule
        if not shifts and table_exists(conn, "clients"):
            dow = date.today().weekday()
            col_map = {0: "day_M_actual", 1: "day_T_actual", 2: "day_W_actual",
                       3: "day_TH_actual", 4: "day_F_actual"}
            if dow in col_map:
                col = col_map[dow]
                rows = conn.execute(f"""
                    SELECT name, shift FROM clients
                    WHERE {col} = 1 AND active = 1
                    ORDER BY shift, name
                """).fetchall()
                for r in rows:
                    k = str(r["shift"] or "1")
                    shifts.setdefault(k, {"shift": k, "clients": [], "count": 0, "confirmed": 0})
                    shifts[k]["clients"].append({"name": r["name"], "status": "scheduled", "source": "schedule"})
                    shifts[k]["count"] += 1

        total = sum(s["count"] for s in shifts.values())
        confirmed = sum(s["confirmed"] for s in shifts.values())

        return {
            "date": today_str,
            "day": date.today().strftime("%A"),
            "shifts": list(shifts.values()),
            "total_scheduled": total,
            "total_confirmed": confirmed,
            "last_updated": datetime.now().isoformat(),
        }
    finally:
        conn.close()


# ── Authorizations Expiry Quick View ─────────────────────────────────────────

@app.get("/api/stats/expiring")
def expiring_authorizations(days: int = 30):
    """
    Clients whose authorizations expire within N days.
    Sorted by expiration date ascending (most urgent first).
    """
    conn = get_db()
    try:
        today = date.today().isoformat()
        cutoff = (date.today() + timedelta(days=days)).isoformat()

        auth_table = None
        if table_exists(conn, "auth_documents"):
            auth_table = "auth_documents"
            date_col = "expiration_date"
        elif table_exists(conn, "authorization"):
            auth_table = "authorization"
            date_col = "service_end_date"

        if not auth_table:
            return {"expiring": [], "count": 0, "window_days": days}

        rows = conn.execute(f"""
            SELECT client_name, {date_col} as expiration_date, status
            FROM {auth_table}
            WHERE {date_col} BETWEEN ? AND ?
            ORDER BY {date_col} ASC
            LIMIT 50
        """, (today, cutoff)).fetchall()

        items = []
        for r in rows:
            exp = r["expiration_date"]
            try:
                days_left = (date.fromisoformat(exp) - date.today()).days
            except Exception:
                days_left = None
            items.append({
                "client_name": r["client_name"],
                "expiration_date": exp,
                "status": r["status"],
                "days_remaining": days_left,
            })

        return {
            "expiring": items,
            "count": len(items),
            "window_days": days,
            "as_of": today,
        }
    finally:
        conn.close()


# ── Employee Stats ────────────────────────────────────────────────────────────

@app.get("/api/stats/employees")
def employee_stats():
    """
    Employee list from auth_tracker.db (employees table if present).
    Falls back to a placeholder if table doesn't exist —
    staff compliance data lives in the xlsx, not the DB.
    """
    conn = get_db()
    try:
        if not table_exists(conn, "employees"):
            return {
                "employees": [],
                "total": 0,
                "note": "employees table not in auth_tracker.db — staff data is in GOJ_Staff_Compliance_Apr2026.xlsx",
                "xlsx_available": os.path.exists(COMPLIANCE_XLSX),
            }

        cols = [c[1] for c in conn.execute("PRAGMA table_info(employees)").fetchall()]
        rows = conn.execute("SELECT * FROM employees").fetchall()
        return {
            "employees": [dict(zip(cols, tuple(r))) for r in rows],
            "total": len(rows),
            "columns": cols,
        }
    finally:
        conn.close()


# ── Clock In / Out ────────────────────────────────────────────────────────────
# Phase 1: stores records in CC_clock_records.json (no DB modification)
# Phase 2 will add a proper clock_records table to auth_tracker.db

def _load_clock_data() -> dict:
    if not os.path.exists(CLOCK_FILE):
        return {"records": []}
    try:
        with open(CLOCK_FILE) as f:
            return json.load(f)
    except Exception:
        return {"records": []}


def _save_clock_data(data: dict):
    with open(CLOCK_FILE, "w") as f:
        json.dump(data, f, indent=2)


@app.get("/api/clockin/status")
def clock_status():
    """
    Who is currently clocked in and today's full clock log.
    """
    data = _load_clock_data()
    today = date.today().isoformat()
    today_log = [r for r in data.get("records", []) if r.get("date") == today]

    # Find currently clocked in: last action for each employee is clock_in
    by_employee: dict = {}
    for r in today_log:
        by_employee.setdefault(r["employee"], []).append(r)

    clocked_in = []
    for emp, records in by_employee.items():
        last = sorted(records, key=lambda x: x.get("time", ""))[-1]
        if last["action"] == "clock_in":
            clocked_in.append({
                "employee": emp,
                "clocked_in_since": last["time"],
                "clocked_in_at": last["timestamp"],
            })

    return {
        "date": today,
        "clocked_in": clocked_in,
        "count_in": len(clocked_in),
        "today_log": today_log,
    }


@app.post("/api/clockin/{employee_name}")
def clock_in(employee_name: str):
    """Record clock-in for an employee."""
    data = _load_clock_data()
    now = datetime.now()
    record = {
        "employee": employee_name,
        "action": "clock_in",
        "date": date.today().isoformat(),
        "time": now.strftime("%H:%M:%S"),
        "timestamp": now.isoformat(),
    }
    data["records"].append(record)
    _save_clock_data(data)
    return {"status": "clocked_in", "employee": employee_name, "time": record["time"]}


@app.post("/api/clockout/{employee_name}")
def clock_out(employee_name: str):
    """Record clock-out for an employee."""
    data = _load_clock_data()
    now = datetime.now()
    record = {
        "employee": employee_name,
        "action": "clock_out",
        "date": date.today().isoformat(),
        "time": now.strftime("%H:%M:%S"),
        "timestamp": now.isoformat(),
    }
    data["records"].append(record)
    _save_clock_data(data)
    return {"status": "clocked_out", "employee": employee_name, "time": record["time"]}


@app.get("/api/clockin/history")
def clock_history(days_back: int = 7):
    """Clock-in/out history for the last N days."""
    data = _load_clock_data()
    cutoff = (date.today() - timedelta(days=days_back)).isoformat()
    recent = [r for r in data.get("records", []) if r.get("date", "") >= cutoff]
    recent.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return {"records": recent, "total": len(recent), "days_back": days_back}


# ── GOJ Pipeline File Status ──────────────────────────────────────────────────

@app.get("/api/goj/pipeline")
def goj_pipeline():
    """
    Status of GOJ pipeline data files (~/.hermes-cloud/home/goj-pipeline/data/).
    Flags stale files (not updated in >24h).
    """
    data_dir = Path(GOJ_DATA_DIR)
    if not data_dir.exists():
        return {
            "status": "unavailable",
            "path": GOJ_DATA_DIR,
            "files": [],
            "note": "GOJ data directory not found",
        }

    files = []
    now = datetime.now()
    for f in data_dir.iterdir():
        if not f.is_file():
            continue
        try:
            stat = f.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime)
            age_hours = (now - mtime).total_seconds() / 3600
            files.append({
                "name": f.name,
                "modified": mtime.isoformat(),
                "size_bytes": stat.st_size,
                "age_hours": round(age_hours, 1),
                "stale": age_hours > 25,  # >25h = missed its daily update
            })
        except Exception:
            pass

    files.sort(key=lambda x: x["modified"], reverse=True)
    stale_count = sum(1 for f in files if f["stale"])

    return {
        "status": "ok",
        "path": GOJ_DATA_DIR,
        "files": files[:20],
        "total_files": len(files),
        "stale_count": stale_count,
        "last_checked": now.isoformat(),
    }


# ── Recent REX Files ──────────────────────────────────────────────────────────

@app.get("/api/files/recent")
def recent_files():
    """
    Recently modified files in ~/Desktop/REX/ (scripts, commands, JSON).
    Useful for the command center to show recent build activity.
    """
    rex_dir = Path(REX_DIR)
    patterns = ["*.py", "*.command", "*.json", "*.md", "*.plist"]
    files = []
    for pattern in patterns:
        for f in rex_dir.glob(pattern):
            try:
                stat = f.stat()
                files.append({
                    "name": f.name,
                    "extension": f.suffix,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "size_bytes": stat.st_size,
                })
            except Exception:
                pass

    files.sort(key=lambda x: x["modified"], reverse=True)
    return {
        "files": files[:25],
        "total": len(files),
        "rex_dir": REX_DIR,
    }


# ── Combined Command Center Snapshot ─────────────────────────────────────────

@app.get("/api/snapshot")
def snapshot():
    """
    Single endpoint for the command center's top-level dashboard widget.
    Returns a compact summary of all key metrics in one call.
    Avoids multiple round trips from the frontend.
    """
    snap = {
        "timestamp": datetime.now().isoformat(),
        "date": date.today().isoformat(),
        "day": date.today().strftime("%A"),
        "clients": {},
        "attendance": {},
        "clock": {},
        "pipeline": {},
    }

    # Clients
    try:
        cs = client_stats()
        snap["clients"] = {
            "total": cs["total_clients"],
            "active": cs["active_clients"],
            "expiring_soon_30d": cs["expiring_soon_30d"],
            "expired": cs["expired_count"],
        }
    except Exception as e:
        snap["clients"] = {"error": str(e)}

    # Attendance
    try:
        att = attendance_stats(days_back=7)
        snap["attendance"] = {
            "today_scheduled": att["today_scheduled"],
            "today_confirmed": att["today_confirmed"],
            "trend_7d": att["trend"],
        }
    except Exception as e:
        snap["attendance"] = {"error": str(e)}

    # Clock status
    try:
        ck = clock_status()
        snap["clock"] = {
            "count_in": ck["count_in"],
            "clocked_in": [c["employee"] for c in ck["clocked_in"]],
        }
    except Exception as e:
        snap["clock"] = {"error": str(e)}

    # Pipeline health
    try:
        pipe = goj_pipeline()
        snap["pipeline"] = {
            "status": pipe["status"],
            "stale_count": pipe.get("stale_count", 0),
            "total_files": pipe.get("total_files", 0),
        }
    except Exception as e:
        snap["pipeline"] = {"error": str(e)}

    return snap


# ── Service Health Check ──────────────────────────────────────────────────────

@app.get("/api/services")
def service_health():
    """
    Server-side port reachability check for all GHS services.
    Runs on the Mac Mini where all services are localhost — works correctly
    whether the caller is local or remote (via Cloudflare tunnel).
    """
    services = [
        {"name": "Hermes Cloud", "port": 3002},
        {"name": "REX Backend",  "port": 8000},
        {"name": "GOJ Dashboard","port": 8080},
        {"name": "CC Stats API", "port": 8001},
        {"name": "Tiger Claw",   "port": 27226},
    ]

    results = []
    for svc in services:
        try:
            sock = socket.create_connection(("127.0.0.1", svc["port"]), timeout=0.8)
            sock.close()
            alive = True
        except Exception:
            alive = False
        results.append({
            "name":  svc["name"],
            "port":  svc["port"],
            "alive": alive,
        })

    return {
        "services":  results,
        "timestamp": datetime.now().isoformat(),
    }


# ── Build Progress ───────────────────────────────────────────────────────────

PROGRESS_FILE = str(Path(REX_DIR) / "CC_build_progress.json")

@app.get("/api/progress")
def get_progress():
    """
    Live build progress data for CC_live_progress.html.
    Reads CC_build_progress.json — agents write to this file to update status.
    """
    path = Path(PROGRESS_FILE)
    if not path.exists():
        raise HTTPException(404, "CC_build_progress.json not found")
    try:
        with open(path) as f:
            data = json.load(f)
        data["_served_at"] = datetime.now().isoformat()
        return data
    except Exception as e:
        raise HTTPException(500, f"Error reading progress file: {e}")


@app.post("/api/progress/update")
async def update_progress(payload: dict):
    """
    Agents call this to update their mission status.
    Payload: {"id": "mission_id", "pct": 75, "status": "live", "detail": "..."}
    """
    path = Path(PROGRESS_FILE)
    if not path.exists():
        raise HTTPException(404, "CC_build_progress.json not found")
    try:
        with open(path) as f:
            data = json.load(f)

        mission_id = payload.get("id")
        if not mission_id:
            raise HTTPException(400, "id is required")

        updated = False
        for m in data.get("missions", []):
            if m["id"] == mission_id:
                if "pct"    in payload: m["pct"]    = payload["pct"]
                if "status" in payload: m["status"] = payload["status"]
                if "detail" in payload: m["detail"] = payload["detail"]
                if "block"  in payload: m["block"]  = payload["block"]
                updated = True
                break

        if not updated:
            raise HTTPException(404, f"Mission '{mission_id}' not found")

        # Recalculate overall %
        missions = data.get("missions", [])
        if missions:
            data["overall_pct"] = round(sum(m["pct"] for m in missions) / len(missions))

        data["_meta"]["updated"] = datetime.now().isoformat()

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        return {"updated": mission_id, "pct": payload.get("pct"), "ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error updating progress: {e}")


# ── Live Progress Dashboard ───────────────────────────────────────────────────

@app.get("/live", response_class=HTMLResponse)
async def live_dashboard():
    """Legacy endpoint — redirects to /progress (v2)."""
    html_path = Path(__file__).parent / "CC_live_progress_v2.html"
    if not html_path.exists():
        html_path = Path(__file__).parent / "CC_live_progress.html"
    if not html_path.exists():
        raise HTTPException(404, "CC_live_progress.html not found")
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/progress", response_class=HTMLResponse)
async def live_dashboard_v2():
    """
    Serves CC_live_progress_v2.html — the enhanced live build progress board.
    Accessible at:
      hermestigerclaw.com/progress  (via Cloudflare tunnel)
      goldhealthsys.com/progress    (deploy CC_live_progress_v2.html to Railway)
    Reads file fresh on every request — no restart needed after HTML edits.
    """
    html_path = Path(__file__).parent / "CC_live_progress_v2.html"
    if not html_path.exists():
        raise HTTPException(404, f"CC_live_progress_v2.html not found at {html_path}")
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/cc", response_class=HTMLResponse)
async def command_center():
    """
    Serves CC_command_center.html — the full GHS Command Center.
    Accessible at:
      hermestigerclaw.com/cc  (via Cloudflare tunnel)
    12 tabs: Hermes / GOJ / Clients / Clock / Phases / BBG / Compound /
             Files / Modules / Build / Guardian / Nerve Center.
    Built-in screensaver activates on idle — doubles as lock screen display.
    """
    html_path = Path(__file__).parent / "CC_command_center.html"
    if not html_path.exists():
        raise HTTPException(404, f"CC_command_center.html not found at {html_path}")
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")
