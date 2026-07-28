#!/usr/bin/env python3
"""CC_payroll.py — GHS Payroll Bridge. Generates ADP/Gusto CSV from attendance data."""
import argparse, csv, sqlite3, sys
from datetime import date, timedelta
from pathlib import Path

DEFAULT_RATES = {
    "admin": 35.00, "nursing": 28.00, "kitchen": 22.00,
    "front_desk": 25.00, "driver": 20.00, "other": 20.00,
}
DEFAULT_RATE = 25.00
DEFAULT_HOURS_PER_DAY = 8.0

PREFERRED_DB_PATHS = [
    "~/Documents/goj files/dashboard/auth_tracker.db",
    "~/goj_corpus/goj files/dashboard/auth_tracker.db",
]


def find_db():
    for p in map(lambda x: Path(x).expanduser(), PREFERRED_DB_PATHS):
        if p.exists():
            try:
                cur = sqlite3.connect(str(p)).cursor()
                cur.execute("SELECT 1 FROM employees LIMIT 1")
                cur.connection.close()
                return p
            except Exception:
                continue
    for p in sorted(Path.home().rglob("auth_tracker.db"),
                    key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            cur = sqlite3.connect(str(p)).cursor()
            cur.execute("SELECT 1 FROM employees LIMIT 1")
            cur.connection.close()
            return p
        except Exception:
            continue
    return None


def load_employees(db_path):
    rows = []
    try:
        cur = sqlite3.connect(str(db_path)).cursor()
        cur.execute("SELECT full_name, role FROM employees WHERE status='active'")
        for name, role in cur.fetchall():
            name = (name or "").strip()
            if name:
                rows.append({"name": name, "role": role or "other"})
        cur.connection.close()
    except Exception as e:
        print(f"Warning: DB read failed ({e})", file=sys.stderr)
    return rows


def load_rates_config(path="~/Desktop/REX/payroll_rates.csv"):
    overrides = {}
    p = Path(path).expanduser()
    if p.exists():
        with open(p, newline="") as f:
            for row in csv.DictReader(f):
                name = row.get("name", "").strip()
                if name:
                    overrides[name] = {
                        "rate": float(row.get("rate", 0) or 0),
                        "hours_per_day": float(row.get("hours_per_day", 0) or 0),
                    }
    return overrides


def biweekly_period(today=None):
    """Return (start, end) of current bi-weekly pay period (epoch: Mon 2026-01-05)."""
    if today is None:
        today = date.today()
    epoch = date(2026, 1, 5)
    period_index = (today - epoch).days // 14
    start = epoch + timedelta(days=period_index * 14)
    return start, start + timedelta(days=13)


def count_weekdays(start, end):
    return sum(1 for i in range((end - start).days + 1)
               if (start + timedelta(days=i)).weekday() < 5)


def main():
    ap = argparse.ArgumentParser(description="GHS Payroll Bridge")
    ap.add_argument("--period", nargs=2, metavar=("START", "END"),
                    help="Pay period start and end (YYYY-MM-DD)")
    ap.add_argument("--format", choices=["adp", "gusto"], default="adp")
    ap.add_argument("--output", "-o", help="Output file path (default: stdout)")
    args = ap.parse_args()

    start, end = (date.fromisoformat(args.period[0]), date.fromisoformat(args.period[1])) \
        if args.period else biweekly_period()
    wd = count_weekdays(start, end)

    db = find_db()
    if not db:
        print("ERROR: No accessible auth_tracker.db found.", file=sys.stderr)
        sys.exit(1)

    employees = load_employees(db)
    if not employees:
        print("ERROR: No active employees found.", file=sys.stderr)
        sys.exit(1)

    overrides = load_rates_config()
    outfile = open(args.output, "w", newline="") if args.output else sys.stdout

    cols_adp = ["employee_name", "hours_worked", "pay_period_start",
                "pay_period_end", "rate", "total_pay"]
    cols_gusto = ["employee_name", "regular_hours", "overtime_hours", "pay_date"]
    cols = cols_gusto if args.format == "gusto" else cols_adp
    writer = csv.DictWriter(outfile, fieldnames=cols)
    writer.writeheader()

    for emp in sorted(employees, key=lambda x: x["name"]):
        o = overrides.get(emp["name"], {})
        rate = o.get("rate") or DEFAULT_RATES.get(emp["role"], DEFAULT_RATE)
        hpd = o.get("hours_per_day") or DEFAULT_HOURS_PER_DAY
        total = wd * hpd
        regular = total if emp.get("overtime_approved") else min(total, 80.0)
        ot = max(total - 80.0, 0.0) if not emp.get("overtime_approved") else 0.0

        if args.format == "gusto":
            pay_date = end
            if pay_date.weekday() >= 5:
                pay_date -= timedelta(days=pay_date.weekday() - 4)
            row = {
                "employee_name": emp["name"],
                "regular_hours": f"{regular:.2f}",
                "overtime_hours": f"{ot:.2f}",
                "pay_date": pay_date.isoformat(),
            }
        else:
            total_pay = (regular * rate) + (ot * rate * 1.5)
            row = {
                "employee_name": emp["name"],
                "hours_worked": f"{regular + ot:.2f}",
                "pay_period_start": start.isoformat(),
                "pay_period_end": end.isoformat(),
                "rate": f"{rate:.2f}",
                "total_pay": f"{total_pay:.2f}",
            }
        writer.writerow(row)

    if outfile is not sys.stdout:
        outfile.close()
        print(f"Wrote {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
