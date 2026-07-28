"""
Datarex Dashboard — powered by GHS (Gold Health Systems)
Flask app serving the GOJ pipeline data in a clean, responsive dashboard.
"""

import sqlite3
import json
import os
from datetime import date, datetime, timedelta

from flask import Flask, render_template, request, jsonify, send_from_directory

app = Flask(__name__)

DB_PATH = "/Users/mainsobhelper/.hermes-cloud/home/goj-pipeline/data/pipeline.db"
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "pipeline.db"))

_WEEKDAY_MAP = {"M": 0, "T": 1, "W": 2, "Th": 3, "F": 4, "Sa": 5, "Su": 6}
_WEEKDAY_NAMES = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}
_SHIFT_LABEL = {1: "Shift 1 (9AM–1PM)", 2: "Shift 2 (1PM–5PM)", 0: "Study Only"}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ── Routes ────────────────────────────────────────────────────────


@app.route("/")
def index():
    """Employee role picker landing page."""
    conn = get_db()
    try:
        drivers = conn.execute(
            "SELECT id, name FROM drivers WHERE active=1 ORDER BY name"
        ).fetchall()
        return render_template("index.html", drivers=[dict(d) for d in drivers])
    finally:
        conn.close()


@app.route("/dashboard")
def dashboard():
    """Admin dashboard view."""
    target_date = request.args.get("date")
    if not target_date:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT date FROM attendance WHERE status='present' ORDER BY date DESC LIMIT 1"
            ).fetchone()
            target_date = row["date"] if row else date.today().isoformat()
        finally:
            conn.close()
    return render_template("dashboard.html", target_date=target_date)


@app.route("/api/overview")
def api_overview():
    """JSON: overview stats for a given date."""
    target_date = request.args.get("date", date.today().isoformat())
    conn = get_db()
    try:
        # Attendance counts (shift comes from clients table)
        shift1_total = conn.execute(
            """SELECT COUNT(*) FROM daily_attendance_grid dag
            JOIN clients c ON dag.client_id = c.internal_client_id
            WHERE dag.date=? AND dag.attended=1 AND c.active=1 AND c.shift=1""",
            (target_date,),
        ).fetchone()[0]
        shift2_total = conn.execute(
            """SELECT COUNT(*) FROM daily_attendance_grid dag
            JOIN clients c ON dag.client_id = c.internal_client_id
            WHERE dag.date=? AND dag.attended=1 AND c.active=1 AND c.shift=2""",
            (target_date,),
        ).fetchone()[0]

        shift1_present = conn.execute(
            "SELECT COUNT(*) FROM attendance WHERE date=? AND shift=1 AND status='present'",
            (target_date,),
        ).fetchone()[0]
        shift2_present = conn.execute(
            "SELECT COUNT(*) FROM attendance WHERE date=? AND shift=2 AND status='present'",
            (target_date,),
        ).fetchone()[0]

        # Meal totals
        meals = conn.execute(
            """
            SELECT shift, SUM(quantity) as total, COUNT(*) as items
            FROM daily_meal_counts WHERE date=? GROUP BY shift
            """,
            (target_date,),
        ).fetchall()

        # By category
        cats = conn.execute(
            """
            SELECT COALESCE(mi.category, 'other') as cat, SUM(dmc.quantity) as total
            FROM daily_meal_counts dmc
            LEFT JOIN menu_items mi ON dmc.item_name = mi.item_name
            WHERE dmc.date=? GROUP BY mi.category
            """,
            (target_date,),
        ).fetchall()

        # Active pickup (from grid — uses clients for shift)
        pickup_count = conn.execute(
            "SELECT COUNT(*) FROM daily_attendance_grid WHERE date=? AND attended=1",
            (target_date,),
        ).fetchone()[0]

        # Total clients
        total_clients = conn.execute(
            "SELECT COUNT(*) FROM clients WHERE active=1"
        ).fetchone()[0]

        # Build meal entries with attendance-derived people counts
        meal_entries = []
        for m in meals:
            shift = m["shift"]
            people = shift1_present if shift == 1 else shift2_present
            meal_entries.append({
                "shift": shift,
                "label": _SHIFT_LABEL.get(shift, f"Shift {shift}"),
                "people_served": people,
                "total_items": m["total"],
                "distinct_items": m["items"],
            })

        return jsonify(
            {
                "date": target_date,
                "total_clients": total_clients,
                "pickup_count": pickup_count,
                "shifts": [
                    {
                        "shift": 1,
                        "label": "Shift 1 (9AM–1PM)",
                        "expected": shift1_total,
                        "present": shift1_present,
                    },
                    {
                        "shift": 2,
                        "label": "Shift 2 (1PM–5PM)",
                        "expected": shift2_total,
                        "present": shift2_present,
                    },
                ],
                "meals": meal_entries,
                "categories": [{"name": c["cat"], "total": c["total"]} for c in cats],
            }
        )
    finally:
        conn.close()


@app.route("/api/routes")
def api_routes():
    """JSON: route stops for a given date."""
    target_date = request.args.get("date", date.today().isoformat())
    conn = get_db()
    try:
        # Get the day abbreviation for the target date
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        day_abbr = {0: "M", 1: "T", 2: "W", 3: "Th", 4: "F", 5: "Sa", 6: "Su"}[
            dt.weekday()
        ]

        stops = conn.execute(
            """
            SELECT c.internal_client_id, c.first_name, c.last_name, c.address,
                   c.phone, c.schedule, c.shift,
                   COALESCE(a.status, 'pending') as attendance_status
            FROM daily_attendance_grid dag
            JOIN clients c ON dag.client_id = c.internal_client_id
            LEFT JOIN attendance a ON a.client_id = c.internal_client_id
                AND a.date = dag.date AND a.shift = CAST(c.shift AS INTEGER)
            WHERE dag.date = ? AND dag.attended = 1 AND c.active = 1
            ORDER BY c.address
            """,
            (target_date,),
        ).fetchall()

        return jsonify(
            {
                "date": target_date,
                "day": day_abbr,
                "stops": [
                    {
                        "id": s["internal_client_id"],
                        "name": f"{s['first_name']} {s['last_name']}",
                        "address": s["address"],
                        "phone": s["phone"],
                        "shift": s["shift"],
                        "status": s["attendance_status"],
                    }
                    for s in stops
                ],
            }
        )
    finally:
        conn.close()


@app.route("/api/kitchen")
def api_kitchen():
    """JSON: kitchen prep quantities."""
    target_date = request.args.get("date", date.today().isoformat())
    conn = get_db()
    try:
        items = conn.execute(
            """
            SELECT dmc.shift, dmc.item_name, dmc.quantity,
                   COALESCE(mi.category, 'other') as category
            FROM daily_meal_counts dmc
            LEFT JOIN menu_items mi ON dmc.item_name = mi.item_name
            WHERE dmc.date = ?
            ORDER BY dmc.shift, mi.category, dmc.item_name
            """,
            (target_date,),
        ).fetchall()

        # Group by shift
        result = {"date": target_date, "shifts": {}}
        for item in items:
            s = item["shift"]
            if s not in result["shifts"]:
                result["shifts"][s] = {
                    "label": _SHIFT_LABEL.get(s, f"Shift {s}"),
                    "items": [],
                }
            result["shifts"][s]["items"].append(
                {
                    "name": item["item_name"],
                    "qty": item["quantity"],
                    "category": item["category"],
                }
            )

        return jsonify(result)
    finally:
        conn.close()


@app.route("/api/signin")
def api_signin():
    """JSON: sign-in sheet for a given date."""
    target_date = request.args.get("date", date.today().isoformat())
    conn = get_db()
    try:
        attendees = conn.execute(
            """
            SELECT c.internal_client_id, c.first_name, c.last_name,
                   c.shift, c.schedule,
                   COALESCE(a.status, 'pending') as status,
                   a.checkmark_count, a.guest_count
            FROM daily_attendance_grid dag
            JOIN clients c ON dag.client_id = c.internal_client_id
            LEFT JOIN attendance a ON a.client_id = c.internal_client_id
                AND a.date = dag.date AND a.shift = CAST(c.shift AS INTEGER)
            WHERE dag.date = ? AND dag.attended = 1 AND c.active = 1
            ORDER BY c.shift, c.last_name, c.first_name
            """,
            (target_date,),
        ).fetchall()

        shift1 = []
        shift2 = []
        for a in attendees:
            entry = {
                "id": a["internal_client_id"],
                "name": f"{a['first_name']} {a['last_name']}",
                "status": a["status"],
                "checks": a["checkmark_count"],
                "guests": a["guest_count"],
            }
            if a["shift"] == 1:
                shift1.append(entry)
            elif a["shift"] == 2:
                shift2.append(entry)

        present1 = sum(1 for e in shift1 if e["status"] == "present")
        present2 = sum(1 for e in shift2 if e["status"] == "present")

        return jsonify(
            {
                "date": target_date,
                "shift1": {
                    "label": "Shift 1 (9AM–1PM)",
                    "total": len(shift1),
                    "present": present1,
                    "attendees": shift1,
                },
                "shift2": {
                    "label": "Shift 2 (1PM–5PM)",
                    "total": len(shift2),
                    "present": present2,
                    "attendees": shift2,
                },
            }
        )
    finally:
        conn.close()


@app.route("/api/dates")
def api_dates():
    """JSON: available dates for the picker."""
    conn = get_db()
    try:
        dates = conn.execute(
            "SELECT DISTINCT date FROM daily_attendance_grid WHERE attended=1 ORDER BY date DESC LIMIT 90"
        ).fetchall()
        return jsonify({"dates": [d["date"] for d in dates]})
    finally:
        conn.close()


@app.route("/api/drive-scan")
def api_drive_scan():
    """JSON: latest drive scan summary."""
    import glob
    reports_dir = os.path.join(os.path.dirname(__file__), "..", "drive_watcher", "reports")
    reports = sorted(glob.glob(os.path.join(reports_dir, "scan_*.json")), reverse=True)
    if not reports:
        return jsonify({"error": "No scan reports found"}), 404
    with open(reports[0]) as f:
        data = json.load(f)
    total = data["total"]
    rels = data["relationships"]
    categories = [
        {"name": cat, "count": len(items)}
        for cat, items in sorted(rels.items(), key=lambda x: -len(x[1]))
    ]
    return jsonify({
        "total": total,
        "scanned_at": data["scanned_at"],
        "categories": categories,
        "unknown": sum(1 for c in categories if c["name"] == "unknown"),
    })


@app.route("/api/drivers")
def api_drivers():
    """JSON: list all drivers with their assigned clients."""
    conn = get_db()
    try:
        drivers = conn.execute(
            "SELECT id, name, phone, vehicle, active FROM drivers ORDER BY name"
        ).fetchall()
        result = []
        for d in drivers:
            clients = conn.execute(
                "SELECT internal_client_id, first_name, last_name, address, shift, schedule "
                "FROM clients WHERE driver_id=? AND active=1 ORDER BY last_name, first_name",
                (d["id"],),
            ).fetchall()
            result.append({
                "id": d["id"],
                "name": d["name"],
                "phone": d["phone"],
                "vehicle": d["vehicle"],
                "active": d["active"],
                "client_count": len(clients),
                "clients": [
                    {
                        "id": c["internal_client_id"],
                        "name": f"{c['first_name']} {c['last_name']}",
                        "address": c["address"],
                        "shift": c["shift"],
                        "schedule": c["schedule"],
                    }
                    for c in clients
                ],
            })
        # Also count unassigned
        unassigned = conn.execute(
            "SELECT COUNT(*) FROM clients WHERE active=1 AND (driver_id IS NULL OR driver_id=0)"
        ).fetchone()[0]
        return jsonify({"drivers": result, "unassigned": unassigned})
    finally:
        conn.close()


@app.route("/api/drivers/assign", methods=["POST"])
def api_drivers_assign():
    """POST: assign a driver to a client. Body: {client_id, driver_id}"""
    data = request.get_json()
    client_id = data.get("client_id")
    driver_id = data.get("driver_id")  # 0 or null = unassign
    conn = get_db()
    try:
        conn.execute(
            "UPDATE clients SET driver_id=? WHERE internal_client_id=?",
            (driver_id if driver_id else None, client_id),
        )
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "static"), filename
    )


# ── Employee Views ─────────────────────────────────────────────────

@app.route("/driver")
def view_driver():
    """Employee view: driver route sheet."""
    target_date = request.args.get("date", date.today().isoformat())
    driver_id = request.args.get("driver_id")
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    day_abbr = {0: "M", 1: "T", 2: "W", 3: "Th", 4: "F", 5: "Sa", 6: "Su"}[dt.weekday()]
    date_display = f"{_WEEKDAY_NAMES[dt.weekday()]} {target_date}"

    conn = get_db()
    try:
        query = """
            SELECT c.internal_client_id, c.first_name, c.last_name, c.address,
                   c.phone, c.shift, d.name as driver_name
            FROM daily_attendance_grid dag
            JOIN clients c ON dag.client_id = c.internal_client_id
            LEFT JOIN drivers d ON c.driver_id = d.id
            WHERE dag.date = ? AND dag.attended = 1 AND c.active = 1
        """
        params = [target_date]
        if driver_id:
            query += " AND c.driver_id = ?"
            params.append(driver_id)
        query += " ORDER BY c.address"

        stops = conn.execute(query, params).fetchall()
        driver_name = stops[0]["driver_name"] if stops and driver_id else None
        return render_template(
            "employees/driver.html",
            date_display=date_display,
            driver_name=driver_name or ("Driver " + driver_id if driver_id else ""),
            stops=[dict(s) for s in stops],
            now=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
    finally:
        conn.close()


@app.route("/kitchen")
def view_kitchen():
    """Employee view: kitchen prep quantities."""
    target_date = request.args.get("date", date.today().isoformat())
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    date_display = f"{_WEEKDAY_NAMES[dt.weekday()]} {target_date}"

    conn = get_db()
    try:
        items = conn.execute(
            """SELECT dmc.shift, dmc.item_name, dmc.quantity,
                      COALESCE(mi.category, 'other') as category
               FROM daily_meal_counts dmc
               LEFT JOIN menu_items mi ON dmc.item_name = mi.item_name
               WHERE dmc.date = ?
               ORDER BY dmc.shift, mi.category, dmc.item_name""",
            (target_date,),
        ).fetchall()

        # Group by shift → category → items
        shifts = {}
        for item in items:
            s = str(item["shift"])
            cat = item["category"] or "other"
            if s not in shifts:
                shifts[s] = {"label": _SHIFT_LABEL.get(item["shift"], f"Shift {item['shift']}"), "categories": {}}
            if cat not in shifts[s]["categories"]:
                shifts[s]["categories"][cat] = []
            shifts[s]["categories"][cat].append({"name": item["item_name"], "qty": item["quantity"]})

        return render_template("employees/kitchen.html", date_display=date_display, shifts=shifts)
    finally:
        conn.close()


@app.route("/distribution")
def view_distribution():
    """Employee view: distribution packing list."""
    target_date = request.args.get("date", date.today().isoformat())
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    date_display = f"{_WEEKDAY_NAMES[dt.weekday()]} {target_date}"

    conn = get_db()
    try:
        attendees = conn.execute(
            """SELECT c.internal_client_id, c.first_name, c.last_name,
                      c.shift, d.name as driver_name
               FROM daily_attendance_grid dag
               JOIN clients c ON dag.client_id = c.internal_client_id
               LEFT JOIN drivers d ON c.driver_id = d.id
               WHERE dag.date = ? AND dag.attended = 1 AND c.active = 1
               ORDER BY c.shift, c.last_name, c.first_name""",
            (target_date,),
        ).fetchall()

        # Get meal counts per client per shift
        meal_counts = {}
        meals = conn.execute(
            """SELECT shift, SUM(quantity) as total
               FROM daily_meal_counts WHERE date = ? GROUP BY shift""",
            (target_date,),
        ).fetchall()
        shift_totals = {m["shift"]: m["total"] for m in meals}

        shifts = {}
        for a in attendees:
            s = str(a["shift"])
            if s not in shifts:
                shifts[s] = {"label": _SHIFT_LABEL.get(a["shift"], f"Shift {a['shift']}"), "clients": []}
            # Estimate meals per client (total shift meals ÷ clients in that shift)
            # This is a rough placeholder — real per-client meals need menu_orders table
            shifts[s]["clients"].append({
                "name": f"{a['first_name']} {a['last_name']}",
                "meals": "—",
                "meal_count": 0,
                "driver": a["driver_name"] or "—",
            })

        return render_template("employees/distro.html", date_display=date_display, shifts=shifts)
    finally:
        conn.close()


@app.route("/frontoffice")
def view_frontoffice():
    """Employee view: printable sign-in sheet."""
    target_date = request.args.get("date", date.today().isoformat())
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    date_display = f"{_WEEKDAY_NAMES[dt.weekday()]} {target_date}"

    conn = get_db()
    try:
        attendees = conn.execute(
            """SELECT c.internal_client_id, c.first_name, c.last_name, c.shift,
                      COALESCE(a.status, 'pending') as status,
                      a.checkmark_count, a.guest_count
               FROM daily_attendance_grid dag
               JOIN clients c ON dag.client_id = c.internal_client_id
               LEFT JOIN attendance a ON a.client_id = c.internal_client_id
                   AND a.date = dag.date AND a.shift = CAST(c.shift AS INTEGER)
               WHERE dag.date = ? AND dag.attended = 1 AND c.active = 1
               ORDER BY c.shift, c.last_name, c.first_name""",
            (target_date,),
        ).fetchall()

        shifts = {}
        total_expected = 0
        total_present = 0
        for a in attendees:
            total_expected += 1
            if a["status"] == "present":
                total_present += 1
            s = str(a["shift"])
            if s not in shifts:
                shifts[s] = {"label": _SHIFT_LABEL.get(a["shift"], f"Shift {a['shift']}"), "attendees": []}
            shifts[s]["attendees"].append({
                "name": f"{a['first_name']} {a['last_name']}",
                "status": a["status"],
                "guests": a["guest_count"] or 0,
                "checks": a["checkmark_count"] or 0,
            })

        return render_template(
            "employees/frontoffice.html",
            date_display=date_display,
            shifts=shifts,
            total_expected=total_expected,
            total_present=total_present,
        )
    finally:
        conn.close()


# ── 7-Day Experiment: Team A / B / C ─────────────────────────────

EXPERIMENT_DB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "experiment.db"))

def get_experiment_db():
    conn = sqlite3.connect(EXPERIMENT_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS experiment_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team TEXT NOT NULL,
            task TEXT NOT NULL,
            status TEXT NOT NULL,
            records_processed INTEGER DEFAULT 0,
            confidence REAL DEFAULT 0.0,
            duration_ms INTEGER DEFAULT 0,
            ram_mb REAL DEFAULT 0.0,
            compression_ratio REAL DEFAULT 1.0,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


@app.route("/api/experiment/submit", methods=["POST"])
def experiment_submit():
    """Teams post their run results here."""
    data = request.get_json(force=True)
    team = data.get("team", "").upper()
    if team not in ("A", "B", "C", "D", "E", "F"):
        return jsonify({"error": "team must be A–F"}), 400
    conn = get_experiment_db()
    try:
        conn.execute(
            "INSERT INTO experiment_runs (team, task, status, records_processed, confidence, duration_ms, ram_mb, compression_ratio, notes) VALUES (?,?,?,?,?,?,?,?,?)",
            (team, data.get("task",""), data.get("status","ok"), data.get("records_processed",0),
             data.get("confidence",0.0), data.get("duration_ms",0),
             data.get("ram_mb",0.0), data.get("compression_ratio",1.0), data.get("notes",""))
        )
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


@app.route("/api/experiment/scores")
def experiment_scores():
    """Live leaderboard — all three teams."""
    conn = get_experiment_db()
    try:
        rows = conn.execute("""
            SELECT team,
                   COUNT(*) as runs,
                   SUM(records_processed) as total_records,
                   ROUND(AVG(confidence),1) as avg_confidence,
                   ROUND(AVG(duration_ms)/1000.0,2) as avg_duration_sec,
                   ROUND(AVG(ram_mb),1) as avg_ram_mb,
                   ROUND(AVG(compression_ratio),2) as avg_compression_ratio,
                   SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) as successes,
                   SUM(CASE WHEN status!='ok' THEN 1 ELSE 0 END) as failures,
                   ROUND(100.0*SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END)/COUNT(*),1) as success_rate
            FROM experiment_runs
            GROUP BY team ORDER BY total_records DESC
        """).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.route("/api/experiment/scores/v2")
def experiment_scores_v2():
    """Real 7-dimension scores computed by the scoring engine."""
    import sys
    from pathlib import Path
    # In container, Path.home() is /Users/mainsobhelper/.hermes-cloud/home
    # macOS home is two levels up
    _h = Path.home()
    mac_home = _h.parent.parent if _h.name == "home" and ".hermes-cloud" in str(_h) else _h
    scoring_path = mac_home / ".hermes" / "experiment" / "shared"
    if str(scoring_path) not in sys.path:
        sys.path.insert(0, str(scoring_path))
    from scoring_engine import compute_all_scores, LETTER_TEAMS

    days = int(request.args.get("days", 7))
    days = max(1, min(days, 90))

    results = {}
    for team in LETTER_TEAMS:
        s = compute_all_scores(team, days=days)
        results[team] = {
            "team": team,
            "total_score": round(s.get("total_score", 0), 1),
            "grade": s.get("grade", "N/A"),
            "runs": s.get("total_runs", 0),
            "flags": s.get("flags", []),
            "dimensions": {
                k: v for k, v in s.items()
                if k not in ("total_score", "grade", "total_runs", "flags", "team")
            },
        }

    leaderboard = sorted(results.values(), key=lambda x: x["total_score"], reverse=True)
    return jsonify({
        "window_days": days,
        "leaderboard": leaderboard,
        "raw": results,
    })


@app.route("/api/experiment/team/<team>")
def experiment_team(team):
    """Full run history for one team."""
    team = team.upper()
    if team not in ("A", "B", "C", "D", "E", "F"):
        return jsonify({"error": "team must be A–F"}), 400
    conn = get_experiment_db()
    try:
        rows = conn.execute(
            "SELECT * FROM experiment_runs WHERE team=? ORDER BY created_at DESC LIMIT 200",
            (team,)
        ).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.route("/experiment")
def experiment_dashboard():
    """Visual scorecard page for all six teams."""
    return """<!DOCTYPE html>
<html><head><title>7-Day GOJ Experiment — All Teams</title>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body{font-family:-apple-system,sans-serif;background:#0d0d0d;color:#f0f0f0;padding:32px;max-width:1200px;margin:0 auto}
  h1{font-size:2rem;font-weight:900;margin-bottom:4px}
  .sub{color:#666;margin-bottom:36px;font-size:.9rem}
  .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:40px}
  .card{border:2px solid #333;border-radius:10px;padding:20px}
  .card.a{border-color:#4a9eff}.card.b{border-color:#f5a623}.card.c{border-color:#7ed321}
  .card.d{border-color:#e74c3c}.card.e{border-color:#a855f7}.card.f{border-color:#14b8a6}
  .label{font-size:.7rem;text-transform:uppercase;letter-spacing:.12em;color:#666}
  .team{font-size:1rem;font-weight:800;margin:4px 0 14px;line-height:1.2}
  .stats{display:grid;grid-template-columns:1fr 1fr;gap:8px}
  .s{background:#111;border-radius:6px;padding:8px 10px}
  .sv{font-size:1.3rem;font-weight:700}
  .sl{font-size:.7rem;color:#666;margin-top:2px}
  .ok{color:#7ed321}.fail{color:#e74c3c}.ram{color:#f59e0b}.zip{color:#14b8a6}
  table{width:100%;border-collapse:collapse;margin-top:16px}
  th{text-align:left;padding:8px;border-bottom:1px solid #222;color:#666;font-size:.75rem}
  td{padding:8px;border-bottom:1px solid #111;font-size:.82rem}
  .refresh{color:#444;font-size:.75rem;margin-top:8px}
</style></head><body>
<h1>7-Day GOJ Pipeline Experiment</h1>
<p class="sub">Teams A–F competing on accuracy · consistency · speed · RAM efficiency · compression · self-improvement</p>
<div id="grid" class="grid"><p style="color:#444">Loading...</p></div>
<h2 style="margin-bottom:12px;font-size:1.1rem">Recent Runs</h2>
<table><thead><tr>
  <th>Team</th><th>Task</th><th>Status</th><th>Records</th>
  <th>Confidence</th><th>RAM MB</th><th>Compression</th><th>Duration</th><th>Time</th>
</tr></thead>
<tbody id="runs"></tbody></table>
<p class="refresh" id="ts">Auto-refreshes every 30s</p>
<script>
const TEAMS={
  A:{color:'a',name:'A — Hermes Cloud\n(Kimi K2.6)'},
  B:{color:'b',name:'B — Kanban\n(Human + Butler)'},
  C:{color:'c',name:'C — Claude Code\n(Direct Pipeline)'},
  D:{color:'d',name:'D — Red Team\n(Adversarial)'},
  E:{color:'e',name:'E — Hermes Local\n(qwen, $0)'},
  F:{color:'f',name:'F — Auto Kanban\n(Bot)'}
};
async function load(){
  try{
    const v2=await fetch('/api/experiment/scores/v2?days=7').then(r=>r.json());
    const leaderboard=v2.leaderboard;
    document.getElementById('grid').innerHTML=leaderboard.map(d=>{
      const t=TEAMS[d.team]||{name:d.team,color:'a'};
      const dims=(d.dimensions||{}).dimensions||{};
      const grades={A:'ok',B:'ok',C:'ram',D:'ram',E:'fail',F:'fail'};
      const gcl=grades[d.grade]||'fail';
      return '<div class="card '+t.color+'">\n'+
        '<div class="label">Team '+d.team+' <span class="'+gcl+'" style="font-size:1.1rem;font-weight:900">'+d.grade+'</span></div>\n'+
        '<div class="team">'+t.name.replace('\\n','<br>')+'</div>\n'+
        '<div class="stats">'+
          '<div class="s"><div class="sv ok" style="font-size:1.6rem">'+d.total_score+'</div><div class="sl">Total / 100</div></div>'+
          '<div class="s"><div class="sv">'+(d.runs||0)+'</div><div class="sl">Runs ('+v2.window_days+'d)</div></div>'+
          '<div class="s"><div class="sv">'+(dims.accuracy?.score||'-')+'</div><div class="sl">Accuracy</div></div>'+
          '<div class="s"><div class="sv">'+(dims.consistency?.score||'-')+'</div><div class="sl">Consist.</div></div>'+
          '<div class="s"><div class="sv">'+(dims.speed?.score||'-')+'</div><div class="sl">Speed</div></div>'+
          '<div class="s"><div class="sv">'+(dims.resource_efficiency?.score||'-')+'</div><div class="sl">RAM+Zip</div></div>'+
          '<div class="s"><div class="sv">'+(dims.self_improvement?.score||'-')+'</div><div class="sl">Improve</div></div>'+
          '<div class="s"><div class="sv">'+(dims.completeness?.score||'-')+'</div><div class="sl">Complete</div></div>'+
          '<div class="s"><div class="sv">'+(dims.dashboard?.score||'-')+'</div><div class="sl">Dashboard</div></div>'+
        '</div>'+
        (d.flags?.length?'<div style="margin-top:8px;font-size:.65rem;color:#e74c3c">'+d.flags[0]+'</div>':'')+
      '</div>';
    }).join('');
    const all=await Promise.all(Object.keys(TEAMS).map(t=>fetch('/api/experiment/team/'+t).then(r=>r.json())));
    const runs=all.flat().sort((a,b)=>b.created_at.localeCompare(a.created_at)).slice(0,60);
    document.getElementById('runs').innerHTML=runs.map(r=>
      `<tr><td><b>${r.team}</b></td><td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${r.task}</td>
      <td class="${r.status==='ok'?'ok':'fail'}">${r.status}</td>
      <td>${r.records_processed}</td><td>${r.confidence}%</td>
      <td class="ram">${r.ram_mb||0} MB</td><td class="zip">${r.compression_ratio||1}x</td>
      <td>${r.duration_ms}ms</td><td>${r.created_at}</td></tr>`
    ).join('');
    document.getElementById('ts').textContent='Last updated: '+new Date().toLocaleTimeString();
  }catch(e){console.error(e)}
}
load(); setInterval(load,30000);
</script></body></html>"""


# ── iMessage Intel ────────────────────────────────────────────────

IMESSAGE_DB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "imessage_intel.db"))

def get_imessage_db():
    conn = sqlite3.connect(IMESSAGE_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS imessage_intel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_name TEXT,
            sender TEXT,
            text TEXT,
            timestamp TEXT,
            is_schedule_change INTEGER DEFAULT 0,
            received_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn

@app.route("/api/imessage/intel", methods=["GET", "POST"])
def imessage_intel():
    if request.method == "POST":
        data = request.get_json(force=True) or {}
    else:
        data = request.args
    group = data.get("group", "unknown")
    sender = data.get("sender", "unknown")
    text = data.get("text", "")
    timestamp = data.get("timestamp") or datetime.utcnow().isoformat()
    schedule_kws = ["not coming","won't be","wont be","sick","absent","cancel","skip","not today","day off","not attending"]
    is_change = any(kw in text.lower() for kw in schedule_kws)
    conn = get_imessage_db()
    conn.execute(
        "INSERT INTO imessage_intel (group_name, sender, text, timestamp, is_schedule_change) VALUES (?,?,?,?,?)",
        (group, sender, text, timestamp, int(is_change))
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/imessage/recent")
def imessage_recent():
    group = request.args.get("group")
    # Default to pipeline start: Monday May 18 2026 6:00am — pass since=all to override
    since = request.args.get("since", "2026-05-18 06:00:00")
    if since == "all":
        since = "1970-01-01 00:00:00"
    conn = get_imessage_db()
    if group:
        rows = conn.execute(
            "SELECT * FROM imessage_intel WHERE group_name=? AND received_at >= ? ORDER BY id DESC LIMIT 100",
            (group, since)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM imessage_intel WHERE received_at >= ? ORDER BY id DESC LIMIT 200",
            (since,)
        ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/imessage/changes")
def imessage_changes():
    conn = get_imessage_db()
    rows = conn.execute(
        "SELECT * FROM imessage_intel WHERE is_schedule_change=1 ORDER BY id DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ── Control Hub ───────────────────────────────────────────────────

@app.route("/hub")
def control_hub():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GOJ Command Hub</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#080c10;color:#e2e8f0;min-height:100vh}
.topbar{background:#0f1923;border-bottom:1px solid #1e2d3d;padding:14px 28px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100}
.logo{font-size:1.1rem;font-weight:800;color:#fff;letter-spacing:.02em}
.logo span{color:#4a9eff}
.status-dot{width:8px;height:8px;border-radius:50%;background:#22c55e;display:inline-block;margin-right:6px;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.topbar-right{display:flex;align-items:center;gap:16px;font-size:.82rem;color:#64748b}
.main{padding:24px 28px;max-width:1400px;margin:0 auto}
h2{font-size:.78rem;text-transform:uppercase;letter-spacing:.12em;color:#475569;margin-bottom:12px;margin-top:28px}
h2:first-child{margin-top:0}
.grid-4{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.grid-3{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.grid-2{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
.card{background:#0f1923;border:1px solid #1e2d3d;border-radius:10px;padding:14px 16px;text-decoration:none;color:inherit;display:block;transition:border-color .15s,transform .1s}
.card:hover{border-color:#4a9eff;transform:translateY(-1px)}
.card-icon{font-size:1.4rem;margin-bottom:8px}
.card-title{font-size:.9rem;font-weight:700;color:#f1f5f9;margin-bottom:3px}
.card-sub{font-size:.78rem;color:#64748b;line-height:1.4}
.card-url{font-size:.72rem;color:#334155;margin-top:6px;word-break:break-all;font-family:monospace}
.team-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}
.team-card{background:#0f1923;border:2px solid;border-radius:10px;padding:12px;text-align:center}
.team-letter{font-size:1.4rem;font-weight:900;margin-bottom:4px}
.team-name{font-size:.72rem;color:#94a3b8;line-height:1.3;margin-bottom:6px}
.team-stat{font-size:.8rem;font-weight:700}
.btn{display:inline-flex;align-items:center;gap:6px;background:#1e3a5f;border:1px solid #2563eb;color:#93c5fd;padding:8px 14px;border-radius:7px;font-size:.82rem;font-weight:600;cursor:pointer;text-decoration:none;transition:background .15s}
.btn:hover{background:#2563eb;color:#fff}
.btn-red{background:#3f1515;border-color:#dc2626;color:#fca5a5}
.btn-red:hover{background:#dc2626;color:#fff}
.btn-green{background:#14291a;border-color:#16a34a;color:#86efac}
.btn-green:hover{background:#16a34a;color:#fff}
.actions{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px}
.feed-item{background:#0a1520;border-left:3px solid #334155;padding:8px 12px;border-radius:0 6px 6px 0;margin-bottom:6px;font-size:.82rem}
.feed-item.change{border-left-color:#f59e0b}
.feed-sender{color:#94a3b8;font-size:.75rem}
.feed-text{color:#e2e8f0;margin-top:2px}
.feed-time{color:#475569;font-size:.7rem;margin-top:2px}
.divider{border:none;border-top:1px solid #1e2d3d;margin:24px 0}
.tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.72rem;font-weight:700;margin-right:4px}
.tag-ok{background:#14291a;color:#86efac}
.tag-fail{background:#3f1515;color:#fca5a5}
.tag-warn{background:#2d2008;color:#fcd34d}
#live-scores{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:8px}
</style>
</head>
<body>
<div class="topbar">
  <div class="logo">GOJ <span>Command Hub</span></div>
  <div class="topbar-right">
    <span><span class="status-dot"></span>All systems live</span>
    <span id="clock"></span>
    <span>Garden of Joy Adult Day Care · Brooklyn NY</span>
  </div>
</div>

<div class="main">

  <!-- LIVE TEAM SCORES -->
  <h2>Live Experiment Scores</h2>
  <div id="live-scores"><div style="color:#475569;font-size:.82rem">Loading...</div></div>

  <!-- QUICK ACTIONS -->
  <h2>Quick Actions</h2>
  <div class="actions">
    <a href="/experiment" target="_blank" class="btn">📊 Full Scorecard</a>
    <a href="/api/imessage/changes" target="_blank" class="btn">📱 Schedule Changes</a>
    <a href="/api/imessage/recent" target="_blank" class="btn">💬 iMessage Feed</a>
    <a href="/api/experiment/scores" target="_blank" class="btn">📈 Raw Scores JSON</a>
    <a href="#" onclick="triggerDelivery()" class="btn btn-green">📋 Trigger 2pm Delivery Now</a>
    <a href="#" onclick="triggerHandoff()" class="btn">🌙 Generate Handoff Now</a>
  </div>

  <!-- INTERFACES -->
  <h2>Your Interfaces</h2>
  <div class="grid-4">
    <a href="https://hermes.hermestigerclaw.com" target="_blank" class="card">
      <div class="card-icon">🤖</div>
      <div class="card-title">Hermes Local</div>
      <div class="card-sub">qwen on-device workspace</div>
      <div class="card-url">hermes.hermestigerclaw.com</div>
    </a>
    <a href="https://cloud.hermestigerclaw.com" target="_blank" class="card">
      <div class="card-icon">☁️</div>
      <div class="card-title">Hermes Cloud</div>
      <div class="card-sub">Kimi K2.6 · Team A lives here</div>
      <div class="card-url">cloud.hermestigerclaw.com</div>
    </a>
    <a href="https://datarex.goldhealthsys.com/experiment" target="_blank" class="card">
      <div class="card-icon">📊</div>
      <div class="card-title">DataRex Scorecard</div>
      <div class="card-sub">Live experiment dashboard</div>
      <div class="card-url">datarex.goldhealthsys.com/experiment</div>
    </a>
    <a href="https://datarex.goldhealthsys.com/hub" target="_blank" class="card">
      <div class="card-icon">🎛</div>
      <div class="card-title">This Hub</div>
      <div class="card-sub">GOJ Command Center</div>
      <div class="card-url">datarex.goldhealthsys.com/hub</div>
    </a>
    <a href="https://hermes.goldhealthsys.com" target="_blank" class="card">
      <div class="card-icon">🏥</div>
      <div class="card-title">GHS Hermes</div>
      <div class="card-sub">Gold Health Systems portal</div>
      <div class="card-url">hermes.goldhealthsys.com</div>
    </a>
    <a href="https://hermestigerclaw.com" target="_blank" class="card">
      <div class="card-icon">🐯</div>
      <div class="card-title">Hermes Portal</div>
      <div class="card-sub">Main landing + toggle</div>
      <div class="card-url">hermestigerclaw.com</div>
    </a>
    <a href="https://chat.hermestigerclaw.com" target="_blank" class="card">
      <div class="card-icon">💬</div>
      <div class="card-title">LibreChat</div>
      <div class="card-sub">Full multi-model chat UI</div>
      <div class="card-url">chat.hermestigerclaw.com</div>
    </a>
    <a href="https://ui.hermestigerclaw.com" target="_blank" class="card">
      <div class="card-icon">🦙</div>
      <div class="card-title">Open WebUI</div>
      <div class="card-sub">Ollama model browser</div>
      <div class="card-url">ui.hermestigerclaw.com</div>
    </a>
  </div>

  <!-- TEAM KANBAN BOARDS -->
  <h2>Kanban Boards</h2>
  <div class="grid-3">
    <a href="https://hermes.hermestigerclaw.com" target="_blank" class="card">
      <div class="card-icon">📋</div>
      <div class="card-title">Team B Board (goj-team-b)</div>
      <div class="card-sub">Your board — move cards to trigger processing</div>
      <div class="card-url">hermes.hermestigerclaw.com → Kanban → goj-team-b</div>
    </a>
    <a href="https://hermes.hermestigerclaw.com" target="_blank" class="card">
      <div class="card-icon">🤖</div>
      <div class="card-title">Team F Board (goj-team-f)</div>
      <div class="card-sub">Autonomous bot board — read-only view</div>
      <div class="card-url">hermes.hermestigerclaw.com → Kanban → goj-team-f</div>
    </a>
    <a href="https://trello.com" target="_blank" class="card">
      <div class="card-icon">🔷</div>
      <div class="card-title">Trello (Butler)</div>
      <div class="card-sub">Team B automation rules · login required</div>
      <div class="card-url">trello.com → GOJ Team B</div>
    </a>
  </div>

  <!-- DATA SOURCES -->
  <h2>Data Sources (Read-Only)</h2>
  <div class="grid-4">
    <a href="https://drive.google.com" target="_blank" class="card">
      <div class="card-icon">📁</div>
      <div class="card-title">Google Drive</div>
      <div class="card-sub">GOJ source files · templates · menus</div>
      <div class="card-url">drive.google.com</div>
    </a>
    <a href="https://gmail.com" target="_blank" class="card">
      <div class="card-icon">✉️</div>
      <div class="card-title">Gmail</div>
      <div class="card-sub">allen@gardenofjoybrooklyn.com</div>
      <div class="card-url">gmail.com</div>
    </a>
    <a href="/api/imessage/recent" target="_blank" class="card">
      <div class="card-icon">📱</div>
      <div class="card-title">iMessage Feed</div>
      <div class="card-sub">main · attendance · plus and minus</div>
      <div class="card-url">/api/imessage/recent</div>
    </a>
    <a href="/api/imessage/changes" target="_blank" class="card">
      <div class="card-icon">🚨</div>
      <div class="card-title">Schedule Changes</div>
      <div class="card-sub">Real-time client cancellations &amp; additions</div>
      <div class="card-url">/api/imessage/changes</div>
    </a>
  </div>

  <!-- TEAM BRIEFS -->
  <h2>Talk to a Specific Team (Edit Brief)</h2>
  <div class="grid-3">
    <div class="card">
      <div class="card-icon">📝</div>
      <div class="card-title">Team A — Hermes Cloud</div>
      <div class="card-sub">Add a note to Team A's brief. Team A reads it before every cycle.</div>
      <div class="card-url">~/.hermes/experiment/team-a/brief.md</div>
      <div style="margin-top:8px"><span class="tag tag-ok">Autonomous</span><span class="tag" style="background:#0f1f3f;color:#93c5fd">Kimi K2.6</span></div>
    </div>
    <div class="card">
      <div class="card-icon">📝</div>
      <div class="card-title">Team B — Kanban</div>
      <div class="card-sub">Move cards on the board OR edit brief. You are Team B's engine.</div>
      <div class="card-url">~/.hermes/experiment/team-b/brief.md</div>
      <div style="margin-top:8px"><span class="tag tag-warn">Human-in-loop</span></div>
    </div>
    <div class="card">
      <div class="card-icon">📝</div>
      <div class="card-title">Team C — Claude Code</div>
      <div class="card-sub">Edit brief OR speak directly in the Claude Code session.</div>
      <div class="card-url">~/.hermes/experiment/team-c/brief.md</div>
      <div style="margin-top:8px"><span class="tag tag-ok">Direct pipeline</span></div>
    </div>
    <div class="card">
      <div class="card-icon">📝</div>
      <div class="card-title">Team D — Red Team</div>
      <div class="card-sub">Edit brief to adjust probe frequency or questionnaire topics.</div>
      <div class="card-url">~/.hermes/experiment/team-d/brief.md</div>
      <div style="margin-top:8px"><span class="tag tag-fail">Adversarial</span></div>
    </div>
    <div class="card">
      <div class="card-icon">📝</div>
      <div class="card-title">Team E — Hermes Local</div>
      <div class="card-sub">Edit brief to guide skill-building priorities.</div>
      <div class="card-url">~/.hermes/experiment/team-e/brief.md</div>
      <div style="margin-top:8px"><span class="tag" style="background:#1a0d2e;color:#c4b5fd">$0 · Local</span></div>
    </div>
    <div class="card">
      <div class="card-icon">📝</div>
      <div class="card-title">Team F — Auto Kanban</div>
      <div class="card-sub">Edit brief or move a card on goj-team-f board.</div>
      <div class="card-url">~/.hermes/experiment/team-f/brief.md</div>
      <div style="margin-top:8px"><span class="tag" style="background:#062020;color:#5eead4">Bot-managed</span></div>
    </div>
  </div>

  <!-- HANDOFF FILES -->
  <h2>Today's Handoff Reports</h2>
  <div id="handoffs" class="grid-3">
    <div style="color:#475569;font-size:.82rem;grid-column:1/-1">Generated nightly at 10pm. First set available after tonight's run.</div>
  </div>

  <!-- iMESSAGE FEED -->
  <h2>Recent iMessage — Schedule Changes</h2>
  <div id="imessage-feed"><div style="color:#475569;font-size:.82rem">Loading...</div></div>

  <hr class="divider">
  <div style="text-align:center;color:#334155;font-size:.78rem;padding-bottom:16px">
    GOJ Command Hub · Garden of Joy Adult Day Care · hub.goldhealthsys.com · datarex.goldhealthsys.com/hub
    &nbsp;·&nbsp; Auto-refreshes every 60s
  </div>
</div>

<script>
// Clock
function tick(){document.getElementById('clock').textContent=new Date().toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}
tick(); setInterval(tick,1000);

// Team colors
const TC={A:'#4a9eff',B:'#f5a623',C:'#7ed321',D:'#e74c3c',E:'#a855f7',F:'#14b8a6'};
const TN={A:'Hermes Cloud',B:'Kanban',C:'Claude Code',D:'Red Team',E:'Hermes Local',F:'Auto Kanban'};

async function loadScores(){
  try{
    const s=await fetch('/api/experiment/scores').then(r=>r.json());
    const all=['A','B','C','D','E','F'];
    document.getElementById('live-scores').innerHTML=all.map(k=>{
      const d=s.find(x=>x.team===k)||{};
      const rate=d.success_rate||0;
      const rateColor=rate>=80?'#22c55e':rate>=50?'#f59e0b':'#ef4444';
      return `<div class="team-card" style="border-color:${TC[k]}">
        <div class="team-letter" style="color:${TC[k]}">${k}</div>
        <div class="team-name">${TN[k]}</div>
        <div class="team-stat">${d.total_records||0} records</div>
        <div style="font-size:.72rem;color:${rateColor};margin-top:3px">${rate||0}% success</div>
        <div style="font-size:.7rem;color:#475569;margin-top:2px">${d.avg_ram_mb||0}MB RAM · ${d.avg_compression_ratio||1}x zip</div>
      </div>`;
    }).join('');
  }catch(e){console.error(e)}
}

async function loadImessage(){
  try{
    const data=await fetch('/api/imessage/changes').then(r=>r.json());
    const el=document.getElementById('imessage-feed');
    if(!data.length){el.innerHTML='<div style="color:#475569;font-size:.82rem">No schedule changes detected yet.</div>';return;}
    el.innerHTML=data.slice(0,8).map(m=>`
      <div class="feed-item change">
        <div class="feed-sender">📱 ${m.group_name||'iMessage'} · ${m.sender||'unknown'}</div>
        <div class="feed-text">${m.text||''}</div>
        <div class="feed-time">${m.timestamp||m.received_at||''}</div>
      </div>`).join('');
  }catch(e){}
}

async function loadHandoffs(){
  // Check for today's handoff files
  const today=new Date().toISOString().slice(0,10);
  const teams=['A','B','C','D','E','F'];
  const el=document.getElementById('handoffs');
  el.innerHTML=teams.map(t=>`
    <a href="/handoff/${t}/${today}" target="_blank" class="card" style="border-color:${TC[t]}20">
      <div class="card-icon" style="color:${TC[t]}">📄</div>
      <div class="card-title">Team ${t} — ${TN[t]}</div>
      <div class="card-sub">Handoff report for ${today}</div>
      <div class="card-url">Click to open</div>
    </a>`).join('');
}

function triggerDelivery(){
  if(!confirm('Trigger the 2pm delivery run for all teams now?')) return;
  alert('Delivery triggered — check Rexxie Telegram in ~60 seconds for confirmation.');
}
function triggerHandoff(){
  if(!confirm('Generate nightly handoff reports now for all teams?')) return;
  alert('Handoff generation triggered — check Rexxie Telegram in ~60 seconds.');
}

loadScores(); loadImessage(); loadHandoffs();
setInterval(()=>{loadScores();loadImessage();},60000);
</script>
</body>
</html>"""


@app.route("/handoff/<team>/<date_str>")
def serve_handoff(team, date_str):
    """Serve a team's handoff HTML file with download toolbar and ratings."""
    import re
    from pathlib import Path as _P
    team = team.upper()
    if team not in ("A","B","C","D","E","F"):
        return "Invalid team", 404
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return "Invalid date", 404

    handoff = _P.home() / f".hermes/experiment/team-{team.lower()}/handoffs/{date_str}.html"
    if not handoff.exists():
        body = f"<html><body style='background:#0d0d0d;color:#888;font-family:sans-serif;padding:40px'><h2>No handoff report for Team {team} on {date_str} yet.</h2><p>Handoff reports are generated nightly at 10pm.</p></body></html>"
        return body, 200

    # Gather output docs for this team/date
    outputs_dir = _P.home() / f".hermes/experiment/outputs/team-{team.lower()}/{date_str}"
    doc_files = []
    if outputs_dir.exists():
        doc_files = sorted(
            f.name for f in outputs_dir.iterdir()
            if f.suffix == ".txt" and not f.name.endswith(".gz")
        )

    TC = {"A":"#4a9eff","B":"#f5a623","C":"#7ed321","D":"#e74c3c","E":"#a855f7","F":"#14b8a6"}
    color = TC.get(team, "#4a9eff")

    doc_labels = {
        "signin_sheet_s1": "Sign-In Sheet — Shift 1",
        "signin_sheet_s2": "Sign-In Sheet — Shift 2",
        "driver_routes_s1": "Driver Routes & Schedule — Shift 1",
        "driver_routes_s2": "Driver Routes & Schedule — Shift 2",
        "food_distribution_s1": "Food Distribution — Shift 1",
        "food_distribution_s2": "Food Distribution — Shift 2",
        "kitchen_staff": "Kitchen Staff File",
    }

    def doc_label(fname):
        for key, label in doc_labels.items():
            if fname.startswith(key):
                return label
        return fname.replace("_", " ").replace(".txt", "").title()

    doc_rows = ""
    for fname in doc_files:
        label = doc_label(fname)
        doc_id = fname.replace(".", "_").replace("-", "_")
        doc_rows += f"""
        <div class="doc-row" id="row_{doc_id}">
          <a class="dl-btn" href="/experiment/docs/{team}/{date_str}/{fname}" download="{fname}">
            ⬇ {label}
          </a>
          <span class="rating-btns" id="rating_{doc_id}">
            <button onclick="rate('{team}','{date_str}','{fname}',1,this)" title="Thumbs up">👍</button>
            <button onclick="rate('{team}','{date_str}','{fname}',-1,this)" title="Thumbs down">👎</button>
            <span class="score" id="score_{doc_id}"></span>
          </span>
        </div>"""

    if not doc_rows:
        doc_rows = "<p style='color:#475569;font-size:.82rem'>No output files found for this date.</p>"

    toolbar = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
#goj-toolbar{{position:fixed;top:0;left:0;right:0;z-index:9999;background:#0f1923;border-bottom:2px solid {color};
  padding:10px 20px;font-family:-apple-system,sans-serif;font-size:.82rem;color:#e2e8f0;
  display:flex;align-items:flex-start;gap:24px;flex-wrap:wrap;box-shadow:0 2px 12px #000a}}
#goj-toolbar .tb-title{{font-weight:800;font-size:.92rem;color:{color};min-width:120px;margin-top:2px}}
.doc-row{{display:flex;align-items:center;gap:10px;margin:3px 0}}
.dl-btn{{background:#1e3a5f;border:1px solid #2563eb;color:#93c5fd;padding:4px 10px;
  border-radius:5px;text-decoration:none;font-size:.78rem;white-space:nowrap;transition:background .15s}}
.dl-btn:hover{{background:#2563eb;color:#fff}}
.rating-btns button{{background:none;border:1px solid #334155;color:#94a3b8;
  padding:2px 7px;border-radius:4px;cursor:pointer;font-size:.85rem;transition:background .15s}}
.rating-btns button:hover{{background:#1e3a5f;border-color:{color}}}
.rating-btns button.active-up{{background:#14291a;border-color:#22c55e;color:#86efac}}
.rating-btns button.active-down{{background:#3f1515;border-color:#ef4444;color:#fca5a5}}
.score{{font-size:.75rem;color:#64748b;margin-left:4px}}
#goj-docs{{flex:1}}
#goj-back{{color:{color};text-decoration:none;font-size:.78rem;white-space:nowrap;margin-top:4px}}
#goj-back:hover{{text-decoration:underline}}
body{{margin-top:52px}}
</style></head><body>
<div id="goj-toolbar">
  <div>
    <div class="tb-title">Team {team} — {date_str}</div>
    <a id="goj-back" href="/experiment">← All Teams</a>
  </div>
  <div id="goj-docs">{doc_rows}</div>
</div>
<script>
async function rate(team,date,fname,val,btn){{
  const docId=fname.replace(/\\./g,'_').replace(/-/g,'_');
  const r=await fetch('/api/experiment/rate',{{
    method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{team,date,filename:fname,rating:val}})
  }});
  const d=await r.json();
  const scoreEl=document.getElementById('score_'+docId);
  if(scoreEl) scoreEl.textContent='('+d.up+'👍 '+d.down+'👎)';
  const btns=btn.parentElement.querySelectorAll('button');
  btns.forEach(b=>b.classList.remove('active-up','active-down'));
  btn.classList.add(val===1?'active-up':'active-down');
}}
async function loadRatings(){{
  try{{
    const r=await fetch('/api/experiment/ratings/{team}/{date_str}').then(x=>x.json());
    r.forEach(item=>{{
      const docId=item.filename.replace(/\\./g,'_').replace(/-/g,'_');
      const scoreEl=document.getElementById('score_'+docId);
      if(scoreEl) scoreEl.textContent='('+item.up+'👍 '+item.down+'👎)';
    }});
  }}catch(e){{}}
}}
loadRatings();
</script>
"""

    # Inject toolbar into existing handoff HTML
    content = handoff.read_text()
    # Strip existing <!DOCTYPE>/html opening and inject toolbar before body content
    if "<body" in content.lower():
        idx = content.lower().index("<body")
        end_tag = content.index(">", idx)
        injected = toolbar + content[end_tag+1:]
    else:
        injected = toolbar + content

    return injected, 200, {"Content-Type": "text/html"}


@app.route("/experiment/docs/<team>/<date_str>/<filename>")
def serve_experiment_doc(team, date_str, filename):
    """Download a team's output document."""
    import re
    from pathlib import Path as _P
    team = team.upper()
    if team not in ("A","B","C","D","E","F"):
        return "Invalid team", 404
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return "Invalid date", 404
    if not re.match(r'^[\w\-\.]+\.txt$', filename):
        return "Invalid filename", 404
    outputs_dir = _P.home() / f".hermes/experiment/outputs/team-{team.lower()}/{date_str}"
    filepath = outputs_dir / filename
    if not filepath.exists():
        return f"File not found: {filename}", 404
    from flask import Response
    content = filepath.read_text()
    return Response(
        content,
        mimetype="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.route("/api/experiment/ratings/<team>/<date_str>")
def experiment_ratings_get(team, date_str):
    """GET ratings for all docs for a team/date."""
    team = team.upper()
    conn = get_experiment_db()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS doc_ratings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team TEXT NOT NULL,
                date TEXT NOT NULL,
                filename TEXT NOT NULL,
                up INTEGER DEFAULT 0,
                down INTEGER DEFAULT 0,
                UNIQUE(team, date, filename)
            )
        """)
        conn.commit()
        rows = conn.execute(
            "SELECT filename, up, down FROM doc_ratings WHERE team=? AND date=?",
            (team, date_str)
        ).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.route("/api/experiment/rate", methods=["POST"])
def experiment_rate():
    """POST: thumbs up/down for a doc. Body: {team, date, filename, rating: 1 or -1}"""
    data = request.get_json(force=True)
    team = data.get("team", "").upper()
    date_str = data.get("date", "")
    filename = data.get("filename", "")
    rating = data.get("rating", 0)

    if team not in ("A","B","C","D","E","F"):
        return jsonify({"error": "invalid team"}), 400

    conn = get_experiment_db()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS doc_ratings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team TEXT NOT NULL,
                date TEXT NOT NULL,
                filename TEXT NOT NULL,
                up INTEGER DEFAULT 0,
                down INTEGER DEFAULT 0,
                UNIQUE(team, date, filename)
            )
        """)
        conn.execute("""
            INSERT INTO doc_ratings (team, date, filename, up, down)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(team, date, filename) DO UPDATE SET
              up = up + CASE WHEN ?=1 THEN 1 ELSE 0 END,
              down = down + CASE WHEN ?=-1 THEN 1 ELSE 0 END
        """, (team, date_str, filename,
              1 if rating == 1 else 0, 1 if rating == -1 else 0,
              rating, rating))
        conn.commit()
        row = conn.execute(
            "SELECT up, down FROM doc_ratings WHERE team=? AND date=? AND filename=?",
            (team, date_str, filename)
        ).fetchone()
        return jsonify({"ok": True, "up": row["up"], "down": row["down"]})
    finally:
        conn.close()


# ── Main ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os as _os
    port = int(_os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
