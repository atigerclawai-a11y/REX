#!/bin/bash
# GOJ Daily Kitchen + Distribution Generator
# Runs at 10:30 AM — syncs Drive menus, generates all sheets
set -e

LOG="$HOME/Desktop/REX/logs/CC_daily_sheets_$(date +%Y%m%d_%H%M).log"
exec > >(tee -a "$LOG") 2>&1

echo "=== GOJ Daily Sheets — $(date) ==="

VENV="$HOME/.rex-venv/bin/python3"
REX="$HOME/Desktop/REX"
DB="$HOME/Documents/goj files/proprietary/goj_proprietary.db"
OUT="$HOME/Documents/goj files/output_docs"
TODAY=$(date +%Y-%m-%d)

mkdir -p "$REX/logs" "$OUT"

# ── Step 1: Sync Drive menus → goj_proprietary.db ──
echo "Step 1: Syncing Drive menus..."
$VENV -c "
import json, sqlite3, sys
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import date, timedelta

# Load token
tp = Path.home() / '.hermes' / 'profiles' / 'cloud' / 'google_token.json'
if not tp.exists():
    tp = Path.home() / '.rex_google_token.json'
if not tp.exists():
    print('ERROR: No Google token found')
    sys.exit(1)

data = json.loads(tp.read_text())
scopes = data.get('scopes', ['https://www.googleapis.com/auth/drive.readonly'])
creds = Credentials.from_authorized_user_file(str(tp), scopes)

sheets = build('sheets', 'v4', credentials=creds)

# Determine target date (tomorrow, since menus are made a day ahead)
target = date.today() + timedelta(days=1)
day_names = {0: 'M', 1: 'T', 2: 'W', 3: 'TH', 4: 'F', 5: 'SA'}
day_code = day_names[target.weekday()]
date_str = target.isoformat()
tab_label = f'{target.month}/{target.day} {day_code}'

print(f'Target: {date_str} ({tab_label})')

# Spreadsheet IDs
S1_ID = '1IfBJbKleeqA329FI3WeoFQp2xqmKYRJiy_I7RC2ZBcw'
S2_ID = '18rs4xZHmdjt78za9tsh1bse94q-9Vn-pKXcnjID3ER0'

def fetch_tab(sid, tab):
    try:
        result = sheets.spreadsheets().values().get(spreadsheetId=sid, range=f\"'{tab}'!A1:H500\").execute()
        return result.get('values', [])
    except Exception as e:
        print(f'  Error fetching {tab}: {e}')
        return []

all_menus = []
for shift_id, shift_num, label in [(S1_ID, '1', 'S1'), (S2_ID, '2', 'S2')]:
    rows = fetch_tab(shift_id, tab_label)
    if not rows:
        print(f'  WARNING: No data for {label} tab {tab_label}')
        continue
    count = 0
    for row in rows[4:]:  # skip header rows
        if not row or not row[0].strip():
            continue
        name = row[0].strip()
        if 'GARDEN' in name.upper() or 'Total' in name or 'menu for' in name.lower():
            continue
        salad = row[2].strip() if len(row) > 2 else ''
        soup = row[3].strip() if len(row) > 3 else ''
        main = row[4].strip() if len(row) > 4 else ''
        side = row[5].strip() if len(row) > 5 else ''
        all_menus.append((name, date_str, day_code, shift_num, salad, soup, main, side))
        count += 1
    print(f'  {label}: {count} clients')

if not all_menus:
    print('No menu data found — exiting')
    sys.exit(0)

# Insert into goj_proprietary.db
db = sqlite3.connect('$DB')
db.execute(\"DELETE FROM client_menus WHERE menu_date = ?\", (date_str,))
for name, md, dc, sh, sa, so, ma, si in all_menus:
    db.execute(\"\"\"
        INSERT INTO client_menus (client_name, menu_date, day_code, shift, salad, soup, main, side, source_sheet)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'cron_sync')
    \"\"\", (name, md, dc, sh, sa, so, ma, si))
db.commit()
db.close()
print(f'Synced {len(all_menus)} menus to goj_proprietary.db')
"

# ── Step 2: Generate kitchen sheets ──
echo ""
echo "Step 2: Kitchen sheets..."
for shift in 1 2; do
    $VENV "$REX/goj_kitchen_paired.py" --date "$TODAY" --shift "$shift" 2>&1 || echo "  WARNING: Kitchen shift $shift failed"
done

# ── Step 3: Generate distribution sheets ──
echo ""
echo "Step 3: Distribution sheets..."
for shift in 1 2; do
    $VENV "$REX/goj_distribution.py" --date "$TODAY" --shift "$shift" 2>&1 || echo "  WARNING: Distribution shift $shift failed"
done

echo ""
echo "=== Done — $(date) ==="
ls -la "$OUT"/Kitchen_* "$OUT"/Distribution_* 2>/dev/null | tail -8
