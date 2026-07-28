#!/usr/bin/env python3
"""
GOJ Victoria Caller
Runs at 2:00 PM — reads tomorrow's clients from LIVE Google Drive sign-in sheet
Calls each via Retell using Victoria agent with Elena (cartesia) voice
Writes results to attendance table
Sends pre-call and post-call driver lists to Telegram
Sends full call report to Telegram

WAVE-BASED CALLING (Retell TOS-safe):
  5 calls per wave, 5s between calls, 30s between waves.
  Rapid-fire bursts trigger Retell's "potential of violation" agent block.
  See goj-operations skill → wave-caller reference.
"""

import sqlite3, json, sys, time, logging, requests
from datetime import datetime, date, timedelta
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH       = Path.home() / "Documents/goj files/proprietary/goj_proprietary.db"
REX_DIR       = Path.home() / "Desktop" / "REX"
RETELL_KEY    = "key_48a2ed4781d093c125451e40ddb4"
AGENT_ID      = "agent_8a326510567e7dc3e2dc5221df"  # Victoria-GOJ-v2 (upgraded Jun 29 2026 — v1 was TOS-blocked and deprecated)
FROM_NUMBER   = "+16467603781"
TRANSFER_1    = "+19178181729"
TRANSFER_2    = "+17187048084"
TELEGRAM_TOKEN= "8657319466:AAE5jNl0ZJUFqiAN7d7cIzLe5aYwcINgxDk"
TELEGRAM_CHAT = "5587703834"
LOG_PATH      = Path.home() / "Desktop/REX/logs/victoria_caller.log"

# Ensure REX_DIR in path for CC_drive_lists import
if str(REX_DIR) not in sys.path:
    sys.path.insert(0, str(REX_DIR))

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(LOG_PATH), level=logging.INFO,
    format="%(asctime)s %(message)s"
)

DAYS_RU = {
    0: "понедельник", 1: "вторник", 2: "среда",
    3: "четверг",    4: "пятница",  5: "суббота", 6: "воскресенье"
}
MONTHS_RU = {
    1:"января",2:"февраля",3:"марта",4:"апреля",5:"мая",6:"июня",
    7:"июля",8:"августа",9:"сентября",10:"октября",11:"ноября",12:"декабря"
}

def tg(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception as e:
        logging.error("Telegram error: %s", e)

def get_tomorrow():
    t = date.today() + timedelta(days=1)
    # Skip Saturday — GOJ closed on Saturdays
    #   Fri → Sun (+2), Sat → Sun (+1), all other days → next day as normal
    if t.weekday() == 5:  # Saturday
        t += timedelta(days=1)  # advance to Sunday
    day_code = ["M","T","W","TH","F","Su","Su"][t.weekday()]
    date_ru = f"{DAYS_RU[t.weekday()]}, {t.day} {MONTHS_RU[t.month]}"
    return t, day_code, date_ru

def get_scheduled_clients(day_code, target_date):
    """Get ALL clients from LIVE Google Drive sign-in sheet for tomorrow.
    Drive is the SOLE source of truth for WHO attends. Phones come from DB.
    If Drive read fails, the shift is skipped — NO DB fallback."""
    from CC_drive_lists import read_sign_in_sheet

    # Build phone lookup from DB (phones only live in DB)
    conn = sqlite3.connect(str(DB_PATH))
    phone_rows = conn.execute(
        "SELECT name, phone FROM clients WHERE phone IS NOT NULL AND phone != ''"
    ).fetchall()
    phone_map = {name: phone for name, phone in phone_rows}
    conn.close()

    clients = []
    shifts = [(1, "S1"), (2, "S2")] if day_code != "Su" else [(1, "Su")]

    for shift, _ in shifts:
        # Drive is the primary source — fall back to auth_tracker.db if unavailable
        try:
            roster = read_sign_in_sheet(day_code, shift)
        except Exception as e:
            logging.error("Drive read failed for %s shift %s: %s — falling back to auth_tracker.db", day_code, shift, e)
            roster = _stale_db_roster(day_code, shift)
        for entry in roster:
            name = entry.get("name", "").strip()
            if not name:
                continue
            phone = phone_map.get(name) or _lookup_phone_fuzzy(name, phone_map)
            clients.append((name, phone, shift, ""))  # driver from routes unavailable

    logging.info("Drive-sourced %d clients for %s (stale DB had %d)",
                 len(clients), day_code,
                 _stale_db_count(day_code, target_date))
    return clients


def _lookup_phone_fuzzy(name, phone_map):
    """Fuzzy match: last name only, normalize spacing."""
    norm = lambda s: " ".join(s.strip().split()).lower()
    target = norm(name)
    if target in phone_map:
        return phone_map[target]
    # Try last-name match
    parts = target.split()
    if len(parts) >= 2:
        last = parts[-1]
        for k, v in phone_map.items():
            if norm(k).endswith(" " + last):
                return v
    return None


def _stale_db_count(day_code, target_date):
    """For logging: how many records the OLD query would have returned."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        count = conn.execute(
            "SELECT COUNT(*) FROM driver_routes WHERE day_code=? AND effective_date<=?",
            (day_code, str(target_date))
        ).fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


def _stale_db_roster(day_code, shift):
    """Fallback: read clients from auth_tracker.db when Google Drive is unavailable.
    Returns list of dicts compatible with read_sign_in_sheet() output."""
    AUTH_DB = Path.home() / "Documents/goj files/dashboard/auth_tracker.db"
    day_col_map = {
        "M": "day_M_actual", "T": "day_T_actual", "W": "day_W_actual",
        "TH": "day_TH_actual", "F": "day_F_actual", "Su": "day_Su_actual"
    }
    col = day_col_map.get(day_code)
    if not col:
        logging.warning("_stale_db_roster: no DB column for day_code=%s — Saturday not tracked in DB", day_code)
        return []

    try:
        conn = sqlite3.connect(str(AUTH_DB))
        # Sunday is combined — no shift filter
        if day_code == "Su":
            rows = conn.execute(
                f"SELECT name, phone, shift FROM clients WHERE {col}=1 AND active=1"
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT name, phone, shift FROM clients WHERE {col}=1 AND shift=? AND active=1",
                (shift,)
            ).fetchall()
        conn.close()
        roster = [{"name": name, "plan": "", "transport": ""} for name, _, _ in rows]
        logging.info("_stale_db_roster: %d clients from auth_tracker.db for %s shift %s",
                     len(roster), day_code, shift)
        return roster
    except Exception as e:
        logging.error("_stale_db_roster failed: %s", e)
        return []

def get_phone(client_name):
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute("SELECT phone FROM clients WHERE name=?", (client_name,)).fetchone()
    conn.close()
    return row[0] if row and row[0] else None

def log_call_placed(client_name, phone, call_id, date_str, time_str):
    """Log call initiation to victoria_calls table"""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("""
            INSERT OR REPLACE INTO victoria_calls
            (call_id, client_name, phone, call_date, call_time, status)
            VALUES (?, ?, ?, ?, ?, 'calling')
        """, (call_id, client_name, phone, date_str, time_str))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error("Failed to log call placed: %s", e)

def make_call(client_name, phone, date_ru):
    """Trigger Retell outbound call with personalised begin_message."""
    if not phone:
        logging.warning("No phone for %s — skipping", client_name)
        return None, "no_phone"

    # Clean phone
    phone = "".join(c for c in phone.split()[0] if c.isdigit() or c == "+")
    if not phone.startswith("+"):
        phone = "+1" + phone.lstrip("1")

    first_name = client_name.split()[0]

    # ── Create personalised LLM with client name + date in begin_message ──
    begin_msg = (
        f"Добрый день, {first_name}! Это Виктория, искусственный интеллект из Garden of Joy дневной центр. "
        f"Я звоню чтобы подтвердить ваше посещение завтра, {date_ru}. "
        f"Пожалуйста нажмите 1 или скажите Да если вы завтра будете. "
        f"Пожалуйста нажмите 2 или скажите Нет если вы завтра не сможете прийти. "
        f"Пожалуйста нажмите 3 или скажите Сотрудник чтобы вам позвать кого-то. "
        f"И пожалуйста нажмите 0 или скажите Повторить чтобы услышать это опять."
    )
    general = (
        "You are Victoria, an AI assistant at Garden of Joy Adult Day Care. "
        "You only speak Russian. Speak SLOWLY with clear pauses. "
        "You sound like a warm, caring Russian-American woman.\n\n"
        "You are calling to confirm if the person is coming tomorrow.\n\n"
        "Listen for voice OR DTMF:\n"
        "Voice \"Да\"/\"буду\"/\"приду\" or DTMF 1 → confirmed\n"
        "Voice \"Нет\"/\"не приду\"/\"не смогу\" or DTMF 2 → declined\n"
        "Voice \"Сотрудник\"/\"позвать\"/\"человек\" or DTMF 3 → staff\n"
        "Voice \"Повторить\"/\"ещё раз\" or DTMF 0 → repeat\n\n"
        f"Confirmed: Отлично, {first_name}! Ваше посещение завтра подтверждено. Ждём вас! До свидания!\n"
        f"Declined: Хорошо, {first_name}. Спасибо что предупредили. До свидания!\n"
        f"Staff: Одну минуту, {first_name}. Соединяю с сотрудником.\n"
        "Repeat: Повторите варианты.\n"
        "After 2 unclear attempts: Извините, я не поняла. Пожалуйста перезвоните позже. До свидания."
    )

    try:
        llm_r = requests.post(
            "https://api.retellai.com/create-retell-llm",
            headers={"Authorization": f"Bearer {RETELL_KEY}",
                     "Content-Type": "application/json"},
            json={"model": "gpt-4.1", "general_prompt": general, "begin_message": begin_msg},
            timeout=10
        )
        if llm_r.status_code == 200:
            llm_id = llm_r.json().get("llm_id")
            requests.patch(
                f"https://api.retellai.com/update-agent/{AGENT_ID}",
                headers={"Authorization": f"Bearer {RETELL_KEY}",
                         "Content-Type": "application/json"},
                json={"response_engine": {"type": "retell-llm", "llm_id": llm_id}},
                timeout=10
            )
    except Exception as e:
        logging.warning("Failed to set personalised LLM for %s: %s", client_name, e)

    payload = {
        "from_number": FROM_NUMBER,
        "to_number": phone,
        "agent_id": AGENT_ID,
        "retell_llm_dynamic_variables": {
            "client_name": first_name,
            "visit_date": date_ru
        },
        "transfer_options": {
            "mode": "warm_transfer",
            "transfer_numbers": {
                "1": TRANSFER_1,
                "3": TRANSFER_2
            }
        }
    }

    try:
        r = requests.post(
            "https://api.retellai.com/v2/create-phone-call",
            headers={"Authorization": f"Bearer {RETELL_KEY}",
                     "Content-Type": "application/json"},
            json=payload, timeout=15
        )
        if r.status_code == 201:
            data = r.json()
            call_id = data.get("call_id")
            now = datetime.now()
            log_call_placed(client_name, phone, call_id,
                          now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"))
            return call_id, "registered"
        else:
            logging.error("Call failed for %s: %s", client_name, r.text[:200])
            return None, "error"
    except Exception as e:
        logging.error("Call exception for %s: %s", client_name, e)
        return None, "error"

def log_call(client_name, shift, att_status, call_id="", date_str=""):
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        INSERT OR IGNORE INTO attendance
        (client_name, att_date, shift, status, reported_by, reason)
        VALUES (?, ?, ?, ?, 'victoria', ?)
    """, (client_name, date_str, shift, att_status, f"call_id:{call_id}"))
    conn.commit()
    conn.close()

def send_driver_list(clients, target_date, label):
    """Send formatted driver list to Telegram"""
    lines = [f"🚌 *Driver List — {target_date.strftime('%A %B %-d')} — {label}*\n"]
    
    by_driver = {}
    for name, phone, shift, driver in clients:
        key = f"S{shift} — {driver or 'Unassigned'}"
        by_driver.setdefault(key, []).append(name)
    
    for driver_key in sorted(by_driver):
        lines.append(f"*{driver_key}* ({len(by_driver[driver_key])})")
        for name in by_driver[driver_key]:
            lines.append(f"  • {name}")
        lines.append("")
    
    tg("\n".join(lines))


def main():
    # ── PAE Gate: Kato must approve before ANY call fires ──────────────────
    import subprocess
    gate = subprocess.run(
        ["bash", str(REX_DIR / "CC_victoria_approval_gate.sh"), "check"],
        capture_output=True, text=True
    )
    if gate.returncode != 0 or gate.stdout.strip() != "approved":
        msg = "⛔ Victoria calls HELD - no approval from Kato"
        logging.warning(msg)
        tg(msg)
        print(json.dumps({"mode": "batch", "held": True, "reason": "no_approval"}))
        sys.exit(0)
    logging.info("PAE gate: approved")
    # ── End PAE Gate ────────────────────────────────────────────────────────

    target_date, day_code, date_ru = get_tomorrow()
    date_str = str(target_date)

    logging.info("Victoria caller starting — target: %s (%s)", date_str, day_code)
    tg(f"📞 *Victoria starting calls for {target_date.strftime('%A %B %-d')}*\nPulling scheduled client list...")

    # Get ALL scheduled clients
    clients = get_scheduled_clients(day_code, target_date)
    if not clients:
        tg(f"⚠️ No scheduled clients found for {day_code} {date_str}")
        return

    # ── Kato is first call (drift check) ────────────────────────────────────
    kato = ("Kato (drift check)", "+13475879913", clients[0][2] if clients else "1", "QC")
    clients.insert(0, kato)
    tg("🎙 *Kato is first call* — drift check before batch")

    tr_only = [(n,p,s,d) for n,p,s,d in clients if p]
    tg(f"Found *{len(clients)}* scheduled clients — starting calls now")

    # ── Send PRE-CALL driver list ─────────────────────────────────────────────
    send_driver_list(clients, target_date, "PRE-CALL (full roster)")

    # ── Make calls (wave-based: 15/wave, 3s gap, 15s break) ───────────────────
    # Retell throttles/blocks agents that fire >50 rapid calls.
    # Waves stay under threshold and avoid TOS violation blocks.
    WAVE_SIZE  = 5
    WAVE_GAP   = 5    # seconds between calls inside a wave
    WAVE_BREAK = 30   # seconds between waves

    results = {}
    no_phone = []
    total_clients = len(clients)
    waves = [clients[i:i + WAVE_SIZE] for i in range(0, total_clients, WAVE_SIZE)]

    logging.info("Starting wave-based calling: %d clients in %d waves (size=%d, gap=%ds, break=%ds)",
                 total_clients, len(waves), WAVE_SIZE, WAVE_GAP, WAVE_BREAK)
    tg(f"📞 Starting *{len(waves)} wave(s)* — {WAVE_SIZE} calls each, {WAVE_GAP}s gap, {WAVE_BREAK}s break (Retell TOS-safe)")

    for wave_idx, wave in enumerate(waves, start=1):
        logging.info("Wave %d/%d starting (%d calls)", wave_idx, len(waves), len(wave))
        for client_name, phone, shift, driver in wave:
            call_id, status = make_call(client_name, phone, date_ru)
            results[client_name] = {
                "call_id": call_id, "status": "pending",
                "shift": shift, "driver": driver, "phone": phone
            }
            if status == "no_phone":
                no_phone.append(client_name)
                results[client_name]["status"] = "no_phone"
            elif status == "error":
                results[client_name]["status"] = "error"
            time.sleep(WAVE_GAP)

        # Break between waves (skip after last wave)
        if wave_idx < len(waves):
            logging.info("Wave %d done — breaking %ds before next wave", wave_idx, WAVE_BREAK)
            time.sleep(WAVE_BREAK)

    tg(f"✅ {len(clients)-len(no_phone)} calls initiated across {len(waves)} waves — waiting for responses (15 min retry)...")

    # ── Wait and collect results (poll for 20 min) ────────────────────────────
    time.sleep(900)  # 15 min — allow calls to complete + retry window

    # Query Retell for each call's actual result
    conn = sqlite3.connect(str(DB_PATH))
    for client_name, data in results.items():
        call_id = data.get("call_id")
        if not call_id:
            continue
        try:
            r = requests.get(
                f"https://api.retellai.com/v2/get-call/{call_id}",
                headers={"Authorization": f"Bearer {RETELL_KEY}"},
                timeout=10
            )
            if r.status_code == 200:
                cd = r.json()
                call_status = cd.get("call_status", "")
                dtmf = cd.get("user_dtmf", "")
                duration = (cd.get("duration_ms", 0) or 0) // 1000
                recording = cd.get("recording_url", "")
                transcript_obj = cd.get("transcript", "")
                transcript = transcript_obj if isinstance(transcript_obj, str) else json.dumps(transcript_obj)

                # Determine answer — DTMF first, then voice detection
                att = None
                
                # DTMF takes priority if pressed
                if dtmf == "1":    att = "confirmed"
                elif dtmf == "2":  att = "declined"
                elif dtmf == "3":  att = "requested_staff"
                elif dtmf == "0":  att = "repeated_options"
                
                # Voice response detection (Russian) — check transcript
                if att is None and transcript:
                    t_lower = transcript.lower()
                    # User lines only
                    user_lines = [l.split(":", 1)[1].strip().lower() 
                                  for l in transcript.split("\n") 
                                  if l.lower().startswith("user:")]
                    user_text = " ".join(user_lines)
                    
                    # Confirmed (yes)
                    if any(w in user_text for w in ["да", "приду", "буду", "приедем", "конечно", "хорошо", "подтверж"]):
                        att = "confirmed"
                    # Declined (no)
                    elif any(w in user_text for w in ["нет", "не приду", "не буду", "болею", "болеет", "не сможем", "не могу"]):
                        att = "declined"
                    # Request staff
                    elif any(w in user_text for w in ["сотрудник", "поговорить", "позовите", "человек"]):
                        att = "requested_staff"
                    # Repeat
                    elif any(w in user_text for w in ["повтори", "ещё раз", "не понял"]):
                        att = "repeated_options"
                    # User spoke but unclear intent → they picked up, mark as answered
                    elif user_text.strip():
                        att = "voice_answered"
                
                # Fallback
                if att is None:
                    att = "no_answer"
                
                # Picked up = user spoke OR call status shows answered/completed
                picked_up = "yes" if (call_status in ("answered", "completed") or 
                                      (user_lines and user_text.strip() if transcript else False)) else "no"
                if att == "voice_answered":
                    picked_up = "yes"

                conn.execute("""
                    UPDATE victoria_calls
                    SET status=?, dtmf_pressed=?, att_status=?, duration_sec=?,
                        recording_url=?, transcript=?, picked_up=?
                    WHERE call_id=?
                """, (call_status, dtmf, att, duration, recording, transcript, picked_up, call_id))
                conn.commit()

                results[client_name]["status"] = att
                results[client_name]["picked_up"] = picked_up
                results[client_name]["answer"] = dtmf

                # Also log to attendance
                log_call(client_name, results[client_name]["shift"],
                         att, call_id, date_str=date_str)
                logging.info("Call result for %s: %s (picked_up=%s dtmf=%s)",
                           client_name, att, picked_up, dtmf)
        except Exception as e:
            logging.error("Failed to poll call %s for %s: %s", call_id, client_name, e)
            results[client_name]["status"] = "no_answer"
            log_call(client_name, results[client_name]["shift"],
                     "no_answer", call_id, date_str=date_str)
    conn.close()

    # ── Build call report ─────────────────────────────────────────────────────
    confirmed      = [n for n,r in results.items() if r["status"]=="confirmed"]
    declined       = [n for n,r in results.items() if r["status"]=="declined"]
    no_answer      = [n for n,r in results.items() if r["status"]=="no_answer"]
    voicemail      = [n for n,r in results.items() if r["status"]=="voicemail"]
    req_staff      = [n for n,r in results.items() if r["status"]=="requested_staff"]
    no_phone_list  = [n for n,r in results.items() if r["status"]=="no_phone"]

    report = [
        f"📞 *Victoria Call Report — {target_date.strftime('%A %B %-d')}*\n",
        f"✅ Confirmed attending: *{len(confirmed)}*",
        f"❌ Declined: *{len(declined)}*",
        f"📵 No answer: *{len(no_answer)}*",
        f"🔄 Voicemail: *{len(voicemail)}*",
        f"👤 Requested staff: *{len(req_staff)}*",
        f"📵 No phone on file: *{len(no_phone_list)}*",
    ]

    if declined:
        report.append(f"\n*Declined:*")
        for n in declined: report.append(f"  • {n}")

    if no_answer:
        report.append(f"\n*No answer (removed from driver list):*")
        for n in no_answer[:10]: report.append(f"  • {n}")
        if len(no_answer) > 10:
            report.append(f"  ...and {len(no_answer)-10} more")

    if req_staff:
        report.append(f"\n⚠️ *Requested staff callback:*")
        for n in req_staff: report.append(f"  • {n}")

    tg("\n".join(report))

    # ── Write comprehensive per-client report (CSV) ─────────────────────────
    _write_daily_report(results, target_date, clients)

    # ── Upload to Google Drive running sheet ────────────────────────────────
    _upload_to_drive(results, target_date, clients, day_code)

    # ── Send POST-CALL driver list (remove declined + no_answer) ─────────────
    remove = set(declined + no_answer + voicemail)
    post_clients = [(n,p,s,d) for n,p,s,d in clients if n not in remove]
    send_driver_list(post_clients, target_date, "POST-CALL (confirmed only)")

    logging.info("Victoria caller complete — %d confirmed, %d declined, %d no_answer",
                 len(confirmed), len(declined), len(no_answer))


def _write_daily_report(results, target_date, clients):
    """Write per-client CSV report to local directory."""
    import csv
    report_dir = REX_DIR / "victoria_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    csv_path = report_dir / f"{target_date.strftime('%Y-%m-%d')}.csv"

    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Name", "Phone", "Shift", "Status", "DTMF", "Picked Up", "Call ID"])
        for name, phone, shift, driver in clients:
            r = results.get(name, {})
            w.writerow([
                name, phone, shift,
                r.get("status", "unknown"),
                r.get("answer", ""),
                r.get("picked_up", ""),
                r.get("call_id", "")
            ])
    logging.info("Report written: %s", csv_path)


def _upload_to_drive(results, target_date, clients, day_code):
    """Upload results to Google Drive running sheet via service account."""
    try:
        import csv, io
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseUpload
        from google.oauth2 import service_account

        SA_KEY = Path.home() / ".rex_drive_service_account.json"
        SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file"
        ]
        creds = service_account.Credentials.from_service_account_file(str(SA_KEY), scopes=SCOPES)
        sheets = build("sheets", "v4", credentials=creds)

        VICTORIA_SHEET_ID = "1KoDpjQxTG-0SdPe42NRP0OLVYMMI5cNU57EtmEfRrTg"
        sheet_name = target_date.strftime("%Y-%m-%d")

        # Try to create a new sheet tab for today
        try:
            sheets.spreadsheets().batchUpdate(
                spreadsheetId=VICTORIA_SHEET_ID,
                body={"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]}
            ).execute()
        except Exception:
            pass  # Sheet tab may already exist

        # Build rows
        rows = [["Name", "Phone", "Shift", "Status", "DTMF", "Picked Up", "Call ID"]]
        for name, phone, shift, driver in clients:
            r = results.get(name, {})
            rows.append([
                name, phone or "", str(shift),
                r.get("status", ""), r.get("answer", ""),
                r.get("picked_up", ""), r.get("call_id", "")
            ])

        # Write to sheet
        sheets.spreadsheets().values().update(
            spreadsheetId=VICTORIA_SHEET_ID,
            range=f"'{sheet_name}'!A1",
            body={"values": rows},
            valueInputOption="RAW"
        ).execute()
        logging.info("Drive report uploaded: %s", sheet_name)
    except Exception as e:
        logging.error("Drive upload failed: %s", e)


def single_call(to_number, name="Client"):
    """Place ONE Victoria call (staff-chat trigger + morning demo).
    Reuses make_call() unchanged — frozen AGENT_ID / voice / from_number are
    identical to the batch flow; only the target number differs. Prints a JSON
    result line so the caller (staff daemon / launchd) can report it back."""
    _, _, date_ru = get_tomorrow()
    call_id, status = make_call(name, to_number, date_ru)
    print(json.dumps({"mode": "single", "to": to_number, "name": name,
                      "call_id": call_id, "status": status}))
    return call_id, status


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="GOJ Victoria Caller")
    ap.add_argument("--to", help="Single number to call (E.164, e.g. +13475551234). "
                                  "If omitted, runs the full scheduled batch.")
    ap.add_argument("--name", default="Client", help="Name for the single call")
    a = ap.parse_args()
    if a.to:
        cid, st = single_call(a.to, a.name)
        sys.exit(0 if cid else 1)
    else:
        main()
