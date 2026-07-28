#!/usr/bin/env python3
"""
CC_drive_lists.py — GOJ Daily Lists from Google Drive (source of truth)
═══════════════════════════════════════════════════════════════════
Reads sign-in sheets and menu sheets DIRECTLY from Google Drive.
NO database dependency for schedule data. Always current.
Generates: kitchen prep, distribution, sign-in PDFs.

Usage:
  python3 CC_drive_lists.py --date 2026-06-19
  python3 CC_drive_lists.py --date 2026-06-19 --kitchen-only
"""
import argparse, sys, os, json, re
from pathlib import Path
from datetime import date, datetime, timedelta
from collections import Counter

# ── Paths ─────────────────────────────────────────────────────────
REX_DIR    = Path.home() / "Desktop" / "REX"
OUTPUT_DIR = Path.home() / "Documents" / "goj files" / "output_docs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Google Sheets API ──────────────────────────────────────────────
sys.path.insert(0, str(REX_DIR))
import importlib.util
spec = importlib.util.spec_from_file_location("ing", str(REX_DIR / "CC_goj_drive_ingest.py"))
ing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ing)

# ── Sheet IDs (source of truth) ────────────────────────────────────
SIGN_IN_ID   = "1ko7aVBhzLMngCuWmIZuCC5eT6WwvNEUiS8Q0vF92oy8"
MENU_S1_ID   = "1IfBJbKleeqA329FI3WeoFQp2xqmKYRJiy_I7RC2ZBcw"  # labeled "First shift" — contains S1 names
MENU_S2_ID   = "18rs4xZHmdjt78za9tsh1bse94q-9Vn-pKXcnjID3ER0"  # labeled "Second Shift" — contains S2 names

# ── Day mappings ───────────────────────────────────────────────────
DAY_MAP = {
    0: ("M",  "Monday"),    1: ("T",  "Tuesday"),
    2: ("W",  "Wednesday"), 3: ("TH", "Thursday"),
    4: ("F",  "Friday"),    5: ("Su", "Saturday"),
    6: ("Su", "Sunday"),
}
DAY_CODES = {"Monday":"M","Tuesday":"T","Wednesday":"W","Thursday":"TH","Friday":"F","Saturday":"Su","Sunday":"Su"}

def get_day_info(d):
    code, name = DAY_MAP[d.weekday()]
    return code, name

def get_services():
    return ing.get_services()

# ═══════════════════════════════════════════════════════════════════
# DRIVE READERS
# ═══════════════════════════════════════════════════════════════════

def read_sign_in_sheet(day_code, shift):
    """Read clients from sign-in sheet. Returns list of {name, plan, transport}."""
    svc = get_services()
    sheets = svc['sheets']
    
    # Sunday uses combined "Su" tab (no shift suffix)
    if day_code == "Su":
        tab = "Su"
    else:
        tab = f"{day_code}{shift}"
    
    result = sheets.spreadsheets().values().get(
        spreadsheetId=SIGN_IN_ID,
        range=f"'{tab}'!A1:H110"
    ).execute()
    values = result.get('values', [])
    
    clients = []
    for row in values[3:]:  # Skip title/header rows
        if not row or not row[0].strip():
            continue
        name = row[0].strip()
        if name in ('Name', 'GARDEN', ''):
            continue
        plan = row[1].strip() if len(row) > 1 else ""
        transport = row[3].strip() if len(row) > 3 else ""
        clients.append({
            'name': name,
            'plan': plan,
            'transport': transport,
        })
    return clients

def read_sign_in_transport(day_code, shift):
    """Read transport addresses from TR tab."""
    svc = get_services()
    sheets = svc['sheets']
    
    # Sunday uses combined "S TR" tab (no shift suffix)
    if day_code == "Su":
        tab = "S TR"
    else:
        tab = f"{day_code}{shift} TR"
    
    try:
        result = sheets.spreadsheets().values().get(
            spreadsheetId=SIGN_IN_ID,
            range=f"'{tab}'!A1:D110"
        ).execute()
        values = result.get('values', [])
    except:
        return {}
    
    addresses = {}
    for row in values[3:]:
        if not row or not row[0].strip():
            continue
        name = row[0].strip()
        addr = row[1].strip() if len(row) > 1 else ""
        if name and addr and name not in ('Name', 'GARDEN'):
            addresses[name] = addr
    return addresses

def read_menu_sheet(sheet_id, service_date):
    """Read menu choices from menu sheet. Returns {name: {salad, soup, main, side}}.
    Menu tabs are named like '6/19 F' (month/day daycode)."""
    svc = get_services()
    sheets = svc['sheets']
    
    month = service_date.month
    day = service_date.day
    day_code, day_name = get_day_info(service_date)
    
    # Sunday menu tabs use "S" instead of "Su"
    menu_day_code = "S" if day_code == "Su" else day_code
    
    target_tab = f"{month}/{day} {menu_day_code}"
    print(f"  Looking for menu tab: '{target_tab}'")
    
    day_tab = target_tab
    
    result = sheets.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{day_tab}'!A1:Z200"
    ).execute()
    values = result.get('values', [])
    
    menus = {}
    # Try to find header row
    header_row = 0
    for i, row in enumerate(values):
        if row and any('name' in str(c).lower() or 'client' in str(c).lower() for c in row):
            header_row = i
            break
    
    # Parse based on common menu sheet format
    for row in values[header_row+1:]:
        if not row or not row[0]:
            continue
        name = str(row[0]).strip()
        if not name or name.lower() in ('name', 'client', 'total', ''):
            continue
        
        salad = str(row[1]).strip() if len(row) > 1 else ""
        soup  = str(row[2]).strip() if len(row) > 2 else ""
        main  = str(row[3]).strip() if len(row) > 3 else ""
        side  = str(row[4]).strip() if len(row) > 4 else ""
        
        if salad or soup or main or side:
            menus[name] = {'salad': salad, 'soup': soup, 'main': main, 'side': side}
    
    return menus

# ═══════════════════════════════════════════════════════════════════
# REPORT GENERATION
# ═══════════════════════════════════════════════════════════════════

def generate_report(service_date):
    """Generate a comprehensive text report from Drive data."""
    day_code, day_name = get_day_info(service_date)
    
    print(f"\n{'='*60}")
    print(f" GOJ Daily Lists — {day_name}, {service_date.strftime('%B %d, %Y')}")
    print(f" Source: Google Drive (live)")
    print(f"{'='*60}")
    
    # Read all data
    is_sunday = (day_code == "Su")
    s1 = read_sign_in_sheet(day_code, 1)
    if is_sunday:
        s2 = []  # Sunday combined tab — no separate S2
    else:
        s2 = read_sign_in_sheet(day_code, 2)
    s1_tr = read_sign_in_transport(day_code, 1)
    if is_sunday:
        s2_tr = {}
    else:
        s2_tr = read_sign_in_transport(day_code, 2)
    
    if is_sunday:
        print(f"\n📋 Sign-In Sheet (Combined Sunday):")
        print(f"  Total: {len(s1)} clients ({sum(1 for c in s1 if c['transport']=='TR')} TR)")
        print(f"  Transport addresses: {len(s1_tr)}")
    else:
        print(f"\n📋 Sign-In Sheet:")
        print(f"  Shift 1: {len(s1)} clients ({sum(1 for c in s1 if c['transport']=='TR')} TR)")
        print(f"  Shift 2: {len(s2)} clients ({sum(1 for c in s2 if c['transport']=='TR')} TR)")
        print(f"  Total:   {len(s1) + len(s2)} clients")
    
    # Plan breakdown
    plans = Counter()
    for c in s1 + s2:
        plan = c['plan'].strip()
        if plan:
            plans[plan] += 1
    print(f"\n📊 Insurance Plans:")
    for plan, count in plans.most_common():
        print(f"  {plan:15s}: {count}")
    
    # Transport breakdown
    tr_s1 = [c for c in s1 if c['transport'] == 'TR']
    ntr_s1 = [c for c in s1 if c['transport'] == 'N/TR']
    if is_sunday:
        tr_s2 = []
        ntr_s2 = []
    else:
        tr_s2 = [c for c in s2 if c['transport'] == 'TR']
        ntr_s2 = [c for c in s2 if c['transport'] == 'N/TR']
    
    print(f"\n🚌 Transport:")
    print(f"  S1 TR: {len(tr_s1)}, S1 N/TR: {len(ntr_s1)}")
    if not is_sunday:
        print(f"  S2 TR: {len(tr_s2)}, S2 N/TR: {len(ntr_s2)}")
    
    # Read menus
    s1_menus = {}
    s2_menus = {}
    try:
        s1_menus = read_menu_sheet(MENU_S1_ID, service_date)
    except Exception as e:
        print(f"\n🍽️  S1 Menus: ERROR — {e}")
    try:
        if not is_sunday:
            s2_menus = read_menu_sheet(MENU_S2_ID, service_date)
    except Exception as e:
        print(f"\n🍽️  S2 Menus: ERROR — {e}")
    print(f"\n🍽️  Menus: S1={len(s1_menus)} loaded, S2={len(s2_menus)} loaded")
    
    # Missing menus
    all_names = {c['name'] for c in s1 + s2}
    menu_names = set(s1_menus.keys()) | set(s2_menus.keys())
    no_menu = all_names - menu_names
    if no_menu:
        print(f"\n⚠️  No menu for {len(no_menu)} clients:")
        for n in sorted(no_menu):
            print(f"    - {n}")
    
    # Drivers
    print(f"\n🚐 Driver Routes (TR only):")
    print(f"  TR addresses: {len(s1_tr)}")
    if not is_sunday:
        print(f"  S2 TR addresses: {len(s2_tr)}")
    
    return {
        'date': service_date.isoformat(),
        'day': day_name,
        'code': day_code,
        's1': s1, 's2': s2,
        's1_tr': s1_tr, 's2_tr': s2_tr,
        's1_menus': s1_menus, 's2_menus': s2_menus,
        'total': len(s1) + len(s2),
    }

# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='GOJ Daily Lists from Google Drive')
    parser.add_argument('--date', type=str, help='Date (YYYY-MM-DD), default: tomorrow')
    parser.add_argument('--kitchen-only', action='store_true')
    parser.add_argument('--diff', type=str, help='Compare with another date (YYYY-MM-DD)')
    args = parser.parse_args()
    
    if args.date:
        service_date = date.fromisoformat(args.date)
    else:
        service_date = date.today() + timedelta(days=1)
    
    result = generate_report(service_date)
    
    # Compare with another date if requested
    if args.diff:
        print(f"\n\n{'='*60}")
        print(f" COMPARISON: {args.date} vs {args.diff}")
        print(f"{'='*60}")
        prev_date = date.fromisoformat(args.diff)
        prev = generate_report(prev_date)
        
        prev_names = {c['name'] for c in prev['s1'] + prev['s2']}
        curr_names = {c['name'] for c in result['s1'] + result['s2']}
        
        added = curr_names - prev_names
        removed = prev_names - curr_names
        
        print(f"\n➕ ADDED ({len(added)}):")
        for n in sorted(added):
            print(f"  + {n}")
        print(f"\n➖ REMOVED ({len(removed)}):")
        for n in sorted(removed):
            print(f"  - {n}")
