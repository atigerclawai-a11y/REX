#!/usr/bin/env python3
"""GOJ Continuity Loop — daily learning handoff (Kato 2026-08-03).

Two commands:
  goj close  — end of day: measure learning delta, bucket it, write days/YYYY-MM-DD.md,
               append LEARNED.md, rewrite CARRY.md (max 7 items), append DEAD.md.
  goj open   — start of day: load CARRY + DEAD + last 3 day files, re-verify gates,
               print the morning brief, ask the one question.

Files (in ~/Desktop/REX/continuity/):
  LEARNED.md  append-only permanent record (never rewritten)
  CARRY.md    overwritten nightly, max 7 items, the handoff
  DEAD.md     append-only paths proven not to work, with reasons
  days/YYYY-MM-DD.md  that day's close report (append-only)

Rule that keeps this honest: learning counts as carried only if it's encoded
somewhere durable. A ruling in a chat transcript is gone at midnight.
"""
import argparse, json, sqlite3, subprocess, sys
from datetime import date, datetime
from pathlib import Path

REX = Path.home() / "Desktop" / "REX"
CONT = REX / "continuity"
DAYS = CONT / "days"
LEARNED = CONT / "LEARNED.md"
CARRY = CONT / "CARRY.md"
DEAD = CONT / "DEAD.md"

DOCS_PROP = Path.home() / "Documents" / "goj files" / "proprietary" / "goj_proprietary.db"
REX_PROP = REX / "goj_proprietary.db"

MAX_CARRY = 7
MAX_CARRY_LINES = 3  # CARRY items bounded: 7 items, 3 lines each

# ── helpers ────────────────────────────────────────────────────────────────
def q(db, sql, *args):
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        cur = con.execute(sql, args)
        return cur.fetchone()[0] if cur.description else None
    except Exception as e:
        return f"ERR:{e}"

def today():
    return date.today().isoformat()

def ensure_dirs():
    DAYS.mkdir(parents=True, exist_ok=True)
    for f in (LEARNED, CARRY, DEAD):
        if not f.exists():
            f.write_text(f"# {f.stem}\n\n", encoding="utf-8")

def db_parity_report():
    """Both DBs, row counts per day, must match — scoped to the ACTIVE food week
    (Monday of current week forward). Historical rows (pre-pipeline era) live in
    different states across copies and are NOT clobber evidence. Returns (ok, lines)."""
    lines = []
    # active food week Monday
    import datetime as _dt
    today_d = _dt.date.today()
    week_monday = (today_d - _dt.timedelta(days=today_d.weekday())).isoformat()
    try:
        a = sqlite3.connect(f"file:{DOCS_PROP}?mode=ro", uri=True)
        r = sqlite3.connect(f"file:{REX_PROP}?mode=ro", uri=True)
        pa = a.execute("SELECT menu_date, source_sheet, COUNT(*) FROM client_menus WHERE menu_date >= ? GROUP BY 1,2", (week_monday,)).fetchall()
        pr = r.execute("SELECT menu_date, source_sheet, COUNT(*) FROM client_menus WHERE menu_date >= ? GROUP BY 1,2", (week_monday,)).fetchall()
        a.close(); r.close()
        d = {}
        for dt, ss, n in pa: d[(dt, ss)] = n
        mism = []
        for dt, ss, n in pr:
            if d.get((dt, ss)) != n:
                mism.append(f"  {dt} {ss}: Documents={d.get((dt,ss))} REX={n}")
        for k, n in d.items():
            if k not in {(x[0], x[1]) for x in pr}:
                mism.append(f"  {k[0]} {k[1]}: Documents={n} REX=MISSING")
        if mism:
            return False, [f"⚠️ DB PARITY BROKEN (active week ≥ {week_monday}) — sync clobber may have bitten:"] + mism[:10]
        return True, [f"✅ DB parity OK for active week ≥ {week_monday}: Documents == REX"]
    except Exception as e:
        return False, [f"⚠️ Parity check failed: {e}"]

# ── goj close ─────────────────────────────────────────────────────────────
def cmd_close(args):
    ensure_dirs()
    d = today()
    print(f"═══ GOJ CLOSE — {d} ═══\n")

    # 1. Measure the day's learning delta — counts only
    print("[1] LEARNING DELTA (counts)")
    delta = {}
    delta["name_alias_today"] = q(DOCS_PROP,
        "SELECT COUNT(*) FROM name_alias WHERE date(created_at) = date('now')") or 0
    delta["corrections_today"] = q(DOCS_PROP,
        "SELECT COUNT(*) FROM menu_corrections WHERE date(created_at) = date('now')") or 0
    delta["review_open"] = q(DOCS_PROP, "SELECT COUNT(*) FROM menu_review_queue") or 0
    delta["quarantine"] = q(DOCS_PROP, "SELECT COUNT(*) FROM menu_quarantine") or 0
    print(f"  name_alias encoded today : {delta['name_alias_today']}")
    print(f"  menu_corrections today   : {delta['corrections_today']}")
    print(f"  review queue still open  : {delta['review_open']}")
    print(f"  quarantine count         : {delta['quarantine']}")
    cov = q(DOCS_PROP, "SELECT menu_date, source_sheet, COUNT(*) FROM client_menus WHERE menu_date >= date('now','-3 day') GROUP BY 1,2")
    print(f"  coverage (3 days): {cov if isinstance(cov, (int, str)) else 'see report'}")

    # 2. State check (lightweight gate — pre_generation_gate.py is per-generation;
    #    the loop's job is parity + quarantine health)
    print("\n[2] STATE CHECK")
    ok, lines = db_parity_report()
    for l in lines: print(" ", l)

    # 3. The four buckets — from the operator (interactive or via --buckets file)
    print("\n[3] FOUR BUCKETS")
    buckets = {"encoded": [], "loose": [], "dead": [], "open": []}
    if args.auto:
        # ── AUTO MODE (nightly cron): derive from measurable state, counts only ──
        rep = DAYS / f"{d}.md"
        if rep.exists():
            print(f"  ⏭️  {d} already closed — day file exists, skipping (idempotent)")
            print("\n═══ CLOSE SKIPPED — already closed today ═══")
            return
        na = int(q(DOCS_PROP, "SELECT COUNT(*) FROM name_alias WHERE date(created_at) = date('now')") or 0)
        mc = int(q(DOCS_PROP, "SELECT COUNT(*) FROM menu_corrections WHERE date(created_at) = date('now')") or 0)
        rq = int(q(DOCS_PROP, "SELECT COUNT(*) FROM menu_review_queue") or 0)
        qt = int(q(DOCS_PROP, "SELECT COUNT(*) FROM menu_quarantine") or 0)
        if na + mc > 0:
            buckets["encoded"] = [f"{na} name_alias + {mc} menu_corrections encoded in DB today (counts only)"]
        if rq > 0:
            buckets["open"] = [f"{rq} review-queue items still open — pending Kato"]
        # LOOSE scratch: sessions may drop loose items in loose_today.md before ending
        scratch = CONT / "loose_today.md"
        if scratch.exists():
            buckets["loose"] = [l.strip("- ") for l in scratch.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")][:6]
            scratch.unlink()  # consumed
        print(f"  auto-derived: encoded={len(buckets['encoded'])} loose={len(buckets['loose'])} "
              f"dead={len(buckets['dead'])} open={len(buckets['open'])} "
              f"(name_alias={na} corrections={mc} review={rq} quarantine={qt})")
    elif args.buckets and Path(args.buckets).exists():
        buckets = json.loads(Path(args.buckets).read_text(encoding="utf-8"))
        print(f"  loaded from {args.buckets}: "
              f"encoded={len(buckets['encoded'])} loose={len(buckets['loose'])} "
              f"dead={len(buckets['dead'])} open={len(buckets['open'])}")
    else:
        print("  (interactive mode: pass --buckets file for scripted closes)")
        print("  ENCODED — learning now durable (name_alias, menu_corrections, dish_aliases.json). Name it + where.")
        print("  LOOSE — learned today, written nowhere. MUST be written to LEARNED.md tonight.")
        print("  DEAD — tried, didn't work. Append to DEAD.md with reason.")
        print("  OPEN — questions waiting on Kato + what's blocked behind them.")
        if args.interactive:
            for b in ("encoded", "loose", "dead", "open"):
                print(f"\n  --- {b.upper()} (one per line, empty to finish) ---")
                while True:
                    line = input(f"  [{b}] ").strip()
                    if not line: break
                    buckets[b].append(line)

    # 4. Write days/YYYY-MM-DD.md
    rep = DAYS / f"{d}.md"
    shipped = args.shipped or "TBD"
    coverage_line = args.coverage or "TBD"
    next_action = args.next or "TBD"
    content = f"""DATE: {d}
SHIPPED: {shipped}
COVERAGE: {coverage_line}
ENCODED: {len(buckets['encoded'])} — {', '.join(buckets['encoded'][:6]) if buckets['encoded'] else 'none'}
LOOSE→WRITTEN: {len(buckets['loose'])} — {', '.join(buckets['loose'][:6]) if buckets['loose'] else 'none'}
DEAD: {len(buckets['dead'])} — {', '.join(buckets['dead'][:6]) if buckets['dead'] else 'none'}
OPEN: {len(buckets['open'])} — {', '.join(buckets['open'][:6]) if buckets['open'] else 'none'}
BROKE: {args.broke or 'none'}
NEXT: {next_action}
"""
    with rep.open("a", encoding="utf-8") as f:
        f.write(content)
    print(f"\n  ✍️  wrote days/{d}.md")

    # 5. Append ENCODED + LOOSE to LEARNED.md (append-only)
    with LEARNED.open("a", encoding="utf-8") as f:
        f.write(f"\n## {d}\n")
        for item in buckets["encoded"]:
            f.write(f"- ENCODED: {item}\n")
        for item in buckets["loose"]:
            f.write(f"- LOOSE: {item}\n")
        if buckets["dead"]:
            with DEAD.open("a", encoding="utf-8") as f2:
                f2.write(f"\n## {d}\n")
                for item in buckets["dead"]:
                    f2.write(f"- {item}\n")
            print("  ✍️  appended DEAD.md")
    print("  ✍️  appended LEARNED.md (append-only, never rewritten)")

    # 6. Rewrite CARRY.md from OPEN + NEXT (max 7 items, 3 lines each)
    carry_items = [f"- [OPEN] {x}" for x in buckets["open"][:MAX_CARRY]]
    if next_action != "TBD":
        carry_items.append(f"- [NEXT] {next_action}")
    if not ok:
        carry_items.insert(0, "- [BROKE] DB PARITY BROKEN — sync clobber check FIRST")
    carry_items = carry_items[:MAX_CARRY]
    CARRY.write_text(
        f"# CARRY — handoff for next session\n# overwritten nightly · max {MAX_CARRY} items · {d}\n\n"
        + "\n".join(carry_items) + "\n", encoding="utf-8")
    print("  ✍️  rewrote CARRY.md (max 7 items)")
    print("\n═══ CLOSE COMPLETE — tomorrow starts where today ended ═══")

# ── goj open ──────────────────────────────────────────────────────────────
def cmd_open(args):
    ensure_dirs()
    print("═══ GOJ OPEN — morning brief ═══\n")

    # 1. Load exactly this: CARRY + DEAD + last 3 day files
    print("[1] CARRY (handoff):")
    if CARRY.exists():
        print("  " + "\n  ".join(l for l in CARRY.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")))
    else:
        print("  (no CARRY yet)")
    print("\n[2] DEAD (do not retry):")
    if DEAD.exists():
        dead_lines = [l for l in DEAD.read_text(encoding="utf-8").splitlines() if l.strip() and l.startswith("-")]
        print("  " + "\n  ".join(dead_lines[:10]) if dead_lines else "  (empty)")
    else:
        print("  (empty)")
    print("\n[3] Last 3 day files:")
    recent = sorted(DAYS.glob("*.md"))[-3:]
    for f in recent:
        first = [l for l in f.read_text(encoding="utf-8").splitlines() if l.startswith(("SHIPPED:", "NEXT:", "OPEN:"))]
        print(f"  {f.name}: {' | '.join(first)}")

    # 2. Re-verify before building
    print("\n[4] RE-VERIFY (green last night ≠ green this morning)")
    ok, lines = db_parity_report()
    for l in lines: print(" ", l)
    rq = q(DOCS_PROP, "SELECT COUNT(*) FROM menu_review_queue") or 0
    print(f"  review queue open: {rq}")

    # 3. Brief
    print("\n[5] BRIEF")
    print(f"  FOOD DAY TODAY: {args.food_day or '(check calendar)'}")
    print(f"  DUE TODAY: {args.due or '(signin/kitchen/distribution/drivers)'}")
    print(f"  BASE: {'re-verified' if ok else 'PARITY BROKEN — fix first'}")
    print(f"  CARRIED QUESTIONS: {rq} open (see CARRY)")
    print(f"  FIRST MOVE: {args.first_move or 'run the sheet chain for the food day'}")
    print("\n  ⚠️  Label facts: VERIFIED (exited 0 this morning) / RECORDED (written yesterday) / ASSUMED")
    print("  ASK: Same focus as yesterday, or has priority moved?")

# ── main ──────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(prog="goj", description="GOJ Continuity Loop")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("close", help="end-of-day learning handoff")
    c.add_argument("--auto", action="store_true", help="auto-derive buckets from DB state (nightly cron; idempotent)")
    c.add_argument("--buckets", help="path to JSON buckets file (scripted closes)")
    c.add_argument("--interactive", action="store_true", help="prompt for buckets interactively")
    c.add_argument("--shipped", help="what shipped today")
    c.add_argument("--coverage", help="coverage movement summary")
    c.add_argument("--broke", help="what regressed (empty = valid)")
    c.add_argument("--next", help="one next action")
    c.set_defaults(fn=cmd_close)
    o = sub.add_parser("open", help="start-of-day brief")
    o.add_argument("--food-day", help="today's food day date")
    o.add_argument("--due", help="sheets due today")
    o.add_argument("--first-move", help="first action")
    o.set_defaults(fn=cmd_open)
    args = p.parse_args()
    args.fn(args)

if __name__ == "__main__":
    main()
