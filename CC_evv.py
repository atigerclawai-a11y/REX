#!/usr/bin/env python3
"""CC_evv.py — EVV (Electronic Visit Verification) system.
Generates daily EVV records CSV per shift (Shift 1: 8am-2pm, Shift 2: 2pm-8pm).
Reads signin.csv for actual timestamps; falls back to scheduled times.
Writes ~/Desktop/REX/output/evv_{date}_shift1.csv and shift2.csv.
"""

import argparse, csv, os, sqlite3, sys
from datetime import date, datetime
from pathlib import Path

HOME = Path.home()
DB_CANDIDATES = [
    HOME / "Documents/goj files/dashboard/auth_tracker.db",
    HOME / "goj_corpus/goj files/dashboard/auth_tracker.db",
    HOME / "Desktop/REX/auth_tracker.db",
]
SIGNIN_CSV = HOME / "goj/data/signin.csv"
OUTPUT_DIR = HOME / "Desktop/REX/output"

DAY_COL = {0: "day_M_actual", 1: "day_T_actual", 2: "day_W_actual",
            3: "day_TH_actual", 4: "day_F_actual", 5: "day_Su_actual",
            6: "day_Su_actual"}  # Sunday = day 6

SHIFT_TIMES = {1: ("08:00", "14:00"), 2: ("14:00", "20:00")}

FIELDS = ["Client Name", "Service Date", "Shift", "Check In", "Check Out",
          "Authorization Number", "Payer", "Auth Status", "Source"]


def find_db():
    for p in DB_CANDIDATES:
        if p.exists():
            try:
                conn = sqlite3.connect(str(p))
                conn.execute("SELECT 1 FROM clients LIMIT 1").fetchone()
                return conn
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
    return None


def load_signin_data(target_date):
    """Parse signin.csv (name,date,time_in,time_out,shift) for target_date."""
    records = {}
    if not SIGNIN_CSV.exists():
        return records
    try:
        with open(SIGNIN_CSV, newline="", encoding="utf-8-sig") as f:
            for row in csv.reader(f):
                if len(row) >= 5:
                    name, d, tin, tout, s = (row[i].strip() for i in range(5))
                    if d == target_date:
                        records[name] = (tin, tout, s)
    except Exception:
        pass
    return records


def main():
    parser = argparse.ArgumentParser(description="Generate EVV records CSV")
    parser.add_argument("--date", default=date.today().isoformat(),
                        help="Date in YYYY-MM-DD format (default: today)")
    args = parser.parse_args()

    target_date = args.date
    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        print(f"ERROR: Invalid date format '{target_date}'. Use YYYY-MM-DD.", file=sys.stderr)
        sys.exit(1)

    conn = find_db()
    if conn is None:
        print("ERROR: No accessible auth_tracker.db found.", file=sys.stderr)
        sys.exit(1)

    signin = load_signin_data(target_date)
    day_col = DAY_COL[dt.weekday()]

    query = f"""
        SELECT c.name, c.shift, c.{day_col},
               COALESCE(a.authorization_number, '') AS auth_num,
               COALESCE(a.status, '') AS auth_status,
               COALESCE(a.payer_canonical, a.payer_raw, '') AS payer
        FROM clients c
        LEFT JOIN authorization a ON a.client_name = c.name AND a.status = 'ACTIVE'
        WHERE c.active = 1 AND c.shift IN (1, 2)
        ORDER BY c.shift, c.name
    """

    rows = conn.execute(query).fetchall()
    conn.close()

    if not rows:
        print(f"No active clients found for {target_date}")
        return

    shift_records = {1: [], 2: []}

    for name, shift, scheduled, auth_num, auth_status, payer in rows:
        if not scheduled:
            continue

        rec = {
            "Client Name": name,
            "Service Date": target_date,
            "Shift": f"Shift {shift}",
            "Authorization Number": auth_num,
            "Payer": payer,
            "Auth Status": auth_status,
        }

        if name in signin:
            tin, tout, _ = signin[name]
            rec["Check In"] = tin
            rec["Check Out"] = tout
            rec["Source"] = "Actual"
        else:
            tin, tout = SHIFT_TIMES[shift]
            rec["Check In"] = tin
            rec["Check Out"] = tout
            rec["Source"] = "Scheduled"

        shift_records[shift].append(rec)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for shift in (1, 2):
        records = shift_records[shift]
        path = OUTPUT_DIR / f"evv_{target_date}_shift{shift}.csv"
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(records)
        print(f"Wrote {len(records)} records → {path}")


if __name__ == "__main__":
    main()
