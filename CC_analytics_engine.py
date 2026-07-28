"""
CC_analytics_engine.py
========================
GHS Weekly Analytics & KPI Report Generator
Gold Health Systems · GOJ Operations

PURPOSE:
    Generates weekly HTML KPI report covering:
    - Client count trend (active, expired, pending renewal)
    - Authorization compliance rate
    - Attendance rate (actual vs. capacity)
    - Menu submission rate (forms received / expected)
    - System health summary (services up/down)
    - Agent activity summary

OUTPUT:
    ~/Desktop/REX/reports/ghs_weekly_kpi_YYYY-WNN.html  (rendered HTML)
    ~/Desktop/REX/reports/ghs_weekly_kpi_YYYY-WNN.json  (raw data for reuse)

USAGE:
    python CC_analytics_engine.py                    # generate this week's report
    python CC_analytics_engine.py --week 2026-W23    # specific week
    python CC_analytics_engine.py --send-telegram    # generate + send to Kato via Telegram

DATA SOURCES:
    - auth_tracker.db → clients, authorization, client_menus
    - ~/Desktop/REX/logs/*.log → agent activity
    - Service health endpoints (localhost:8000, 8080, 3002)

Gold Health Systems · June 4, 2026
"""

import sys
import json
import sqlite3
import logging
import datetime
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────

DB_PATH      = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
REPORTS_DIR  = Path.home() / "Desktop" / "REX" / "reports"
LOGS_DIR     = Path.home() / "Desktop" / "REX" / "logs"
CONFIG_FILE  = Path.home() / "Desktop" / "REX" / "rex_telegram_config.json"

SERVICE_HEALTH = {
    "REX API (:8000)":       "http://localhost:8000/api/health",
    "GOJ Dashboard (:8080)": "http://localhost:8080/health",
    "Hermes Gateway (:3002)":"http://localhost:3002/health",
    "TigerClaw (:27226)":    "http://localhost:27226/health",
    "Ollama (:11434)":       "http://localhost:11434/api/tags",
}

# ─────────────────────────────────────────────────────────────────────────────
# DATA COLLECTION
# ─────────────────────────────────────────────────────────────────────────────

def _db_query(sql: str, params: tuple = ()) -> List[tuple]:
    """Run a read-only query against auth_tracker.db."""
    if not DB_PATH.exists():
        logger.warning("auth_tracker.db not found at %s", DB_PATH)
        return []
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            return conn.execute(sql, params).fetchall()
    except Exception as exc:
        logger.error("DB query failed: %s | SQL: %s", exc, sql[:80])
        return []


def get_client_counts() -> Dict[str, int]:
    """Count clients by authorization status."""
    rows = _db_query("""
        SELECT a.status, COUNT(DISTINCT c.id) as cnt
        FROM clients c
        LEFT JOIN authorization a ON a.client_id = c.id
        GROUP BY a.status
    """)
    counts = {"ACTIVE": 0, "EXPIRED": 0, "PENDING RENEWAL": 0, "NO_AUTH": 0, "TOTAL": 0}
    for status, cnt in rows:
        key = status.upper() if status else "NO_AUTH"
        counts[key] = counts.get(key, 0) + cnt
    counts["TOTAL"] = sum(v for k, v in counts.items() if k != "TOTAL")
    return counts


def get_auth_compliance_rate() -> float:
    """Percentage of clients with ACTIVE or PENDING RENEWAL authorization."""
    counts = get_client_counts()
    total = counts.get("TOTAL", 0)
    if total == 0:
        return 0.0
    compliant = counts.get("ACTIVE", 0) + counts.get("PENDING RENEWAL", 0)
    return round((compliant / total) * 100, 1)


def get_menu_submission_stats(week_start: Optional[str] = None) -> Dict[str, Any]:
    """
    Menu submission rate for a given week.
    week_start format: 'YYYY-MM-DD' (Monday)
    """
    if week_start is None:
        today = datetime.date.today()
        week_start_date = today - datetime.timedelta(days=today.weekday())
        week_start = week_start_date.isoformat()

    rows = _db_query("""
        SELECT COUNT(DISTINCT client_id) as submitted,
               AVG(confidence) as avg_confidence
        FROM client_menus
        WHERE week_start = ?
    """, (week_start,))

    submitted = rows[0][0] if rows else 0
    avg_confidence = round((rows[0][1] or 0) * 100, 1) if rows else 0

    # Total active clients who should have a menu
    total_active_rows = _db_query("""
        SELECT COUNT(DISTINCT c.id) FROM clients c
        JOIN authorization a ON a.client_id = c.id
        WHERE a.status = 'ACTIVE'
    """)
    total_active = total_active_rows[0][0] if total_active_rows else 0

    submission_rate = round((submitted / total_active * 100), 1) if total_active > 0 else 0

    return {
        "week_start": week_start,
        "menus_submitted": submitted,
        "active_clients": total_active,
        "submission_rate_pct": submission_rate,
        "avg_ocr_confidence_pct": avg_confidence,
    }


def get_attendance_stats() -> Dict[str, Any]:
    """Recent attendance data (last 5 days with records)."""
    rows = _db_query("""
        SELECT date, COUNT(*) as present
        FROM attendance
        WHERE present = 1
        GROUP BY date
        ORDER BY date DESC
        LIMIT 7
    """)
    if not rows:
        return {"recent_days": [], "avg_daily_attendance": 0}

    days = [{"date": r[0], "present": r[1]} for r in rows]
    avg = round(sum(d["present"] for d in days) / len(days), 1)
    return {"recent_days": days, "avg_daily_attendance": avg}


def check_service_health() -> Dict[str, str]:
    """Quick health check of all key services."""
    results = {}
    for name, url in SERVICE_HEALTH.items():
        try:
            req = urllib.request.urlopen(url, timeout=2)
            results[name] = "✅ UP" if req.status < 500 else f"⚠️ {req.status}"
        except urllib.error.URLError:
            results[name] = "❌ DOWN"
        except Exception:
            results[name] = "❓ UNKNOWN"
    return results


# ─────────────────────────────────────────────────────────────────────────────
# REPORT GENERATION
# ─────────────────────────────────────────────────────────────────────────────

def collect_report_data(week_label: str) -> Dict[str, Any]:
    """Collect all KPI data for the report."""
    logger.info("Collecting KPI data for week %s...", week_label)

    # Parse week_label (e.g. "2026-W23") to get Monday date
    try:
        year, week_num = week_label.split("-W")
        week_start_date = datetime.datetime.strptime(f"{year} {week_num} 1", "%Y %W %w").date()
        week_start = week_start_date.isoformat()
    except Exception:
        week_start = None

    client_counts  = get_client_counts()
    compliance_pct = get_auth_compliance_rate()
    menu_stats     = get_menu_submission_stats(week_start)
    attendance     = get_attendance_stats()
    service_health = check_service_health()

    return {
        "generated_at":   datetime.datetime.now().isoformat(),
        "week_label":     week_label,
        "week_start":     week_start,
        "client_counts":  client_counts,
        "compliance_pct": compliance_pct,
        "menu_stats":     menu_stats,
        "attendance":     attendance,
        "service_health": service_health,
    }


def render_html_report(data: Dict[str, Any]) -> str:
    """Render the KPI data as a styled HTML report."""

    def status_badge(value: float, green_threshold: float = 90.0,
                      yellow_threshold: float = 75.0) -> str:
        color = ("#27ae60" if value >= green_threshold
                 else "#f39c12" if value >= yellow_threshold
                 else "#e74c3c")
        return f'<span style="color:{color};font-weight:bold">{value}%</span>'

    cc = data["client_counts"]
    ms = data["menu_stats"]
    att = data["attendance"]
    svc = data["service_health"]

    service_rows = "".join(
        f"<tr><td>{name}</td><td>{status}</td></tr>"
        for name, status in svc.items()
    )

    recent_att = "".join(
        f"<tr><td>{d['date']}</td><td>{d['present']}</td></tr>"
        for d in att.get("recent_days", [])[:5]
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>GHS Weekly KPI — {data['week_label']}</title>
  <style>
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #0a0a12; color: #e0e0e0;
            padding: 32px; max-width: 900px; margin: 0 auto; }}
    h1 {{ color: #00d4ff; border-bottom: 2px solid #00d4ff33; padding-bottom: 8px; }}
    h2 {{ color: #7fdbff; margin-top: 32px; }}
    .kpi-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 24px 0; }}
    .kpi-card {{ background: #12122a; border: 1px solid #2a2a4a; border-radius: 8px;
                 padding: 20px; text-align: center; }}
    .kpi-number {{ font-size: 2.5em; font-weight: bold; color: #00d4ff; }}
    .kpi-label {{ font-size: 0.85em; color: #888; margin-top: 4px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
    th {{ background: #1a1a3a; color: #7fdbff; padding: 8px; text-align: left; }}
    td {{ padding: 8px; border-bottom: 1px solid #2a2a4a; }}
    .footer {{ margin-top: 48px; font-size: 0.8em; color: #555; }}
    .warn {{ color: #f39c12; }}
    .good {{ color: #27ae60; }}
    .bad  {{ color: #e74c3c; }}
  </style>
</head>
<body>
  <h1>🏥 Gold Health Systems — Weekly KPI</h1>
  <p style="color:#888">Week: <strong>{data['week_label']}</strong> · Generated: {data['generated_at'][:19]}</p>

  <h2>👥 Client Overview</h2>
  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-number good">{cc.get('ACTIVE', 0)}</div>
      <div class="kpi-label">Active Clients</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-number {'bad' if cc.get('EXPIRED', 0) > 10 else 'warn'}">{cc.get('EXPIRED', 0)}</div>
      <div class="kpi-label">Expired Auth</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-number warn">{cc.get('PENDING RENEWAL', 0)}</div>
      <div class="kpi-label">Pending Renewal</div>
    </div>
  </div>

  <h2>📋 Authorization Compliance</h2>
  <p>Compliance rate (Active + Pending / Total): {status_badge(data['compliance_pct'])}</p>
  <p>Total clients: <strong>{cc.get('TOTAL', 0)}</strong></p>

  <h2>🍽️ Menu Submissions — {ms['week_start'] or 'N/A'}</h2>
  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-number">{ms['menus_submitted']}</div>
      <div class="kpi-label">Menus Received</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-number">{status_badge(ms['submission_rate_pct'])}</div>
      <div class="kpi-label">Submission Rate</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-number">{ms['avg_ocr_confidence_pct']}%</div>
      <div class="kpi-label">Avg OCR Confidence</div>
    </div>
  </div>

  <h2>📅 Recent Attendance</h2>
  <p>7-day avg daily attendance: <strong>{att['avg_daily_attendance']}</strong></p>
  <table>
    <tr><th>Date</th><th>Present</th></tr>
    {recent_att or '<tr><td colspan="2" style="color:#888">No attendance data</td></tr>'}
  </table>

  <h2>🖥️ Service Health</h2>
  <table>
    <tr><th>Service</th><th>Status</th></tr>
    {service_rows}
  </table>

  <div class="footer">
    Generated by CC_analytics_engine.py · Gold Health Systems · {datetime.date.today().isoformat()}
  </div>
</body>
</html>"""
    return html


# ─────────────────────────────────────────────────────────────────────────────
# TELEGRAM SEND (optional)
# ─────────────────────────────────────────────────────────────────────────────

def send_telegram_summary(data: Dict[str, Any], report_path: Path) -> None:
    """Send a text summary to Kato via Telegram."""
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        token = cfg.get("bot_token")
        chat_id = cfg.get("chairman_chat_id") or "5587703834"
    except Exception as exc:
        logger.warning("Cannot load Telegram config: %s", exc)
        return

    cc = data["client_counts"]
    ms = data["menu_stats"]
    svc = data["service_health"]
    down = [n for n, s in svc.items() if "DOWN" in s]

    msg = (
        f"📊 *GHS Weekly KPI — {data['week_label']}*\n\n"
        f"👥 Clients: {cc.get('ACTIVE', 0)} active · {cc.get('EXPIRED', 0)} expired · "
        f"{cc.get('PENDING RENEWAL', 0)} pending\n"
        f"📋 Auth compliance: {data['compliance_pct']}%\n"
        f"🍽️ Menu submission: {ms['submission_rate_pct']}% "
        f"({ms['menus_submitted']}/{ms['active_clients']})\n"
        f"📅 Avg attendance: {data['attendance']['avg_daily_attendance']}/day\n"
    )

    if down:
        msg += f"\n⚠️ Services DOWN: {', '.join(down)}\n"
    else:
        msg += "\n✅ All services UP\n"

    msg += f"\nFull report: {report_path.name}"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}).encode()
    req = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
        logger.info("Telegram summary sent to Chairman")
    except Exception as exc:
        logger.warning("Telegram send failed: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# CLI ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="GHS Weekly KPI Report Generator")
    parser.add_argument("--week", default=None,
                        help="Week in YYYY-WNN format (default: current week)")
    parser.add_argument("--send-telegram", action="store_true",
                        help="Send summary to Kato via Telegram")
    args = parser.parse_args()

    # Determine week label
    if args.week:
        week_label = args.week
    else:
        today = datetime.date.today()
        week_label = f"{today.year}-W{today.isocalendar()[1]:02d}"

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("═" * 55)
    logger.info("  CC_analytics_engine — %s", week_label)
    logger.info("═" * 55)

    data = collect_report_data(week_label)

    # Save JSON
    json_path = REPORTS_DIR / f"ghs_weekly_kpi_{week_label.replace('-', '_')}.json"
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    logger.info("JSON saved: %s", json_path)

    # Save HTML
    html = render_html_report(data)
    html_path = REPORTS_DIR / f"ghs_weekly_kpi_{week_label.replace('-', '_')}.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info("HTML report saved: %s", html_path)

    # Quick console summary
    cc = data["client_counts"]
    print(f"\n{'═' * 55}")
    print(f"  GHS KPI — {week_label}")
    print(f"{'═' * 55}")
    print(f"  Clients:     {cc.get('ACTIVE', 0)} active · {cc.get('EXPIRED', 0)} expired · "
          f"{cc.get('PENDING RENEWAL', 0)} pending")
    print(f"  Compliance:  {data['compliance_pct']}%")
    print(f"  Menus:       {data['menu_stats']['submission_rate_pct']}% submitted")
    print(f"  Attendance:  {data['attendance']['avg_daily_attendance']} avg/day")
    print(f"\n  Report: {html_path}")
    print(f"{'═' * 55}\n")

    if args.send_telegram:
        send_telegram_summary(data, html_path)


if __name__ == "__main__":
    main()
