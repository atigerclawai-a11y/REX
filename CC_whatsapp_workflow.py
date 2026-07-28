#!/usr/bin/env python3
"""
CC_whatsapp_workflow.py — Intelligence layer for GOJ WhatsApp groups.
Sits on top of CC_whatsapp_bridge.py. Classifies messages by intent,
cross-references with auth_tracker.db, takes autonomous action.

Design principles:
- Silent in chat (never auto-reply)
- Cross-reference everything with DB before acting
- Log all actions with source chat message for audit
- Escalate only genuinely new/actionable items to Kato via Telegram
"""

import json, os, re, sqlite3, hashlib, urllib.request
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import defaultdict

# ── Paths ───────────────────────────────────────────────────────────────
HOME = Path.home()
AUTH_DB = HOME / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
PROP_DB = HOME / "Documents" / "goj files" / "proprietary" / "goj_proprietary.db"
ROUTES_FILE = HOME / "Desktop" / "REX" / "GOJ_Master_Routes.json"
AUDIT_LOG = HOME / "Desktop" / "REX" / "whatsapp_workflow_audit.jsonl"
KITCHEN_ADJUST = HOME / "Desktop" / "REX" / "kitchen_adjustments.json"
STATE_FILE = HOME / ".whatsapp_bridge" / "workflow_state.json"

# ── Telegram ────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("REXXIE_TOKEN", "") or os.getenv("TELEGRAM_BOT_TOKEN", "")
KATO_ID = "5587703834"


def tg_alert(msg: str):
    """Send Telegram alert to Kato."""
    if not TELEGRAM_TOKEN:
        return
    try:
        data = json.dumps({"chat_id": KATO_ID, "text": msg, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data=data, headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def audit(action: str, group: str, sender: str, detail: str, source_msg: str = ""):
    """Append to workflow audit log."""
    entry = {
        "ts": datetime.now().isoformat(),
        "action": action,
        "group": group,
        "sender": sender,
        "detail": detail,
        "source_msg": source_msg[:200],
    }
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_LOG, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ── DB Helpers ──────────────────────────────────────────────────────────

def get_db(path: Path):
    """Get SQLite connection by path. Returns None if unreachable."""
    try:
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None


def client_exists(name: str) -> dict | None:
    """Check if client exists in auth_tracker. Returns row or None."""
    db = get_db(AUTH_DB)
    if not db:
        return None
    # Fuzzy match — case insensitive, handle common variations
    row = db.execute(
        "SELECT * FROM clients WHERE LOWER(name) LIKE ?",
        (f"%{name.lower().strip()}%",)
    ).fetchone()
    db.close()
    return dict(row) if row else None


def get_auth_status(name: str) -> dict | None:
    """Get authorization status for a client."""
    db = get_db(AUTH_DB)
    if not db:
        return None
    row = db.execute("""
        SELECT client_name, service_start_date, service_end_date, authorization_number
        FROM authorization WHERE LOWER(client_name) LIKE ?
        ORDER BY service_end_date DESC LIMIT 1
    """, (f"%{name.lower().strip()}%",)).fetchone()
    db.close()
    return dict(row) if row else None


def get_attendance(client_name: str) -> dict:
    """Get client's weekly attendance pattern."""
    db = get_db(AUTH_DB)
    if not db:
        return {}
    row = db.execute(
        "SELECT day_M_actual, day_T_actual, day_W_actual, day_TH_actual, day_F_actual, day_Su_actual "
        "FROM clients WHERE LOWER(name) LIKE ?",
        (f"%{client_name.lower().strip()}%",)
    ).fetchone()
    db.close()
    return dict(row) if row else {}


def get_menu(client_name: str, target_date: str) -> list:
    """Get client's menu orders for a date."""
    db = get_db(PROP_DB)
    if not db:
        return []
    rows = db.execute(
        "SELECT * FROM client_menus WHERE LOWER(client_name) LIKE ? AND menu_date=?",
        (f"%{client_name.lower().strip()}%", target_date)
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def update_client_phone(name: str, phone: str) -> bool:
    """Update client phone in auth_tracker. Returns True if changed."""
    db = get_db(AUTH_DB)
    if not db:
        return False
    existing = db.execute(
        "SELECT phone FROM clients WHERE LOWER(name) LIKE ?",
        (f"%{name.lower().strip()}%",)
    ).fetchone()
    if existing and existing["phone"] == phone:
        db.close()
        return False
    db.execute(
        "UPDATE clients SET phone=?, updated_at=datetime('now') WHERE LOWER(name) LIKE ?",
        (phone, f"%{name.lower().strip()}%")
    )
    db.commit()
    db.close()
    return True


# ── Plus and Minus Image Handler ────────────────────────────────────────

def handle_plus_minus_image(image_data_b64: str, group: str, sender: str):
    """OCR a +/- list image, extract names, update kitchen adjustments."""
    audit("PLUS_MINUS_IMAGE", group, sender, "Processing +/- list image")
    
    # Write image to temp file
    import base64, tempfile
    img_data = base64.b64decode(image_data_b64)
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.write(img_data)
    tmp.close()
    
    # Try OCR with tesseract first (fast, local)
    try:
        import subprocess
        result = subprocess.run(
            ["tesseract", tmp.name, "stdout", "-l", "rus+eng", "--psm", "6"],
            capture_output=True, text=True, timeout=30
        )
        text = result.stdout.strip()
    except Exception:
        text = ""
    
    # Parse names and +/- status
    adjustments = parse_plus_minus_text(text)
    
    if adjustments:
        plus_count = sum(1 for a in adjustments if a["status"] == "+")
        minus_count = sum(1 for a in adjustments if a["status"] == "-")
        
        # Auto-apply kitchen adjustments (with approval queue for DB changes)
        apply_kitchen_adjustments(adjustments)
        
        detail = {
            "description": f"+/- list: {plus_count} attending, {minus_count} not attending",
            "plus_names": [a["name"] for a in adjustments if a["status"] == "+"],
            "minus_names": [a["name"] for a in adjustments if a["status"] == "-"],
        }
        queue_approval("kitchen_adjustment", detail, "")
        
        audit("PLUS_MINUS_DONE", group, sender,
              f"Extracted {len(adjustments)} names ({plus_count}+, {minus_count}-)")
        tg_alert(f"📸 <b>+/- List Processed</b>\n{plus_count} attending, {minus_count} not attending\nKitchen adjustments updated for {today}")
    
    # Cleanup
    Path(tmp.name).unlink(missing_ok=True)
    return adjustments


def parse_plus_minus_text(text: str) -> list:
    """Parse OCR'd +/- list into structured adjustments."""
    if not text:
        return []
    
    adjustments = []
    # Pattern: lines like "Name Surname +" or "- Name Surname" or "Name Surname -"
    lines = text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        status = None
        if '+' in line:
            status = '+'
        elif '-' in line or '—' in line or '–' in line:
            status = '-'
        
        if status:
            # Extract name (remove the +/- symbol and clean)
            name = line.replace('+', '').replace('-', '').replace('—', '').replace('–', '').strip()
            # Remove numbers, stray punctuation
            name = re.sub(r'[0-9.,;:()\[\]{}]', '', name).strip()
            if len(name) > 3 and not name.isdigit():
                adjustments.append({
                    "name": name,
                    "status": status,
                    "date": date.today().isoformat(),
                    "source": "whatsapp_ocr",
                })
    
    return adjustments


# ── Message Classification ──────────────────────────────────────────────

def classify_message(msg_text: str, group: str, sender: str) -> dict:
    """Classify a WhatsApp message and determine action."""
    text = msg_text.strip()
    low = text.lower()
    result = {
        "intent": "unknown",
        "action": "log_only",
        "client_name": None,
        "driver_name": None,
        "date_mentioned": None,
        "phone_number": None,
        "auth_issue": None,
    }
    
    # Detect phone numbers
    phone_match = re.search(r'(\d{3}[-.\s]?\d{3}[-.\s]?\d{4})', text)
    if phone_match:
        result["phone_number"] = phone_match.group(1).replace(' ', '-')
    
    # ── Plus and Minus Group ──
    if group.lower() in ("plus and minus", "plus & minus"):
        result["intent"] = "plus_minus_update"
        result["action"] = "update_kitchen_counts"
        return result
    
    # ── Attendance Group ──
    if "attendance" in group.lower():
        # Auth expiration patterns
        auth_patterns = [
            r'(?:authorization|auth|авторизац\w*).*?(?:ends?|expires?|end|exp)\s*(\d+/\d+)',
            r'(?:authorization|auth|авторизац\w*).*?(?:заканчивается|кончается)',
        ]
        for pat in auth_patterns:
            m = re.search(pat, low)
            if m:
                result["intent"] = "auth_expiring"
                result["action"] = "check_auth_status"
                result["date_mentioned"] = m.group(1) if m.lastindex else None
                # Extract client name (usually near the auth mention)
                name_parts = text.split()
                for i, w in enumerate(name_parts):
                    if any(kw in w.lower() for kw in ['authorization', 'auth', 'авторизац']):
                        if i > 0:
                            result["client_name"] = name_parts[i-1]
                        if i > 1:
                            result["client_name"] = f"{name_parts[i-2]} {name_parts[i-1]}"
                        break
                break
        
        # Missing data patterns
        if any(kw in low for kw in ['нет дня рождения', 'no birthday', 'нет в']):
            result["intent"] = "missing_client_data"
            result["action"] = "flag_data_gap"
        
        # Signature requests
        if any(kw in low for kw in ['signature', 'sign for', 'подпис']):
            result["intent"] = "signature_request"
            result["action"] = "check_doc_delivery"
            # Detect escalation
            if '3rd' in low or 'third' in low or 'again' in low:
                result["action"] = "escalate_signature"
        
        # Schedule anomalies
        if any(kw in low for kw in ['why is', 'why are', 'his days', 'her days', 'today?']):
            result["intent"] = "schedule_anomaly"
            result["action"] = "flag_schedule_anomaly"
            # Dad has authority to trigger corrections
            if "dad" in sender.lower() or "vlad" in sender.lower():
                result["action"] = "correct_schedule"
        
        # Print notifications
        if "at printer" in low or "на принтере" in low:
            result["intent"] = "document_at_printer"
            result["action"] = "log_doc_delivery"
        
        # ── Wrong contact data (phone number is someone else's) ──
        if any(kw in low for kw in ['дочер', 'daughter', 'сын', 'son', 'нужно удалить',
                                     'это не ее', 'это не его', 'wrong number', 'не тот номер']):
            result["intent"] = "wrong_contact_data"
            result["action"] = "flag_wrong_contact"
        
        # ── Cross-system data gap (Carecenta vs report/DB) ──
        if any(kw in low for kw in ['not in carecenta', 'нет в carecenta', 'carecenta', 
                                     'but yes at the report', 'needs to be cleaned',
                                     'не в carecenta']):
            result["intent"] = "cross_system_gap"
            result["action"] = "flag_data_sync_gap"
        
        # ── System access issue ──
        if any(kw in low for kw in ["can't log in", "cannot log in", "password change",
                                     "did someone change", "не могу зайти", "пароль"]):
            result["intent"] = "system_access_issue"
            result["action"] = "log_access_issue"
        
        # Count requests
        if "counts for" in low:
            result["intent"] = "count_request"
            result["action"] = "log_doc_delivery"
        
        return result
    
    # ── Main Group ──
    if "main" in group.lower():
        # ── Permanent schedule change (всегда/always) ──
        if any(kw in low for kw in ['всегда', 'always', 'постоянно', 'permanent']):
            result["intent"] = "permanent_schedule_change"
            result["action"] = "queue_base_schedule_update"
            return result
        
        # ── Medical absence ──
        medical_kw = ['surgery', 'hospital', 'doctor', 'dr ', 'appointment', 'больниц',
                      'операц', 'хирург', 'врач', 'доктор', 'appt']
        if any(kw in low for kw in medical_kw) and any(kw in low for kw in ['no', 'not', 'нет', 'не']):
            result["intent"] = "medical_absence"
            result["action"] = "track_medical_absence"
            return result
        
        # ── Self-transport ──
        if any(kw in low for kw in ['сами', 'сам', 'своей машин', 'своем', 'own car', 
                                     'priedut sami', 'сами приедут', 'сам приедет']):
            result["intent"] = "self_transport"
            result["action"] = "mark_self_transport"
            return result
        
        # ── Future-dated swap (7/23 instead of 7/22) ──
        swap_match = re.search(r'(\d+/\d+).*?(?:instead|вместо).*?(\d+/\d+)', text, re.IGNORECASE)
        if swap_match:
            result["intent"] = "future_date_swap"
            result["action"] = "queue_future_swap"
            result["date_mentioned"] = swap_match.group(1)
            result["old_date"] = swap_match.group(2)
            return result
        
        # Transport change patterns
        transport_kw = ['транспорт', 'transport', 'забрал', 'забрать', 'pick up', 'drop off',
                        'driver', 'водител', 'ravil', 'рафик', 'alisher', 'алишер',
                        'vadik', 'вадик', 'oleg', 'олег', 'andrey', 'андрей',
                        'valera', 'валера', 'gena', 'гена']
        
        if any(kw in low for kw in transport_kw):
            result["intent"] = "transport_change"
            result["action"] = "update_transport"
            
            # Detect specific driver
            driver_names = {
                'ravil': 'Ravil', 'рафик': 'Ravil', 'равиль': 'Ravil',
                'alisher': 'Alisher', 'алишер': 'Alisher',
                'vadik': 'Vadik', 'вадик': 'Vadik',
                'oleg': 'Oleg', 'олег': 'Oleg',
                'andrey': 'Andrey', 'андрей': 'Andrey',
                'valera': 'Valera', 'валера': 'Valera',
                'gena': 'Gena', 'гена': 'Gena',
            }
            for kw, name in driver_names.items():
                if kw in low:
                    result["driver_name"] = name
                    break
            
            # Detect day of week
            days = {
                'понедельник': 'Monday', 'monday': 'Monday', 'mon': 'Monday',
                'вторник': 'Tuesday', 'tuesday': 'Tuesday', 'tue': 'Tuesday',
                'среда': 'Wednesday', 'wednesday': 'Wednesday', 'wed': 'Wednesday',
                'четверг': 'Thursday', 'thursday': 'Thursday', 'thu': 'Thursday',
                'пятниц': 'Friday', 'friday': 'Friday', 'fri': 'Friday',
                'суббот': 'Saturday', 'saturday': 'Saturday', 'sat': 'Saturday',
                'воскресен': 'Sunday', 'sunday': 'Sunday', 'sun': 'Sunday',
            }
            for kw, day in days.items():
                if kw in low:
                    result["date_mentioned"] = day
                    break
        
        # Driver-wide announcements
        if "all drivers" in low or "всем водител" in low or "всем приехать" in low:
            result["intent"] = "driver_announcement"
            result["action"] = "log_driver_announcement"
        
        return result
    
    return result


# ── Action Handlers ─────────────────────────────────────────────────────

def execute_action(classification: dict, raw_msg: dict):
    """Execute the action determined by message classification."""
    intent = classification["intent"]
    action = classification["action"]
    group = raw_msg.get("group", "")
    sender = raw_msg.get("sender", "")
    text = raw_msg.get("text", "")
    
    if action == "log_only":
        audit("LOG", group, sender, f"Unknown: {text[:100]}")
        return
    
    if action == "check_auth_status":
        name = classification.get("client_name")
        if name:
            auth = get_auth_status(name)
            if auth:
                expiry = auth.get("service_end_date", "unknown")
                audit("AUTH_CHECK", group, sender,
                      f"{name}: auth expires {expiry}" +
                      (f" (mentioned: {classification['date_mentioned']})" if classification.get("date_mentioned") else ""))
                try:
                    exp_date = datetime.strptime(expiry, "%Y-%m-%d").date()
                    if (exp_date - date.today()).days <= 30:
                        tg_alert(f"⚠️ <b>Auth Expiring</b>\n{name}: expires {expiry}\nReported by {sender}")
                except Exception:
                    pass
            else:
                audit("AUTH_GAP", group, sender, f"{name}: no auth record in DB")
                tg_alert(f"🔴 <b>Auth Gap — {name}</b>\nNot in authorization table\nReported by {sender}")
    
    elif action == "flag_data_gap":
        audit("DATA_GAP", group, sender, text[:150])
        tg_alert(f"📋 <b>Missing Client Data</b>\n{sender}: {text[:200]}")
    
    elif action in ("check_doc_delivery", "escalate_signature"):
        today = date.today()
        signin_path = HOME / "Documents" / "goj files" / "output_docs"
        sheets_today = list(signin_path.glob(f"*{today.strftime('%a')}*signin*")) if signin_path.exists() else []
        if sheets_today:
            audit("SIG_REQUEST", group, sender, f"Signatures requested — {len(sheets_today)} sheets exist")
        else:
            audit("SIG_MISSING", group, sender, "Signatures requested but NO sheets found")
            if action == "escalate_signature":
                tg_alert(f"🚨 <b>Signature Escalation</b>\n{sender} requested 3+ times\nNo sheets for today!")
    
    elif action == "flag_schedule_anomaly":
        audit("SCHEDULE_ANOMALY", group, sender, text[:150])
        tg_alert(f"⚠️ <b>Schedule Anomaly</b>\n{sender}: {text[:200]}")
    
    elif action == "correct_schedule":
        # Dad has authority — queue for approval then apply
        detail = {"description": f"Dad flagged schedule issue: {text[:150]}", "source_group": group}
        queue_approval("schedule_correction", detail, text)
    
    elif action == "update_transport":
        driver = classification.get("driver_name", "unknown")
        day = classification.get("date_mentioned", "today")
        audit("TRANSPORT", group, sender, f"Transport change — {driver}, {day}: {text[:100]}")
        # Queue for approval — affects routes, sign-in, food list
        detail = {
            "description": f"Transport: {sender}: {text[:120]}",
            "driver": driver,
            "day": day,
            "source_group": group,
        }
        queue_approval("transport_change", detail, text)
    
    elif action in ("log_doc_delivery", "count_request"):
        audit("DOC_PRINT", group, sender, f"Document at printer: {text[:100]}")
    
    elif action == "log_driver_announcement":
        audit("DRIVER_ANN", group, sender, text[:150])
    
    elif action == "update_kitchen_counts":
        audit("KITCHEN_UPDATE", group, sender, text[:100] if text else "image-based update")
    
    # ── New intent handlers ──
    elif action == "queue_base_schedule_update":
        detail = {"description": f"Permanent schedule change: {text[:150]}", "source_group": group}
        queue_approval("attendance_change", detail, text)
        audit("PERMANENT_SCHEDULE", group, sender, text[:150])
    
    elif action == "track_medical_absence":
        detail = {"description": f"Medical absence: {text[:150]}", "source_group": group}
        queue_approval("attendance_change", detail, text)
        tg_alert(f"🏥 <b>Medical Absence</b>\n{sender}: {text[:200]}\nMay need multi-day follow-up")
        audit("MEDICAL_ABSENCE", group, sender, text[:150])
    
    elif action == "mark_self_transport":
        audit("SELF_TRANSPORT", group, sender, text[:100])
        # Update routes to mark as self-transport
        detail = {"description": f"Self-transport: {text[:120]}", "source_group": group}
        queue_approval("transport_change", detail, text)
    
    elif action == "queue_future_swap":
        new_date = classification.get("date_mentioned", "")
        old_date = classification.get("old_date", "")
        detail = {"description": f"Future swap: {old_date} → {new_date}: {text[:120]}"}
        queue_approval("attendance_change", detail, text)
        audit("FUTURE_SWAP", group, sender, f"{old_date} → {new_date}: {text[:100]}")
    
    elif action == "flag_wrong_contact":
        audit("WRONG_CONTACT", group, sender, text[:150])
        tg_alert(f"📵 <b>Wrong Contact Data</b>\n{sender}: {text[:200]}\nPhone needs deletion/correction")
    
    elif action == "flag_data_sync_gap":
        audit("CROSS_SYSTEM_GAP", group, sender, text[:150])
        tg_alert(f"🔄 <b>Cross-System Data Gap</b>\n{sender}: {text[:200]}\nClient in report but not in Carecenta")
    
    elif action == "log_access_issue":
        audit("ACCESS_ISSUE", group, sender, text[:100])
        tg_alert(f"🔐 <b>System Access Issue</b>\n{sender}: Can't log in — may need password reset")


# ── Approval Queue ──────────────────────────────────────────────────────

APPROVAL_FILE = HOME / "Desktop" / "REX" / "whatsapp_approval_queue.json"


def queue_approval(change_type: str, detail: dict, source_msg: str):
    """Queue a destructive change for Kato's one-click approval via Telegram."""
    approvals = {}
    if APPROVAL_FILE.exists():
        approvals = json.loads(APPROVAL_FILE.read_text())
    
    change_id = hashlib.md5(f"{change_type}{json.dumps(detail)}{source_msg[:50]}".encode()).hexdigest()[:10]
    
    if change_id not in approvals:
        approvals[change_id] = {
            "id": change_id,
            "type": change_type,
            "detail": detail,
            "source": source_msg[:200],
            "status": "pending",
            "created": datetime.now().isoformat(),
        }
        APPROVAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        APPROVAL_FILE.write_text(json.dumps(approvals, indent=2))
        
        # Send Telegram with the change for one-click approval
        type_emoji = {"attendance_change": "📅", "transport_change": "🚗", 
                      "kitchen_adjustment": "🍽️", "schedule_correction": "🔧"}
        emoji = type_emoji.get(change_type, "📋")
        
        msg = f"{emoji} <b>Approve: {change_type.replace('_', ' ').title()}</b>\n"
        msg += f"{detail.get('description', source_msg[:150])}\n\n"
        msg += f"<code>/approve {change_id}</code> | <code>/deny {change_id}</code>"
        tg_alert(msg)
        
        audit("QUEUED_APPROVAL", "system", change_type, 
              f"{change_id}: {detail.get('description', '')}", source_msg[:100])
    
    return change_id


def apply_attendance_change(client_name: str, old_day: str, new_day: str, shift: str = "1"):
    """Apply a day change to auth_tracker.db."""
    day_cols = {
        "monday": "day_M_actual", "tuesday": "day_T_actual", "wednesday": "day_W_actual",
        "thursday": "day_TH_actual", "friday": "day_F_actual", "saturday": "day_Su_actual",
        "sunday": "day_Su_actual",
    }
    old_col = day_cols.get(old_day.lower().replace('day', '').strip())
    new_col = day_cols.get(new_day.lower().replace('day', '').strip())
    
    if not new_col:
        return False
    
    db = get_db(AUTH_DB)
    if not db:
        return False
    
    try:
        # Remove from old day if specified
        if old_col and old_col != new_col:
            db.execute(f"UPDATE clients SET {old_col}=0 WHERE LOWER(name) LIKE ?", 
                      (f"%{client_name.lower().strip()}%",))
        # Add to new day
        shift_val = 2 if "2" in str(shift) or "second" in str(shift).lower() else 1
        db.execute(f"UPDATE clients SET {new_col}=? WHERE LOWER(name) LIKE ?",
                  (shift_val, f"%{client_name.lower().strip()}%"))
        db.commit()
        return True
    except Exception as e:
        print(f"[wf] Attendance change failed: {e}")
        return False
    finally:
        db.close()


def apply_route_update(client_name: str, driver: str, day: str):
    """Update GOJ_Master_Routes.json with a transport change."""
    if not ROUTES_FILE.exists():
        return False
    
    try:
        routes = json.loads(ROUTES_FILE.read_text())
        # Search for client in routes
        day_key_map = {
            "monday": "M", "tuesday": "T", "wednesday": "W",
            "thursday": "TH", "friday": "F", "saturday": "Sa", "sunday": "Su",
        }
        day_code = day_key_map.get(day.lower(), "")
        
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
            audit("ROUTE_UPDATE", "system", "apply", 
                  f"{client_name}: driver={driver}, day={day}")
            return True
    except Exception as e:
        print(f"[wf] Route update failed: {e}")
    return False


def apply_kitchen_adjustments(adjustments: list):
    """Apply +/- adjustments to kitchen count sheet and running file."""
    if not adjustments:
        return
    
    today = date.today().isoformat()
    plus_names = [a["name"] for a in adjustments if a["status"] == "+"]
    minus_names = [a["name"] for a in adjustments if a["status"] == "-"]
    
    # Update the running kitchen adjustments file
    existing = {}
    if KITCHEN_ADJUST.exists():
        existing = json.loads(KITCHEN_ADJUST.read_text())
    
    existing[today] = existing.get(today, []) + adjustments
    KITCHEN_ADJUST.parent.mkdir(parents=True, exist_ok=True)
    KITCHEN_ADJUST.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
    
    # Also update DB attendance for minus clients
    db = get_db(AUTH_DB)
    if db:
        today_day = date.today().strftime("%A").lower()
        day_cols = {
            "monday": "day_M_actual", "tuesday": "day_T_actual", "wednesday": "day_W_actual",
            "thursday": "day_TH_actual", "friday": "day_F_actual",
            "saturday": "day_Su_actual", "sunday": "day_Su_actual",
        }
        col = day_cols.get(today_day)
        if col:
            for name in minus_names:
                db.execute(f"UPDATE clients SET {col}=0 WHERE LOWER(name) LIKE ?",
                          (f"%{name.lower().strip()}%",))
            db.commit()
        db.close()
    
    audit("KITCHEN_APPLIED", "system", "apply",
          f"+{len(plus_names)} names, -{len(minus_names)} names for {today}")


# ── Proactive Intelligence ──────────────────────────────────────────────

PROACTIVE_STATE = HOME / "Desktop" / "REX" / "whatsapp_proactive_state.json"


def _run_proactive_checks(stats: dict):
    """Run predictive checks based on message patterns and time of day."""
    now = datetime.now()
    hour = now.hour
    weekday = now.strftime("%A")
    
    # Load historical state for pattern tracking
    state = {}
    if PROACTIVE_STATE.exists():
        state = json.loads(PROACTIVE_STATE.read_text())
    
    # Track today's signature request count
    sig_requests = stats.get("signature_request", 0)
    if sig_requests >= 2:
        # Lena's asking multiple times — sheets might not have been sent
        today = date.today()
        signin_path = HOME / "Documents" / "goj files" / "output_docs"
        sheets = list(signin_path.glob(f"*{today.strftime('%a')}*signin*")) if signin_path.exists() else []
        if not sheets:
            tg_alert(f"🔔 <b>Proactive Alert</b>\nLena requested signatures {sig_requests}x today\nNo sign-in sheets found — were they generated?")
            audit("PROACTIVE_SIG", "system", "proactive", f"{sig_requests} signature requests, 0 sheets found")
    
    # 10am — expect Plus and Minus list
    if hour == 10 and "plus_minus_image" not in stats:
        # Check if we've seen the +/- list today
        last_plus_minus = state.get("last_plus_minus_date")
        if last_plus_minus != date.today().isoformat():
            tg_alert(f"⏰ <b>10am — Expecting +/- List</b>\nNo +/- list image detected yet today.\nKitchen needs this for food prep.")
            audit("PROACTIVE_PLUSMINUS", "system", "proactive", "10am — no +/- list yet")
    
    # Pre-noon: check if kitchen sheets are ready
    if 11 <= hour <= 12 and weekday not in ("Saturday", "Sunday"):
        # Check if today's kitchen sheets exist
        today = date.today()
        kitchen_path = HOME / "Documents" / "goj files" / "output_docs"
        kitchen_sheets = list(kitchen_path.glob(f"*Kitchen*{today.strftime('%b%d')}*"))
        if not kitchen_sheets:
            tg_alert(f"🍽️ <b>No Kitchen Sheets for {weekday}</b>\nNoon refresh may have failed.\nCheck: /queue for pending approvals")
            audit("PROACTIVE_KITCHEN", "system", "proactive", f"No kitchen sheets for {weekday}")
    
    # Track recurring transport patterns
    transport_count = stats.get("transport_change", 0)
    if transport_count >= 4:
        audit("PROACTIVE_TRANSPORT", "system", "proactive", 
              f"Heavy transport day: {transport_count} changes — check driver capacity")
    
    # Update state
    state["last_run"] = now.isoformat()
    state["last_plus_minus_date"] = state.get("last_plus_minus_date", date.today().isoformat())
    state[f"sig_requests_{date.today().isoformat()}"] = sig_requests
    state[f"transport_{date.today().isoformat()}"] = transport_count
    
    # Keep only last 30 days of state
    keys = list(state.keys())
    for k in keys:
        if k.startswith("sig_requests_") or k.startswith("transport_"):
            day_str = k.split("_", 2)[-1] if "_" in k else ""
            try:
                d = datetime.strptime(day_str, "%Y-%m-%d").date()
                if (date.today() - d).days > 30:
                    del state[k]
            except ValueError:
                pass
    
    PROACTIVE_STATE.parent.mkdir(parents=True, exist_ok=True)
    PROACTIVE_STATE.write_text(json.dumps(state, indent=2))


# ── Main Entry Point ────────────────────────────────────────────────────

def process_messages(messages: list) -> dict:
    """Process a batch of WhatsApp messages through the workflow engine.
    
    Args:
        messages: list of dicts from CC_whatsapp_bridge.py read_group_messages()
                  Each has: group, sender, text, is_schedule_change, timestamp
    
    Returns:
        dict with summary of actions taken
    """
    stats = defaultdict(int)
    
    for msg in messages:
        group = msg.get("group", "")
        sender = msg.get("sender", "")
        text = msg.get("text", "")
        has_image = msg.get("has_image", False)
        image_b64 = msg.get("image_b64")
        
        # ── Image handling for Plus and Minus ──
        if has_image and image_b64 and "plus" in group.lower():
            adjustments = handle_plus_minus_image(image_b64, group, sender)
            if adjustments:
                stats["plus_minus_image"] += 1
                continue
        
        if not text.strip():
            continue
        
        # ── Phone number detection (runs BEFORE classification) ──
        phone_match = re.search(r'(\d{3}[-.\s]?\d{3}[-.\s]?\d{4})', text)
        if phone_match:
            phone = phone_match.group(1).replace(' ', '-').replace('.', '-')
            # Try to identify the client name (usually before "number" or the phone)
            client_hint = text.split("number")[0].strip() if "number" in text.lower() else ""
            if client_hint:
                updated = update_client_phone(client_hint, phone)
                if updated:
                    audit("PHONE_UPDATE", group, sender, f"Updated {client_hint}: {phone}", text[:200])
                    stats["phone_update"] += 1
        
        # Classify
        classification = classify_message(text, group, sender)
        stats[classification["intent"]] += 1
        
        # Execute
        execute_action(classification, msg)
    
    # ── Proactive Intelligence ─────────────────────────────────────────
    _run_proactive_checks(stats)
    
    # Generate daily summary
    total = sum(stats.values())
    if total > 0:
        summary = f"📱 <b>WhatsApp Workflow — {date.today()}</b>\n{total} messages processed\n"
        for intent, count in sorted(stats.items()):
            if count > 0:
                summary += f"• {intent}: {count}\n"
        audit("DAILY_SUMMARY", "system", "workflow", summary)
    
    return dict(stats)
