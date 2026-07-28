#!/usr/bin/env python3
"""CC_menu_intake.py — Scanned menu → goj_proprietary.db intake.

Parses MinerU OCR markdown from scanned client menu forms and writes
per-client per-day food selections into client_menus (REX DB), then syncs
to the Documents DB that the generators read.

RULES:
- Drive is source of truth. OCR rows NEVER overwrite existing rows for the
  same (client_name, menu_date, shift) — INSERT OR IGNORE only. OCR fills gaps.
- source_sheet = 'ocr_scan' so provenance is clear.
- Unmatched clients are reported, never silently dropped.

Usage:
  python3 CC_menu_intake.py                     # process all menu MDs in menu_ocr_full
  python3 CC_menu_intake.py <md> [<md>...]      # specific files
  python3 CC_menu_intake.py --dir <dir>         # all */ocr/*.md under dir
  python3 CC_menu_intake.py --dry-run           # report only, no DB writes
"""

import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

HOME = Path.home()
REX_DIR = HOME / "Desktop/REX"
sys.path.insert(0, str(REX_DIR))

from goj_menu_form_parser import (parse_menu_md, load_roster, fuzzy_roster,
                                  DAY_CODES, norm_text, week_from_filename)

REX_DB = REX_DIR / "goj_proprietary.db"
DST_DB = HOME / "Documents/goj files/proprietary/goj_proprietary.db"
AUTH_DB = HOME / "Documents/goj files/dashboard/auth_tracker.db"
OCR_ROOT = REX_DIR / "menu_ocr_full"
DAY_MAP = {"M": "day_M_actual", "T": "day_T_actual", "W": "day_W_actual",
           "TH": "day_TH_actual", "F": "day_F_actual", "Su": "day_Su_actual"}


def shift_lookup_factory():
    def lookup(client_name, day_code):
        col = DAY_MAP.get(day_code)
        if not col or not AUTH_DB.exists():
            return None
        try:
            conn = sqlite3.connect(str(AUTH_DB))
            row = conn.execute(
                f"SELECT {col} FROM clients WHERE name=? AND active=1",
                (client_name,)).fetchone()
            conn.close()
            if row and str(row[0]) in ("1", "2"):
                return str(row[0])
        except Exception:
            pass
        return None
    return lookup


def merge_client_days(dst, src_days):
    """Merge src day selections into dst (p1 + p2 of same client)."""
    for d, cats in src_days.items():
        for cat, item in cats.items():
            dst.setdefault(d, {})
            if dst[d].get(cat) in (None, "") and item:
                dst[d][cat] = item


def find_menu_mds(root):
    out = []
    for md in sorted(Path(root).glob("*/ocr/*.md")):
        try:
            head = md.read_text(encoding="utf-8", errors="replace")[:6000]
        except Exception:
            continue
        if "Имя" in head or "САЛАТЫ" in head or "САЛАТ" in head:
            out.append(md)
    return out


def main():
    args = [a for a in sys.argv[1:]]
    dry_run = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]

    if args and args[0] == "--dir":
        mds = find_menu_mds(args[1])
    elif args:
        mds = [Path(a) for a in args]
    else:
        mds = find_menu_mds(OCR_ROOT)

    if not mds:
        print("No menu OCR markdown found.")
        return 1

    roster, norm = load_roster()
    shift_lookup = shift_lookup_factory()
    print(f"Roster: {len(roster)} active clients | {len(mds)} menu docs")

    # merged[(matched_name, week_start)] = {"days": {...}, "shift": str|None, "srcs": set}
    merged = {}
    unmatched = {}
    per_doc = []

    for md in mds:
        doc = md.parent.parent.name
        parsed = parse_menu_md(md, roster, norm,
                               fallback_monday=week_from_filename(doc))
        ws = parsed["stats"]["week_start"]
        n_sel = 0
        for raw, info in parsed["clients"].items():
            name = info["matched"]
            if not name:
                unmatched.setdefault(doc, []).append(raw)
                continue
            key = (name, ws)
            if key not in merged:
                merged[key] = {"days": {}, "shift": info["shift"], "srcs": set()}
            merge_client_days(merged[key]["days"], info["days"])
            if not merged[key]["shift"] and info["shift"]:
                merged[key]["shift"] = info["shift"]
            merged[key]["srcs"].add(doc)
            n_sel += info["selections"]
        per_doc.append((doc, parsed["stats"]["clients"], parsed["stats"]["matched"], n_sel, ws))

    print(f"\n{'DOC':<46} {'CLI':>4} {'MATCH':>5} {'SEL':>5}  WEEK")
    for doc, nc, nm, ns, ws in per_doc:
        print(f"{doc:<46} {nc:>4} {nm:>5} {ns:>5}  {ws}")

    # Build DB rows
    rows = []
    for (name, ws), info in merged.items():
        if not ws:
            continue
        week_monday = date.fromisoformat(ws)
        for d, cats in info["days"].items():
            if not cats or d > 4:
                continue
            menu_date = week_monday + timedelta(days=d)
            day_code = DAY_CODES[d]
            shift = info["shift"] or shift_lookup(name, day_code) or "1"
            rows.append((name, str(menu_date), day_code, shift,
                         cats.get("salad"), cats.get("soup"),
                         cats.get("main"), cats.get("side"), "ocr_scan"))

    print(f"\nMerged: {len(merged)} client-weeks → {len(rows)} client-day rows")

    if dry_run:
        from collections import Counter
        by_date = Counter(r[1] for r in rows)
        for dt in sorted(by_date):
            print(f"  {dt}: {by_date[dt]} rows")
        if unmatched:
            print(f"\nUnmatched ({sum(len(v) for v in unmatched.values())}):")
            for doc, names in unmatched.items():
                for n in names:
                    print(f"  [{doc}] {n}")
        return 0

    # Write to REX DB — INSERT OR IGNORE (never clobber Drive data)
    conn = sqlite3.connect(str(REX_DB))
    before = conn.execute("SELECT COUNT(*) FROM client_menus WHERE source_sheet='ocr_scan'").fetchone()[0]
    written = 0
    for r in rows:
        cur = conn.execute(
            "INSERT OR IGNORE INTO client_menus "
            "(client_name, menu_date, day_code, shift, salad, soup, main, side, source_sheet) "
            "VALUES (?,?,?,?,?,?,?,?,?)", r)
        written += cur.rowcount
    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM client_menus WHERE source_sheet='ocr_scan'").fetchone()[0]
    conn.close()
    print(f"DB: {written} new rows written (ocr_scan total {before} → {after})")

    # Sync to Documents DB (same INSERT OR IGNORE semantics, per-date)
    if DST_DB.exists():
        src = sqlite3.connect(str(REX_DB))
        dst = sqlite3.connect(str(DST_DB))
        dates = [r[0] for r in src.execute(
            "SELECT DISTINCT menu_date FROM client_menus WHERE source_sheet='ocr_scan'").fetchall()]
        synced = 0
        for dt in dates:
            orows = src.execute(
                "SELECT client_name, menu_date, day_code, shift, salad, soup, main, side, source_sheet "
                "FROM client_menus WHERE menu_date=? AND source_sheet='ocr_scan'", (dt,)).fetchall()
            for orow in orows:
                cur = dst.execute(
                    "INSERT OR IGNORE INTO client_menus "
                    "(client_name, menu_date, day_code, shift, salad, soup, main, side, source_sheet) "
                    "VALUES (?,?,?,?,?,?,?,?,?)", orow)
                synced += cur.rowcount
        dst.commit()
        dst.close()
        src.close()
        print(f"Documents DB: {synced} new rows synced")

    if unmatched:
        print(f"\n⚠ Unmatched names ({sum(len(v) for v in unmatched.values())}) — review needed:")
        for doc, names in list(unmatched.items())[:5]:
            for n in names:
                print(f"  [{doc}] {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
