#!/bin/bash
# ====================================================================
#  GOJ Calendar 2026 Importer
#  Reads "Copy of Calendar 2026.xlsx" from the Desktop and imports:
#    1. client_schedule  — weekly schedule (day + shift) per client
#    2. attendance_log   — historical Y-attendance for Jan–Apr 2026
#
#  Uses INSERT OR IGNORE — safe to run multiple times.
#  Double-click to run. Requires the xlsx in ~/Desktop/REX/
# ====================================================================

set -uo pipefail

REX="$HOME/Desktop/REX"
DB="$HOME/Documents/goj files/dashboard/auth_tracker.db"
XLSX="$REX/Copy of Calendar 2026.xlsx"
LOG_DIR="$REX/logs"
TS=$(date +%Y%m%d_%H%M%S)
LOG="$LOG_DIR/calendar_import_${TS}.log"
mkdir -p "$LOG_DIR"
exec > >(tee "$LOG") 2>&1

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  GOJ Calendar 2026 Importer                         ║"
echo "║  $(date +%Y-%m-%d\ %H:%M)                                ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Python detection ──────────────────────────────────────────────────────────
PY=""
for C in "$HOME/debate-chamber/.venv/bin/python3" "$REX/.venv/bin/python3" "$(command -v python3 2>/dev/null)"; do
    [ -f "$C" ] && PY="$C" && break
done
[ -z "$PY" ] && echo "❌ No Python found." && read -n 1 && exit 1

# ── Dep check ─────────────────────────────────────────────────────────────────
"$PY" -c "import openpyxl" 2>/dev/null || {
    echo "❌ openpyxl not installed. Run: pip3 install openpyxl"
    read -n 1; exit 1
}
echo "✅  openpyxl OK"

# ── File check ────────────────────────────────────────────────────────────────
if [ ! -f "$XLSX" ]; then
    echo "❌ xlsx not found at: $XLSX"
    echo "   Please copy 'Copy of Calendar 2026.xlsx' into ~/Desktop/REX/"
    read -n 1; exit 1
fi
echo "✅  xlsx found"
echo ""

"$PY" - <<PYEOF
import openpyxl, sqlite3, calendar
from pathlib import Path
from datetime import date, datetime

XLSX = Path("$XLSX")
DB   = Path("$DB")

# ── DOW mappings ──────────────────────────────────────────────────────────────
# Schedule columns (0-indexed): col3=M, col4=T, col5=W, col6=TH, col7=F, col8=Su
SCHED_COLS = {3: 'M', 4: 'T', 5: 'W', 6: 'TH', 7: 'F', 8: 'SU'}

# DOW labels in the date header row → day_key
DOW_LABEL_MAP = {
    'M': 'M', 'T': 'T', 'W': 'W',
    'Th': 'TH', 'TH': 'TH',
    'F': 'F',
    'Sa': 'SA', 'SA': 'SA',
    'Su': 'SU', 'SU': 'SU',
}

# Month sheets to import: (sheet_name, year, month)
MONTH_SHEETS = [
    ('Jan', 2026, 1),
    ('Feb', 2026, 2),
    ('Mar', 2026, 3),
    ('Apr', 2026, 4),
]

# ── Database setup ────────────────────────────────────────────────────────────
if not DB.exists():
    print(f"⚠️  Database not found at {DB}")
    print("   Creating it...")
    DB.parent.mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(str(DB))
cur  = conn.cursor()

# attendance_log (already exists from sign-in logger; recreate if missing)
cur.execute("""
    CREATE TABLE IF NOT EXISTS attendance_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        log_date    TEXT NOT NULL,
        day_key     TEXT,
        shift       INTEGER,
        client_name TEXT NOT NULL,
        status      TEXT DEFAULT 'scheduled',
        source      TEXT,
        note        TEXT,
        logged_at   TEXT,
        UNIQUE(log_date, shift, client_name)
    )
""")

# client_schedule — weekly schedule per client
cur.execute("""
    CREATE TABLE IF NOT EXISTS client_schedule (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        client_name TEXT NOT NULL,
        plan        TEXT,
        day_of_week TEXT NOT NULL,
        shift       INTEGER,
        updated_at  TEXT,
        UNIQUE(client_name, day_of_week)
    )
""")
conn.commit()

# ── Parse & import ────────────────────────────────────────────────────────────
wb = openpyxl.load_workbook(str(XLSX), read_only=True, data_only=True)

total_sched  = 0
total_attend = 0
total_skip   = 0
now_iso      = datetime.now().isoformat()

for sheet_name, year, month in MONTH_SHEETS:
    if sheet_name not in wb.sheetnames:
        print(f"  ⚠️  Sheet '{sheet_name}' not found — skipping")
        continue

    ws    = wb[sheet_name]
    rows  = list(ws.iter_rows(values_only=True))
    header0 = rows[0]   # day numbers (1..N starting at col9)
    header1 = rows[1]   # DOW labels  (W, Th, F… starting at col9)

    days_in_month = calendar.monthrange(year, month)[1]

    # Build col_idx → (date_obj, day_key) for attendance columns
    date_cols = {}
    for col_idx in range(9, 9 + days_in_month):
        day_num = col_idx - 8          # col9=day1, col10=day2…
        if day_num < 1 or day_num > days_in_month:
            continue
        if col_idx >= len(header1):
            continue
        dow_label = header1[col_idx]
        day_key   = DOW_LABEL_MAP.get(str(dow_label), None) if dow_label else None
        try:
            d = date(year, month, day_num)
        except ValueError:
            continue
        date_cols[col_idx] = (d, day_key)

    sheet_sched  = 0
    sheet_attend = 0
    sheet_skip   = 0

    for row in rows[2:]:
        if not row[1]:
            continue
        name = str(row[1]).strip()
        if not name or name.upper() == 'NAME':
            continue
        plan = str(row[2]).strip() if row[2] else None

        # Build schedule: day_of_week → shift
        client_sched = {}
        for col_idx, day_key in SCHED_COLS.items():
            val = row[col_idx] if col_idx < len(row) else None
            if val and str(val).strip() not in ('', 'None'):
                try:
                    shift_num = int(float(str(val).strip()))
                    client_sched[day_key] = shift_num
                except ValueError:
                    pass

        # Upsert schedule rows
        for day_key, shift_num in client_sched.items():
            cur.execute("""
                INSERT INTO client_schedule (client_name, plan, day_of_week, shift, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(client_name, day_of_week)
                DO UPDATE SET plan=excluded.plan, shift=excluded.shift, updated_at=excluded.updated_at
            """, (name, plan, day_key, shift_num, now_iso))
            sheet_sched += 1

        # Import Y-attendance
        for col_idx, (d, day_key) in date_cols.items():
            if col_idx >= len(row):
                continue
            val = row[col_idx]
            if val != 'Y':
                continue

            # Determine shift from schedule for this DOW
            shift_num = client_sched.get(day_key)

            try:
                cur.execute("""
                    INSERT OR IGNORE INTO attendance_log
                    (log_date, day_key, shift, client_name, status, source, logged_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (d.isoformat(), day_key, shift_num, name,
                      'attended', 'calendar_2026_xlsx', now_iso))
                if cur.rowcount > 0:
                    sheet_attend += 1
                else:
                    sheet_skip += 1
            except Exception as e:
                print(f"    DB err {name} {d}: {e}")

    conn.commit()
    print(f"  {sheet_name:4s}  schedule rows: {sheet_sched:5d}  attendance: {sheet_attend:5d}  skipped: {sheet_skip}")
    total_sched  += sheet_sched
    total_attend += sheet_attend
    total_skip   += sheet_skip

conn.close()

print(f"""
╔══════════════════════════════════════════════════════╗
║  Import Complete                                    ║
╚══════════════════════════════════════════════════════╝
  Schedule entries upserted:  {total_sched}
  Attendance rows inserted:   {total_attend}
  Already existed (skipped):  {total_skip}
  Database:  {DB}
""")
PYEOF

echo ""
read -n 1 -p "Press any key to close..."
