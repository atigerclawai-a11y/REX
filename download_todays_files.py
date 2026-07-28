#!/usr/bin/env python3
"""
download_todays_files.py — Download today's GOJ email attachments and process them.
Run this on the Mac: python3 ~/Desktop/REX/download_todays_files.py
"""
import json, base64, sys
from pathlib import Path

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
except ImportError:
    import subprocess
    subprocess.run([sys.executable, '-m', 'pip', 'install',
        'google-api-python-client', 'google-auth-httplib2',
        'google-auth-oauthlib', '--break-system-packages', '-q'])
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

# Token paths — try several locations
TOKEN_PATHS = [
    Path.home() / '.rex_google_token.json',
    Path.home() / 'Desktop' / 'REX' / '.rex_google_token.json',
    Path.home() / 'Desktop' / 'REX' / 'GOJ_Backups' / 'GOJ_2026-04-19_06-11' / 'gmail' / 'gmail_token.json',
]

creds = None
for tp in TOKEN_PATHS:
    if tp.exists():
        print(f"Using token: {tp}")
        creds = Credentials.from_authorized_user_info(json.loads(tp.read_text()))
        break

if not creds:
    print("ERROR: No Google token found. Tried:")
    for tp in TOKEN_PATHS:
        print(f"  {tp}")
    sys.exit(1)

if creds.expired and creds.refresh_token:
    creds.refresh(Request())
    print("Token refreshed OK")

service = build('gmail', 'v1', credentials=creds)
print("Gmail API connected\n")

# Today's message IDs
MESSAGES = {
    'sign_in':           '19dab8de8bff2a10',
    'calendar_attend':   '19dab8f0fb3da992',
    'first_shift_menu':  '19dab91a3b4a3a03',
    'menu_first_shift':  '19dab9cd4f19ccaf',
    'menu_second_shift': '19dab9d466ebc0d8',
    'cohl_anthem':       '19dabd7370178dc8',
}

# Save to goj files folder
OUT_DIR = Path.home() / 'Documents' / 'goj files' / 'todays_files'
OUT_DIR.mkdir(parents=True, exist_ok=True)
print(f"Saving to: {OUT_DIR}\n")

def download_parts(parts, msg_id, label):
    saved = []
    for part in parts:
        fname = part.get('filename', '')
        if fname:
            att_id = part.get('body', {}).get('attachmentId')
            data = part.get('body', {}).get('data')
            if att_id:
                att = service.users().messages().attachments().get(
                    userId='me', messageId=msg_id, id=att_id).execute()
                data = att['data']
            if data:
                fb = base64.urlsafe_b64decode(data)
                out = OUT_DIR / f"{label}_{fname}"
                out.write_bytes(fb)
                print(f"  ✓ {fname}  ({len(fb):,} bytes)")
                saved.append(out)
        # recurse into sub-parts
        for sub in part.get('parts', []):
            saved += download_parts([sub], msg_id, label)
    return saved

all_files = []
for label, msg_id in MESSAGES.items():
    print(f"[{label}]")
    msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
    payload = msg.get('payload', {})
    parts = payload.get('parts', [payload])
    files = download_parts(parts, msg_id, label)
    if not files:
        print("  (no attachment)")
    all_files += files

print(f"\n=== Downloaded {len(all_files)} files ===")
for f in all_files:
    print(f"  {f.name}")

# ── Now process what we got ──────────────────────────────────────────────────
import sqlite3, openpyxl, re
from datetime import datetime

DB_PATH = Path.home() / 'Documents' / 'goj files' / 'auth_tracker.db'
if not DB_PATH.exists():
    print(f"\nDB not found at {DB_PATH}")
    sys.exit(0)

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row

CANONICAL_MAP = {
    'cphl':'Anthem',
    'eld serve':'ElderServe — Riverspring Health',
    'elder serve':'ElderServe — Riverspring Health',
    'elderserve':'ElderServe — Riverspring Health',
    'anthem':'Anthem — Integra',
    'vcm':'VillageCare MAX',
    'swh':'Senior Whole Health',
    'vns':'VNS Health',
    'aetna':'Aetna Better Health',
    'metro plus':'MetroPlus Health',
    'metroplus':'MetroPlus Health',
    'pr.pay':'Private Pay',
    'pr. pay':'Private Pay',
    'private pay':'Private Pay',
    'empire':'Empire BlueCross BlueShield',
}

def norm_plan(raw):
    if not raw: return None, True
    k = str(raw).strip().lower()
    c = CANONICAL_MAP.get(k)
    return (c, False) if c else (str(raw).strip(), True)

def parse_day(v):
    return int(v) if v in (1, 2, 1.0, 2.0) else 0

summary_lines = []

for f in all_files:
    name = f.name.lower()
    print(f"\n{'='*60}")
    print(f"Processing: {f.name}")

    if not name.endswith('.xlsx') and not name.endswith('.xls'):
        print("  (not an xlsx — skipping DB import)")
        continue

    try:
        wb = openpyxl.load_workbook(str(f), data_only=True)
    except Exception as e:
        print(f"  ERROR opening: {e}")
        continue

    print(f"  Sheets: {wb.sheetnames}")

    # ── SIGN IN processing ───────────────────────────────────────────────────
    if 'sign_in' in f.name or 'sign in' in ''.join(wb.sheetnames).lower():
        ws_name = next((s for s in wb.sheetnames if 'sign' in s.lower()), wb.sheetnames[0])
        ws = wb[ws_name]
        print(f"  Using sheet: {ws_name}")
        updated = inserted = skipped = 0
        for row in ws.iter_rows(min_row=3, values_only=True):
            name_val = row[0]
            if not name_val or not isinstance(name_val, str) or len(name_val.strip()) < 2:
                continue
            client_name = name_val.strip()
            if client_name == 'AAAAAAAA':
                continue
            try:
                M = parse_day(row[9]); T = parse_day(row[10]); W = parse_day(row[11])
                TH = parse_day(row[12]); F = parse_day(row[13]); Su = parse_day(row[14] if len(row) > 14 else 0)
            except:
                M=T=W=TH=F=Su=0
            active = 1 if any([M,T,W,TH,F,Su]) else 0
            plan_raw = str(row[1]).strip() if row[1] else ''
            plan_canonical, plan_flagged = norm_plan(plan_raw)
            ex = conn.execute('SELECT client_id FROM clients WHERE name=?', (client_name,)).fetchone()
            try:
                if ex:
                    conn.execute('''UPDATE clients SET
                        plan_raw=?,plan_canonical=?,plan_flagged=?,active=?,
                        day_M_actual=?,day_M_base=?,day_T_actual=?,day_T_base=?,
                        day_W_actual=?,day_W_base=?,day_TH_actual=?,day_TH_base=?,
                        day_F_actual=?,day_F_base=?,day_Su_actual=?,day_Su_base=?,
                        updated_at=CURRENT_TIMESTAMP WHERE name=?''',
                        (plan_raw, plan_canonical, 1 if plan_flagged else 0, active,
                         M,M,T,T,W,W,TH,TH,F,F,Su,Su, client_name))
                    updated += 1
                else:
                    conn.execute('''INSERT INTO clients
                        (name,plan_raw,plan_canonical,plan_flagged,active,
                         day_M_actual,day_M_base,day_T_actual,day_T_base,
                         day_W_actual,day_W_base,day_TH_actual,day_TH_base,
                         day_F_actual,day_F_base,day_Su_actual,day_Su_base)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (client_name, plan_raw, plan_canonical, 1 if plan_flagged else 0, active,
                         M,M,T,T,W,W,TH,TH,F,F,Su,Su))
                    inserted += 1
            except Exception as e:
                skipped += 1
        conn.commit()
        total_active = conn.execute('SELECT COUNT(*) FROM clients WHERE active=1').fetchone()[0]
        msg = f"Sign-In import: {updated} updated, {inserted} inserted, {skipped} skipped | DB active: {total_active}"
        print(f"  {msg}")
        summary_lines.append(msg)

    # ── CALENDAR / ATTENDANCE ────────────────────────────────────────────────
    elif 'calendar' in f.name:
        # Find April sheet
        apr_sheet = next((s for s in wb.sheetnames if 'apr' in s.lower() or '4' in s), wb.sheetnames[0])
        ws = wb[apr_sheet]
        print(f"  Using sheet: {apr_sheet}")
        # Col B=Name, C=Plan, D-I = M/T/W/TH/F/Su, J+ = daily attendance dates
        headers = [ws.cell(2, c).value for c in range(1, ws.max_column+1)]
        print(f"  Row 2 headers (first 12): {headers[:12]}")
        # Find date columns for this week (Apr 14-19)
        this_week_dates = ['2026-04-14','2026-04-15','2026-04-16','2026-04-17','2026-04-18','2026-04-19']
        # Try to find columns matching these dates
        date_cols = {}
        for ci, h in enumerate(headers):
            if h is None: continue
            if isinstance(h, datetime):
                ds = h.date().isoformat()
                if ds in this_week_dates:
                    date_cols[ds] = ci+1
            elif isinstance(h, str) and any(d in h for d in ['14','15','16','17','18','19']):
                for d in this_week_dates:
                    if d[-2:] in str(h):
                        date_cols[d] = ci+1
        print(f"  Found date columns for this week: {date_cols}")
        att_inserted = 0
        for row in ws.iter_rows(min_row=3, values_only=True):
            client_name = row[1] if len(row) > 1 else None
            if not client_name or not isinstance(client_name, str) or len(client_name.strip()) < 2:
                continue
            client_name = client_name.strip()
            for date_str, col_idx in date_cols.items():
                val = row[col_idx-1] if len(row) >= col_idx else None
                if val and str(val).strip() not in ('', '0', 'None'):
                    # Mark attendance
                    try:
                        conn.execute('''INSERT OR REPLACE INTO attendance_log
                            (client_name, attendance_date, present, source, created_at)
                            VALUES (?,?,1,'calendar_import',CURRENT_TIMESTAMP)''',
                            (client_name, date_str))
                        att_inserted += 1
                    except Exception as e:
                        # attendance_log might have different schema
                        pass
        conn.commit()
        msg = f"Calendar import: {att_inserted} attendance records"
        print(f"  {msg}")
        summary_lines.append(msg)

    # ── MENU FILES ───────────────────────────────────────────────────────────
    elif 'menu' in f.name:
        # Determine shift from filename
        shift = 2 if 'second' in f.name.lower() else 1
        print(f"  Menu file — Shift {shift}")
        # Try each sheet
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            print(f"  Sheet '{sheet_name}': {ws.max_row} rows x {ws.max_column} cols")
            # Print first few rows to understand structure
            for ri in range(1, min(5, ws.max_row+1)):
                row_vals = [ws.cell(ri, ci).value for ci in range(1, min(10, ws.max_column+1))]
                print(f"    Row {ri}: {row_vals}")
        summary_lines.append(f"Menu shift {shift}: opened, needs manual review of structure")

print(f"\n{'='*60}")
print("SUMMARY:")
for line in summary_lines:
    print(f"  • {line}")

# Final DB counts
total = conn.execute('SELECT COUNT(*) FROM clients').fetchone()[0]
active = conn.execute('SELECT COUNT(*) FROM clients WHERE active=1').fetchone()[0]
menus_this_week = conn.execute("SELECT COUNT(*) FROM client_menus WHERE week_start='2026-04-14'").fetchone()[0]
print(f"\nDB Status:")
print(f"  Clients: {total} total, {active} active")
print(f"  Menu orders week of Apr 14: {menus_this_week}")
conn.close()
print("\nDone.")
