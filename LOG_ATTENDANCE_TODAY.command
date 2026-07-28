#!/bin/bash
# ====================================================================
#  GOJ Attendance Logger — Sign-In Sheet → Database
#  Parses today's generated sign-in PDFs and logs all scheduled
#  clients to attendance_log in auth_tracker.db
#
#  Double-click to run. Safe to run multiple times (skips duplicates).
# ====================================================================

set -uo pipefail

REX="$HOME/Desktop/REX"
DB="$HOME/Documents/goj files/dashboard/auth_tracker.db"
LOG_DIR="$REX/logs"
TS=$(date +%Y%m%d_%H%M%S)
LOG="$LOG_DIR/attendance_${TS}.log"
mkdir -p "$LOG_DIR"
exec > >(tee "$LOG") 2>&1

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  GOJ Attendance Logger — $(date +%Y-%m-%d\ %H:%M)           ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# Python detection
PY=""
for C in "$HOME/debate-chamber/.venv/bin/python3" "$REX/.venv/bin/python3" "$(command -v python3 2>/dev/null)"; do
    [ -f "$C" ] && PY="$C" && break
done
[ -z "$PY" ] && echo "❌ No Python found." && read -n 1 && exit 1

"$PY" - <<PYEOF
import pdfplumber, re, sqlite3, json
from pathlib import Path
from datetime import datetime, date as dt_date

REX  = Path("$REX")
DB   = Path("$DB")

def parse_signin_sheet(path):
    clients = []
    date_str = None
    shift = None
    with pdfplumber.open(str(path)) as pdf:
        for pg in pdf.pages:
            text = pg.extract_text() or ''
            for line in text.split('\n'):
                m = re.search(r'Date:\s*(.+?)\s+Shift:\s*(\d+)', line)
                if m and not date_str:
                    date_str = m.group(1).strip()
                    shift = m.group(2).strip()
                m2 = re.match(
                    r'^(\d+)\s+(.+?)\s+(False|True|Medicaid|Medicare)\s+(Y|N)\s+(Y|N|CDPAP)\s*(.*)$',
                    line
                )
                if m2:
                    clients.append({
                        'name': m2.group(2).strip(),
                        'ch': m2.group(4),
                        'tr': m2.group(5),
                    })
    return date_str, shift, clients

# Find today's sign-in sheets
today = dt_date.today().isoformat()
dow_map = {'Mon':'M','Tue':'T','Wed':'W','Thu':'TH','Fri':'F','Sat':'SA','Sun':'SU'}
dow_key = dow_map.get(datetime.now().strftime('%a'), 'M')

SCAN_DIR = REX / "Scanned docs"
SCAN_DIR.mkdir(exist_ok=True)
sheets = sorted(SCAN_DIR.glob("GOJ_M_S*_*_signin.pdf"))
if not sheets:
    # Fallback: also check REX root for backwards compatibility
    sheets = sorted(REX.glob("GOJ_M_S*_*_signin.pdf"))
if not sheets:
    print(f"⚠️  No sign-in PDFs found in {SCAN_DIR}")
    exit(0)

print(f"Found {len(sheets)} sign-in sheet(s)")

# Ensure attendance_log table
if not DB.exists():
    print(f"⚠️  Database not found: {DB}")
    print("   Creating it with attendance_log table...")
    DB.parent.mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(str(DB))
cur  = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS attendance_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        log_date TEXT NOT NULL,
        day_key TEXT,
        shift INTEGER,
        client_name TEXT NOT NULL,
        status TEXT DEFAULT 'scheduled',
        source TEXT,
        note TEXT,
        logged_at TEXT,
        UNIQUE(log_date, shift, client_name)
    )
""")
conn.commit()

total_new = 0
total_skip = 0

for sheet in sheets:
    date_str, shift, clients = parse_signin_sheet(sheet)

    try:
        log_date = datetime.strptime(date_str, '%A, %B %d, %Y').date().isoformat()
    except:
        log_date = today

    print(f"\n  {sheet.name}: {len(clients)} clients  date={log_date}  shift={shift}")

    new_count = 0
    skip_count = 0
    for c in clients:
        try:
            cur.execute("""
                INSERT OR IGNORE INTO attendance_log
                (log_date, day_key, shift, client_name, status, source, note, logged_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                log_date, dow_key, int(shift), c['name'],
                'scheduled', 'generated_signin_sheet',
                f"CH={c['ch']} TR={c['tr']}",
                datetime.now().isoformat()
            ))
            if cur.rowcount > 0:
                new_count += 1
            else:
                skip_count += 1
        except Exception as e:
            print(f"    DB error for {c['name']}: {e}")

    conn.commit()
    print(f"    ✅  New: {new_count}  Already logged: {skip_count}")
    total_new   += new_count
    total_skip  += skip_count

conn.close()

print(f"""
╔══════════════════════════════════════════════════════╗
║  Summary                                            ║
╚══════════════════════════════════════════════════════╝
  New entries logged:    {total_new}
  Already existed:       {total_skip}
  Database:              {DB}
""")
PYEOF

echo ""
read -n 1 -p "Press any key to close..."
