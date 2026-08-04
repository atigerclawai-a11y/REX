#!/usr/bin/env python3
"""CC_attendance_live.py — Live Attendance Board.

FastAPI router + HTML page. Mounts to REX at /attendance-live.
Reads biometric_log.csv for today's sign-ins, cross-references with
auth_tracker.db client_schedule to show who's present vs absent.
Green card = signed in today. Red card = not yet signed in.
30-second auto-refresh. Big font readable from 15 feet.

RECONSTRUCTED 2026-08-03 from __pycache__/CC_attendance_live.cpython-311.pyc
(strings extraction — scripts/ purge victim). Behavior preserved.
"""

import csv
from datetime import datetime, date
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter(tags=["attendance-live"])

AUTH_DB = Path.home() / "Documents/goj files/dashboard/auth_tracker.db"
BIOMETRIC_LOG = Path.home() / "Desktop/REX/output/biometric_log.csv"

# Python weekday: Monday=0..Sunday=6 (matches client_schedule.day_of_week which
# is stored Monday-first in auth_tracker)
DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _get_today_signins():
    """Return {client_name: sign_in_timestamp} for today only."""
    today = date.today().isoformat()
    result = {}
    if not BIOMETRIC_LOG.exists():
        return result
    with BIOMETRIC_LOG.open(newline="") as f:
        for row in csv.DictReader(f):
            ts = row.get("timestamp") or row.get("time") or ""
            if today in ts:
                result[row.get("client_name", "")] = ts
    return result


def _get_today_clients():
    """Return clients scheduled today from client_schedule, with shift info."""
    import sqlite3
    if not AUTH_DB.exists():
        return []
    dow = DAY_NAMES[datetime.now().weekday()]
    try:
        conn = sqlite3.connect(f"file:{AUTH_DB}?mode=ro", uri=True)
        rows = conn.execute(
            "SELECT cs.client_name AS name, cs.shift "
            "FROM client_schedule cs WHERE cs.day_of_week = ?",
            (dow,),
        ).fetchall()
        conn.close()
        return [{"name": r[0], "shift": r[1]} for r in rows]
    except sqlite3.Error:
        return []


@router.get("/attendance-live/api/data")
def attendance_live_data():
    """Return today's attendance data as JSON."""
    signins = _get_today_signins()
    clients = _get_today_clients()
    today = date.today().isoformat()
    return JSONResponse({
        "date": today,
        "total_scheduled": len(clients),
        "signed_in": len(signins),
        "clients": clients,
        "signins": signins,
    })


@router.get("/attendance-live")
def attendance_live_page():
    """Serve the live attendance dashboard HTML page."""
    html = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GOJ Live Attendance</title>
<style>
  body { background:#06080a; color:#e8f2ea; font-family:-apple-system,sans-serif; margin:0; padding:24px; }
  h1 { font-size:44px; margin:0 0 8px; color:#7bc98e; }
  .meta { font-size:26px; color:#8aa; margin-bottom:24px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:14px; }
  .card { border-radius:12px; padding:16px; font-size:26px; background:#0e1410; border:1px solid #1e2a22; }
  .card.present { border-color:#5d9b6b; background:#0f1f14; color:#9fe8b2; }
  .card.absent  { border-color:#7a3b3b; background:#1c1010; color:#e8a0a0; }
  .card .name { font-weight:700; font-size:30px; }
  .card .sub  { font-size:22px; color:#8aa; margin-top:6px; }
</style></head>
<body>
  <h1>GOJ ATTENDANCE</h1>
  <div class="meta" id="meta">Loading…</div>
  <div class="grid" id="grid"></div>
<script>
const API = '/attendance-live/api/data';
function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function fmtTime(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  return d.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',hour12:false});
}
async function refresh() {
  try {
    const r = await fetch(API);
    const d = await r.json();
    document.getElementById('meta').textContent =
      d.date + ' — ' + d.signed_in + '/' + d.total_scheduled + ' signed in';
    const grid = document.getElementById('grid');
    grid.innerHTML = '';
    for (const c of d.clients) {
      const ts = d.signins[c.name] || '';
      const card = document.createElement('div');
      card.className = 'card ' + (ts ? 'present' : 'absent');
      card.innerHTML = '<div class="name">' + esc(c.name) + '</div>' +
        '<div class="sub">' + (ts ? '✅ ' + fmtTime(ts) : 'not yet') +
        (c.shift ? ' · S' + esc(c.shift) : '') + '</div>';
      grid.appendChild(card);
    }
  } catch (e) {
    document.getElementById('meta').textContent = 'Error loading: ' + e;
  }
}
refresh();
setInterval(refresh, 30000);
</script></body></html>"""
    return HTMLResponse(html)
