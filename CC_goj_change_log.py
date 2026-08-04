#!/usr/bin/env python3
"""
CC_goj_change_log.py — GOJ Change Log → Google Drive.
Appends every WhatsApp +/− schedule change to a Google Sheet:
  columns: Timestamp | Sender | Message | Client | Type | Reason

Reads imessage_intel.db (WhatsApp bridge) for change messages,
dedupes by message id, appends new ones to the sheet.
Sheet: "GOJ Change Log" (created once, shared with Kato).

Usage:
  python3 CC_goj_change_log.py            # incremental append
  python3 CC_goj_change_log.py --init     # create sheet + header (first run)
  python3 CC_goj_change_log.py --backfill # backfill last 7 days
"""
import json, re, sys, os
from datetime import datetime, timedelta
from pathlib import Path

HOME = Path.home()
SA_PATH = HOME / ".rex_drive_service_account.json"
DB_PATH = Path(HOME) / "Desktop/REX/data/imessage_intel.db"
STATE_PATH = Path(HOME) / "Desktop/REX/data/change_log_state.json"
SHEET_ID_PATH = Path(HOME) / "Desktop/REX/data/change_log_sheet_id.txt"
KATO_EMAIL = "atigerclawai@gmail.com"

# change-detection keywords (matches datarex SCHEDULE_KWS + gaps found 8/4)
CHANGE_KWS = [
    "not coming", "won't be", "wont be", "sick", "absent", "cancel", "skip",
    "not today", "day off", "not attending", "больниц", "уехал", "болеет",
    "chang", "change", "switch", "смен", "перенос", "appointment", "доктор",
    "вместо", "прид", "будет", "перевод", "vocation", "vacation", "отдых",
    "одых", "не будет", "поедет",
]

def parse_change(text, sender):
    """Classify: minus / plus / change / note. Return (type, client, reason)."""
    low = text.lower()
    client = ""
    reason = ""
    # strip "No"/"No X" prefixes (Russian-English mix)
    m = re.match(r"^\s*no\s+([A-Za-zА-Яа-яЁё-]+(?:\s+[A-Za-zА-Яа-яЁё-]+)?)", text, re.I)
    if m:
        client = m.group(1)
        rest = text[m.end():].strip()
        reason = rest if rest else "cancelled"
        typ = "MINUS"
    elif re.match(r"^\s*[\+\-]", text.strip()):
        typ = "PLUS" if text.strip().startswith("+") else "MINUS"
        rest = text.strip()[1:].strip()
        parts = rest.split(",", 1)
        client = parts[0].strip()
        reason = parts[1].strip() if len(parts) > 1 else ""
    elif "chang" in low or "switch" in low or "смен" in low or "перенос" in low or "перевод" in low:
        typ = "CHANGE"
        # client = first capitalized token group before chang/switch
        m2 = re.match(r"^\s*([A-Za-zА-Яа-яЁё-]+(?:\s+[A-Za-zА-Яа-яЁё-]+)?)", text)
        if m2:
            client = m2.group(1)
        reason = text
    elif any(k in low for k in ["sick", "болеет", "больниц", "доктор", "appointment", "врач"]):
        typ = "MINUS"
        m2 = re.match(r"^\s*(?:no\s+)?([A-Za-zА-Яа-яЁё-]+(?:\s+[A-Za-zА-Яа-яЁё-]+)?)", text, re.I)
        if m2:
            client = m2.group(1)
        reason = text
    else:
        typ = "NOTE"
        m2 = re.match(r"^\s*([A-Za-zА-Яа-яЁё-]+(?:\s+[A-Za-zА-Яа-яЁё-]+)?)", text)
        if m2:
            client = m2.group(1)
        reason = text
    return typ, client, reason

def get_creds():
    """OAuth (granted Drive/Sheets per Kato Jul 19 override). SA lacks write."""
    import google.oauth2.credentials as gcred
    import google.auth.transport.requests as greq
    tok = json.load(open(HOME / ".rex_google_token.json"))
    creds = gcred.Credentials(
        token=tok.get("token"),
        refresh_token=tok.get("refresh_token"),
        token_uri=tok.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=tok.get("client_id"),
        client_secret=tok.get("client_secret"),
        scopes=["https://www.googleapis.com/auth/drive",
                "https://www.googleapis.com/auth/spreadsheets"],
    )
    if creds.expired or not creds.valid:
        creds.refresh(greq.Request())
        # persist refreshed token
        tok2 = {
            "token": creds.token, "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri, "client_id": creds.client_id,
            "client_secret": creds.client_secret, "scopes": creds.scopes,
        }
        json.dump(tok2, open(HOME / ".rex_google_token.json", "w"))
    return creds

def get_or_create_sheet(svc, sheets):
    sid_path = SHEET_ID_PATH
    if sid_path.exists():
        sid = sid_path.read_text().strip()
        try:
            svc.files().get(fileId=sid).execute()
            return sid
        except Exception:
            pass
    # create
    meta = {'name': 'GOJ Change Log', 'mimeType': 'application/vnd.google-apps.spreadsheet'}
    f = svc.files().create(body=meta, fields='id').execute()
    sid = f['id']
    sid_path.write_text(sid)
    # share with Kato
    svc.permissions().create(fileId=sid, body={
        'type': 'user', 'role': 'writer', 'emailAddress': KATO_EMAIL}).execute()
    # header
    sheets.spreadsheets().values().update(
        spreadsheetId=sid, range='A1:F1',
        valueInputOption='RAW',
        body={'values': [['Timestamp', 'Sender', 'Message', 'Client', 'Type', 'Reason']]}).execute()
    print(f"✅ Sheet created: https://docs.google.com/spreadsheets/d/{sid}")
    return sid

def fetch_messages(since_days=7):
    import sqlite3
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    since = (datetime.now() - timedelta(days=since_days)).isoformat()
    rows = con.execute("""
        SELECT id, sender, text, received_at, is_schedule_change
        FROM imessage_intel
        WHERE received_at >= ? AND text IS NOT NULL AND text != ''
        ORDER BY received_at
    """, (since,)).fetchall()
    con.close()
    return rows

def main():
    import warnings
    warnings.filterwarnings("ignore")
    import googleapiclient.discovery as disc

    backfill = "--backfill" in sys.argv
    days = 14 if backfill else 1

    svc = disc.build('drive', 'v3', credentials=get_creds(), cache_discovery=False)
    sheets = disc.build('sheets', 'v4', credentials=get_creds(), cache_discovery=False)
    sid = get_or_create_sheet(svc, sheets)

    # state: last synced message id
    state = {}
    if STATE_PATH.exists():
        state = json.load(open(STATE_PATH))
    last_id = state.get("last_id", 0)

    rows = fetch_messages(days)
    new_rows = []
    for r in rows:
        if r["id"] <= last_id:
            continue
        typ, client, reason = parse_change(r["text"], r["sender"])
        # only log schedule-relevant types
        if typ == "NOTE":
            # keep notes but mark them; keep everything for now
            pass
        new_rows.append([
            r["received_at"][:16], r["sender"], r["text"],
            client, typ, reason,
        ])
        last_id = max(last_id, r["id"])

    if not new_rows:
        # silent — nothing to report (no_agent cron delivers only non-empty stdout)
        return

    # append
    sheets.spreadsheets().values().append(
        spreadsheetId=sid, range='A2:F',
        valueInputOption='RAW', insertDataOption='INSERT_ROWS',
        body={'values': new_rows}).execute()

    state["last_id"] = last_id
    state["last_sync"] = datetime.now().isoformat()
    json.dump(state, open(STATE_PATH, "w"))
    print(f"✅ Appended {len(new_rows)} change(s) → GOJ Change Log")
    for n in new_rows[-5:]:
        print(f"   {n[0]} | {n[4]:6s} | {n[3]} | {n[5]}")

if __name__ == "__main__":
    main()
