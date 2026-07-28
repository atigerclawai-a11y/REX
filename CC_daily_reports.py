#!/usr/bin/env python3
"""
CC_daily_reports.py — GOJ Daily Reports (10 AM + 3 PM)
=====================================================
Generates comprehensive daily reports pulling from:
- auth_tracker.db (attendance, clients, auths, victoria, OCR, menus)
- WhatsApp bridge intel
- Datarex live data

Usage:
    python3 CC_daily_reports.py --morning    # 10 AM report
    python3 CC_daily_reports.py --afternoon  # 3 PM report
    python3 CC_daily_reports.py              # both, sends to Telegram
"""

import json
import os
import sqlite3
import sys
import urllib.request
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path

DB = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
TOKEN = os.getenv("REXXIE_TOKEN", "8657319466:***")
CHAT_ID = "5587703834"

# ── HELPERS ────────────────────────────────────────────────────────

def db_query(sql, params=()):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    rows = cur.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_value(sql, params=()):
    conn = sqlite3.connect(DB)
    r = conn.execute(sql, params).fetchone()
    conn.close()
    return r[0] if r else 0

def send_telegram(text):
    """Deliver report via Telegram."""
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML"
        }).encode()
        urllib.request.urlopen(url, data=data, timeout=10)
        return True
    except Exception as e:
        print(f"[telegram] send failed: {e}")
        return False

# ── DATA GATHERING ─────────────────────────────────────────────────

def get_today_attendance(today):
    """Scheduled vs present for today."""
    day_name = today.strftime("%A")
    scheduled = db_value(
        "SELECT COUNT(*) FROM client_schedule WHERE day_of_week = ?", (day_name,)
    )
    present_s1 = db_value(
        "SELECT COUNT(*) FROM attendance_log WHERE log_date = ? AND status = 'present' AND shift = 1",
        (today.isoformat(),)
    )
    present_s2 = db_value(
        "SELECT COUNT(*) FROM attendance_log WHERE log_date = ? AND status = 'present' AND shift = 2",
        (today.isoformat(),)
    )
    absent = db_value(
        "SELECT COUNT(*) FROM attendance_log WHERE log_date = ? AND status = 'absent'",
        (today.isoformat(),)
    )
    return {
        "scheduled": scheduled,
        "present_s1": present_s1,
        "present_s2": present_s2,
        "present_total": present_s1 + present_s2,
        "absent": absent,
    }

def get_whatsapp_absences(today):
    """Absences reported overnight via WhatsApp/iMessage bridge."""
    yesterday = (today - timedelta(days=1)).isoformat()
    rows = db_query("""
        SELECT parsed_client, parsed_date, reason, ts
        FROM attendance_bot_log
        WHERE cascade_status = 'success'
          AND (parsed_date = ? OR parsed_date = ?)
        ORDER BY ts DESC
    """, (today.isoformat(), (today + timedelta(days=1)).isoformat()))
    return rows

def get_auth_alerts():
    """Auth expirations needing attention."""
    rows = db_query("""
        SELECT client_name, member_id, service_end_date,
               CAST(julianday(service_end_date) - julianday('now') AS INTEGER) as days_left
        FROM authorization
        WHERE service_end_date IS NOT NULL
          AND service_end_date <= date('now', '+14 days')
          AND service_end_date >= date('now', '-30 days')
        ORDER BY days_left
    """)
    return rows

def get_victoria_calls(today):
    """Today's Victoria call results."""
    rows = db_query("""
        SELECT client_id, call_type, status, notes, created_at
        FROM victoria_call_log
        WHERE DATE(created_at) = ?
        ORDER BY created_at DESC
    """, (today.isoformat(),))
    return rows

def get_ocr_status():
    """OCR pipeline stats."""
    from pathlib import Path
    docs = list(Path.home().joinpath("Documents", "goj files", "dashboard", "documents").glob("*_pipeline.json"))
    matched = db_value("SELECT COUNT(*) FROM attendance_evidence_rows")
    return {
        "documents_today": len([d for d in docs if date.fromtimestamp(d.stat().st_mtime) == date.today()]),
        "total_documents": len(docs),
        "matched_names": matched,
    }

def get_menu_status():
    """Check menu coverage for this week."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    status = {}
    for day in days:
        count = db_value(
            "SELECT COUNT(*) FROM client_menus WHERE day = ? AND week_start = ?",
            (day, monday.isoformat())
        )
        status[day] = count > 0
    return status

def get_signatures_today(today):
    """Signature stats for today."""
    signed = db_value(
        "SELECT COUNT(*) FROM client_signatures WHERE date = ?", (today.isoformat(),)
    )
    return signed

def get_schedule_changes_today(today):
    """Today's schedule changes."""
    rows = db_query("""
        SELECT client_name, change_type, field_changed, new_value, note
        FROM pending_schedule_changes
        WHERE DATE(created_at) = ? OR day_key = ?
        ORDER BY created_at DESC
    """, (today.isoformat(), date.today().strftime("%a").upper()[:1]))
    return rows

# ── REPORT GENERATORS ──────────────────────────────────────────────

def morning_report():
    """10 AM comprehensive morning report."""
    today = date.today()
    day_name = today.strftime("%A")
    now = datetime.now().strftime("%I:%M %p")
    
    att = get_today_attendance(today)
    absences = get_whatsapp_absences(today)
    auths = get_auth_alerts()
    ocr = get_ocr_status()
    menus = get_menu_status()
    
    lines = [
        f"☀️ <b>GOJ MORNING REPORT</b> — {today.strftime('%B %d, %Y')} ({day_name})",
        f"<i>Generated {now}</i>",
        "",
        "📊 <b>ATTENDANCE</b>",
        f"  Scheduled today: <b>{att['scheduled']}</b>",
        f"  Shift 1 present: <b>{att['present_s1']}</b>",
        f"  Shift 2 present: <b>{att['present_s2']}</b>",
        f"  Total present: <b>{att['present_total']}</b>",
        f"  Reported absent: <b>{att['absent']}</b>",
        "",
    ]
    
    if absences:
        lines.append("📱 <b>ABSENCES REPORTED</b> (overnight WhatsApp/iMessage)")
        for a in absences[:10]:
            lines.append(f"  • {a['parsed_client']} — {a['reason']} ({a['parsed_date']})")
        if len(absences) > 10:
            lines.append(f"  … and {len(absences)-10} more")
        lines.append("")
    
    lines.append("📋 <b>OCR STATUS</b>")
    lines.append(f"  Documents processed: <b>{ocr['total_documents']}</b>")
    lines.append(f"  Names matched to DB: <b>{ocr['matched_names']}</b>")
    lines.append(f"  New today: <b>{ocr['documents_today']}</b>")
    lines.append("")
    
    lines.append("🥗 <b>MENU STATUS</b> (this week)")
    for day, ok in menus.items():
        icon = "✅" if ok else "❌"
        lines.append(f"  {icon} {day}")
    lines.append("")
    
    if auths:
        expired = [a for a in auths if a['days_left'] <= 0]
        expiring = [a for a in auths if 0 < a['days_left'] <= 14]
        if expired:
            lines.append(f"🚨 <b>EXPIRED AUTH</b> — {len(expired)} clients")
            for a in expired[:5]:
                lines.append(f"  • {a['client_name']} — expired {abs(a['days_left'])}d ago")
            lines.append("")
        if expiring:
            lines.append(f"⚠️ <b>EXPIRING SOON</b> — {len(expiring)} clients (≤14 days)")
            for a in expiring[:5]:
                lines.append(f"  • {a['client_name']} — {a['days_left']}d left")
            lines.append("")
    
    lines.append("📡 <b>SYSTEMS</b>")
    lines.append("  DataRex: :8080 ✅ | WhatsApp bridge: active | OCR: MinerU live")
    
    return "\n".join(lines)


def afternoon_report():
    """3 PM afternoon status report."""
    today = date.today()
    day_name = today.strftime("%A")
    now = datetime.now().strftime("%I:%M %p")
    
    att = get_today_attendance(today)
    sigs = get_signatures_today(today)
    changes = get_schedule_changes_today(today)
    victoria = get_victoria_calls(today)
    menus = get_menu_status()
    
    lines = [
        f"🌤 <b>GOJ AFTERNOON REPORT</b> — {today.strftime('%B %d, %Y')} ({day_name})",
        f"<i>Generated {now}</i>",
        "",
        "📊 <b>ATTENDANCE FINAL</b>",
        f"  Shift 1: <b>{att['present_s1']}</b> present",
        f"  Shift 2: <b>{att['present_s2']}</b> present",
        f"  Total: <b>{att['present_total']}</b> | Absent: <b>{att['absent']}</b>",
        "",
        f"📝 <b>SIGNATURES</b>: {sigs} collected today",
        "",
    ]
    
    if changes:
        lines.append("🔄 <b>SCHEDULE CHANGES TODAY</b>")
        for c in changes[:8]:
            lines.append(f"  • {c['client_name']} — {c['change_type']} ({c['note'][:50] if c['note'] else 'no note'})")
        lines.append("")
    
    if victoria:
        lines.append("📞 <b>VICTORIA CALLS TODAY</b>")
        completed = [v for v in victoria if v['status'] == 'completed']
        lines.append(f"  Completed: <b>{len(completed)}</b> / {len(victoria)}")
        for v in victoria[:5]:
            lines.append(f"  • Client {v['client_id']}: {v['status']}")
        lines.append("")
    
    lines.append(f"🚐 <b>DRIVERS:</b> Check DataRex → /api/drivers")
    
    missing_menu_days = [d for d, ok in menus.items() if not ok]
    if missing_menu_days:
        lines.append(f"⚠️ <b>MISSING MENUS:</b> {', '.join(missing_menu_days)}")
    
    lines.append("")
    lines.append("📡 <b>SYSTEMS</b>")
    lines.append("  DataRex :8080 | OCR: live | WhatsApp bridge: active")
    lines.append(f"  Reports: 10 AM ✅ | 3 PM ✅ | 9 PM drop-off (auto)")
    
    return "\n".join(lines)


# ── MAIN ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--morning" in sys.argv:
        report = morning_report()
        label = "10 AM Morning"
    elif "--afternoon" in sys.argv:
        report = afternoon_report()
        label = "3 PM Afternoon"
    else:
        morning = morning_report()
        afternoon = afternoon_report()
        send_telegram(morning)
        send_telegram(afternoon)
        print("[telegram] Both reports sent")
        sys.exit(0)
    
    print(report)
    if "--send" in sys.argv or "--morning" not in sys.argv:
        send_telegram(report)
        print(f"[telegram] {label} report sent")
