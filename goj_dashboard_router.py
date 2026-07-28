"""
GOJ Comprehensive Dashboard — goj.goldhealthsys.com
====================================================
FastAPI router serving the full Garden of Joy operations dashboard.

Routes:
    /                    → Full dashboard HTML
    /api/dashboard/data  → JSON data endpoint (all metrics)
    /api/dashboard/health → Service health check
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pathlib import Path
import sqlite3
import json
import subprocess
from datetime import datetime, date

router = APIRouter(tags=["goj-dashboard"])

DB_PATH = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
OUTPUT_DIR = Path.home() / "Documents" / "goj files" / "output_docs"
SIGNATURES_DIR = Path.home() / "Documents" / "goj files" / "dashboard" / "documents" / "signatures"

DAY_CODES = {"M": "Monday", "T": "Tuesday", "W": "Wednesday", "TH": "Thursday", "F": "Friday", "Su": "Sunday"}
DAY_COLUMNS = {
    "M": "day_M_actual", "T": "day_T_actual", "W": "day_W_actual",
    "TH": "day_TH_actual", "F": "day_F_actual", "Su": "day_Su_actual"
}


def query_db(query: str, params: tuple = ()) -> list:
    """Run a query against auth_tracker.db."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        return [{"error": str(e)}]


@router.get("/api/dashboard/data")
async def dashboard_data():
    """Return all dashboard metrics as JSON."""
    today = date.today()
    day_code = today.strftime("%a")
    # Map Python day codes to GOJ codes
    goj_map = {"Mon": "M", "Tue": "T", "Wed": "W", "Thu": "TH", "Fri": "F", "Sat": "M", "Sun": "Su"}
    today_goj = goj_map.get(day_code, "M")
    day_col = DAY_COLUMNS.get(today_goj, "day_M_actual")

    # Total clients
    total = query_db("SELECT COUNT(*) as count FROM clients")[0]["count"]

    # Active clients
    active = query_db("SELECT COUNT(*) as count FROM clients WHERE active=1")[0]["count"]

    # Attendance today (both shifts)
    s1 = query_db(f"SELECT COUNT(*) as count FROM clients WHERE {day_col}=1")[0]["count"]
    s2 = query_db(f"SELECT COUNT(*) as count FROM clients WHERE {day_col}=2")[0]["count"]

    # By plan type
    plans = query_db("""
        SELECT plan_canonical, COUNT(*) as count 
        FROM clients WHERE active=1 
        GROUP BY plan_canonical ORDER BY count DESC
    """)

    # Transport (TR)
    tr_count = query_db(f"SELECT COUNT(*) as count FROM clients WHERE {day_col} IN (1,2) AND transportation='TR'")[0]["count"]

    # Authorization expirations (next 30 days)
    expiring = query_db("""
        SELECT a.client_name, a.payer_canonical as plan_type, a.service_end_date as auth_end,
               c.transportation as transport
        FROM authorization a
        LEFT JOIN clients c ON c.name = a.client_name
        WHERE a.service_end_date <= date('now', '+30 days') AND a.service_end_date >= date('now')
        ORDER BY a.service_end_date LIMIT 20
    """)

    # Recent documents in output_docs
    docs = []
    for f in sorted(OUTPUT_DIR.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)[:20]:
        docs.append({
            "name": f.name,
            "size_kb": round(f.stat().st_size / 1024, 1),
            "mtime": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        })

    # Menu history (last 7 days)
    menu_history = query_db("""
        SELECT cm.client_name, cm.main as main_dish, cm.side, cm.day, cm.week_start, c.transportation as transport
        FROM client_menus cm
        LEFT JOIN clients c ON c.name = cm.client_name
        WHERE cm.week_start >= date('now', '-14 days')
        ORDER BY cm.week_start DESC, cm.day, cm.client_name
        LIMIT 200
    """)

    # Sign-in history (last 30 days from attendance_log)
    signin_history = query_db("""
        SELECT client_name, log_date, shift, time_in, time_out, source_file
        FROM attendance_log
        WHERE log_date >= date('now', '-30 days')
        ORDER BY log_date DESC, shift, client_name
        LIMIT 200
    """)

    # If attendance_log is empty, fall back to attendance_staged_rows
    if not signin_history:
        signin_history = query_db("""
            SELECT client_name, staged_at as log_date, '1' as shift, time_in, time_out, source_file
            FROM attendance_staged_rows
            WHERE staged_at >= date('now', '-30 days')
            ORDER BY staged_at DESC
            LIMIT 200
        """)

    # Extracted signatures
    signatures = []
    if SIGNATURES_DIR.exists():
        for sig_dir in sorted(SIGNATURES_DIR.glob("*/")):
            pngs = list(sig_dir.glob("*.png"))
            if pngs:
                signatures.append({
                    "document": sig_dir.name,
                    "count": len(pngs),
                    "files": [str(p.relative_to(SIGNATURES_DIR)) for p in pngs[:5]]
                })

    # Authorization details per client (active auths)
    auths_active = query_db("""
        SELECT a.client_name, a.payer_canonical as plan_type,
               a.service_start_date as auth_start, a.service_end_date as auth_end,
               a.authorization_number as visit_type,
               c.transportation as transport, c.address
        FROM authorization a
        LEFT JOIN clients c ON c.name = a.client_name
        WHERE a.service_end_date >= date('now')
        ORDER BY a.service_end_date
        LIMIT 100
    """)

    # Recent OCR jobs
    ocr_jobs = query_db("""
        SELECT file_path, doc_type, processed_at, status
        FROM goj_file_registry
        ORDER BY processed_at DESC LIMIT 20
    """)

    # Service health
    services = {}
    for name, port in [("REX Backend", 8000), ("GOJ Dashboard", 8080), ("Tiger Claw Hub", 9000), ("BBG Ops", 8100), ("n8n", 5678)]:
        try:
            r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--connect-timeout", "3",
                               f"http://127.0.0.1:{port}"], capture_output=True, text=True, timeout=5)
            services[name] = {"port": port, "up": r.stdout.strip() not in ("", "000")}
        except:
            services[name] = {"port": port, "up": False}

    # Weekly attendance breakdown
    weekly = {}
    for code, col in DAY_COLUMNS.items():
        s1c = query_db(f"SELECT COUNT(*) as count FROM clients WHERE {col}=1")[0]["count"]
        s2c = query_db(f"SELECT COUNT(*) as count FROM clients WHERE {col}=2")[0]["count"]
        weekly[DAY_CODES[code]] = {"s1": s1c, "s2": s2c, "total": s1c + s2c}

    # Driver counts by day
    drivers = {}
    for code, col in DAY_COLUMNS.items():
        dc = query_db(f"SELECT COUNT(*) as count FROM clients WHERE {col} IN (1,2) AND transportation='TR'")[0]["count"]
        drivers[DAY_CODES[code]] = dc

    return {
        "timestamp": datetime.now().isoformat(),
        "clients": {
            "total": total,
            "active": active,
            "attending_today": {"shift_1": s1, "shift_2": s2, "total": s1 + s2},
            "transport_today": tr_count
        },
        "plans": plans,
        "authorizations_expiring": expiring,
        "authorizations_active": auths_active,
        "weekly_attendance": weekly,
        "weekly_drivers": drivers,
        "recent_documents": docs,
        "menu_history": menu_history,
        "signin_history": signin_history,
        "signatures": signatures,
        "ocr_jobs": ocr_jobs,
        "services": services,
        "today": {"day": DAY_CODES.get(today_goj, "Unknown"), "code": today_goj, "date": today.isoformat()}
    }


@router.get("/api/progress")
async def api_progress():
    """Return build progress for the Command Center upgrade."""
    return {
        "timestamp": datetime.now().isoformat(),
        "phases": [
            {"id":"p0","name":"Progress Tracker","status":"done","icon":"📊"},
            {"id":"p1","name":"n8n Dashboard API","status":"done","icon":"🔗"},
            {"id":"p2","name":"Authorization War Room","status":"building","icon":"⚠️"},
            {"id":"p3","name":"Live Attendance Panel","status":"pending","icon":"👥"},
            {"id":"p4","name":"Billing Pipeline","status":"pending","icon":"💰"},
            {"id":"p5","name":"Payer Scorecard","status":"pending","icon":"📈"},
            {"id":"p6","name":"Schedule Commander","status":"pending","icon":"📅"},
            {"id":"p7","name":"Anomaly Detection","status":"pending","icon":"🔍"},
            {"id":"p8","name":"Voice Commands","status":"pending","icon":"🎤"},
            {"id":"p9","name":"Kitchen Command","status":"pending","icon":"🍽️"},
            {"id":"p10","name":"Fleet Command","status":"pending","icon":"🚗"},
            {"id":"p11","name":"Document Hub","status":"pending","icon":"📄"},
            {"id":"p12","name":"Compliance Shield","status":"pending","icon":"🛡️"},
            {"id":"p13","name":"Emergency Response","status":"pending","icon":"🚨"},
            {"id":"p14","name":"Family Portal","status":"pending","icon":"👨‍👩‍👧"},
        ]
    }


@router.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Serve the full GOJ dashboard HTML."""
    return DASHBOARD_HTML


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Garden of Joy — Operations Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root {
  --bg: #0a0f1a;
  --card: #111827;
  --border: #1e293b;
  --text: #e2e8f0;
  --muted: #64748b;
  --accent: #38bdf8;
  --green: #22c55e;
  --red: #ef4444;
  --yellow: #eab308;
  --purple: #a855f7;
  --orange: #f97316;
}
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }
.header { background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%); padding: 24px 32px; border-bottom: 2px solid var(--accent); display: flex; justify-content: space-between; align-items: center; }
.header h1 { font-size: 1.8rem; color: var(--accent); }
.header .subtitle { color: var(--muted); font-size: 0.9rem; margin-top: 4px; }
.header .live { display: flex; gap: 12px; align-items: center; }
.live-dot { width: 10px; height: 10px; background: var(--green); border-radius: 50%; animation: pulse 2s infinite; }
@keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.4; } }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px,1fr)); gap: 16px; padding: 24px; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
.card h3 { font-size: 0.8rem; text-transform: uppercase; color: var(--muted); margin-bottom: 12px; letter-spacing: 1px; }
.stat-row { display: flex; justify-content: space-between; align-items: center; margin: 8px 0; }
.stat-value { font-size: 2rem; font-weight: 700; }
.stat-label { font-size: 0.85rem; color: var(--muted); }
.badge { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; }
.badge-green { background: rgba(34,197,94,0.15); color: var(--green); }
.badge-red { background: rgba(239,68,68,0.15); color: var(--red); }
.badge-yellow { background: rgba(234,179,8,0.15); color: var(--yellow); }
.badge-purple { background: rgba(168,85,247,0.15); color: var(--purple); }
.full-width { grid-column: 1 / -1; }
.chart-container { position: relative; height: 250px; }
table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
th { text-align: left; padding: 8px 12px; color: var(--muted); border-bottom: 1px solid var(--border); font-size: 0.75rem; text-transform: uppercase; }
td { padding: 8px 12px; border-bottom: 1px solid rgba(30,41,59,0.5); }
tr:hover td { background: rgba(56,189,248,0.05); }
.plan-bar { height: 6px; border-radius: 3px; margin-top: 4px; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.grid-3 { display: grid; grid-template-columns: repeat(3,1fr); gap: 12px; }
.mini-stat { text-align: center; padding: 12px; background: rgba(15,23,42,0.5); border-radius: 8px; }
.mini-stat .value { font-size: 1.4rem; font-weight: 700; }
.mini-stat .label { font-size: 0.7rem; color: var(--muted); margin-top: 2px; }
.service-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 6px; }
.service-up { background: var(--green); }
.service-down { background: var(--red); }
.refresh { font-size: 0.75rem; color: var(--muted); }
.loading { text-align: center; padding: 40px; color: var(--muted); }
@media (max-width: 768px) { .grid { grid-template-columns: 1fr; } .grid-2,.grid-3 { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>🌿 Garden of Joy</h1>
    <div class="subtitle">Operations Dashboard — 3152 Brighton 6th St, Brooklyn NY 11235</div>
  </div>
  <div class="live">
    <div class="live-dot"></div>
    <span style="font-size:0.85rem" id="live-time">Loading...</span>
  </div>
</div>

<div class="grid" id="dashboard">
  <div class="loading">⏳ Loading dashboard data...</div>
</div>

<script>
async function loadDashboard() {
  try {
    const resp = await fetch('/api/dashboard/data');
    const d = await resp.json();
    renderDashboard(d);
    document.getElementById('live-time').textContent = 'Live · ' + d.today.date + ' · ' + d.today.day;
  } catch(e) {
    document.getElementById('dashboard').innerHTML = '<div class="loading">❌ Failed to load data. Is the backend running?</div>';
  }
}

function renderDashboard(d) {
  const c = d.clients;
  const services = d.services || {};
  const weekly = d.weekly_attendance || {};
  const plans = d.plans || [];
  const auth = d.authorizations_expiring || [];
  const drivers = d.weekly_drivers || {};
  const docs = d.recent_documents || [];

  // Service status dots
  let serviceHTML = Object.entries(services).map(([name, s]) =>
    `<span><span class="service-dot ${s.up ? 'service-up' : 'service-down'}"></span>${name}</span>`
  ).join(' &nbsp; ');

  const totalAttending = (c.attending_today?.total || 0);
  const s1 = c.attending_today?.shift_1 || 0;
  const s2 = c.attending_today?.shift_2 || 0;

  let planHTML = plans.slice(0, 10).map(p => {
    const pct = Math.round(p.count / c.active * 100);
    const colors = ['#38bdf8','#a855f7','#22c55e','#eab308','#f97316','#ef4444','#ec4899','#06b6d4'];
    const color = colors[plans.indexOf(p) % colors.length];
    return `<div class="stat-row"><span>${p.plan_canonical || 'Unknown'}</span><span>${p.count} (${pct}%)</span></div>
            <div class="plan-bar" style="width:${pct}%;background:${color}"></div>`;
  }).join('');

  let authHTML = auth.slice(0, 10).map(a =>
    `<tr><td>${a.client_name || '?'}</td><td><span class="badge badge-yellow">${a.plan_type || '?'}</span></td><td>${a.auth_end || '?'}</td><td>${a.transport || ''}</td></tr>`
  ).join('');

  let docsHTML = docs.slice(0, 8).map(f =>
    `<tr><td>${f.name}</td><td>${f.size_kb} KB</td><td>${f.mtime}</td></tr>`
  ).join('');

  let menuHTML = (d.menu_history || []).slice(0, 30).map(m =>
    `<tr><td>${m.client_name || '?'}</td><td>${m.main_dish || ''}</td><td>${m.side || ''}</td><td>${m.day || ''}</td><td>${m.week_start || ''}</td><td><span class="badge ${m.transport === 'TR' ? 'badge-yellow' : ''}">${m.transport || ''}</span></td></tr>`
  ).join('');

  let signinHTML = (d.signin_history || []).slice(0, 30).map(s =>
    `<tr><td>${s.client_name || '?'}</td><td>${s.log_date || ''}</td><td>${s.shift || ''}</td><td>${s.time_in || ''} / ${s.time_out || ''}</td></tr>`
  ).join('');

  let sigHTML = (d.signatures || []).map(s =>
    `<div class="stat-row"><span>📁 ${s.document}</span><span>${s.count} signatures</span></div>`
  ).join('') || '<div class="stat-row"><span>No signatures yet</span></div>';

  let authActiveHTML = (d.authorizations_active || []).slice(0, 30).map(a =>
    `<tr><td>${a.client_name || '?'}</td><td><span class="badge badge-purple">${a.plan_type || '?'}</span></td><td>${a.auth_start || ''}</td><td>${a.auth_end || ''}</td><td>${a.visit_type || ''}</td><td>${a.transport || ''}</td></tr>`
  ).join('');

  document.getElementById('dashboard').innerHTML = `
    <!-- Row 1: Key Metrics -->
    <div class="card"><h3>👥 Clients</h3>
      <div class="grid-2">
        <div class="mini-stat"><div class="value" style="color:var(--accent)">${c.total}</div><div class="label">Total</div></div>
        <div class="mini-stat"><div class="value" style="color:var(--green)">${c.active}</div><div class="label">Active</div></div>
      </div>
      <div style="margin-top:12px"><span class="badge badge-green">Active ${Math.round(c.active/c.total*100)}%</span></div>
    </div>

    <div class="card"><h3>📋 Today's Attendance</h3>
      <div class="grid-2">
        <div class="mini-stat"><div class="value" style="color:var(--accent)">${totalAttending}</div><div class="label">Total Today</div></div>
        <div class="mini-stat"><div class="value" style="color:var(--orange)">${c.transport_today || 0}</div><div class="label">Need Transport (TR)</div></div>
      </div>
      <div class="grid-2" style="margin-top:12px">
        <div class="mini-stat"><div class="value">${s1}</div><div class="label">Shift 1 (9AM-1PM)</div></div>
        <div class="mini-stat"><div class="value">${s2}</div><div class="label">Shift 2 (1:15-5:15)</div></div>
      </div>
    </div>

    <div class="card"><h3>🟢 Services</h3>
      <div style="display:flex;flex-direction:column;gap:8px">${serviceHTML}</div>
    </div>

    <!-- Row 2: Weekly Attendance Chart -->
    <div class="card full-width"><h3>📊 Weekly Attendance by Shift</h3>
      <div class="chart-container"><canvas id="weeklyChart"></canvas></div>
    </div>

    <!-- Row 3: Driver Routes + Plan Distribution -->
    <div class="card"><h3>🚗 Drivers (TR) by Day</h3>
      <div class="chart-container"><canvas id="driverChart"></canvas></div>
    </div>

    <div class="card"><h3>📦 Plan Distribution</h3>
      ${planHTML || '<div class="stat-row"><span>No plan data</span></div>'}
    </div>

    <!-- Row 4: Auth Expirations -->
    <div class="card full-width"><h3>⚠️ Authorizations Expiring (Next 30 Days)</h3>
      <table><thead><tr><th>Client</th><th>Plan</th><th>Expires</th><th>Transport</th></tr></thead>
      <tbody>${authHTML || '<tr><td colspan="4">No expiring authorizations</td></tr>'}</tbody></table>
    </div>

    <!-- Row 5: Recent Documents -->
    <div class="card full-width"><h3>📄 Recent Documents (output_docs/)</h3>
      <table><thead><tr><th>File</th><th>Size</th><th>Modified</th></tr></thead>
      <tbody>${docsHTML || '<tr><td colspan="3">No documents found</td></tr>'}</tbody></table>
    </div>

    <!-- Row 6: Menu History -->
    <div class="card full-width"><h3>🍽️ Menu History (Last 14 Days)</h3>
      <table><thead><tr><th>Client</th><th>Main Dish</th><th>Side</th><th>Day</th><th>Week</th><th>Transport</th></tr></thead>
      <tbody>${menuHTML}</tbody></table>
    </div>

    <!-- Row 7: Sign-In History + Signatures -->
    <div class="card"><h3>✍️ Sign-In History (Last 30 Days)</h3>
      <table><thead><tr><th>Client</th><th>Date</th><th>Shift</th><th>In/Out</th></tr></thead>
      <tbody>${signinHTML}</tbody></table>
    </div>

    <div class="card"><h3>🖊️ Extracted Signatures</h3>
      ${sigHTML || '<div class="stat-row"><span>No signatures extracted yet. Run CC_ocr_pipeline.py on a sign-in sheet.</span></div>'}
    </div>

    <!-- Row 8: Active Authorizations -->
    <div class="card full-width"><h3>📋 Active Authorizations</h3>
      <table><thead><tr><th>Client</th><th>Plan</th><th>Auth Start</th><th>Auth End</th><th>Visit Type</th><th>Transport</th></tr></thead>
      <tbody>${authActiveHTML}</tbody></table>
    </div>
  `;

  // Charts
  const days = Object.keys(weekly);
  const s1Data = days.map(d => weekly[d]?.s1 || 0);
  const s2Data = days.map(d => weekly[d]?.s2 || 0);
  const driverData = days.map(d => drivers[d] || 0);

  new Chart(document.getElementById('weeklyChart'), {
    type: 'bar',
    data: {
      labels: days,
      datasets: [
        { label: 'Shift 1', data: s1Data, backgroundColor: '#38bdf8', borderRadius: 4 },
        { label: 'Shift 2', data: s2Data, backgroundColor: '#a855f7', borderRadius: 4 }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#94a3b8' } } },
      scales: {
        x: { ticks: { color: '#64748b' }, grid: { color: '#1e293b' } },
        y: { ticks: { color: '#64748b' }, grid: { color: '#1e293b' } }
      }
    }
  });

  new Chart(document.getElementById('driverChart'), {
    type: 'line',
    data: {
      labels: days,
      datasets: [{ label: 'TR Clients', data: driverData, borderColor: '#f97316', backgroundColor: 'rgba(249,115,22,0.1)', fill: true, tension: 0.3 }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#94a3b8' } } },
      scales: {
        x: { ticks: { color: '#64748b' }, grid: { color: '#1e293b' } },
        y: { ticks: { color: '#64748b' }, grid: { color: '#1e293b' } }
      }
    }
  });
}

loadDashboard();
setInterval(loadDashboard, 60000);
</script>
</body>
</html>"""
