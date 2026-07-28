#!/usr/bin/env python3
"""
CC_cron_guardian.py — GHS Self-Healing Cron Guardian
=====================================================
Monitors all GOJ cron jobs (n8n + launchd automations).
- Intercepts failures before they hit Kato's Telegram
- Self-fixes what it can (restarts dead services, re-queues jobs, repairs common errors)
- Buffers all cron activity into a digest
- Sends ONE consolidated message at 9pm: what ran, what broke, what was fixed, what needs Kato

Architecture:
  - Runs every 2 minutes via LaunchAgent (com.ghs.cron-guardian.plist)
  - Reads from launchd logs and n8n webhook log
  - Writes to ~/Desktop/REX/logs/cron_guardian.log
  - Accumulates the day's events in ~/Desktop/REX/CC_cron_digest.json
  - At 9:00–9:05pm: fires digest to Kato via Telegram, resets the buffer

Usage:
  python CC_cron_guardian.py          # run one check cycle
  python CC_cron_guardian.py digest   # force-send tonight's digest now
  python CC_cron_guardian.py status   # print today's buffer to stdout

Install:
  python CC_cron_guardian.py install  # writes and loads the LaunchAgent plist
"""

import subprocess, json, os, sys, re, time, logging, traceback
from pathlib import Path
from datetime import datetime, date
from typing import Optional

# ── CONFIG ──────────────────────────────────────────────────────────────────
BASE          = Path.home() / "Desktop/REX"
LOG_DIR       = BASE / "logs"
LOG_FILE      = LOG_DIR / "cron_guardian.log"
DIGEST_FILE   = BASE / "CC_cron_digest.json"
DIGEST_HOUR   = 21       # 9pm
DIGEST_WINDOW = 5        # send between 21:00 and 21:05

TELEGRAM_BOT_TOKEN = os.environ.get("HERMES_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = "5587703834"   # Kato

# GOJ daily automation schedule (for missed-job detection)
EXPECTED_JOBS = [
    {"id": "morning_report",      "hour": 7,  "minute": 30, "name": "Morning Report",           "service": "com.goj.morning-report"},
    {"id": "kitchen_distrib",     "hour": 10, "minute": 30, "name": "Kitchen + Distribution",    "service": "com.goj.kitchen-sheet"},
    {"id": "signin_driver",       "hour": 15, "minute": 15, "name": "Sign-in + Driver Sheets",   "service": "com.goj.driver-sheet"},
    {"id": "missing_menus_fri",   "hour": 20, "minute": 30, "name": "Missing Menus Alert (Fri)", "service": "com.goj.missing-menus", "weekday": 5},
    {"id": "dropoff_rundown",     "hour": 21, "minute": 0,  "name": "Drop-off Rundown",          "service": "com.goj.dropoff"},
    {"id": "weekly_email_fri",    "hour": 21, "minute": 0,  "name": "Weekly Email (Fri)",        "service": "com.goj.weekly-email", "weekday": 5},
]

# Services that can be auto-restarted
RESTARTABLE_SERVICES = {
    "com.rex.backend":                  {"type": "launchd", "plist": "~/Library/LaunchAgents/com.rex.backend.plist"},
    "com.goj.datarex":                  {"type": "launchd", "plist": "~/Library/LaunchAgents/com.goj.datarex.plist"},
    "ai.hermes.gateway-cloud":          {"type": "launchd", "plist": "~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist"},
    "com.hermes.claus-watchman":        {"type": "launchd", "plist": "~/Library/LaunchAgents/com.hermes.claus-watchman.plist"},
    "com.ghs.dock-enforcer":            {"type": "launchd", "plist": "~/Library/LaunchAgents/com.ghs.dock-enforcer.plist"},
}

PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ghs.cron-guardian</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/sh</string>
        <string>-c</string>
        <string>source ~/.rex-venv/bin/activate 2>/dev/null || source ~/debate-chamber/.venv/bin/activate 2>/dev/null; python "$HOME/Desktop/REX/CC_cron_guardian.py" 2>>"$HOME/Desktop/REX/logs/cron_guardian_err.log"</string>
    </array>
    <key>RunAtLoad</key>
    <false/>
    <key>StartInterval</key>
    <integer>120</integer>
    <key>StandardOutPath</key>
    <string>/tmp/cron-guardian.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/cron-guardian-err.log</string>
</dict>
</plist>
"""

# ── LOGGING ─────────────────────────────────────────────────────────────────
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [GUARDIAN] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("cron_guardian")

# ── DIGEST STATE ─────────────────────────────────────────────────────────────
def load_digest() -> dict:
    today = str(date.today())
    if DIGEST_FILE.exists():
        try:
            d = json.loads(DIGEST_FILE.read_text())
            if d.get("date") == today:
                return d
        except Exception:
            pass
    return {
        "date": today,
        "jobs_ran": [],      # {id, name, time, status}
        "jobs_missed": [],   # {id, name, expected_time}
        "fixes_applied": [], # {type, service, action, time, result}
        "errors_seen": [],   # {source, message, time, severity}
        "needs_kato": [],    # {item, reason, urgency}
        "last_check": None,
    }

def save_digest(d: dict):
    DIGEST_FILE.write_text(json.dumps(d, indent=2, default=str))

def add_event(digest: dict, category: str, event: dict):
    event["_ts"] = datetime.now().isoformat()
    digest[category].append(event)
    save_digest(digest)

# ── LAUNCHD HELPERS ──────────────────────────────────────────────────────────
def launchctl_list() -> dict:
    """Returns {label: {pid, status}} for all loaded agents."""
    result = {}
    try:
        out = subprocess.check_output(["launchctl", "list"], text=True, timeout=10)
        for line in out.splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) >= 3:
                pid_str, status_str, label = parts[0], parts[1], parts[2]
                result[label] = {
                    "pid": None if pid_str == "-" else pid_str,
                    "status": int(status_str) if status_str.isdigit() or (status_str.startswith('-') and status_str[1:].isdigit()) else 0
                }
    except Exception as e:
        log.warning(f"launchctl list failed: {e}")
    return result

def restart_service(label: str, plist_path: str) -> tuple[bool, str]:
    """Unload + load a LaunchAgent. Returns (success, message)."""
    plist = os.path.expanduser(plist_path)
    if not os.path.exists(plist):
        return False, f"plist not found: {plist}"
    try:
        subprocess.run(["launchctl", "unload", plist], timeout=10, capture_output=True)
        time.sleep(2)
        result = subprocess.run(["launchctl", "load", plist], timeout=10, capture_output=True, text=True)
        if result.returncode == 0:
            return True, f"Restarted {label}"
        else:
            return False, f"Load failed: {result.stderr.strip()}"
    except Exception as e:
        return False, str(e)

def check_http_health(url: str, timeout: int = 5) -> bool:
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status < 400
    except Exception:
        return False

# ── CORE CHECKS ─────────────────────────────────────────────────────────────
def check_critical_services(digest: dict):
    """Check that REX (8000) and GOJ Dashboard (8080) are alive. Restart if dead."""
    services = [
        {"url": "http://localhost:8000/api/health", "name": "REX FastAPI",    "label": "com.rex.backend"},
        {"url": "http://localhost:8080/health",      "name": "GOJ Dashboard",  "label": "com.goj.datarex"},
    ]
    agents = launchctl_list()

    for svc in services:
        alive = check_http_health(svc["url"])
        if not alive:
            log.warning(f"{svc['name']} is DOWN — attempting restart")
            info = RESTARTABLE_SERVICES.get(svc["label"], {})
            if info:
                ok, msg = restart_service(svc["label"], info["plist"])
                fix = {"type": "service_restart", "service": svc["name"], "action": msg, "result": "success" if ok else "failed"}
                add_event(digest, "fixes_applied", fix)
                if ok:
                    log.info(f"✅ Auto-fixed: {svc['name']} restarted")
                else:
                    log.error(f"❌ Could not restart {svc['name']}: {msg}")
                    add_event(digest, "needs_kato", {"item": f"{svc['name']} is DOWN", "reason": f"Auto-restart failed: {msg}", "urgency": "HIGH"})
            else:
                add_event(digest, "needs_kato", {"item": f"{svc['name']} is DOWN", "reason": "No restart config — manual fix needed", "urgency": "HIGH"})

def check_missed_jobs(digest: dict):
    """Compare current time to expected job schedule. Flag anything that should have run."""
    now = datetime.now()
    today_wd = now.weekday() + 1  # 1=Mon ... 7=Sun

    already_missed = {e["id"] for e in digest.get("jobs_missed", [])}
    already_ran = {e["id"] for e in digest.get("jobs_ran", [])}

    for job in EXPECTED_JOBS:
        if "weekday" in job and job["weekday"] != today_wd:
            continue
        expected_dt = now.replace(hour=job["hour"], minute=job["minute"], second=0, microsecond=0)
        if now < expected_dt:
            continue  # hasn't run yet today — skip
        # Should have run by now
        grace_minutes = 20
        if (now - expected_dt).seconds / 60 < grace_minutes:
            continue  # within grace period
        if job["id"] in already_ran:
            continue  # we saw it run
        if job["id"] in already_missed:
            continue  # already noted today
        log.warning(f"MISSED JOB: {job['name']} expected at {job['hour']:02d}:{job['minute']:02d}")
        add_event(digest, "jobs_missed", {"id": job["id"], "name": job["name"], "expected": f"{job['hour']:02d}:{job['minute']:02d}"})

def check_launchd_errors(digest: dict):
    """Check launchd agents for exit codes indicating failure."""
    agents = launchctl_list()
    for label, info in agents.items():
        if not label.startswith(("com.goj.", "com.rex.", "ai.hermes.")):
            continue
        status = info.get("status", 0)
        pid = info.get("pid")
        if status != 0 and pid is None:
            # Non-zero last exit, not currently running = crashed
            log.warning(f"Crashed agent: {label} (exit={status})")
            already = any(e.get("service") == label for e in digest.get("errors_seen", []))
            if not already:
                add_event(digest, "errors_seen", {
                    "source": "launchd", "message": f"{label} exited with code {status}",
                    "severity": "MEDIUM"
                })
                # Try auto-restart for known restartable services
                if label in RESTARTABLE_SERVICES:
                    info_svc = RESTARTABLE_SERVICES[label]
                    ok, msg = restart_service(label, info_svc["plist"])
                    add_event(digest, "fixes_applied", {"type": "crash_restart", "service": label, "action": msg, "result": "success" if ok else "failed"})
                    log.info(f"{'✅' if ok else '❌'} Crash recovery for {label}: {msg}")

def check_telegram_bot(digest: dict):
    """Check if the Hermes Telegram gateway bot is responding."""
    # Check for zombie plist that steals the Rexxie token
    try:
        result = subprocess.run(
            ["launchctl", "list"], capture_output=True, text=True, timeout=5
        )
        if "hermes.rexxie-bot" in result.stdout:
            log.warning("ZOMBIE PLIST DETECTED: com.hermes.rexxie-bot is loaded — unloading")
            plist = os.path.expanduser("~/Library/LaunchAgents/com.hermes.rexxie-bot.plist")
            subprocess.run(["launchctl", "unload", plist], capture_output=True)
            add_event(digest, "fixes_applied", {
                "type": "zombie_kill",
                "service": "com.hermes.rexxie-bot",
                "action": "Unloaded zombie plist (was stealing Rexxie token)",
                "result": "success"
            })
        # Check hermes gateway is up
        hermes_ok = check_http_health("http://localhost:3002/health", timeout=4)
        if not hermes_ok:
            already = any("hermes" in e.get("source","") for e in digest.get("errors_seen",[]))
            if not already:
                add_event(digest, "errors_seen", {
                    "source": "hermes_gateway",
                    "message": "Hermes gateway :3002 not responding — Telegram bot may be offline",
                    "severity": "HIGH"
                })
    except Exception as e:
        log.warning(f"Telegram check error: {e}")

def check_kanban_proxy(digest: dict):
    """Check if Kanban proxy on port 9119 is running."""
    if check_http_health("http://localhost:9119", timeout=3):
        return  # All good
    already = any("9119" in e.get("message","") for e in digest.get("errors_seen",[]))
    if not already:
        add_event(digest, "errors_seen", {
            "source": "kanban_proxy",
            "message": "Kanban dashboard proxy :9119 is DOWN — Hermes Workspace not running",
            "severity": "MEDIUM"
        })
        add_event(digest, "needs_kato", {
            "item": "Kanban :9119 DOWN",
            "reason": "Hermes Workspace not running · PAE-5 unquarantine would fix permanently",
            "urgency": "MEDIUM"
        })

def check_n8n_status(digest: dict):
    """Ping n8n healthcheck if accessible."""
    try:
        ok = check_http_health("http://localhost:5678/healthz", timeout=3)
        if not ok:
            already = any("n8n" in e.get("source","") for e in digest.get("errors_seen",[]))
            if not already:
                add_event(digest, "errors_seen", {"source":"n8n","message":"n8n not responding on port 5678","severity":"MEDIUM"})
                add_event(digest, "needs_kato", {"item":"n8n is DOWN","reason":"Port 5678 not responding","urgency":"MEDIUM"})
    except Exception:
        pass

def check_gmail_token(digest: dict):
    """Check if the Gmail token exists and is fresh enough."""
    token_path = Path.home() / ".rex_google_token.json"
    if not token_path.exists():
        already = any("gmail" in e.get("source","").lower() for e in digest.get("errors_seen",[]))
        if not already:
            add_event(digest, "errors_seen", {"source":"gmail_token","message":"~/.rex_google_token.json missing — GOJ pipeline stale","severity":"HIGH"})
            add_event(digest, "needs_kato", {"item":"Gmail token missing","reason":"Run CC_google_oauth_fix.command to restore GOJ pipeline","urgency":"HIGH"})
        return
    try:
        age_hours = (time.time() - token_path.stat().st_mtime) / 3600
        if age_hours > 12:
            already = any(e.get("item","").startswith("Gmail token") for e in digest.get("needs_kato",[]))
            if not already:
                add_event(digest, "needs_kato", {"item":f"Gmail token is {age_hours:.0f}h old","reason":"May be stale — run CC_google_oauth_fix.command if GOJ reports show yesterday's data","urgency":"LOW"})
    except Exception:
        pass

def check_dock_enforcer(digest: dict):
    """Ensure the dock enforcer LaunchAgent is running."""
    agents = launchctl_list()
    label = "com.ghs.dock-enforcer"
    if label not in agents:
        log.warning("Dock enforcer not loaded — reloading")
        plist = os.path.expanduser("~/Library/LaunchAgents/com.ghs.dock-enforcer.plist")
        if os.path.exists(plist):
            subprocess.run(["launchctl", "load", plist], timeout=10, capture_output=True)
            add_event(digest, "fixes_applied", {"type":"plist_reload","service":label,"action":"Reloaded dock enforcer plist","result":"attempted"})

# ── TELEGRAM ─────────────────────────────────────────────────────────────────
def send_telegram(msg: str) -> bool:
    if not TELEGRAM_BOT_TOKEN:
        log.warning("No HERMES_BOT_TOKEN set — cannot send Telegram")
        return False
    import urllib.request, urllib.parse
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception as e:
        log.error(f"Telegram send failed: {e}")
        return False

def format_digest_message(d: dict) -> str:
    now_str = datetime.now().strftime("%a %b %-d · %-I:%M %p")
    lines = [f"🛡 *GHS Cron Guardian — {now_str}*", ""]

    jobs_ran = d.get("jobs_ran", [])
    if jobs_ran:
        lines.append("✅ *Jobs completed:*")
        for j in jobs_ran:
            lines.append(f"  • {j['name']} @ {j.get('time','?')} — {j.get('status','ok')}")
        lines.append("")

    fixes = d.get("fixes_applied", [])
    if fixes:
        lines.append("🔧 *Auto-fixed:*")
        for f in fixes:
            icon = "✅" if f.get("result") == "success" else "⚠️"
            lines.append(f"  {icon} {f['service']} — {f['action']}")
        lines.append("")

    missed = d.get("jobs_missed", [])
    if missed:
        lines.append("⚠️ *Missed jobs:*")
        for j in missed:
            lines.append(f"  • {j['name']} (expected {j.get('expected','?')})")
        lines.append("")

    errors = d.get("errors_seen", [])
    high_errors = [e for e in errors if e.get("severity") in ("HIGH", "CRITICAL")]
    if high_errors:
        lines.append("🚨 *Errors detected:*")
        for e in high_errors:
            lines.append(f"  • [{e.get('severity')}] {e.get('source')}: {e.get('message','')[:80]}")
        lines.append("")

    needs_kato = d.get("needs_kato", [])
    if needs_kato:
        lines.append("👋 *Needs your attention:*")
        for n in needs_kato:
            urgency_icon = {"HIGH":"🔴","MEDIUM":"🟡","LOW":"🟢"}.get(n.get("urgency",""), "⚪")
            lines.append(f"  {urgency_icon} {n['item']}")
            if n.get("reason"):
                lines.append(f"     ↳ {n['reason']}")
        lines.append("")

    if not jobs_ran and not fixes and not missed and not errors and not needs_kato:
        lines.append("✅ All systems nominal — nothing needed your attention today.")
    else:
        total_ran = len(jobs_ran)
        total_fixed = len([f for f in fixes if f.get("result")=="success"])
        lines.append(f"_Summary: {total_ran} jobs ran · {total_fixed} issues auto-fixed · {len(needs_kato)} need you_")

    return "\n".join(lines)

# ── DIGEST SEND + RESET ────────────────────────────────────────────────────
def maybe_send_digest(digest: dict) -> bool:
    now = datetime.now()
    if now.hour == DIGEST_HOUR and now.minute < DIGEST_WINDOW:
        sent_key = f"sent_{date.today()}"
        if digest.get(sent_key):
            return False
        msg = format_digest_message(digest)
        log.info("Sending 9pm digest to Kato...")
        ok = send_telegram(msg)
        if ok:
            digest[sent_key] = True
            save_digest(digest)
            log.info("✅ Digest sent")
        else:
            log.error("❌ Digest send failed")
        return ok
    return False

# ── MARK JOB AS RAN ──────────────────────────────────────────────────────────
def mark_job_ran(digest: dict, job_id: str, status: str = "ok"):
    """Called externally or by hook integrations to record a job completing."""
    job_def = next((j for j in EXPECTED_JOBS if j["id"] == job_id), None)
    name = job_def["name"] if job_def else job_id
    add_event(digest, "jobs_ran", {"id": job_id, "name": name, "time": datetime.now().strftime("%H:%M"), "status": status})

# ── MAIN CYCLE ────────────────────────────────────────────────────────────────
def run_cycle():
    log.info("── Guardian cycle start ──")
    digest = load_digest()
    digest["last_check"] = datetime.now().isoformat()

    try:
        check_critical_services(digest)
    except Exception:
        log.error(traceback.format_exc())

    try:
        check_launchd_errors(digest)
    except Exception:
        log.error(traceback.format_exc())

    try:
        check_missed_jobs(digest)
    except Exception:
        log.error(traceback.format_exc())

    try:
        check_n8n_status(digest)
    except Exception:
        pass

    try:
        check_telegram_bot(digest)
    except Exception:
        pass

    try:
        check_kanban_proxy(digest)
    except Exception:
        pass

    try:
        check_gmail_token(digest)
    except Exception:
        pass

    try:
        check_dock_enforcer(digest)
    except Exception:
        pass

    save_digest(digest)
    maybe_send_digest(digest)
    log.info(f"── Cycle done · {len(digest['fixes_applied'])} fixes · {len(digest['needs_kato'])} needs-kato ──")

def install_launchagent():
    plist_path = Path.home() / "Library/LaunchAgents/com.ghs.cron-guardian.plist"
    plist_path.write_text(PLIST_TEMPLATE)
    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    result = subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"✅ Cron Guardian installed and loaded: {plist_path}")
        print("   Runs every 2 minutes. 9pm digest sent to Telegram.")
    else:
        print(f"❌ Load failed: {result.stderr}")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"

    if cmd == "install":
        install_launchagent()
    elif cmd == "digest":
        d = load_digest()
        msg = format_digest_message(d)
        print(msg)
        if "--send" in sys.argv:
            send_telegram(msg)
    elif cmd == "status":
        d = load_digest()
        print(json.dumps(d, indent=2, default=str))
    elif cmd == "mark":
        # CC_cron_guardian.py mark morning_report ok
        d = load_digest()
        job_id = sys.argv[2] if len(sys.argv) > 2 else "unknown"
        status = sys.argv[3] if len(sys.argv) > 3 else "ok"
        mark_job_ran(d, job_id, status)
        print(f"Marked {job_id} as {status}")
    else:
        run_cycle()
