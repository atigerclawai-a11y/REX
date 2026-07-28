#!/usr/bin/env python3
"""
GOJ v1.2 — Daily Sheets Wrapper
Calls both generate_distribution_sheet.py and generate_kitchen_sheet.py.
Usage: python3 generate_daily_sheets.py [--date YYYY-MM-DD] [--db PATH] [--output-dir PATH]
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from generate_distribution_sheet import generate as gen_distribution, next_business_day
from generate_kitchen_sheet       import generate as gen_kitchen

DEFAULT_DB  = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
DEFAULT_OUT = Path.home() / "Documents" / "goj files" / "documents" / "print_sheets"


def run(service_date: date, db_path: Path, output_dir: Path) -> dict:
    # ── Drive-first: sync attendance + menus before generating anything ────
    from CC_drive_preflight import preflight
    print("🔍 Running Drive preflight to sync live data...")
    pf = preflight(service_date.isoformat())
    print(f"   Attendance: S1={pf['stats'].get('s1_attendance', '?')} S2={pf['stats'].get('s2_attendance', '?')}")
    print(f"   Menus: S1={pf['stats'].get('s1_menu', '?')} S2={pf['stats'].get('s2_menu', '?')}")
    if pf.get('no_menu'):
        print(f"   ⚠️  {len(pf['no_menu'])} clients missing menus")

    print(f"\n{'='*60}")
    print(f" GOJ Daily Sheet Generator — {service_date.strftime('%A, %B %d, %Y')}")
    print(f"{'='*60}\n")

    print("📋 Distribution Sheets:")
    dist_files, no_menu = gen_distribution(service_date, db_path, output_dir)

    print("\n🍳 Kitchen Prep Order:")
    kitchen_file, counts = gen_kitchen(service_date, db_path, output_dir)

    print(f"\n{'='*60}")
    print(f" ✅ Complete — {len(dist_files) + 1} files generated")
    if no_menu:
        print(f"\n ⚠️  CLIENTS WITH NO MENU ({len(no_menu)}):")
        for name in no_menu:
            print(f"    • {name}")
    else:
        print(" ✅ All clients have menus")
    print(f"{'='*60}\n")

    return {
        "service_date":    service_date,
        "distribution":    dist_files,
        "kitchen":         kitchen_file,
        "no_menu_clients": no_menu,
        "menu_counts":     counts,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate all GOJ daily print sheets")
    parser.add_argument("--date",       default=None)
    parser.add_argument("--db",         default=str(DEFAULT_DB))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    service_date = date.fromisoformat(args.date) if args.date else next_business_day(date.today())
    run(service_date, Path(args.db), Path(args.output_dir))
