#!/usr/bin/env python3
"""
GOJ Google Sheets → SQLite Import Script
Run this from your Mac once to pull live member + attendance data.

Usage:
  pip3 install requests --break-system-packages
  python3 tools/goj_import.py

Requires: You must be logged into Google in your browser.
This script will open the gviz export URLs — make sure the sheets
are accessible (shared with your account or public).

If the sheets are private, run once with --export-browser to get
a temporary auth approach via your browser cookies.
"""

import csv
import json
import os
import sqlite3
import sys
import io
from datetime import datetime

# Sheet IDs (from Allen's email today)
SIGN_IN_SHEET_ID = '175dcfpmOEiOon3sWoX3ix2yC557NxY_6DAJE-5JZbhs'
CALENDAR_SHEET_ID = '1Vbguf9t-U_9DdMShAbnG_qGULmQyqBZVQBgiNgUb76Y'

# Output paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
DB_PATH = os.path.join(ROOT_DIR, 'data', 'rex.db')
JSON_PATH = os.path.join(ROOT_DIR, 'data', 'goj_live_data.json')

PLAN_MAP = {
    'elder serve': 'Eld Serve', 'eld serve': 'Eld Serve',
    'metro plus': 'MetroPlus', 'metroplus': 'MetroPlus',
    'pr.pay': 'Pr.Pay', 'pr. pay': 'Pr.Pay', 'pr pay': 'Pr.Pay',
    'cphl': 'Anthem', 'vcm': 'VCM', 'swh': 'SWH',
    'anthem': 'Anthem', 'aetna': 'Aetna', 'vns': 'VNS', 'empire': 'Empire'
}
VALID_PLANS = {'VCM','Eld Serve','SWH','Anthem','Aetna','VNS','MetroPlus','Pr.Pay','Empire'}
DAY_TABS = ['M1','M2','T1','T2','W1','W2','TH1','TH2','F1','F2','Su']


def fetch_csv(sheet_id, sheet_name=None):
    """Fetch a sheet as CSV using gviz export (requires browser cookies or public access)."""
    try:
        import requests
    except ImportError:
        print("Installing requests...")
        os.system(f"{sys.executable} -m pip install requests --break-system-packages -q")
        import requests

    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv"
    if sheet_name:
        url += f"&sheet={sheet_name.replace(' ', '+')}"

    # Try with browser cookies (macOS Chrome)
    try:
        import browser_cookie3
        cookies = browser_cookie3.chrome(domain_name='.google.com')
        resp = requests.get(url, cookies=cookies, timeout=15)
    except Exception:
        # Fallback: try without cookies (works if sheet is public)
        resp = requests.get(url, timeout=15)

    if resp.status_code == 200 and 'text/csv' in resp.headers.get('content-type',''):
        return resp.text
    elif resp.status_code == 200:
        # Might be HTML login page
        if '<html' in resp.text[:100].lower():
            print(f"  ⚠ Sheet '{sheet_name}' requires authentication.")
            print("  → In Google Sheets, click Share → Change to 'Anyone with link can view'")
            print("  → Re-run this script")
            return None
        return resp.text
    else:
        print(f"  ✗ HTTP {resp.status_code} for sheet '{sheet_name}'")
        return None


def parse_members(csv_text):
    """Parse master sign-in sheet into member records."""
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    members = []

    for row in rows[1:]:  # skip header
        if len(row) < 9: continue
        name = row[0].strip()
        if not name or len(name) < 3 or name == 'Name': continue
        if not any(c.isalpha() for c in name): continue

        raw_plan = row[1].strip()
        plan = PLAN_MAP.get(raw_plan.lower(), raw_plan)
        if plan not in VALID_PLANS: continue

        member = {
            'name': name,
            'plan': plan,
            'cdpap': 'yes' if row[2].strip() == 'V' else '',
            'transport': row[3].strip(),
            'table': row[4].strip(),
            'shift': row[6].strip() or '1',
            'address': row[7].strip(),
            'phone': row[8].strip(),
            'days': {
                'M':  1 if len(row) > 9  and row[9].strip()  == '1' else 0,
                'T':  1 if len(row) > 10 and row[10].strip() == '1' else 0,
                'W':  1 if len(row) > 11 and row[11].strip() == '1' else 0,
                'TH': 1 if len(row) > 12 and row[12].strip() == '1' else 0,
                'F':  1 if len(row) > 13 and row[13].strip() == '1' else 0,
                'Su': 1 if len(row) > 14 and row[14].strip() == '1' else 0,
            },
            'memberId': row[15].strip() if len(row) > 15 else '',
            'dob': row[16].strip() if len(row) > 16 else '',
            'dobMonth': row[17].strip() if len(row) > 17 else '',
            'homeCare': row[18].strip() if len(row) > 18 else '',
            'notes': {
                'apr': row[19].strip() if len(row) > 19 else '',
                'mar': row[20].strip() if len(row) > 20 else '',
                'feb': row[21].strip() if len(row) > 21 else '',
                'jan': row[22].strip() if len(row) > 22 else '',
                'dec': row[23].strip() if len(row) > 23 else '',
                'nov': row[24].strip() if len(row) > 24 else '',
            }
        }
        members.append(member)

    return members


def parse_day_roster(csv_text, tab_name):
    """Parse a day/shift attendance sheet."""
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    roster = []
    for row in rows[1:]:
        if len(row) < 2: continue
        name = row[0].strip()
        if not name or len(name) < 2: continue
        if 'GARDEN OF JOY' in name.upper(): continue
        if not any(c.isalpha() for c in name): continue
        roster.append({
            'name': name,
            'plan': row[1].strip() if len(row) > 1 else '',
            'transport': row[3].strip() if len(row) > 3 else '',
        })
    return roster


def parse_calendar(csv_text):
    """Parse Calendar 2026 — extract April attendance per member."""
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    members = []
    for row in rows[2:]:  # skip 2 header rows
        if len(row) < 11: continue
        name = row[1].strip()
        if not name or len(name) < 2: continue
        attendance = {}
        for d in range(1, 32):
            val = row[8 + d].strip() if len(row) > 8 + d else ''
            if val.upper() in ('Y', '1'):
                attendance[d] = True
        members.append({'name': name, 'plan': row[2].strip(), 'attendance': attendance, 'daysPresent': len(attendance)})
    return members


def save_to_sqlite(members, daily_rosters, db_path):
    """Save all GOJ data to REX SQLite database."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Create tables if not exist
    cur.execute('''
        CREATE TABLE IF NOT EXISTS goj_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            plan TEXT,
            cdpap TEXT,
            transport TEXT,
            shift TEXT,
            address TEXT,
            phone TEXT,
            days_json TEXT,
            member_id TEXT,
            dob TEXT,
            home_care TEXT,
            notes_json TEXT,
            updated_at TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS goj_daily_rosters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tab TEXT NOT NULL,
            name TEXT NOT NULL,
            plan TEXT,
            transport TEXT,
            updated_at TEXT
        )
    ''')

    # Clear and reload
    cur.execute('DELETE FROM goj_members')
    cur.execute('DELETE FROM goj_daily_rosters')

    ts = datetime.now().isoformat()
    for m in members:
        cur.execute('''
            INSERT INTO goj_members (name, plan, cdpap, transport, shift, address, phone,
                days_json, member_id, dob, home_care, notes_json, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''', (m['name'], m['plan'], m['cdpap'], m['transport'], m['shift'],
              m['address'], m['phone'], json.dumps(m['days']),
              m['memberId'], m['dob'], m['homeCare'],
              json.dumps(m['notes']), ts))

    for tab, roster in daily_rosters.items():
        for r in roster:
            cur.execute('''
                INSERT INTO goj_daily_rosters (tab, name, plan, transport, updated_at)
                VALUES (?,?,?,?,?)
            ''', (tab, r['name'], r['plan'], r['transport'], ts))

    conn.commit()
    conn.close()
    print(f"  ✓ Saved {len(members)} members + {sum(len(v) for v in daily_rosters.values())} roster entries to SQLite")


def main():
    print("\n🥚 GOJ Data Import — Garden of Joy Adult Day Care")
    print("=" * 50)
    print(f"Sign-In Sheet: {SIGN_IN_SHEET_ID}")
    print(f"Calendar Sheet: {CALENDAR_SHEET_ID}")
    print()

    # Fetch sign-in master
    print("📋 Fetching master sign-in sheet...")
    sign_in_csv = fetch_csv(SIGN_IN_SHEET_ID, 'sign in')
    if not sign_in_csv:
        print("❌ Could not fetch sign-in sheet. See instructions above.")
        sys.exit(1)
    members = parse_members(sign_in_csv)
    print(f"  ✓ Parsed {len(members)} members")

    # Fetch daily rosters
    print("📅 Fetching daily attendance rosters...")
    daily_rosters = {}
    for tab in DAY_TABS:
        csv_text = fetch_csv(SIGN_IN_SHEET_ID, tab)
        if csv_text:
            daily_rosters[tab] = parse_day_roster(csv_text, tab)
            print(f"  ✓ {tab}: {len(daily_rosters[tab])} members")

    # Fetch calendar
    print("📆 Fetching April 2026 calendar...")
    cal_csv = fetch_csv(CALENDAR_SHEET_ID)
    cal_data = parse_calendar(cal_csv) if cal_csv else []
    print(f"  ✓ Calendar: {len(cal_data)} member records")

    # Compute stats
    plan_counts = {}
    for m in members:
        plan_counts[m['plan']] = plan_counts.get(m['plan'], 0) + 1
    day_counts = {d: sum(1 for m in members if m['days'].get(d)) for d in ['M','T','W','TH','F','Su']}
    van_count = sum(1 for m in members if m['transport'] == 'TR')
    apr_by_day = {}
    for d in range(1, 13):
        cnt = sum(1 for m in cal_data if m['attendance'].get(d))
        if cnt > 0: apr_by_day[d] = cnt

    # Build full package
    package = {
        'meta': {
            'generated': datetime.now().isoformat(),
            'totalMembers': len(members),
            'source': 'Google Sheets live import'
        },
        'members': members,
        'dailyRosters': daily_rosters,
        'aprilAttendance': cal_data,
        'stats': {
            'plans': plan_counts,
            'transport': {'van': van_count, 'self': len(members) - van_count},
            'cdpap': sum(1 for m in members if m['cdpap'] == 'yes'),
            'byDay': day_counts,
            'aprilByDay': apr_by_day
        }
    }

    # Save to JSON
    os.makedirs(os.path.dirname(JSON_PATH), exist_ok=True)
    with open(JSON_PATH, 'w') as f:
        json.dump(package, f, indent=2)
    print(f"\n✓ JSON saved → {JSON_PATH}")

    # Save to SQLite
    print("💾 Saving to SQLite database...")
    save_to_sqlite(members, daily_rosters, DB_PATH)
    print(f"✓ SQLite saved → {DB_PATH}")

    print(f"\n📊 Summary:")
    print(f"   Total members: {len(members)}")
    for plan, cnt in sorted(plan_counts.items(), key=lambda x: -x[1]):
        print(f"   {plan}: {cnt}")
    print(f"   Van transport: {van_count} | Self: {len(members)-van_count}")
    print(f"   CDPAP: {package['stats']['cdpap']}")
    print(f"\n   Daily rosters: M={len(daily_rosters.get('M1',[]))+len(daily_rosters.get('M2',[]))} "
          f"T={len(daily_rosters.get('T1',[]))+len(daily_rosters.get('T2',[]))} "
          f"W={len(daily_rosters.get('W1',[]))+len(daily_rosters.get('W2',[]))} "
          f"TH={len(daily_rosters.get('TH1',[]))+len(daily_rosters.get('TH2',[]))} "
          f"F={len(daily_rosters.get('F1',[]))+len(daily_rosters.get('F2',[]))} "
          f"Su={len(daily_rosters.get('Su',[]))}")
    print(f"\n✅ GOJ data import complete! Restart the REX backend to pick up changes.")


if __name__ == '__main__':
    main()
