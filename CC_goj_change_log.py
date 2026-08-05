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
    """Service Account (Kato hard rule 2026-08-04: Drive/Sheets = SA, NEVER OAuth).
    Fixed 08-04: OAuth token was stale/deleted → files().create() failed every run."""
    from google.oauth2 import service_account as gsa
    creds = gsa.Credentials.from_service_account_file(
        str(SA_PATH),
        scopes=["https://www.googleapis.com/auth/drive",
                "https://www.googleapis.com/auth/spreadsheets"],
    )
    return creds

def _sheet_id(sheets, sid):
    """Return the numeric sheetId of the first sheet (needed for batchUpdate)."""
    meta = sheets.spreadsheets().get(spreadsheetId=sid, fields='sheets.properties.sheetId,sheets.properties.title').execute()
    return meta['sheets'][0]['properties']['sheetId']


def _current_last_row(sheets, sid):
    """Row index (1-based) of the last row with content, for coloring."""
    r = sheets.spreadsheets().values().get(spreadsheetId=sid, range='A:G').execute()
    return len(r.get('values', []))


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
        spreadsheetId=sid, range='A1:G1',
        valueInputOption='RAW',
        body={'values': [['Timestamp', 'Sender', 'Message', 'Client', 'Type', 'Reason', 'Group']]}).execute()
    print(f"✅ Sheet created: https://docs.google.com/spreadsheets/d/{sid}")
    return sid

# ── Group whitelist ─────────────────────────────────────────────────────
# The change log must ONLY ingest the three GOJ WhatsApp groups:
#   main, attendance, plus and minus.
# (Kato rule 8/4: "main group, attendance group, and plus and minus group
#  all from whats app" — everything else is noise.)
# JID → canonical name. `Main` confirmed 8/4 via bridge state.json exact
# 47/47 message-id match; Attendance identified by Lena's sign-in-verification
# content; Plus and Minus = image-post group (text often empty).
GROUP_ALIASES = {
    "120363410220335589@g.us": "Main",
    "120363428164994197@g.us": "Attendance",
    "120363429083958383@g.us": "Plus and Minus",
}
# canonical group names (lowercase) that are allowed in the log
GOJ_GROUPS = {"main", "attendance", "plus and minus", "plus"}


def resolve_group(g: str) -> str | None:
    """Map a raw group value (JID or subject) to a canonical GOJ group name.
    Returns None for non-GOJ groups (prayer chat, unknown, empty)."""
    g = (g or "").strip()
    if not g:
        return None
    if g in GROUP_ALIASES:
        return GROUP_ALIASES[g]
    low = g.lower()
    if "plus" in low or "minus" in low:
        return "Plus and Minus"
    if "attendance" in low:
        return "Attendance"
    if low == "main" or low.endswith("main") or "main" in low:
        return "Main"
    return None


# row background colors per group (R,G,B 0-1 for Sheets API)
GROUP_COLORS = {
    "Main":          (0.85, 0.92, 1.0),  # light blue
    "Attendance":    (0.87, 1.0, 0.87),  # light green
    "Plus and Minus": (1.0, 0.94, 0.82), # light orange
}


def fetch_messages(since_days=7):
    import sqlite3
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    since = (datetime.now() - timedelta(days=since_days)).isoformat()
    rows = con.execute("""
        SELECT id, group_name, sender, text, received_at
        FROM imessage_intel
        WHERE received_at >= ? AND text IS NOT NULL AND text != ''
        ORDER BY received_at
    """, (since,)).fetchall()
    con.close()
    # whitelist: only the three GOJ WhatsApp groups
    return [r for r in rows if resolve_group(r["group_name"]) is not None]

def main():
    import warnings
    warnings.filterwarnings("ignore")
    import googleapiclient.discovery as disc

    backfill = "--backfill" in sys.argv
    days = 14 if backfill else 1

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
        group = resolve_group(r["group_name"]) or ""
        new_rows.append([
            r["received_at"][:16], r["sender"], r["text"],
            client, typ, reason, group,
        ])
        last_id = max(last_id, r["id"])

    if not new_rows:
        # silent — nothing to report (no_agent cron delivers only non-empty stdout)
        return

    # ── LOCAL LOG (source of truth, SA cannot write Drive) ──
    LOCAL_LOG = HOME / "Desktop/REX/data/change_log.json"
    local = []
    if LOCAL_LOG.exists():
        local = json.load(open(LOCAL_LOG))
    existing = {tuple(r[:7]) for r in local}
    added = [r for r in new_rows if tuple(r[:7]) not in existing]
    local.extend(added)
    json.dump(local, open(LOCAL_LOG, "w"), ensure_ascii=False, indent=1)
    state["last_id"] = last_id
    json.dump(state, open(STATE_PATH, "w"))

    # ── DRIVE best-effort (SA quota=0, may fail — local log still authoritative) ──
    try:
        svc = disc.build('drive', 'v3', credentials=get_creds(), cache_discovery=False)
        sheets = disc.build('sheets', 'v4', credentials=get_creds(), cache_discovery=False)
        sid = get_or_create_sheet(svc, sheets)
        sheets.spreadsheets().values().append(
            spreadsheetId=sid, range='A2:G',
            valueInputOption='RAW', insertDataOption='INSERT_ROWS',
            body={'values': added}).execute()
    except Exception as e:
        # Drive write failed (quota/permission) — local log still has the data
        pass

    print(f"📋 {len(added)} change(s) logged locally (Drive write: "
          f"{'OK' if 'sid' in dir() else 'skipped — SA cannot write'})")

    # color-code each appended row by its group chat
    first_row = _current_last_row(sheets, sid)
    n = len(new_rows)
    color_requests = []
    for i, row in enumerate(new_rows):
        grp = row[6]
        rgb = GROUP_COLORS.get(grp)
        if not rgb:
            continue
        color_requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": _sheet_id(sheets, sid),
                    "startRowIndex": first_row - n + i,
                    "endRowIndex": first_row - n + i + 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 7,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {
                            "red": rgb[0], "green": rgb[1], "blue": rgb[2],
                        }
                    }
                },
                "fields": "userEnteredFormat.backgroundColor",
            }
        })
    if color_requests:
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=sid, body={"requests": color_requests}).execute()

    state["last_id"] = last_id
    state["last_sync"] = datetime.now().isoformat()
    json.dump(state, open(STATE_PATH, "w"))
    print(f"✅ Appended {len(new_rows)} change(s) → GOJ Change Log")
    for n in new_rows[-5:]:
        print(f"   {n[0]} | {n[4]:6s} | {n[3]} | {n[5]}")

if __name__ == "__main__":
    main()
