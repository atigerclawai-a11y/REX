#!/usr/bin/env python3
"""
GOJ Daily Scheduler — v1.0 (April 2026)
════════════════════════════════════════════════════════════════════════════════
Manages all scheduled GOJ operations via Rexxie (Telegram).
Called by launchd at specific times; each invocation handles one job.

LOCKED SCHEDULE (from GOJ_LOCKED_PARAMETERS.md):
  7:30am daily        → morning_report        — morning briefing via Rexxie
  10:30am daily       → kitchen_sheets        — kitchen + distribution PDFs
  3:15pm daily        → changes_routes        — schedule changes + driver routes
  8:30pm Fri only     → missing_menus_fri     — missing menus alert
  9:00pm daily        → nightly_rundown       — full drop-off rundown
  9:00pm Fri only     → weekly_email_fri      — weekly summary email

Usage:
  python3 goj_daily_scheduler.py --job morning_report
  python3 goj_daily_scheduler.py --job kitchen_sheets
  python3 goj_daily_scheduler.py --job changes_routes
  python3 goj_daily_scheduler.py --job missing_menus_fri
  python3 goj_daily_scheduler.py --job nightly_rundown
  python3 goj_daily_scheduler.py --job weekly_email_fri
  python3 goj_daily_scheduler.py --job status_check

All output is logged to ~/Desktop/REX/logs/goj_scheduler.log
════════════════════════════════════════════════════════════════════════════════
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
REX_DIR       = Path.home() / "Desktop" / "REX"
DASHBOARD_DIR = Path.home() / "Documents" / "goj files" / "dashboard"
DB_PATH       = DASHBOARD_DIR / "auth_tracker.db"
TG_CONFIG     = REX_DIR / "rex_rexxie_telegram_config.json"
LOG_DIR       = REX_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "goj_scheduler.log"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("goj_scheduler")


# ══════════════════════════════════════════════════════════════════════════════
# Telegram helpers
# ══════════════════════════════════════════════════════════════════════════════

def _load_tg_config() -> tuple[str, int]:
    """Load bot token and owner chat ID from Rexxie config."""
    if not TG_CONFIG.exists():
        raise FileNotFoundError(f"Telegram config not found: {TG_CONFIG}")
    cfg = json.loads(TG_CONFIG.read_text())
    return cfg["bot_token"], int(cfg["owner_chat_id"])


def send_message(text: str, parse_mode: str = "Markdown") -> bool:
    """Send a Telegram text message to Kato via Rexxie."""
    try:
        token, chat_id = _load_tg_config()
        url  = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({
            "chat_id":    chat_id,
            "text":       text,
            "parse_mode": parse_mode,
        }).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            result = json.loads(r.read())
            if result.get("ok"):
                log.info("✅ Telegram message sent")
                return True
            else:
                log.error(f"Telegram error: {result}")
                return False
    except Exception as e:
        log.error(f"Failed to send Telegram message: {e}")
        return False


def send_document(pdf_bytes: bytes, filename: str, caption: str = "") -> bool:
    """Send a PDF file to Kato via Rexxie."""
    try:
        token, chat_id = _load_tg_config()
        url      = f"https://api.telegram.org/bot{token}/sendDocument"
        boundary = "----GOJSchedulerBoundary"

        def field(name: str, value: str) -> bytes:
            return (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode()

        body = (
            field("chat_id",    str(chat_id)) +
            field("parse_mode", "Markdown") +
            (field("caption", caption) if caption else b"") +
            f"--{boundary}\r\n".encode() +
            f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'.encode() +
            b"Content-Type: application/pdf\r\n\r\n" +
            pdf_bytes +
            f"\r\n--{boundary}--\r\n".encode()
        )
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
            if result.get("ok"):
                log.info(f"✅ Sent document: {filename}")
                return True
            else:
                log.error(f"Document send error: {result}")
                return False
    except Exception as e:
        log.error(f"Failed to send document {filename}: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# Database helpers
# ══════════════════════════════════════════════════════════════════════════════

def get_db() -> sqlite3.Connection:
    """Open auth_tracker.db with row factory."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _today_service_date() -> date:
    """Return today's date (Mon–Sat). Sunday returns Monday."""
    d = date.today()
    if d.weekday() == 6:  # Sunday
        return d + timedelta(days=1)
    return d


def _is_weekday() -> bool:
    """Return True if today is Mon–Sat (GOJ operates Mon–Sat)."""
    return date.today().weekday() < 6


def _is_friday() -> bool:
    return date.today().weekday() == 4


# ══════════════════════════════════════════════════════════════════════════════
# JOB 1 — 7:30am: Morning Report
# ══════════════════════════════════════════════════════════════════════════════

def job_morning_report():
    """
    7:30am daily via Rexxie.
    Sends a morning briefing: auth expirations, attendance summary,
    any pending flags, and what sheets will be sent at 10:30am.
    """
    log.info("=== JOB: morning_report ===")
    today = date.today()
    dow   = today.strftime("%A")

    if not _is_weekday():
        log.info("Sunday — skipping morning report")
        return

    try:
        db   = get_db()
        cur  = db.cursor()

        # Auth expirations in next 30 days
        cutoff = (today + timedelta(days=30)).isoformat()
        cur.execute("""
            SELECT client_name, service_end_date
            FROM authorization
            WHERE status = 'ACTIVE'
              AND service_end_date <= ?
            ORDER BY service_end_date
            LIMIT 10
        """, (cutoff,))
        expiring = cur.fetchall()

        # Already expired
        cur.execute("""
            SELECT COUNT(*) as n FROM authorization WHERE status = 'EXPIRED'
        """)
        expired_count = cur.fetchone()["n"]

        # Clients with menus this week
        week_start = (today - timedelta(days=today.weekday())).isoformat()
        cur.execute("""
            SELECT COUNT(DISTINCT client_id) as n
            FROM client_menus
            WHERE week_start = ?
        """, (week_start,))
        menus_this_week = cur.fetchone()["n"]

        cur.execute("SELECT COUNT(*) as n FROM clients")
        total_clients = cur.fetchone()["n"]

        db.close()

        # Build message
        lines = [
            f"☀️ *Good morning — {dow}, {today.strftime('%B %d')}*",
            "",
            "📋 *Today's Operations*",
            f"  • Menus loaded this week: {menus_this_week}/{total_clients} clients",
            f"  • Kitchen + distribution sheets → *10:30am*",
            f"  • Schedule changes + routes → *3:15pm*",
            f"  • Nightly rundown → *9:00pm*",
        ]

        if today.weekday() == 4:  # Friday
            lines += [
                "",
                "📅 *Friday Schedule*",
                "  • Missing menus alert → 8:30pm",
                "  • Weekly summary email → 9:00pm",
            ]

        if expiring:
            lines += ["", "⚠️ *Authorizations Expiring (≤30 days)*"]
            for row in expiring:
                lines.append(f"  • {row['client_name']} — expires {row['service_end_date']}")

        if expired_count > 0:
            lines += ["", f"🔴 *Already Expired: {expired_count} auths* — review needed"]

        send_message("\n".join(lines))

    except Exception as e:
        log.error(f"morning_report failed: {e}")
        send_message(f"⚠️ Morning report failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# JOB 2 — 10:30am: Kitchen + Distribution Sheets
# ══════════════════════════════════════════════════════════════════════════════

def job_kitchen_sheets():
    """
    10:30am daily via Rexxie.
    Generates kitchen prep order + distribution sheets for today,
    sends them as PDFs via Telegram.
    """
    log.info("=== JOB: kitchen_sheets ===")

    if not _is_weekday():
        log.info("Sunday — skipping kitchen sheets")
        return

    service_date = _today_service_date()

    # Add generator scripts to path
    sys.path.insert(0, str(REX_DIR / "CC_archive" / "file_generators"))
    sys.path.insert(0, str(REX_DIR))
    try:
        from generate_daily_sheets import run as generate_sheets
    except ImportError as e:
        msg = f"⚠️ Cannot import sheet generators: {e}"
        log.error(msg)
        send_message(msg)
        return

    out_dir = DASHBOARD_DIR.parent / "documents" / "print_sheets"
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = generate_sheets(service_date, DB_PATH, out_dir)

        sent_count = 0

        # Send kitchen sheet
        if result.get("kitchen") and Path(result["kitchen"]).exists():
            pdf_bytes = Path(result["kitchen"]).read_bytes()
            caption   = (
                f"🍳 *Kitchen Prep Order*\n"
                f"{service_date.strftime('%A, %B %d, %Y')}"
            )
            if send_document(pdf_bytes, Path(result["kitchen"]).name, caption):
                sent_count += 1

        # Send distribution sheets
        for fpath in result.get("distribution", []):
            if Path(fpath).exists():
                pdf_bytes = Path(fpath).read_bytes()
                caption   = (
                    f"📋 *Distribution Sheet — {Path(fpath).stem}*\n"
                    f"{service_date.strftime('%A, %B %d, %Y')}"
                )
                if send_document(pdf_bytes, Path(fpath).name, caption):
                    sent_count += 1

        # Summary message
        no_menu = result.get("no_menu_clients", [])
        lines   = [
            f"✅ *Sheets ready — {service_date.strftime('%A, %B %d')}*",
            f"  Sent {sent_count} PDF(s)",
        ]
        if no_menu:
            lines += [
                "",
                f"⚠️ *No menu for {len(no_menu)} client(s):*",
            ] + [f"  • {c}" for c in no_menu[:15]]
            if len(no_menu) > 15:
                lines.append(f"  … and {len(no_menu)-15} more")

        send_message("\n".join(lines))

    except Exception as e:
        log.error(f"kitchen_sheets failed: {e}")
        send_message(f"⚠️ Kitchen/distribution sheets failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# JOB 3 — 3:15pm: Schedule Changes + Driver Routes
# ══════════════════════════════════════════════════════════════════════════════

def job_changes_routes():
    """
    3:15pm daily via Rexxie.
    Reports pending schedule changes logged today and driver route summary.
    """
    log.info("=== JOB: changes_routes ===")

    if not _is_weekday():
        log.info("Sunday — skipping changes/routes")
        return

    today = date.today()

    try:
        db  = get_db()
        cur = db.cursor()

        # Pending schedule changes logged today
        cur.execute("""
            SELECT client_name, change_type,
                   day_key AS old_day, new_value AS new_day,
                   note AS notes, created_at
            FROM pending_schedule_changes
            WHERE DATE(created_at) = ?
            ORDER BY created_at DESC
        """, (today.isoformat(),))
        changes = cur.fetchall()

        # Driver route summary for tomorrow
        tomorrow = today + timedelta(days=1)
        if tomorrow.weekday() == 6:  # Skip Sunday
            tomorrow = today + timedelta(days=2)

        cur.execute("""
            SELECT c.transportation, COUNT(*) as n
            FROM clients c
            WHERE c.transportation IS NOT NULL
              AND c.transportation != ''
            GROUP BY c.transportation
            ORDER BY n DESC
        """)
        routes = cur.fetchall()

        db.close()

        lines = [
            f"🔄 *3:15pm Update — {today.strftime('%A, %B %d')}*",
            "",
        ]

        if changes:
            lines += [f"📝 *Schedule Changes Today ({len(changes)}):*"]
            for ch in changes:
                change_type = ch["change_type"] if ch["change_type"] else "change"
                old_day = ch["old_day"] or "?"
                new_day = ch["new_day"] or "?"
                lines.append(
                    f"  • {ch['client_name']}: {old_day} → {new_day} "
                    f"({change_type})"
                )
                if ch["notes"]:
                    lines.append(f"    _{ch['notes']}_")
        else:
            lines.append("✅ *No schedule changes logged today*")

        if routes:
            lines += ["", f"🚌 *Driver Routes — {tomorrow.strftime('%A')}:*"]
            for r in routes:
                if r["transportation"]:
                    lines.append(f"  • {r['transportation']}: {r['n']} clients")

        send_message("\n".join(lines))

    except Exception as e:
        log.error(f"changes_routes failed: {e}")
        send_message(f"⚠️ Schedule/routes report failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# JOB: signin_driver_sheets — 3:00pm weekdays
# ══════════════════════════════════════════════════════════════════════════════

def job_signin_driver_sheets():
    """
    3:00pm weekdays — Generate sign-in + driver route sheets for next business day
    and send as PDFs via Telegram to Kato.
    Mon–Thu → generates for tomorrow; Fri → generates for Monday.
    """
    log.info("=== JOB: signin_driver_sheets ===")

    if not _is_weekday():
        log.info("Weekend — skipping signin/driver sheets")
        return

    # Determine next business day
    today = date.today()
    if today.weekday() == 4:  # Friday → Monday
        next_day = today + timedelta(days=3)
    else:
        next_day = today + timedelta(days=1)

    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_codes = ["M", "T", "W", "TH", "F", "Sa", "Su"]
    next_day_name = day_names[next_day.weekday()]
    next_day_code = day_codes[next_day.weekday()]
    next_date_str = next_day.strftime("%Y-%m-%d")
    next_date_fmt = next_day.strftime("%B %d, %Y")

    # Paths
    generator = DASHBOARD_DIR / "generate_tomorrow.py"
    out_dir   = DASHBOARD_DIR.parent / "output_docs"
    out_dir.mkdir(parents=True, exist_ok=True)

    import subprocess
    venv_py = REX_DIR / ".venv" / "bin" / "python3"
    py_bin  = str(venv_py) if venv_py.exists() else sys.executable

    # Run sign-in generator
    generated_files = []
    try:
        result = subprocess.run(
            [py_bin, str(generator), "--day", next_day_name, "--mode", "signin"],
            capture_output=True, text=True, cwd=str(DASHBOARD_DIR), timeout=120
        )
        log.info(f"signin generator stdout: {result.stdout[-500:]}")
        if result.returncode != 0:
            log.warning(f"signin generator stderr: {result.stderr[-300:]}")
    except Exception as e:
        log.error(f"signin generator failed: {e}")

    # Run driver generator
    try:
        result = subprocess.run(
            [py_bin, str(generator), "--day", next_day_name, "--mode", "drivers"],
            capture_output=True, text=True, cwd=str(DASHBOARD_DIR), timeout=120
        )
        log.info(f"drivers generator stdout: {result.stdout[-500:]}")
        if result.returncode != 0:
            log.warning(f"drivers generator stderr: {result.stderr[-300:]}")
    except Exception as e:
        log.error(f"drivers generator failed: {e}")

    # Collect generated PDFs
    day_code_upper = next_day_code
    expected_files = [
        out_dir / f"GOJ_{day_code_upper}_S1_{next_day_name}_signin.pdf",
        out_dir / f"GOJ_{day_code_upper}_S2_{next_day_name}_signin.pdf",
        out_dir / f"GOJ_{day_code_upper}_S1_{next_day_name}_drivers.pdf",
        out_dir / f"GOJ_{day_code_upper}_S2_{next_day_name}_drivers.pdf",
    ]
    for f in expected_files:
        if f.exists():
            generated_files.append(f)

    # Load route data to count clients/drivers
    routes_path = REX_DIR / "GOJ_Master_Routes.json"
    shift1_count = shift2_count = driver_count = 0
    try:
        import json, re as _re
        routes = json.loads(routes_path.read_text())
        s1_key = f"{next_day_code}1"
        s2_key = f"{next_day_code}2"
        s1_entries = [e for e in routes.get(s1_key, []) if e.get("status","active")=="active"]
        s2_entries = [e for e in routes.get(s2_key, []) if e.get("status","active")=="active"]
        # Count from DB if available (more accurate)
        if DB_PATH.exists():
            import sqlite3
            col_map = {"M":"day_M_actual","T":"day_T_actual","W":"day_W_actual",
                       "TH":"day_TH_actual","F":"day_F_actual","Su":"day_Su_actual"}
            col = col_map.get(next_day_code)
            if col:
                db = sqlite3.connect(str(DB_PATH))
                s1c = db.execute(f"SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=1").fetchone()[0]
                s2c = db.execute(f"SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=2").fetchone()[0]
                db.close()
                shift1_count, shift2_count = s1c, s2c
        if shift1_count == 0:
            shift1_count, shift2_count = len(s1_entries), len(s2_entries)
        # Count unique named drivers
        driver_set = set()
        for e in s1_entries + s2_entries:
            if e.get("car_service"): continue
            raw = e.get("driver","").strip()
            if not raw or raw.lower() in ("(unassigned)","tba",""): continue
            for part in _re.split(r"[/,]", raw):
                part = part.strip()
                if part and part.lower() not in ("(unassigned)","tba",""):
                    driver_set.add(part.title())
        driver_count = len(driver_set)
    except Exception as e:
        log.warning(f"Route counting failed: {e}")

    total_clients = shift1_count + shift2_count

    # Fall back to templates if nothing generated
    use_fallback = len(generated_files) == 0
    if use_fallback:
        log.warning("No sheets generated — falling back to blank templates")
        fallback_signin = REX_DIR / "TEMPLATE_signin.pdf"
        fallback_driver = REX_DIR / "TEMPLATE_driver.pdf"
        for t in [fallback_signin, fallback_driver]:
            if t.exists():
                generated_files.append(t)

    # Send summary message
    if use_fallback:
        summary = (
            f"🚗 <b>GOJ Sheets for {next_day_name}, {next_date_fmt}</b>\n\n"
            f"⚠️ Could not generate populated sheets — sending blank templates instead.\n\n"
            f"📋 Blank sign-in sheet and driver template attached below."
        )
    else:
        summary = (
            f"🚗 <b>GOJ Sheets for {next_day_name}, {next_date_fmt}</b>\n\n"
            f"👥 Clients expected: {total_clients}\n"
            f"  Shift 1: {shift1_count} | Shift 2: {shift2_count}\n"
            f"🚌 Drivers on duty: {driver_count}\n\n"
            f"📋 Sign-in sheet and driver lists attached below."
        )

    send_message(summary, parse_mode="HTML")

    # Send PDFs
    sent = 0
    for pdf_path in generated_files:
        if pdf_path.exists():
            try:
                pdf_bytes = pdf_path.read_bytes()
                caption   = f"📄 {pdf_path.stem.replace('_', ' ')} — {next_day_name} {next_date_fmt}"
                if send_document(pdf_bytes, pdf_path.name, caption):
                    sent += 1
                    log.info(f"Sent: {pdf_path.name}")
                else:
                    log.warning(f"Failed to send: {pdf_path.name}")
            except Exception as e:
                log.error(f"Error sending {pdf_path.name}: {e}")

    log.info(f"signin_driver_sheets complete — {sent}/{len(generated_files)} PDFs sent")


# ══════════════════════════════════════════════════════════════════════════════
# JOB 4 — 8:30pm Friday: Missing Menus Alert
# ══════════════════════════════════════════════════════════════════════════════

def job_missing_menus_fri():
    """
    8:30pm Friday only via Rexxie.
    Checks which clients have no menu for NEXT week (menus should be in by Friday).
    """
    log.info("=== JOB: missing_menus_fri ===")

    if not _is_friday():
        log.info(f"Not Friday ({date.today().strftime('%A')}) — skipping missing menus alert")
        return

    today      = date.today()
    # Next week starts next Monday
    days_ahead = 7 - today.weekday()  # weekday() == 4 for Friday
    next_monday = today + timedelta(days=days_ahead)
    week_start  = next_monday.isoformat()

    try:
        db  = get_db()
        cur = db.cursor()

        # Clients with at least one menu entry next week
        cur.execute("""
            SELECT DISTINCT client_id FROM client_menus WHERE week_start = ?
        """, (week_start,))
        have_menu_ids = {row["client_id"] for row in cur.fetchall()}

        # All active clients
        cur.execute("""
            SELECT client_id, name
            FROM clients
            ORDER BY name
        """)
        all_clients = cur.fetchall()

        missing = [
            c for c in all_clients
            if c["client_id"] not in have_menu_ids
        ]

        db.close()

        lines = [
            f"📋 *Friday Menu Check — Week of {next_monday.strftime('%B %d')}*",
            "",
        ]

        if missing:
            lines += [
                f"⚠️ *{len(missing)} clients missing menus for next week:*",
                "",
            ]
            for c in missing[:30]:
                lines.append(f"  • {c['name']}")
            if len(missing) > 30:
                lines.append(f"  … and {len(missing)-30} more")
            lines += [
                "",
                "_Menus should be scanned and emailed by end of day._",
            ]
        else:
            lines.append(f"✅ *All {len(all_clients)} clients have menus for next week!*")

        send_message("\n".join(lines))

        # GOJ v1.3 — Auto-trigger OCR on any unprocessed PDFs in menus folder
        _maybe_trigger_ocr(week_start)

    except Exception as e:
        log.error(f"missing_menus_fri failed: {e}")
        send_message(f"⚠️ Missing menus check failed: {e}")


def _maybe_trigger_ocr(week_start: str):
    """GOJ v1.3 — If new menu PDFs are in the folder and not yet in DB, trigger OCR."""
    import subprocess, threading

    menu_dir = os.path.expanduser("~/Documents/goj files/dashboard/documents/menus")
    if not os.path.isdir(menu_dir):
        return

    pdfs = [f for f in os.listdir(menu_dir) if f.lower().endswith('.pdf')]
    if not pdfs:
        return

    # Check if DB already has menus for this week
    try:
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) FROM client_menus WHERE week_start=?", (week_start,))
        count = cur.fetchone()[0]
        db.close()
        if count > 0:
            log.info(f"_maybe_trigger_ocr: {count} menus already in DB for {week_start}, skipping")
            return
    except Exception as e:
        log.warning(f"_maybe_trigger_ocr DB check failed: {e}")

    log.info(f"_maybe_trigger_ocr: {len(pdfs)} PDFs found, 0 in DB for {week_start} — starting OCR")
    send_message(f"🔍 Found {len(pdfs)} menu PDF(s) — starting 4-engine OCR automatically. Send `MENU FLAGS` to Rexxie when done.")

    venv_py = os.path.expanduser("~/Desktop/REX/.venv/bin/python3")
    py = venv_py if os.path.exists(venv_py) else "python3"
    ocr_script = os.path.expanduser("~/Desktop/REX/goj_menu_consensus_ocr.py")
    db_path = os.path.expanduser("~/Documents/goj files/dashboard/auth_tracker.db")
    flags_path = os.path.expanduser("~/Desktop/REX/goj_menu_flags_queue.json")
    learning_path = os.path.expanduser("~/Desktop/REX/goj_menu_learning.json")
    log_path = os.path.expanduser("~/Desktop/REX/logs/ocr_auto_run.log")

    def _run():
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, 'w') as logf:
            result = subprocess.run(
                [py, ocr_script, '--menu-dir', menu_dir, '--db', db_path,
                 '--learning', learning_path, '--flags', flags_path],
                stdout=logf, stderr=logf
            )
        if result.returncode == 0:
            send_message("✅ OCR complete. Send `MENU FLAGS` to review any low-confidence results.")
        else:
            send_message(f"⚠️ OCR finished with errors. Check `{log_path}`.")

    threading.Thread(target=_run, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════════════
# JOB 5 — 9:00pm Daily: Nightly Rundown
# ══════════════════════════════════════════════════════════════════════════════

def job_nightly_rundown():
    """
    9:00pm daily via Rexxie.
    Target: "No decisions necessary."
    Full summary of the day — attendance, schedule changes, auth flags, menus.
    """
    log.info("=== JOB: nightly_rundown ===")

    if not _is_weekday():
        log.info("Sunday — skipping nightly rundown")
        return

    today = date.today()

    try:
        db  = get_db()
        cur = db.cursor()

        # Attendance today (if attendance_log table exists)
        try:
            cur.execute("""
                SELECT
                    SUM(CASE WHEN status = 'present' THEN 1 ELSE 0 END) AS present,
                    SUM(CASE WHEN status = 'absent'  THEN 1 ELSE 0 END) AS absent,
                    SUM(CASE WHEN status = 'late'    THEN 1 ELSE 0 END) AS late,
                    COUNT(*) AS total
                FROM attendance_log
                WHERE log_date = ?
            """, (today.isoformat(),))
            att = cur.fetchone()
            att_present = att["present"] or 0
            att_absent  = att["absent"]  or 0
            att_late    = att["late"]    or 0
        except Exception:
            att_present = att_absent = att_late = None

        # Schedule changes today
        try:
            cur.execute("""
                SELECT COUNT(*) as n FROM pending_schedule_changes
                WHERE DATE(created_at) = ?
            """, (today.isoformat(),))
            change_count = cur.fetchone()["n"]
        except Exception:
            change_count = 0

        # Auth expiring within 7 days
        cutoff7 = (today + timedelta(days=7)).isoformat()
        cur.execute("""
            SELECT client_name, service_end_date
            FROM authorization
            WHERE status = 'ACTIVE' AND service_end_date <= ?
            ORDER BY service_end_date
        """, (cutoff7,))
        urgent_auths = cur.fetchall()

        # Menu coverage for today's date
        week_start = (today - timedelta(days=today.weekday())).isoformat()
        cur.execute("""
            SELECT COUNT(DISTINCT client_id) as n
            FROM client_menus
            WHERE week_start = ?
        """, (week_start,))
        menus_count = cur.fetchone()["n"]

        cur.execute("SELECT COUNT(*) as n FROM clients")
        total_clients = cur.fetchone()["n"]

        db.close()

        lines = [
            f"🌙 *Nightly Rundown — {today.strftime('%A, %B %d, %Y')}*",
            "_No decisions necessary._",
            "",
        ]

        # Attendance block
        if att_present is not None:
            lines += [
                "📊 *Attendance Today*",
                f"  Present: {att_present} | Absent: {att_absent} | Late: {att_late}",
                "",
            ]

        # Menus block
        menu_pct = int((menus_count / total_clients) * 100) if total_clients else 0
        menu_icon = "✅" if menu_pct >= 95 else "⚠️"
        lines += [
            f"🍽️ *Menu Coverage This Week*",
            f"  {menu_icon} {menus_count}/{total_clients} clients ({menu_pct}%)",
            "",
        ]

        # Schedule changes block
        if change_count > 0:
            lines += [
                f"🔄 *Schedule Changes Today: {change_count}*",
                "  Review dashboard for details",
                "",
            ]
        else:
            lines += ["✅ *No schedule changes today*", ""]

        # Auth urgency block
        if urgent_auths:
            lines += [f"🚨 *Auth Expiring in 7 Days ({len(urgent_auths)}):*"]
            for a in urgent_auths:
                lines.append(f"  • {a['client_name']} — {a['service_end_date']}")
            lines.append("")

        lines += [
            "─────────────────────",
            "✅ *Day complete. System nominal.*",
        ]

        if today.weekday() == 4:  # Friday reminder
            lines += ["", "📧 Weekly summary email sending at 9pm → Kato email"]

        send_message("\n".join(lines))

    except Exception as e:
        log.error(f"nightly_rundown failed: {e}")
        send_message(f"⚠️ Nightly rundown failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# JOB 6 — 9:00pm Friday: Weekly Summary Email
# ══════════════════════════════════════════════════════════════════════════════

def job_weekly_email_fri():
    """
    9:00pm Friday only.
    Sends a weekly summary email to Kato via Gmail API (if configured).
    Falls back to Telegram summary if Gmail not available.
    """
    log.info("=== JOB: weekly_email_fri ===")

    if not _is_friday():
        log.info(f"Not Friday ({date.today().strftime('%A')}) — skipping weekly email")
        return

    today      = date.today()
    week_start = (today - timedelta(days=today.weekday())).isoformat()
    week_end   = today.isoformat()

    try:
        db  = get_db()
        cur = db.cursor()

        # Menu coverage for the week
        cur.execute("""
            SELECT COUNT(DISTINCT client_id) as n
            FROM client_menus WHERE week_start = ?
        """, (week_start,))
        menus_count = cur.fetchone()["n"]

        cur.execute("SELECT COUNT(*) as n FROM clients")
        total_clients = cur.fetchone()["n"]

        # Schedule changes this week
        try:
            cur.execute("""
                SELECT COUNT(*) as n FROM pending_schedule_changes
                WHERE DATE(created_at) >= ?
            """, (week_start,))
            changes_week = cur.fetchone()["n"]
        except Exception:
            changes_week = 0

        # Auth expiring in 30 days
        cutoff30 = (today + timedelta(days=30)).isoformat()
        cur.execute("""
            SELECT COUNT(*) as n FROM authorization
            WHERE status = 'ACTIVE' AND service_end_date <= ?
        """, (cutoff30,))
        auths_expiring_soon = cur.fetchone()["n"]

        cur.execute("""
            SELECT COUNT(*) as n FROM authorization WHERE status = 'EXPIRED'
        """)
        expired_total = cur.fetchone()["n"]

        db.close()

        # Try Gmail send
        gmail_sent = _try_send_weekly_email(
            today, week_start, menus_count, total_clients,
            changes_week, auths_expiring_soon, expired_total
        )

        # Always also send via Telegram as confirmation
        menu_pct  = int((menus_count / total_clients) * 100) if total_clients else 0
        tg_lines = [
            f"📧 *Weekly Summary — Week of {week_start}*",
            "",
            f"🍽️ Menu coverage: {menus_count}/{total_clients} ({menu_pct}%)",
            f"🔄 Schedule changes: {changes_week}",
            f"⚠️ Auths expiring ≤30 days: {auths_expiring_soon}",
            f"🔴 Already expired auths: {expired_total}",
            "",
        ]
        if gmail_sent:
            tg_lines.append("✅ Weekly summary email sent to Kato")
        else:
            tg_lines.append("⚠️ Email not sent (Gmail not configured) — summary above is via Telegram only")

        send_message("\n".join(tg_lines))

    except Exception as e:
        log.error(f"weekly_email_fri failed: {e}")
        send_message(f"⚠️ Weekly email job failed: {e}")


def _try_send_weekly_email(
    today: date, week_start: str,
    menus_count: int, total_clients: int,
    changes_week: int, auths_expiring_soon: int, expired_total: int
) -> bool:
    """Attempt to send weekly summary via Gmail API. Returns True if sent."""
    gmail_token = REX_DIR / "gmail_token.json"
    gmail_creds = REX_DIR / "google_credentials.json"
    if not gmail_token.exists() or not gmail_creds.exists():
        log.warning("Gmail credentials not found — skipping email send")
        return False

    try:
        import base64
        from email.mime.text import MIMEText
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds   = Credentials.from_authorized_user_file(str(gmail_token))
        service = build("gmail", "v1", credentials=creds)

        menu_pct  = int((menus_count / total_clients) * 100) if total_clients else 0
        week_end  = today.isoformat()

        subject = f"GOJ Weekly Summary — Week of {week_start}"
        body    = f"""Garden of Joy — Weekly Operations Summary
Week: {week_start} through {week_end}

MENU COVERAGE
  Clients with menus this week: {menus_count} / {total_clients} ({menu_pct}%)

SCHEDULE CHANGES
  Changes logged this week: {changes_week}

AUTHORIZATIONS
  Expiring within 30 days: {auths_expiring_soon}
  Already expired: {expired_total}

---
Generated automatically by GOJ REX Scheduler.
Dashboard: http://localhost:8080
"""
        msg = MIMEText(body)
        msg["to"]      = "atigerclawai@gmail.com"
        msg["subject"] = subject

        encoded = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(
            userId="me",
            body={"raw": encoded}
        ).execute()

        log.info("✅ Weekly summary email sent via Gmail")
        return True

    except Exception as e:
        log.error(f"Gmail send failed: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# STATUS CHECK — run manually to verify scheduler config
# ══════════════════════════════════════════════════════════════════════════════

def job_status_check():
    """Verify all scheduler dependencies and report status via Telegram."""
    log.info("=== JOB: status_check ===")

    lines = ["🔧 *GOJ Scheduler Status Check*", ""]

    # DB check
    if DB_PATH.exists():
        try:
            db  = get_db()
            cur = db.cursor()
            cur.execute("SELECT COUNT(*) as n FROM clients")
            n = cur.fetchone()["n"]
            db.close()
            lines.append(f"✅ Database: {n} clients")
        except Exception as e:
            lines.append(f"❌ Database error: {e}")
    else:
        lines.append(f"❌ Database not found: {DB_PATH}")

    # Telegram config
    if TG_CONFIG.exists():
        lines.append("✅ Telegram config: found")
    else:
        lines.append(f"❌ Telegram config missing: {TG_CONFIG}")

    # Gmail token
    if (REX_DIR / "gmail_token.json").exists():
        lines.append("✅ Gmail token: found")
    else:
        lines.append("⚠️ Gmail token: not found (weekly email will use Telegram fallback)")

    # Sheet generators
    gen_dist  = REX_DIR / "generate_distribution_sheet.py"
    gen_kitch = REX_DIR / "generate_kitchen_sheet.py"
    lines.append(f"{'✅' if gen_dist.exists() else '❌'} Distribution generator: {gen_dist.name}")
    lines.append(f"{'✅' if gen_kitch.exists() else '❌'} Kitchen generator: {gen_kitch.name}")

    # Log dir
    lines.append(f"✅ Log dir: {LOG_DIR}")

    lines += [
        "",
        "*Scheduled jobs:*",
        "  7:30am  → morning_report",
        "  10:30am → kitchen_sheets",
        "  3:15pm  → changes_routes",
        "  8:30pm Fri → missing_menus_fri",
        "  9:00pm  → nightly_rundown",
        "  9:00pm Fri → weekly_email_fri",
    ]

    send_message("\n".join(lines))


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

JOBS = {
    "morning_report":        job_morning_report,
    "kitchen_sheets":        job_kitchen_sheets,
    "signin_driver_sheets":  job_signin_driver_sheets,
    "changes_routes":        job_changes_routes,
    "missing_menus_fri":     job_missing_menus_fri,
    "nightly_rundown":       job_nightly_rundown,
    "weekly_email_fri":      job_weekly_email_fri,
    "status_check":          job_status_check,
}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="GOJ Daily Scheduler — invoke one job per call"
    )
    parser.add_argument(
        "--job",
        required=True,
        choices=list(JOBS.keys()),
        help="Which scheduled job to run"
    )
    args = parser.parse_args()

    log.info(f"Starting job: {args.job} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    try:
        JOBS[args.job]()
        log.info(f"Job completed: {args.job}")
    except Exception as e:
        log.error(f"Job {args.job} raised unhandled exception: {e}")
        sys.exit(1)
