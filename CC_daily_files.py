#!/usr/bin/env python3
"""CC_daily_files.py — Generate all daily working files for GOJ employees.

One command → kitchen sheets (S1+S2), distribution sheets (S1+S2), sign-in
sheets (S1+S2). Data comes from goj_proprietary.db, which is fed by:
  1. Drive sync (CC_drive_preflight.py) — source of truth
  2. OCR scan intake (CC_menu_intake.py) — fills gaps from scanned menu forms
  3. last_order_fallback — previous week carry-forward

Usage:
  python3 CC_daily_files.py 2026-07-27            # all 6 PDFs for date
  python3 CC_daily_files.py 2026-07-27 --no-signin
  python3 CC_daily_files.py tomorrow
"""

import subprocess
import sys
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

HOME = Path.home()
REX = HOME / "Desktop/REX"
PROP_DB = HOME / "Documents/goj files/proprietary/goj_proprietary.db"
OUT_DOCS = HOME / "Documents/goj files/output_docs"
PRINT_SHEETS = HOME / "Documents/goj files/documents/print_sheets"
VENV_PY = REX / ".venv/bin/python3"
REX_VENV_PY = HOME / ".rex-venv/bin/python3"
DASHBOARD = HOME / "Documents/goj files/dashboard"
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def run(cmd, label, timeout=300):
    print(f"  [{label}] {' '.join(str(c) for c in cmd)}")
    try:
        r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True,
                           timeout=timeout, cwd=str(REX))
        tail = (r.stdout or "").strip().splitlines()[-3:]
        for line in tail:
            print(f"    {line}")
        if r.returncode != 0:
            err = (r.stderr or "").strip().splitlines()[-2:]
            for line in err:
                print(f"    ERR: {line}")
            return False
        return True
    except subprocess.TimeoutExpired:
        print(f"    ERR: timeout after {timeout}s")
        return False


def db_counts(dt):
    if not PROP_DB.exists():
        return {}
    conn = sqlite3.connect(str(PROP_DB))
    rows = conn.execute(
        "SELECT shift, source_sheet, COUNT(*) FROM client_menus "
        "WHERE menu_date=? GROUP BY shift, source_sheet", (dt,)).fetchall()
    conn.close()
    out = {}
    for shift, src, n in rows:
        out.setdefault(shift, {})[src] = n
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    arg = sys.argv[1]
    if arg == "tomorrow":
        dt = date.today() + timedelta(days=1)
    else:
        dt = date.fromisoformat(arg)
    ds = str(dt)
    day_name = DAY_NAMES[dt.weekday()]
    do_signin = "--no-signin" not in sys.argv

    print(f"═══ GOJ Daily Working Files — {day_name} {ds} ═══")

    counts = db_counts(ds)
    for shift in sorted(counts):
        srcs = ", ".join(f"{s}={n}" for s, n in sorted(counts[shift].items()))
        print(f"  Menu data S{shift}: {sum(counts[shift].values())} rows ({srcs})")
    if not counts:
        print("  ⚠ No menu data in DB for this date — generators will use fallbacks")

    results = {}

    # Kitchen S1 + S2 (parallel via background procs would be nicer; sequential is safer on RAM)
    # Weekends are single-shift days (Sat/Sun = shift 1 only, no shift-2 menu data exists) —
    # running S2 on a weekend makes the pipeline fail falsely.
    shifts = (1, 2) if dt.weekday() < 5 else (1,)
    for shift in shifts:
        ok = run([VENV_PY, "goj_kitchen_paired.py", "--date", ds,
                  "--shift", str(shift), "--skip-preflight"], f"kitchen S{shift}")
        results[f"kitchen_S{shift}"] = ok

    # Distribution (both shifts in one call)
    results["distribution"] = run(
        [REX_VENV_PY, "generate_distribution_sheet.py", "--date", ds], "distribution")

    # Sign-in sheets
    if do_signin:
        results["signin"] = run(
            [REX_VENV_PY, str(DASHBOARD / "generate_tomorrow.py"),
             "--day", day_name, "--mode", "signin"],
            "signin", timeout=600)

    # Verify outputs
    print("\n── Output verification ──")
    found = []
    mon = dt.strftime("%b%d")
    pats = [f"Kitchen_*{mon}*", f"*{ds}*", f"signin*{day_name}*"]
    for d, pat in ((OUT_DOCS, pats), (PRINT_SHEETS, pats)):
        if d.exists():
            for p in pat:
                found.extend(d.glob(p))
    seen = set()
    for f in sorted(found):
        if f in seen:
            continue
        seen.add(f)
        age = (datetime.now().timestamp() - f.stat().st_mtime) / 60
        fresh = "✅ FRESH" if age < 30 else f"⚠ {int(age)}min old"
        print(f"  {fresh}  {f.name} ({f.stat().st_size//1024}KB)")

    ok_n = sum(1 for v in results.values() if v)
    print(f"\n═══ {ok_n}/{len(results)} generators succeeded ═══")
    return 0 if ok_n == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
