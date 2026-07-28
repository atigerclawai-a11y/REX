#!/usr/bin/env python3
"""
CC_build_monitor.py — Build Activity Monitor Agent
====================================================
Watches the GOJ build pipeline: ingestion state, code activity, service health,
and reports it as a unified snapshot. Designed to be called from the GOJ Live
dashboard (/goj-live/build-status endpoint) AND to run standalone for Telegram
or CLI checks.

What it monitors:
  1. GOJ Drive ingestion daemon: last run, per-source last seen, errors
  2. Recent code activity: files modified in ~/Desktop/REX in the last N hours
  3. Service health: REX :8000, stats :8001, hub :9000, transition-drive-hook,
     drive-ingest daemon
  4. Database freshness: auth_tracker.db tables (clients, attendance_log, auth)
  5. Build artifacts: handoff_runs/, gdrive_mirror/, output_docs/

Usage:
    python3 CC_build_monitor.py                 # JSON to stdout
    python3 CC_build_monitor.py --human         # human-readable
    python3 CC_build_monitor.py --html          # HTML snippet
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

HOME = Path.home()
REX  = HOME / "Desktop" / "REX"
INGEST_STATE = REX / ".goj_drive_ingest_state.json"
INGEST_LOG   = REX / "logs" / "goj_drive_ingest.log"
DB_PATH      = HOME / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Section: ingestion state ─────────────────────────────────────────────────

def ingestion_status() -> Dict[str, Any]:
    if not INGEST_STATE.exists():
        return {"daemon": "not_started", "state": {}}
    try:
        state = json.loads(INGEST_STATE.read_text())
    except Exception as e:
        return {"daemon": "state_unreadable", "error": str(e)}
    last_run = state.get("last_run")
    age_min = None
    if last_run:
        try:
            dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
            age_min = (datetime.now(timezone.utc) - dt).total_seconds() / 60
        except Exception:
            pass
    daemon = "running" if (age_min is not None and age_min < 10) else "stale"
    return {
        "daemon":   daemon,
        "last_run": last_run,
        "age_minutes": round(age_min, 1) if age_min is not None else None,
        "sources":  state.get("stats", {}),
        "seen":     state.get("seen", {}),
    }


# ── Section: code activity ───────────────────────────────────────────────────

def code_activity(hours: int = 24) -> Dict[str, Any]:
    """Files in REX touched in the last N hours."""
    cutoff = time.time() - hours * 3600
    recent: List[Dict[str, Any]] = []
    for p in REX.rglob("CC_*.py"):
        try:
            mt = p.stat().st_mtime
            if mt >= cutoff:
                recent.append({
                    "file":      p.name,
                    "size":      p.stat().st_size,
                    "modified":  datetime.fromtimestamp(mt).isoformat(timespec="seconds"),
                })
        except Exception:
            continue
    # Also include .md and .command files in the top REX dir
    for p in REX.glob("CC_*.md"):
        try:
            mt = p.stat().st_mtime
            if mt >= cutoff:
                recent.append({
                    "file":      p.name,
                    "size":      p.stat().st_size,
                    "modified":  datetime.fromtimestamp(mt).isoformat(timespec="seconds"),
                })
        except Exception:
            continue
    recent.sort(key=lambda x: x["modified"], reverse=True)
    return {
        "window_hours": hours,
        "files_touched": len(recent),
        "files":       recent[:25],
    }


# ── Section: service health ──────────────────────────────────────────────────

def _launchctl_status(label: str) -> Dict[str, Any]:
    """Pull current PID + last exit from launchctl list."""
    try:
        out = subprocess.check_output(
            ["launchctl", "list"], text=True, stderr=subprocess.DEVNULL
        )
    except Exception as e:
        return {"label": label, "error": str(e)}
    for ln in out.splitlines():
        parts = ln.split()
        if len(parts) >= 3 and parts[-1] == label:
            pid = parts[0]
            exit_code = parts[1]
            return {
                "label": label,
                "pid":   None if pid == "-" else int(pid),
                "last_exit": int(exit_code) if exit_code.lstrip("-").isdigit() else exit_code,
                "running": pid != "-",
            }
    return {"label": label, "found": False}


def _http_check(url: str, timeout: float = 3.0) -> Dict[str, Any]:
    """Quick HTTP health probe."""
    import urllib.request
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return {"url": url, "status": r.status, "ok": 200 <= r.status < 400}
    except Exception as e:
        return {"url": url, "status": None, "ok": False, "error": str(e)[:80]}


def services() -> Dict[str, Any]:
    return {
        "launchd": [
            _launchctl_status("com.goj.drive-ingest"),
            _launchctl_status("com.goj.transition-drive-hook"),
            _launchctl_status("com.goj.transition-agent"),
            _launchctl_status("com.ghs.stats-api"),
            _launchctl_status("com.rex.backend"),
            _launchctl_status("com.goj.datarex"),
            _launchctl_status("com.goj.hub"),
        ],
        "http": [
            _http_check("http://127.0.0.1:8000/api/health"),
            _http_check("http://127.0.0.1:8000/goj-live/snapshot"),
            _http_check("http://127.0.0.1:8001/health"),
            _http_check("http://127.0.0.1:8080/health"),
            _http_check("http://127.0.0.1:9000/"),
        ],
    }


# ── Section: database freshness ──────────────────────────────────────────────

def database_freshness() -> Dict[str, Any]:
    if not DB_PATH.exists():
        return {"error": "auth_tracker.db not found"}
    with sqlite3.connect(str(DB_PATH)) as conn:
        out = {}
        out["clients_total"] = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
        out["attendance_total"] = conn.execute("SELECT COUNT(*) FROM attendance_log").fetchone()[0]
        out["attendance_min_date"] = conn.execute("SELECT MIN(log_date) FROM attendance_log").fetchone()[0]
        out["attendance_max_date"] = conn.execute("SELECT MAX(log_date) FROM attendance_log").fetchone()[0]
        out["attendance_today_count"] = conn.execute(
            "SELECT COUNT(*) FROM attendance_log WHERE log_date = date('now')"
        ).fetchone()[0]
        out["authorization_total"] = conn.execute("SELECT COUNT(*) FROM authorization").fetchone()[0]
        out["authorization_drive_ingested"] = conn.execute(
            "SELECT COUNT(*) FROM authorization WHERE source_type='PORTAL' AND notes LIKE 'Drive PDF%'"
        ).fetchone()[0]
        out["menus_total"] = conn.execute("SELECT COUNT(*) FROM client_menus").fetchone()[0]
    return out


# ── Section: build artifacts ─────────────────────────────────────────────────

def artifacts() -> Dict[str, Any]:
    out = {}
    for path, label in [
        (REX / "handoff_runs",  "handoff_runs"),
        (REX / "gdrive_mirror", "gdrive_mirror"),
        (HOME / "Documents" / "goj files" / "output_docs", "output_docs"),
    ]:
        if not path.exists():
            out[label] = {"exists": False}
            continue
        try:
            files = list(path.rglob("*"))
            sizes = [f.stat().st_size for f in files if f.is_file()]
            out[label] = {
                "exists":    True,
                "path":      str(path),
                "file_count": len([f for f in files if f.is_file()]),
                "total_bytes": sum(sizes),
                "newest":     max((f.stat().st_mtime for f in files if f.is_file()), default=0),
            }
            if out[label]["newest"]:
                out[label]["newest"] = datetime.fromtimestamp(out[label]["newest"]).isoformat(timespec="seconds")
        except Exception as e:
            out[label] = {"exists": True, "error": str(e)}
    return out


# ── Composite snapshot ──────────────────────────────────────────────────────

def snapshot() -> Dict[str, Any]:
    return {
        "ts":          _now(),
        "ingestion":   ingestion_status(),
        "code":        code_activity(),
        "services":    services(),
        "database":    database_freshness(),
        "artifacts":   artifacts(),
    }


# ── Renderers ────────────────────────────────────────────────────────────────

def render_human(snap: Dict[str, Any]) -> str:
    lines = [
        f"GOJ Build Monitor — {snap['ts']}",
        "",
        "── INGESTION DAEMON ──",
        f"  daemon: {snap['ingestion'].get('daemon', '?')}",
        f"  last run: {snap['ingestion'].get('last_run', '?')} "
        f"({snap['ingestion'].get('age_minutes', '?')} min ago)",
    ]
    for src, st in snap["ingestion"].get("sources", {}).items():
        lines.append(f"    {src}: {st.get('status','?')} "
                     f"· seen={st.get('seen_rows','?')} · changed={st.get('changed_rows','?')}")
    lines += ["", "── DATABASE FRESHNESS ──"]
    for k, v in snap["database"].items():
        lines.append(f"  {k}: {v}")
    lines += ["", "── SERVICES ──"]
    for s in snap["services"]["launchd"]:
        pid = s.get("pid", "-")
        lines.append(f"  {s.get('label','?')}: pid={pid} last_exit={s.get('last_exit','?')}")
    for h in snap["services"]["http"]:
        lines.append(f"  {h['url']}: {'✅' if h['ok'] else '❌'} ({h.get('status','?')})")
    lines += ["", f"── CODE ACTIVITY (last {snap['code']['window_hours']}h) ──",
              f"  files touched: {snap['code']['files_touched']}"]
    for f in snap["code"]["files"][:10]:
        lines.append(f"  {f['modified']} · {f['file']} ({f['size']} bytes)")
    return "\n".join(lines)


def render_html(snap: Dict[str, Any]) -> str:
    # Very compact HTML for embedding in dashboard
    h = ['<div class="build-monitor" style="font-family:monospace;font-size:11px;color:#c8d6e5">']
    h.append(f"<div><b>Build Monitor</b> — {snap['ts'][:19].replace('T',' ')} UTC</div>")
    ing = snap["ingestion"]
    color = "#0f8" if ing.get("daemon") == "running" else "#ff0"
    h.append(f"<div>Daemon: <span style='color:{color}'>{ing.get('daemon','?')}</span> "
             f"· last run {ing.get('age_minutes','?')} min ago</div>")
    db = snap["database"]
    h.append(f"<div>DB: {db.get('clients_total','?')} clients · "
             f"{db.get('attendance_total','?')} attendance rows · "
             f"max date {db.get('attendance_max_date','?')} · "
             f"{db.get('authorization_total','?')} auths "
             f"({db.get('authorization_drive_ingested','?')} from Drive)</div>")
    h.append("</div>")
    return "\n".join(h)


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--human", action="store_true")
    p.add_argument("--html",  action="store_true")
    args = p.parse_args()
    snap = snapshot()
    if args.human:
        print(render_human(snap))
    elif args.html:
        print(render_html(snap))
    else:
        print(json.dumps(snap, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
