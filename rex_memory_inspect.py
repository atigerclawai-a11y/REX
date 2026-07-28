#!/usr/bin/env python3
"""
rex_memory_inspect.py
──────────────────────────────────────────────────────────────────
Rexxie GOJ – Memory Confidence Inspector

Reads ALL Rexxie memory databases and prints each memory with a
% confidence grade showing how well the system understands it.

The confidence grade is CONTEXT-INDEPENDENT — it measures how
established/reliable the memory is, not its relevance to any query.

Confidence formula:
  • Memory type weight  (30%) — decisions/preferences score higher than ideas
  • Recency             (25%) — fresh memories decay slowly over 14-day half-life
  • Access frequency    (25%) — recalled often = more trusted
  • Explicit importance (20%) — manually set or default 0.5

Grade scale:
  90–100%  A  (High confidence — use freely)
  75–89%   B  (Good confidence — likely reliable)
  60–74%   C  (Moderate confidence — verify if critical)
  45–59%   D  (Low confidence — treat as approximate)
   0–44%   F  (Very low — may be stale or unverified)

Run:
    python ~/Desktop/REX/rex_memory_inspect.py
    python ~/Desktop/REX/rex_memory_inspect.py --type decision
    python ~/Desktop/REX/rex_memory_inspect.py --min-grade B
    python ~/Desktop/REX/rex_memory_inspect.py --db rexxie_memory.db
"""

from __future__ import annotations

import argparse
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# ─────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────

REX_DIR   = Path.home() / "Desktop" / "REX"
REX_HOME  = Path.home() / ".rex"

# All databases to inspect and what tables to look for in each
DB_CONFIG = {
    "rexxie_memory.db": {
        "tables": ["rexxie_ideas"],
        "schema": "ideas",
    },
    "rex_memory.db": {
        "tables": ["memories"],
        "schema": "memories",
    },
    "rex_exchanges.db": {
        "tables": ["exchanges", "messages", "history"],
        "schema": "exchanges",
    },
    "goj_rexxie.db": {
        "tables": ["rexxie_ideas", "memories"],
        "schema": "ideas",
    },
}

# Backend database
BACKEND_DB = REX_HOME / "rex_journeys.db"

# Type importance weights (must match rex_memory_priority.py)
TYPE_WEIGHTS: dict[str, float] = {
    "decision":   1.00,
    "blocker":    0.95,
    "preference": 0.85,
    "state":      0.80,
    "question":   0.65,
    "idea":       0.55,
}
DEFAULT_TYPE_WEIGHT = 0.50

HALF_LIFE_DAYS  = 14.0
ACCESS_BOOST_CAP   = 0.30
ACCESS_BOOST_SCALE = 5.0

GRADE_THRESHOLDS = [
    (0.90, "A", "High confidence"),
    (0.75, "B", "Good confidence"),
    (0.60, "C", "Moderate confidence"),
    (0.45, "D", "Low confidence"),
    (0.00, "F", "Very low confidence"),
]

# ANSI colors (disabled if not a TTY)
USE_COLOR = sys.stdout.isatty()

def _c(code: str, text: str) -> str:
    if not USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"

def green(t):  return _c("32", t)
def yellow(t): return _c("33", t)
def red(t):    return _c("31", t)
def cyan(t):   return _c("36", t)
def bold(t):   return _c("1",  t)
def dim(t):    return _c("2",  t)


# ─────────────────────────────────────────────────────────────────
# SCORING FUNCTIONS
# ─────────────────────────────────────────────────────────────────

def _recency_score(created_at_iso: str) -> float:
    """Exponential decay — fresh = 1.0, old = approaching 0."""
    try:
        created = datetime.fromisoformat(str(created_at_iso))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        age_days = (now - created).total_seconds() / 86400.0
        return math.pow(2.0, -age_days / HALF_LIFE_DAYS)
    except Exception:
        return 0.50


def _access_boost_normalized(access_count: int) -> float:
    """Logarithmic access frequency boost, normalized 0-1."""
    if access_count <= 0:
        return 0.0
    raw = math.log1p(access_count) / math.log1p(ACCESS_BOOST_SCALE)
    return min(raw, 1.0)   # normalized 0→1


def memory_confidence(
    mem_type:   str,
    created_at: str,
    access_count: int  = 0,
    importance:   float = 0.50,
) -> float:
    """
    Context-independent confidence score (0.0–1.0).

    Tells you how well-established this memory is as knowledge,
    independent of any specific query or topic.
    """
    type_wt  = TYPE_WEIGHTS.get(str(mem_type).lower(), DEFAULT_TYPE_WEIGHT)
    recency  = _recency_score(created_at)
    acc_norm = _access_boost_normalized(access_count)
    imp_norm = max(0.0, min(1.0, float(importance)))

    score = (
        type_wt  * 0.30 +
        recency  * 0.25 +
        acc_norm * 0.25 +
        imp_norm * 0.20
    )
    return round(score, 4)


def grade_label(score: float) -> tuple[int, str, str]:
    """Return (percent, letter, description) for a score."""
    pct = int(round(score * 100))
    for threshold, letter, desc in GRADE_THRESHOLDS:
        if score >= threshold:
            return pct, letter, desc
    return pct, "F", "Very low confidence"


def colorize_grade(pct: int, letter: str) -> str:
    label = f"{pct:3d}% [{letter}]"
    if letter == "A":
        return green(label)
    elif letter == "B":
        return green(label)
    elif letter == "C":
        return yellow(label)
    elif letter == "D":
        return yellow(label)
    else:
        return red(label)


# ─────────────────────────────────────────────────────────────────
# DATABASE READERS
# ─────────────────────────────────────────────────────────────────

def _connect(db_path: Path) -> sqlite3.Connection | None:
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"  {red('ERROR')} connecting to {db_path.name}: {e}")
        return None


def _list_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r["name"] for r in rows}


def _read_ideas_table(
    conn: sqlite3.Connection,
    table: str,
    filter_type: str | None = None,
    min_grade: str | None = None,
) -> list[dict]:
    """Read a rexxie_ideas-style table."""
    cols = _table_columns(conn, table)

    select_parts = ["id", "idea_type", "content", "status", "created_at"]
    if "access_count" in cols:
        select_parts.append("COALESCE(access_count, 0) AS access_count")
    else:
        select_parts.append("0 AS access_count")
    if "importance" in cols:
        select_parts.append("COALESCE(importance, 0.5) AS importance")
    else:
        select_parts.append("0.5 AS importance")
    if "source" in cols:
        select_parts.append("source")
    if "component_link" in cols:
        select_parts.append("component_link")

    sql = f"SELECT {', '.join(select_parts)} FROM {table}"
    params = []
    if "status" in cols:
        sql += " WHERE status != 'archived'"
    if filter_type:
        connector = "AND" if "WHERE" in sql else "WHERE"
        sql += f" {connector} idea_type = ?"
        params.append(filter_type)
    sql += " ORDER BY created_at DESC LIMIT 1000"

    rows = conn.execute(sql, params).fetchall()

    results = []
    for row in rows:
        score = memory_confidence(
            mem_type     = row["idea_type"] or "idea",
            created_at   = row["created_at"] or "",
            access_count = row["access_count"],
            importance   = row["importance"],
        )
        pct, letter, desc = grade_label(score)

        if min_grade:
            grade_order = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
            if grade_order.get(letter, 0) < grade_order.get(min_grade, 0):
                continue

        results.append({
            "id":        row["id"],
            "type":      row["idea_type"] or "unknown",
            "content":   row["content"] or "",
            "status":    row["status"] if "status" in row.keys() else "?",
            "created_at": row["created_at"] or "",
            "access":    row["access_count"],
            "score":     score,
            "pct":       pct,
            "letter":    letter,
            "desc":      desc,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def _read_memories_table(
    conn: sqlite3.Connection,
    table: str,
    min_grade: str | None = None,
) -> list[dict]:
    """Read a memories-style table (simpler schema)."""
    cols = _table_columns(conn, table)

    select_parts = []
    if "id" in cols:
        select_parts.append("id")
    else:
        select_parts.append("rowid AS id")
    if "content" in cols:
        select_parts.append("content")
    elif "text" in cols:
        select_parts.append("text AS content")
    else:
        select_parts.append("'' AS content")
    if "created_at" in cols:
        select_parts.append("created_at")
    elif "timestamp" in cols:
        select_parts.append("timestamp AS created_at")
    else:
        select_parts.append("'' AS created_at")

    sql = f"SELECT {', '.join(select_parts)} FROM {table} ORDER BY created_at DESC LIMIT 500"

    try:
        rows = conn.execute(sql).fetchall()
    except Exception as e:
        return []

    results = []
    for row in rows:
        content = row["content"] or ""
        if not content.strip():
            continue
        score = memory_confidence(
            mem_type   = "state",     # generic session memory type
            created_at = row["created_at"] or "",
            access_count = 0,
            importance = 0.50,
        )
        pct, letter, desc = grade_label(score)

        if min_grade:
            grade_order = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
            if grade_order.get(letter, 0) < grade_order.get(min_grade, 0):
                continue

        results.append({
            "id":         row["id"],
            "type":       "session",
            "content":    content,
            "status":     "active",
            "created_at": row["created_at"] or "",
            "access":     0,
            "score":      score,
            "pct":        pct,
            "letter":     letter,
            "desc":       desc,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def _read_exchanges_table(
    conn: sqlite3.Connection,
    table: str,
    limit: int = 20,
) -> list[dict]:
    """Read conversation exchange history (last N entries)."""
    cols = _table_columns(conn, table)

    select_parts = []
    if "id" in cols:
        select_parts.append("id")
    else:
        select_parts.append("rowid AS id")
    if "user_message" in cols:
        select_parts.append("user_message")
    elif "message" in cols:
        select_parts.append("message AS user_message")
    else:
        select_parts.append("'' AS user_message")
    if "rexxie_response" in cols:
        select_parts.append("rexxie_response")
    elif "response" in cols:
        select_parts.append("response AS rexxie_response")
    else:
        select_parts.append("'' AS rexxie_response")
    if "created_at" in cols:
        select_parts.append("created_at")
    elif "timestamp" in cols:
        select_parts.append("timestamp AS created_at")
    else:
        select_parts.append("'' AS created_at")

    sql = f"SELECT {', '.join(select_parts)} FROM {table} ORDER BY created_at DESC LIMIT {limit}"

    try:
        rows = conn.execute(sql).fetchall()
    except Exception:
        return []

    results = []
    for row in rows:
        results.append({
            "id":         row["id"],
            "user":       (row["user_message"] or "")[:120],
            "rexxie":     (row["rexxie_response"] or "")[:120],
            "created_at": row["created_at"] or "",
        })
    return results


# ─────────────────────────────────────────────────────────────────
# DISPLAY
# ─────────────────────────────────────────────────────────────────

def _print_section(title: str):
    print()
    print(bold(f"{'─' * 70}"))
    print(bold(f"  {title}"))
    print(bold(f"{'─' * 70}"))


def _print_memory_row(m: dict, idx: int):
    grade_str = colorize_grade(m["pct"], m["letter"])
    type_str  = cyan(f"[{m['type'].upper():10s}]")
    content   = m["content"][:110].replace("\n", " ")
    date_str  = dim(m["created_at"][:10] if m["created_at"] else "no-date")
    access    = dim(f"↺{m['access']}") if m["access"] > 0 else dim("↺0")

    print(f"  {grade_str}  {type_str}  {content}")
    print(f"             {date_str}  {access}  {dim(m['desc'])}")
    print()


def _print_summary_stats(memories: list[dict], db_name: str, table: str):
    if not memories:
        print(f"  {dim('(no memories found)')}")
        return

    grade_counts = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    for m in memories:
        grade_counts[m["letter"]] = grade_counts.get(m["letter"], 0) + 1

    avg_score = sum(m["score"] for m in memories) / len(memories)
    avg_pct, avg_letter, _ = grade_label(avg_score)

    print(f"  {bold('Total memories:')} {len(memories)}")
    print(f"  {bold('Average confidence:')} {colorize_grade(avg_pct, avg_letter)}")
    print(f"  {bold('Grade breakdown:')}", end="")
    for letter in ["A", "B", "C", "D", "F"]:
        count = grade_counts.get(letter, 0)
        if count > 0:
            print(f"  {letter}:{count}", end="")
    print()


# ─────────────────────────────────────────────────────────────────
# MAIN INSPECTOR
# ─────────────────────────────────────────────────────────────────

def inspect_database(
    db_path: Path,
    filter_type: str | None = None,
    min_grade:   str | None = None,
    show_exchanges: bool = False,
    verbose: bool = False,
) -> dict:
    """Inspect a single database. Returns stats dict."""
    stats = {"db": db_path.name, "tables": {}, "total": 0}

    conn = _connect(db_path)
    if conn is None:
        print(f"  {yellow('SKIP')} {db_path.name} — not found or unreadable")
        return stats

    all_tables = _list_tables(conn)
    if not all_tables:
        print(f"  {yellow('EMPTY')} {db_path.name} — no tables")
        conn.close()
        return stats

    if verbose:
        print(f"  Tables: {', '.join(all_tables)}")

    for table in all_tables:
        cols = _table_columns(conn, table)

        # Identify table type
        if "idea_type" in cols and "content" in cols:
            memories = _read_ideas_table(conn, table, filter_type, min_grade)
            _print_section(f"{db_path.name}  ›  {table}  ({len(memories)} memories)")
            _print_summary_stats(memories, db_path.name, table)

            print()
            for idx, m in enumerate(memories, 1):
                _print_memory_row(m, idx)

            stats["tables"][table] = len(memories)
            stats["total"] += len(memories)

        elif "content" in cols or "text" in cols:
            memories = _read_memories_table(conn, table, min_grade)
            _print_section(f"{db_path.name}  ›  {table}  ({len(memories)} session memories)")
            _print_summary_stats(memories, db_path.name, table)

            print()
            for idx, m in enumerate(memories[:30], 1):   # cap session memories at 30
                _print_memory_row(m, idx)
            if len(memories) > 30:
                print(f"  {dim(f'... and {len(memories) - 30} more. Use --verbose to see all.')}")

            stats["tables"][table] = len(memories)
            stats["total"] += len(memories)

        elif show_exchanges and ("user_message" in cols or "message" in cols):
            exchanges = _read_exchanges_table(conn, table)
            _print_section(f"{db_path.name}  ›  {table}  (last {len(exchanges)} exchanges)")
            for ex in exchanges:
                print(f"  {dim(ex['created_at'][:16])}  You: {ex['user'][:80]}")
                if ex["rexxie"]:
                    print(f"  {'':18s}  Rex: {ex['rexxie'][:80]}")
                print()
            stats["tables"][table] = len(exchanges)

        else:
            if verbose:
                cols_list = _table_columns(conn, table)
                print(f"  {dim(f'Table {table!r}: {len(cols_list)} columns — skipped (unrecognized schema)')}")

    conn.close()
    return stats


def run_inspection(args):
    print()
    print(bold("=" * 70))
    print(bold("  REXXIE MEMORY CONFIDENCE INSPECTOR"))
    print(bold("  Garden of Joy — REX System"))
    print(bold(f"  {datetime.now().strftime('%A, %B %d, %Y  %H:%M')}"))
    print(bold("=" * 70))

    if args.min_grade:
        print(f"  Filter: minimum grade {bold(args.min_grade)}")
    if args.type:
        print(f"  Filter: type = {bold(args.type)}")

    # Determine which databases to inspect
    if args.db:
        # Specific DB requested
        db_path = Path(args.db)
        if not db_path.is_absolute():
            db_path = REX_DIR / db_path
        dbs_to_check = [db_path]
    else:
        # All known databases
        dbs_to_check = []
        for db_name in DB_CONFIG:
            candidate = REX_DIR / db_name
            dbs_to_check.append(candidate)
        # Also check backend DB
        dbs_to_check.append(BACKEND_DB)

    all_stats = []
    for db_path in dbs_to_check:
        s = inspect_database(
            db_path,
            filter_type    = args.type,
            min_grade      = args.min_grade,
            show_exchanges = args.exchanges,
            verbose        = args.verbose,
        )
        all_stats.append(s)

    # ── OVERALL SUMMARY ──
    _print_section("OVERALL SUMMARY")
    total_memories = sum(s["total"] for s in all_stats)
    print(f"  {bold('Databases scanned:')} {len(all_stats)}")
    print(f"  {bold('Total memories found:')} {total_memories}")
    print()
    print(bold("  Confidence legend:"))
    print(f"    {green('A (90-100%)')}  High confidence — use freely in responses")
    print(f"    {green('B (75-89%)')}   Good confidence — likely reliable")
    print(f"    {yellow('C (60-74%)')}  Moderate — verify if critical")
    print(f"    {yellow('D (45-59%)')}  Low — treat as approximate")
    print(f"    {red('F ( 0-44%)')}   Very low — stale or unverified")
    print()
    print(bold("  Score components:"))
    print(f"    30%  Memory type (decision/preference > idea/question)")
    print(f"    25%  Recency (14-day half-life decay)")
    print(f"    25%  Access frequency (recalled more = more trusted)")
    print(f"    20%  Explicit importance flag")
    print()


# ─────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Inspect Rexxie memory databases with confidence grades.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python rex_memory_inspect.py                    # inspect all databases
  python rex_memory_inspect.py --min-grade B      # only B+ memories
  python rex_memory_inspect.py --type decision    # only decisions
  python rex_memory_inspect.py --db rexxie_memory.db
  python rex_memory_inspect.py --exchanges        # also show conversation log
        """,
    )
    parser.add_argument("--type",      help="Filter by memory type (decision, preference, idea, blocker, state, question)")
    parser.add_argument("--min-grade", help="Minimum grade to display (A, B, C, D, F)", dest="min_grade")
    parser.add_argument("--db",        help="Inspect only this database file (name or full path)")
    parser.add_argument("--exchanges", action="store_true", help="Also display conversation exchange history")
    parser.add_argument("--verbose",   action="store_true", help="Show all tables including unrecognized schemas")

    args = parser.parse_args()
    run_inspection(args)


if __name__ == "__main__":
    main()
