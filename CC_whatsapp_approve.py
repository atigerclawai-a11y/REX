#!/usr/bin/env python3
"""
CC_whatsapp_approve.py — Telegram command handler for approval queue.
Run by the Rexxie bot or as a standalone watcher. Processes:
  /approve <id>  — apply queued change to DB, routes, sheets
  /deny <id>     — reject and remove from queue
  /queue          — list pending approvals
  /approve_all    — approve all pending (use with caution)
"""

import json, os, subprocess, sqlite3, sys
from datetime import date, datetime
from pathlib import Path

HOME = Path.home()
QUEUE_FILE = HOME / "Desktop" / "REX" / "whatsapp_approval_queue.json"
AUDIT_LOG = HOME / "Desktop" / "REX" / "whatsapp_workflow_audit.jsonl"
AUTH_DB = HOME / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
ROUTES_FILE = HOME / "Desktop" / "REX" / "GOJ_Master_Routes.json"
REX_VENV = HOME / "Desktop" / "REX" / ".rex-venv" / "bin" / "python3"


def load_queue():
    if QUEUE_FILE.exists():
        return json.loads(QUEUE_FILE.read_text())
    return {}


def save_queue(q):
    QUEUE_FILE.write_text(json.dumps(q, indent=2))


def audit(action, detail):
    entry = {"ts": datetime.now().isoformat(), "action": action, "detail": detail}
    with open(AUDIT_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def apply_to_db(change):
    """Parse change description and apply to auth_tracker.db."""
    detail = change["detail"]
    desc = detail.get("description", "")
    ctype = change["type"]
    
    if ctype not in ("attendance_change", "transport_change", "schedule_correction",
                     "kitchen_adjustment"):
        return
    
    db = sqlite3.connect(str(AUTH_DB))
    db.row_factory = sqlite3.Row
    
    try:
        # Extract client name — look for capitalized names (common in Russian/English)
        name_patterns = [
            r'(?:Transport:.*?:\s*)?([A-ZА-Я][a-zа-я]+\s+[A-ZА-Я][a-zа-я]+)',  # First Last
            r'(?:Transport:.*?:\s*)?([A-ZА-Я][a-zа-я]+)',  # Single name
        ]
        client_name = ""
        for pat in name_patterns:
            m = re.search(pat, desc)
            if m:
                client_name = m.group(1).strip()
                break
        
        if not client_name:
            return
        
        day_map = {
            "monday": "day_M_actual", "tuesday": "day_T_actual", "wednesday": "day_W_actual",
            "thursday": "day_TH_actual", "friday": "day_F_actual",
            "saturday": "day_Su_actual", "sunday": "day_Su_actual",
            "mon": "day_M_actual", "tue": "day_T_actual", "wed": "day_W_actual",
            "thu": "day_TH_actual", "fri": "day_F_actual", "sat": "day_Su_actual", "sun": "day_Su_actual",
            "сегодня": date.today().strftime("%A").lower(),
            "tomorrow": (date.today() + timedelta(days=1)).strftime("%A").lower(),
            "завтра": (date.today() + timedelta(days=1)).strftime("%A").lower(),
        }
        # Map Russian day names
        ru_days = {"понедельник": "monday", "вторник": "tuesday", "среда": "wednesday",
                   "четверг": "thursday", "пятница": "friday", "суббота": "saturday",
                   "воскресенье": "sunday"}
        
        desc_low = desc.lower()
        day_col = None
        for kw, col in day_map.items():
            if kw in desc_low:
                if isinstance(col, str) and col in day_map:
                    day_col = day_map[col]
                else:
                    day_col = col
                break
        
        # Also check Russian days
        if not day_col:
            for ru, en in ru_days.items():
                if ru in desc_low:
                    day_col = day_map[en]
                    break
        
        if not day_col:
            return
        
        shift = 2 if "2" in desc or "second" in desc_low or "втор" in desc_low else 1
        
        # Determine action based on change type and description
        if ctype in ("schedule_correction", "medical_absence") or any(
            kw in desc_low for kw in ["no ", "not ", "нет", "не ", "sick"]):
            # Remove from attendance
            db.execute(f"UPDATE clients SET {day_col}=0 WHERE LOWER(name) LIKE ?",
                      (f"%{client_name.lower()}%",))
            audit("APPLIED_DB", f"{ctype}: {client_name} removed from {day_col}")
        else:
            # Add to attendance
            db.execute(f"UPDATE clients SET {day_col}=? WHERE LOWER(name) LIKE ?",
                      (shift, f"%{client_name.lower()}%",))
            audit("APPLIED_DB", f"{ctype}: {client_name} added to {day_col}={shift}")
        
        db.commit()
        
    except Exception as e:
        print(f"[approve] DB apply error: {e}")
    finally:
        db.close()


def apply_to_routes(change):
    """Apply transport change to GOJ_Master_Routes.json."""
    detail = change["detail"]
    if change["type"] != "transport_change":
        return
    
    if not ROUTES_FILE.exists():
        return
    
    try:
        routes = json.loads(ROUTES_FILE.read_text())
        driver = detail.get("driver", "")
        day = detail.get("day", "")
        desc = detail.get("description", "")
        
        # Extract client name from description
        # Pattern: "Transport: Lena (Sadik): Marder Yakov tomorrow 1st shift"
        import re
        name_match = re.search(r'Transport:.*?:\s*(.+?)\s*(?:tomorrow|today|friday|monday|tuesday|wednesday|thursday|saturday|sunday|will|wants)', desc, re.IGNORECASE)
        client_name = name_match.group(1).strip() if name_match else ""
        
        if client_name and driver:
            found = False
            for route_key, clients in routes.items():
                if isinstance(clients, list):
                    for c in clients:
                        if isinstance(c, dict) and client_name.lower() in c.get("name", "").lower():
                            c["driver"] = driver
                            c["transport"] = "TR"
                            found = True
            if found:
                ROUTES_FILE.write_text(json.dumps(routes, indent=2))
                audit("APPROVED_ROUTES", f"transport: {client_name} → {driver}")
    
    except Exception as e:
        print(f"[approve] Routes error: {e}")


def regenerate_sheets():
    """Trigger daily sheet regeneration via the noon refresh pipeline."""
    try:
        result = subprocess.run(
            [REX_VENV, "-c", """
import subprocess, sys
result = subprocess.run(
    [sys.executable, "CC_scan_to_docs.py", "--pipeline", 
     "--date", __import__('datetime').date.today().isoformat(), "--drive-sync"],
    capture_output=True, text=True, timeout=120, cwd=str(__import__('pathlib').Path.home() / "Desktop/REX")
)
print(result.stdout[-500:] if result.stdout else result.stderr[-500:])
"""],
            capture_output=True, text=True, timeout=180,
            cwd=str(HOME / "Desktop" / "REX"),
            env={**os.environ, "PATH": os.environ.get("PATH", "")}
        )
        audit("SHEETS_REGENERATED", f"exit={result.returncode}")
        return result.returncode == 0
    except Exception as e:
        audit("SHEETS_ERROR", str(e))
        return False


def process_approval(change_id: str, approved: bool = True):
    """Process a single approval or denial."""
    queue = load_queue()
    
    if change_id not in queue:
        return f"❌ Change {change_id} not found in queue."
    
    change = queue[change_id]
    
    if change["status"] != "pending":
        return f"⚠️ Change {change_id} already {change['status']}."
    
    if approved:
        # Apply the change
        apply_to_db(change)
        apply_to_routes(change)
        change["status"] = "approved"
        change["approved_at"] = datetime.now().isoformat()
        audit("APPROVED", f"{change_id}: {change['type']}")
        
        # Regenerate sheets if this affects attendance/routes
        if change["type"] in ("attendance_change", "transport_change", 
                              "schedule_correction", "kitchen_adjustment"):
            ok = regenerate_sheets()
            audit("SHEETS_AFTER_APPROVAL", f"regenerated={'ok' if ok else 'failed'}")
        
        msg = f"✅ <b>Approved</b> {change_id}\n{change['detail'].get('description', '')[:150]}"
        if change["type"] in ("attendance_change", "transport_change", "kitchen_adjustment"):
            msg += "\n📊 Sheets regenerated."
    else:
        change["status"] = "denied"
        change["denied_at"] = datetime.now().isoformat()
        audit("DENIED", f"{change_id}: {change['type']}")
        msg = f"❌ <b>Denied</b> {change_id}"
    
    save_queue(queue)
    return msg


def list_queue():
    """List all pending approvals."""
    queue = load_queue()
    pending = {k: v for k, v in queue.items() if v["status"] == "pending"}
    
    if not pending:
        return "📋 No pending approvals."
    
    lines = [f"📋 <b>{len(pending)} Pending</b>\n"]
    for cid, c in pending.items():
        emoji = {"transport_change": "🚗", "schedule_correction": "🔧",
                 "kitchen_adjustment": "🍽️", "attendance_change": "📅"}.get(c["type"], "📋")
        desc = c["detail"].get("description", "")[:60]
        lines.append(f"{emoji} <code>/approve {cid}</code> {desc}")
    
    return "\n".join(lines)


def approve_all():
    """Approve all pending changes."""
    queue = load_queue()
    pending = [k for k, v in queue.items() if v["status"] == "pending"]
    
    if not pending:
        return "📋 Nothing to approve."
    
    results = []
    for cid in pending:
        result = process_approval(cid, approved=True)
        results.append(result)
    
    return f"✅ Approved {len(pending)} changes\n" + "\n".join(results[-3:])


# ── CLI / Bot Entry Point ──────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(list_queue())
        sys.exit(0)
    
    cmd = sys.argv[1].lower()
    
    if cmd == "list" or cmd == "queue":
        print(list_queue())
    
    elif cmd == "approve_all":
        print(approve_all())
    
    elif cmd in ("approve", "deny"):
        if len(sys.argv) < 3:
            print("Usage: approve <id> or deny <id>")
            sys.exit(1)
        change_id = sys.argv[2]
        approved = cmd == "approve"
        print(process_approval(change_id, approved))
    
    else:
        # Assume it's a change ID — default to approve
        print(process_approval(cmd, approved=True))
