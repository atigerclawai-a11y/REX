#!/usr/bin/env python3
"""
CC_attendance.py — Unified Attendance Backend
───────────────────────────────────────────────
Port 8101 · GHS Staff Clock-In · Hub integration endpoint

Three data streams → one encrypted DB:
  1. WiFi/MAC    — router detects staff phone MAC → clock_in/clock_out
  2. ZK Biometric — fingerprint_id / rfid_card → clock_in/clock_out  
  3. Driver PWA  — GPS-verified mobile clock-in → clock_in/clock_out

All writes via CC_attendance_db (AES-256-GCM + audit hash chain).
Read endpoints serve hub dashboard (GOJ_ATTEND → :8101).
"""
from __future__ import annotations

import json, logging, os, re, sys, uuid
from datetime import date, datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs as url_parse_qs

# ── INIT ──────────────────────────────────────────────────────────────
HOME = Path.home()
LOG_DIR = HOME / "Desktop/REX/logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=LOG_DIR / "attendance.log",
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

sys.path.insert(0, str(HOME / "Desktop/REX"))
from CC_attendance_db import AttendanceDB, decrypt_field

db = AttendanceDB()

# ── HELPERS ────────────────────────────────────────────────────────────

ROUTES = {}

def route(pattern: str):
    """Register a regex route."""
    def decorator(fn):
        ROUTES[re.compile(pattern)] = fn
        return fn
    return decorator

def json_resp(handler, data, status=200):
    body = json.dumps(data, default=str).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)

def html_resp(handler, html, status=200):
    body = html.encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)

def read_body(handler) -> dict:
    length = int(handler.headers.get("Content-Length", 0))
    if length == 0:
        return {}
    return json.loads(handler.rfile.read(length))

def query_params(handler) -> dict:
    """Parse ?key=val from path."""
    qs = {}
    if "?" in handler.path:
        for k, v in url_parse_qs(handler.path.split("?")[1]).items():
            qs[k] = v[0]
    return qs

def staff_row_to_dict(r) -> dict:
    """Convert sqlite3.Row to dict, decrypting phone."""
    d = dict(r)
    if d.get("phone"):
        try:
            d["phone"] = decrypt_field(d["phone"])
        except Exception:
            pass
    return d

# ── ENDPOINTS ─────────────────────────────────────────────────────────

@route(r"^/health/?$")
def health(handler, _match):
    with db.conn() as cn:
        staff_cnt = cn.execute("SELECT COUNT(*) FROM staff WHERE active=1").fetchone()[0]
        audit_cnt = cn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    json_resp(handler, {
        "status": "ok",
        "service": "CC_attendance",
        "port": 8101,
        "staff_count": staff_cnt,
        "audit_entries": audit_cnt,
        "db": str(db.db_path),
    })


@route(r"^/api/staff/?$")
def staff_list(handler, _match):
    if handler.command == "GET":
        active_only = query_params(handler).get("all", "").lower() != "true"
        rows = db.list_staff(active_only=active_only)
        json_resp(handler, {"staff": rows, "count": len(rows)})
    elif handler.command == "POST":
        data = read_body(handler)
        name = data.get("name", "").strip()
        if not name:
            return json_resp(handler, {"error": "name required"}, 400)
        sid = db.register_staff(
            name=name,
            phone=data.get("phone"),
            mac=data.get("mac"),
            department=data.get("department", "staff"),
            rfid=data.get("rfid"),
            fingerprint_id=data.get("fingerprint_id"),
        )
        json_resp(handler, {"staff_id": sid, "name": name}, 201)
    else:
        json_resp(handler, {"error": "method not allowed"}, 405)


@route(r"^/api/staff/(?P<staff_id>\d+)/?$")
def staff_one(handler, match):
    staff_id = int(match.group("staff_id"))
    row = db.get_staff(staff_id)
    if not row:
        return json_resp(handler, {"error": "not found"}, 404)
    json_resp(handler, row)


@route(r"^/api/event/?$")
def event_wifi(handler, _match):
    """WiFi/Router MAC detection event. POST {mac: 'aa:bb:cc:dd:ee:ff'}"""
    if handler.command != "POST":
        return json_resp(handler, {"error": "POST only"}, 405)

    data = read_body(handler)
    mac = data.get("mac", "").strip()
    if not mac:
        return json_resp(handler, {"error": "mac required"}, 400)

    row = db.get_staff_by_mac(mac)
    if not row:
        logging.info("MAC %s — unknown device", mac)
        return json_resp(handler, {"action": "unknown_mac", "mac": mac})

    staff = dict(row)
    open_sid = db.get_session_id(staff["id"])
    action = "out" if open_sid else "in"
    event_type = "clock_out" if open_sid else "clock_in"
    session_id = open_sid or str(uuid.uuid4())

    eid = db.log_event(
        staff_id=staff["id"],
        event_type=event_type,
        method="wifi",
        source_device=mac,
        session_id=session_id,
    )

    logging.info("%s clocked %s (wifi MAC, event=%d)", staff["name"], action, eid)
    json_resp(handler, {
        "action": action,
        "staff_id": staff["id"],
        "name": staff["name"],
        "event_id": eid,
        "session_id": session_id,
    })


@route(r"^/api/biometric/?$")
def event_biometric(handler, _match):
    """ZK Biometric event. POST {fingerprint_id: 'fp_001'} or {rfid: 'card_A'}"""
    if handler.command != "POST":
        return json_resp(handler, {"error": "POST only"}, 405)

    data = read_body(handler)
    fp_id = data.get("fingerprint_id", "").strip()
    rfid = data.get("rfid", "").strip()

    if fp_id:
        row = db.get_staff_by_fingerprint(fp_id)
    elif rfid:
        row = db.get_staff_by_rfid(rfid)
    else:
        return json_resp(handler, {"error": "fingerprint_id or rfid required"}, 400)

    if not row:
        logging.info("Biometric %s/%s — unknown", fp_id or rfid, "")
        return json_resp(handler, {"action": "unknown_biometric", "id": fp_id or rfid})

    staff = dict(row)
    open_sid = db.get_session_id(staff["id"])
    action = "out" if open_sid else "in"
    event_type = "clock_out" if open_sid else "clock_in"
    session_id = open_sid or str(uuid.uuid4())

    eid = db.log_event(
        staff_id=staff["id"],
        event_type=event_type,
        method="zk_biometric" if fp_id else "rfid",
        source_device=fp_id or rfid,
        session_id=session_id,
    )

    logging.info("%s clocked %s (ZK, event=%d)", staff["name"], action, eid)
    json_resp(handler, {
        "action": action,
        "staff_id": staff["id"],
        "name": staff["name"],
        "event_id": eid,
        "session_id": session_id,
    })


@route(r"^/api/driver/clock/?$")
def event_driver(handler, _match):
    """Driver PWA clock-in with GPS. POST {staff_id: 1, lat: 40.68, lon: -73.94}"""
    if handler.command != "POST":
        return json_resp(handler, {"error": "POST only"}, 405)

    data = read_body(handler)
    staff_id = data.get("staff_id")
    if not staff_id:
        return json_resp(handler, {"error": "staff_id required"}, 400)

    row = db.get_staff(staff_id)
    if not row:
        return json_resp(handler, {"error": "staff not found"}, 404)

    open_sid = db.get_session_id(staff_id)
    action = "out" if open_sid else "in"
    event_type = "clock_out" if open_sid else "clock_in"
    session_id = open_sid or str(uuid.uuid4())

    lat = data.get("lat")
    lon = data.get("lon")

    eid = db.log_event(
        staff_id=staff_id,
        event_type=event_type,
        method="mobile_pwa",
        source_device="driver_pwa",
        gps_lat=lat,
        gps_lon=lon,
        session_id=session_id,
    )

    logging.info(
        "%s clocked %s (Driver PWA, event=%d, gps=%s,%s)",
        row["name"], action, eid, lat, lon,
    )
    json_resp(handler, {
        "action": action,
        "staff_id": staff_id,
        "name": row["name"],
        "event_id": eid,
        "gps_verified": lat is not None and lon is not None,
    })


@route(r"^/api/attendance/today/?$")
def attendance_today(handler, _match):
    """Today's staff attendance with computed hours."""
    hours = db.get_hours(target_date=date.today().isoformat())
    json_resp(handler, {"date": date.today().isoformat(), "staff": hours})


@route(r"^/api/hours/?$")
def hours_range(handler, _match):
    """Hours for a date range. ?from=YYYY-MM-DD&to=YYYY-MM-DD&staff_id=N"""
    params = query_params(handler)
    staff_id = params.get("staff_id")
    date_from = params.get("from", (date.today() - timedelta(days=7)).isoformat())
    date_to = params.get("to", date.today().isoformat())

    if staff_id:
        # Raw events for one staff
        events = db.get_todays_events()  # will be overridden by range query
        with db.conn() as cn:
            rows = cn.execute(
                """SELECT e.*, s.name FROM attendance_events e
                   JOIN staff s ON s.id = e.staff_id
                   WHERE e.staff_id = ? AND DATE(e.ts) BETWEEN ? AND ?
                   ORDER BY e.ts""",
                (int(staff_id), date_from, date_to),
            ).fetchall()
        json_resp(handler, {
            "staff_id": int(staff_id),
            "from": date_from,
            "to": date_to,
            "events": [dict(r) for r in rows],
        })
    else:
        hours = db.get_hours(start_date=date_from, end_date=date_to)
        json_resp(handler, {"from": date_from, "to": date_to, "staff": hours})


@route(r"^/api/compliance/?$")
def compliance(handler, _match):
    """Active compliance flags — overtime, meal breaks, late arrivals."""
    flags = db.get_active_flags()
    json_resp(handler, {"flags": flags, "count": len(flags)})


@route(r"^/api/compliance/generate/?$")
def compliance_generate(handler, _match):
    """Generate today's compliance flags from attendance data."""
    today = date.today().isoformat()
    hours = db.get_hours(target_date=today)
    generated = []

    for staff in hours:
        sid = staff["staff_id"]
        name = staff["name"]
        total = staff["total_seconds"]

        # Daily overtime: >8h = flag, >7h = warning
        if total > 28_800:
            fid = db.create_flag(sid, "daily_overtime",
                                 threshold="8.0h",
                                 actual=f"{total/3600:.1f}h")
            generated.append({"type": "daily_overtime", "staff": name, "flag_id": fid})

        # Meal break: NYC requires 30min for shifts >6h
        if total > 21_600:
            sessions = staff["sessions"]
            has_30m_break = any(
                s.get("duration_seconds", 0) >= 1800 and
                s.get("out") is not None  # completed break
                for s in sessions
            )
            if not has_30m_break:
                fid = db.create_flag(sid, "missed_break",
                                     threshold="30min",
                                     actual="none_recorded")
                generated.append({"type": "missed_break", "staff": name, "flag_id": fid})

        # Late arrival: >15min after 9am
        sessions = staff["sessions"]
        if sessions:
            first_in = sessions[0].get("in")
            if first_in:
                try:
                    in_dt = datetime.fromisoformat(first_in)
                    expected = in_dt.replace(hour=9, minute=0, second=0, microsecond=0)
                    if in_dt > expected + timedelta(minutes=15):
                        late_mins = round((in_dt - expected).total_seconds() / 60)
                        fid = db.create_flag(sid, "late_arrival",
                                             threshold="9:15 AM",
                                             actual=f"{in_dt.strftime('%H:%M')} ({late_mins}min late)")
                        generated.append({"type": "late_arrival", "staff": name,
                                          "late_minutes": late_mins, "flag_id": fid})
                except (ValueError, TypeError):
                    pass

    json_resp(handler, {"generated": generated, "count": len(generated)})


@route(r"^/api/audit/?$")
def audit_verify(handler, _match):
    valid, msg = db.verify_audit_chain()
    json_resp(handler, {"valid": valid, "message": msg})


# ── DASHBOARD ─────────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GHS Attendance · 8101</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0a0a0a;color:#e0e0e0;padding:24px}
  h1{color:#f0c040;font-size:22px;margin-bottom:4px}
  .sub{color:#888;font-size:13px;margin-bottom:20px}
  .card{background:#1a1a1a;border:1px solid #333;border-radius:8px;padding:16px;margin-bottom:16px}
  .card h2{font-size:16px;color:#ccc;margin-bottom:8px;border-bottom:1px solid #333;padding-bottom:6px}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #2a2a2a}
  th{color:#888;font-weight:600}
  .in{color:#4caf50}.out{color:#f44336}.late{color:#ff9800}
  .flag{background:#2a1a1a;border-left:3px solid #f44336;padding:8px 12px;margin:6px 0;font-size:13px}
  .flag.warn{border-color:#ff9800}
  .ok{color:#4caf50}
  .refresh{float:right;color:#f0c040;cursor:pointer;font-size:12px}
  .small{font-size:12px;color:#666}
  .badge{padding:2px 6px;border-radius:4px;font-size:11px}
  .badge.green{background:#1b5e20;color:#81c784}
  .badge.red{background:#b71c1c;color:#ef9a9a}
</style>
</head>
<body>
<h1>🕐 GHS Attendance</h1>
<div class="sub">Port 8101 · Unified Clock-In · <span id="time">--</span></div>

<div class="card">
  <h2>Today's Hours <span class="refresh" onclick="loadAll()">⟳ refresh</span></h2>
  <div id="today">Loading…</div>
</div>

<div class="card">
  <h2>⚠️ Compliance Flags <span class="refresh" onclick="flagGen()">⚙ generate</span></h2>
  <div id="flags">Loading…</div>
</div>

<div class="card">
  <h2>API Endpoints</h2>
  <table>
    <tr><th>Method</th><th>Path</th><th>Description</th></tr>
    <tr><td>GET</td><td>/health</td><td>Health + stats</td></tr>
    <tr><td>GET/POST</td><td>/api/staff</td><td>List / register staff</td></tr>
    <tr><td>GET</td><td>/api/staff/{id}</td><td>Staff detail</td></tr>
    <tr><td>POST</td><td>/api/event</td><td>WiFi/MAC clock event</td></tr>
    <tr><td>POST</td><td>/api/biometric</td><td>ZK fingerprint/RFID event</td></tr>
    <tr><td>POST</td><td>/api/driver/clock</td><td>Driver PWA clock-in/out</td></tr>
    <tr><td>GET</td><td>/api/attendance/today</td><td>Today's hours</td></tr>
    <tr><td>GET</td><td>/api/compliance</td><td>Active flags</td></tr>
    <tr><td>GET</td><td>/api/compliance/generate</td><td>Generate today's flags</td></tr>
    <tr><td>GET</td><td>/api/audit</td><td>Verify audit chain</td></tr>
  </table>
</div>

<script>
async function loadAll() {
  try {
    const t = await fetch('/api/attendance/today').then(r=>r.json())
    const f = await fetch('/api/compliance').then(r=>r.json())
    renderToday(t)
    renderFlags(f)
    document.getElementById('time').textContent = new Date().toLocaleTimeString()
  } catch(e) { document.getElementById('today').textContent='Error loading' }
}

async function flagGen() {
  await fetch('/api/compliance/generate')
  loadAll()
}

function renderToday(data) {
  if (!data.staff || !data.staff.length)
    return document.getElementById('today').innerHTML = '<p class="small">No attendance today.</p>'
  let h = '<table><tr><th>Staff</th><th>Clock In</th><th>Clock Out</th><th>Hours</th><th>Status</th></tr>'
  data.staff.forEach(s => {
    const st = s.status==='in' ? '<span class="in">IN</span>' : '<span class="out">OUT</span>'
    const fi = s.sessions?.length ? s.sessions[0].in?.slice(11,19) : '--'
    const lo = s.sessions?.length && s.sessions[s.sessions.length-1].out
      ? s.sessions[s.sessions.length-1].out.slice(11,19) : '--'
    h += `<tr><td>${s.name}</td><td>${fi}</td><td>${lo}</td><td>${s.total_fmt}</td><td>${st}</td></tr>`
  })
  h+='</table>'
  document.getElementById('today').innerHTML = h
}

function renderFlags(data) {
  if (!data.flags || !data.flags.length)
    return document.getElementById('flags').innerHTML='<p class="ok">✅ No compliance flags</p>'
  let h = ''
  data.flags.forEach(f => {
    const cls = f.flag_type.includes('overtime') ? 'flag warn' : 'flag'
    h += `<div class="${cls}"><strong>${f.flag_type}</strong>: ${f.name} — ${f.actual_value || ''}</div>`
  })
  document.getElementById('flags').innerHTML = h
}

loadAll()
setInterval(loadAll, 30000)
</script>
</body>
</html>"""


# ── HANDLER ───────────────────────────────────────────────────────────

class AttendanceHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/") or "/"
        for pattern, fn in ROUTES.items():
            m = pattern.match(path)
            if m:
                return fn(self, m)
        if path == "/":
            return html_resp(self, DASHBOARD_HTML)
        json_resp(self, {"error": "not found"}, 404)

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/") or "/"
        for pattern, fn in ROUTES.items():
            m = pattern.match(path)
            if m:
                return fn(self, m)
        json_resp(self, {"error": "not found"}, 404)

    def log_message(self, *args):
        pass


# ── MAIN ──────────────────────────────────────────────────────────────

def main(port: int = 8101):
    server = HTTPServer(("127.0.0.1", port), AttendanceHandler)
    msg = f"CC_attendance v1.0 · http://127.0.0.1:{port}"
    logging.info(msg)
    print(msg)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Shutdown")
        server.shutdown()


if __name__ == "__main__":
    main()
