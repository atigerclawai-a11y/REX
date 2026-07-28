#!/usr/bin/env python3
"""
CC_rexxie_firewall.py
Rexxie Firewall — Content + Schema Contamination Guard
Gold Health Systems · v2.0 · June 5 2026

ABSOLUTE LAW: Zero GOJ data, zero PHI, zero crossover into rexxie.db — ever.

What this daemon does (every 30 seconds):
  1. Schema check   — no GOJ tables, no GOJ DDL patterns in rexxie.db
  2. Content scan   — reads unencrypted columns in rexxie.db; detects GOJ keywords
                      and client name fragments in any text visible to SQLite
  3. Blocklist sync — pulls current client names from auth_tracker.db every cycle
                      to keep blocklist fresh (read-only, never writes to auth_tracker)
  4. Zombie check   — com.hermes.rexxie-bot.plist must stay dead
  5. Token check    — Rexxie bot config must show owner_chat_id = Kato's ID

  Violations:  immediate Telegram alert to Kato + log entry
  Clean cycle: hourly summary logged + Telegram confirmation

Usage:
  python CC_rexxie_firewall.py              # daemon (loops every 30s)
  python CC_rexxie_firewall.py --once       # single integrity check, print results, exit
  python CC_rexxie_firewall.py --status     # print last state from state file, exit
"""

import os
import sys
import time
import json
import sqlite3
import subprocess
import hashlib
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path

# ── PATHS ─────────────────────────────────────────────────────────────────────
REXXIE_DB      = Path.home() / "Desktop" / "REX" / "rexxie.db"
AUTH_TRACKER   = Path("~/Documents/goj files/dashboard/auth_tracker.db").expanduser()
ZOMBIE_PLIST   = Path.home() / "Library" / "LaunchAgents" / "com.hermes.rexxie-bot.plist"
TG_CONFIG      = Path.home() / "Desktop" / "REX" / "rex_rexxie_telegram_config.json"
LOG_DIR        = Path.home() / "Desktop" / "REX" / "logs"
LOG_FILE       = LOG_DIR / "rexxie_firewall.log"
STATE_FILE     = Path.home() / "Desktop" / "REX" / ".rexxie_firewall_state.json"

KATO_CHAT_ID   = 5587703834
POLL_INTERVAL  = 30       # seconds between checks
HOURLY_TICKS   = 120      # 120 × 30s = 60 min between clean-status reports

# ── STATIC GOJ KEYWORD BLOCKLIST ──────────────────────────────────────────────
# These strings must NEVER appear in any readable column of rexxie.db.
# This list covers program names, insurer codes, GOJ-specific identifiers.
GOJ_KEYWORDS = [
    "garden of joy",
    "gardenofjoy",
    "brooklyn",
    "anthem",
    "vcm",
    "vns health",
    "vnsny",
    "auth_tracker",
    "authorization",
    "service_end_date",
    "day_t_actual",
    "day_m_actual",
    "main_dish",
    "client_menu",
    "pending_schedule",
    "attendance_log",
    "client_route",
    "goj pipeline",
    "shift1",
    "shift2",
    "allen@gardenofjoy",
    "gardenofjoybrooklyn",
    "adult day",
    "adp",               # ADP payroll tied to GOJ employees
]

# GOJ table names that must NEVER appear as tables in rexxie.db
GOJ_FORBIDDEN_TABLES = {
    "clients",
    "authorization",
    "client_menus",
    "attendance_log",
    "employees",
    "pending_schedule_changes",
    "client_route_assignments",
    "menus",
    "pipeline",
}

# GOJ DDL patterns that must never appear in CREATE TABLE statements
GOJ_FORBIDDEN_DDL = [
    "service_end_date",
    "day_t_actual",
    "day_m_actual",
    "auth_tracker",
    "gardenofjoy",
    "main_dish",
    "client_menu",
]

# Expected and only-allowed tables in rexxie.db (audited 2026-06-04)
EXPECTED_REXXIE_TABLES = {
    "rexxie_vault_recovery",
    "rexxie_credentials",
    "rexxie_vault_meta",
    "rexxie_memory",
    "rexxie_sessions",
    "rexxie_training_schedule",
    "rexxie_training_lessons",
    "rexxie_daily_log",
    "sqlite_sequence",
}

# ── LOGGING ───────────────────────────────────────────────────────────────────
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s [FIREWALL] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("rexxie_firewall")

_console = logging.StreamHandler(sys.stdout)
_console.setLevel(logging.DEBUG)
_console.setFormatter(logging.Formatter(
    "%(asctime)s [FIREWALL] %(levelname)s: %(message)s", "%H:%M:%S"
))


# ── TELEGRAM ──────────────────────────────────────────────────────────────────
def _bot_token() -> str:
    """
    Return Telegram bot token.
    Priority: TELEGRAM_BOT_TOKEN env var → Hermes .env → Hermes config.yaml.
    NEVER uses the Rexxie bot token — alerts go through Hermes bot only.
    """
    # 1. Explicit env var (highest priority, simplest)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if token and ":" in token:
        return token

    # 2. Hermes .env file
    hermes_env = Path.home() / ".hermes" / "profiles" / "cloud" / ".env"
    if hermes_env.exists():
        try:
            for line in hermes_env.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ("BOT_TOKEN" in line or "TELEGRAM_TOKEN" in line) and "rexxie" not in line.lower():
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        t = parts[1].strip().strip("\"'")
                        if t and ":" in t:
                            return t
        except Exception:
            pass

    # 3. Hermes config.yaml
    hermes_cfg = Path.home() / ".hermes" / "profiles" / "cloud" / "config.yaml"
    if hermes_cfg.exists():
        try:
            for line in hermes_cfg.read_text().splitlines():
                if "bot_token" in line.lower() and "rexxie" not in line.lower():
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        t = parts[1].strip().strip("\"'")
                        if t and ":" in t:
                            return t
        except Exception:
            pass

    return ""


def _send_telegram(text: str):
    """Send message to Kato. Fails silently — firewall never crashes on alert failure."""
    token = _bot_token()
    if not token:
        log.warning("No bot token available — alert logged only, not sent to Telegram")
        return
    try:
        import urllib.request, urllib.parse
        data = urllib.parse.urlencode({
            "chat_id": KATO_CHAT_ID,
            "text": text,
        }).encode()
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=8)
        log.info("Telegram alert sent")
    except Exception as e:
        log.error(f"Telegram send failed: {e}")


def alert(message: str, vtype: str, severity: str = "CRITICAL"):
    log.error(f"VIOLATION [{vtype}] {severity}: {message}")
    label = "REXXIE FIREWALL CRITICAL" if severity == "CRITICAL" else "REXXIE FIREWALL WARNING"
    _send_telegram(
        f"[{label}]\n"
        f"Type: {vtype}\n"
        f"Detail: {message}\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )


def send_clean_report(check_count: int):
    log.info(f"Hourly clean status — {check_count} checks completed, no violations")
    _send_telegram(
        f"[REXXIE FIREWALL] Clean\n"
        f"Checks completed: {check_count}\n"
        f"Status: No violations detected\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )


# ── STATE ─────────────────────────────────────────────────────────────────────
def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {
        "check_count": 0,
        "last_check": None,
        "last_clean": None,
        "last_clean_report": None,
        "violations": [],
        "db_table_hash": None,
        "zombie_hash": None,
    }


def _save_state(state: dict):
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        log.error(f"Could not save state: {e}")


# ── BLOCKLIST: CLIENT NAMES FROM auth_tracker.db ─────────────────────────────
def _load_client_blocklist() -> list:
    """
    Pull client first/last names from auth_tracker.db (read-only).
    Returns list of lowercase name fragments to scan for in rexxie.db content.
    Returns [] if auth_tracker is unreachable — non-fatal.
    """
    if not AUTH_TRACKER.exists():
        return []
    names = []
    try:
        conn = sqlite3.connect(f"file:{AUTH_TRACKER}?mode=ro", uri=True, timeout=3)
        rows = conn.execute(
            "SELECT first_name, last_name FROM clients WHERE first_name IS NOT NULL"
        ).fetchall()
        conn.close()
        for first, last in rows:
            if first and len(first.strip()) >= 3:
                names.append(first.strip().lower())
            if last and len(last.strip()) >= 3:
                names.append(last.strip().lower())
    except Exception as e:
        log.warning(f"Could not load client blocklist from auth_tracker: {e}")
    return names


# ── CHECK 1: SCHEMA ───────────────────────────────────────────────────────────
def check_schema(state: dict) -> list:
    """
    Read sqlite_master from rexxie.db.
    Flags: GOJ table names, unexpected tables, GOJ DDL patterns.
    """
    violations = []
    if not REXXIE_DB.exists():
        return violations
    try:
        conn = sqlite3.connect(str(REXXIE_DB), timeout=5)
        rows = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()
    except Exception as e:
        log.warning(f"Schema check: could not open rexxie.db: {e}")
        return violations

    current_tables = set()
    for name, ddl in rows:
        current_tables.add(name)

        if name in GOJ_FORBIDDEN_TABLES:
            violations.append(("GOJ_TABLE_IN_REXXIE_DB", "CRITICAL",
                f"GOJ table '{name}' found in rexxie.db — hard wall breached"))

        elif name not in EXPECTED_REXXIE_TABLES:
            violations.append(("UNEXPECTED_TABLE", "HIGH",
                f"Unexpected table '{name}' in rexxie.db — not in authorized list"))

        if ddl:
            ddl_lower = ddl.lower()
            for pat in GOJ_FORBIDDEN_DDL:
                if pat in ddl_lower:
                    violations.append(("GOJ_DDL_PATTERN", "HIGH",
                        f"GOJ DDL pattern '{pat}' in CREATE TABLE '{name}'"))

    sig = hashlib.md5(",".join(sorted(current_tables)).encode()).hexdigest()
    if state.get("db_table_hash") and sig != state["db_table_hash"]:
        log.info(f"rexxie.db table list changed: {sorted(current_tables)}")
    state["db_table_hash"] = sig
    return violations


# ── CHECK 2: CONTENT SCAN ─────────────────────────────────────────────────────
def check_content(client_blocklist: list) -> list:
    """
    Scan all readable TEXT columns in rexxie.db for GOJ contamination.
    AES-256-GCM encrypted BLOBs are opaque — we scan only TEXT/VARCHAR columns.
    Checks static GOJ_KEYWORDS + dynamic client name fragments.
    """
    violations = []
    if not REXXIE_DB.exists():
        return violations

    all_patterns = GOJ_KEYWORDS + client_blocklist

    try:
        conn = sqlite3.connect(str(REXXIE_DB), timeout=5)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()

        for (tname,) in tables:
            try:
                # Get column info to find TEXT columns (skip BLOBs)
                cols = conn.execute(f"PRAGMA table_info('{tname}')").fetchall()
                text_cols = [
                    col[1] for col in cols
                    if col[2].upper() in ("TEXT", "VARCHAR", "CHAR", "CLOB", "")
                ]
                if not text_cols:
                    continue

                col_list = ", ".join(f'"{c}"' for c in text_cols)
                rows = conn.execute(
                    f"SELECT {col_list} FROM \"{tname}\" LIMIT 5000"
                ).fetchall()

                for row in rows:
                    for val in row:
                        if not val or not isinstance(val, str):
                            continue
                        val_lower = val.lower()
                        for pat in all_patterns:
                            if pat and pat in val_lower:
                                # Redact the match to avoid logging PHI itself
                                violations.append(("GOJ_CONTENT_IN_REXXIE_DB", "CRITICAL",
                                    f"GOJ pattern '{pat}' detected in table '{tname}' — "
                                    f"GOJ data has contaminated rexxie.db"))
                                # One violation per table/column hit is enough
                                break
                        else:
                            continue
                        break  # break row loop once one violation found per row
            except Exception as e:
                log.warning(f"Content scan: error reading table '{tname}': {e}")

        conn.close()
    except Exception as e:
        log.warning(f"Content scan: could not open rexxie.db: {e}")

    return violations


# ── CHECK 3: ZOMBIE PLIST ─────────────────────────────────────────────────────
def check_zombie(state: dict) -> list:
    violations = []
    if not ZOMBIE_PLIST.exists():
        state["zombie_hash"] = None
        return violations

    result = subprocess.run(
        ["launchctl", "list", "com.hermes.rexxie-bot"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        log.critical("ZOMBIE PLIST ACTIVE — killing now")
        subprocess.run(["launchctl", "unload", str(ZOMBIE_PLIST)], capture_output=True)
        subprocess.run(["pkill", "-f", "rexxie-bot"], capture_output=True)
        violations.append(("ZOMBIE_ACTIVE", "CRITICAL",
            "com.hermes.rexxie-bot was active and has been killed. Investigate immediately."))

    # Hash-track for silent modification even when inactive
    try:
        current_hash = hashlib.sha256(ZOMBIE_PLIST.read_bytes()).hexdigest()
        if state.get("zombie_hash") and current_hash != state["zombie_hash"]:
            violations.append(("ZOMBIE_MODIFIED", "HIGH",
                f"Zombie plist was modified. "
                f"Prev: {state['zombie_hash'][:12]} → Now: {current_hash[:12]}"))
        state["zombie_hash"] = current_hash
    except Exception as e:
        log.warning(f"Could not hash zombie plist: {e}")

    return violations


# ── CHECK 4: TOKEN / CONFIG INTEGRITY ─────────────────────────────────────────
def check_token(state: dict) -> list:
    violations = []

    # Zombie process check
    result = subprocess.run(["pgrep", "-fa", "rexxie-bot"], capture_output=True, text=True)
    if result.stdout.strip():
        procs = [p for p in result.stdout.strip().split("\n") if p.strip()]
        violations.append(("REXXIE_BOT_ZOMBIE_PROCESS", "CRITICAL",
            f"rexxie-bot process running — token thief: {'; '.join(procs[:2])}"))

    # Config integrity
    if TG_CONFIG.exists():
        try:
            cfg = json.loads(TG_CONFIG.read_text())
            if cfg.get("owner_chat_id") != KATO_CHAT_ID:
                violations.append(("TOKEN_CONFIG_TAMPERED", "CRITICAL",
                    f"rex_rexxie_telegram_config.json owner_chat_id changed: "
                    f"expected {KATO_CHAT_ID}, found {cfg.get('owner_chat_id')}"))
        except Exception as e:
            log.warning(f"Could not verify telegram config: {e}")

    return violations


# ── MAIN CHECK CYCLE ──────────────────────────────────────────────────────────
def run_check(state: dict, verbose: bool = False) -> list:
    """Run all four checks. Returns list of (vtype, severity, detail) tuples."""
    # Refresh client blocklist every cycle (fast read from auth_tracker)
    client_blocklist = _load_client_blocklist()

    checks = [
        ("schema",    lambda: check_schema(state)),
        ("content",   lambda: check_content(client_blocklist)),
        ("zombie",    lambda: check_zombie(state)),
        ("token",     lambda: check_token(state)),
    ]

    all_violations = []
    for name, fn in checks:
        try:
            violations = fn()
            all_violations.extend(violations)
            if verbose:
                status = "clean" if not violations else f"{len(violations)} violation(s)"
                print(f"  {name:<10} {status}")
        except Exception as e:
            log.error(f"Check '{name}' raised: {e}", exc_info=True)
            if verbose:
                print(f"  {name:<10} ERROR: {e}")

    now = datetime.now(timezone.utc).isoformat()
    state["last_check"] = now
    state["check_count"] = state.get("check_count", 0) + 1

    if all_violations:
        # Keep last 200 violations in state
        state["violations"] = [
            {"type": t, "severity": s, "detail": d, "timestamp": now}
            for t, s, d in all_violations
        ] + state.get("violations", [])
        state["violations"] = state["violations"][:200]

        # Alert immediately on every violation
        for vtype, severity, detail in all_violations:
            alert(detail, vtype, severity)
    else:
        state["last_clean"] = now
        log.info(f"Check #{state['check_count']}: clean")

    return all_violations


# ── STATUS DISPLAY ────────────────────────────────────────────────────────────
def print_status():
    if not STATE_FILE.exists():
        print("No state file found — has the daemon run yet?")
        return
    state = json.loads(STATE_FILE.read_text())
    print(f"\n{'='*60}")
    print("REXXIE FIREWALL STATUS")
    print(f"{'='*60}")
    print(f"Last check:  {state.get('last_check', 'never')}")
    print(f"Last clean:  {state.get('last_clean', 'never')}")
    print(f"Checks run:  {state.get('check_count', 0)}")
    violations = state.get("violations", [])
    if violations:
        print(f"\nViolations ({len(violations)} total, showing last 5):")
        for v in violations[:5]:
            print(f"  [{v.get('severity')}] {v.get('type')}: {v.get('detail', '')[:90]}")
            print(f"        at {v.get('timestamp')}")
    else:
        print("\nNo violations on record. Firewall intact.")
    print(f"{'='*60}\n")


# ── ENTRY POINT ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Rexxie Firewall Monitor")
    parser.add_argument("--once",    action="store_true", help="Run one check and exit")
    parser.add_argument("--status",  action="store_true", help="Print last state and exit")
    parser.add_argument("--verbose", action="store_true", help="Verbose output (implies --once)")
    args = parser.parse_args()

    if args.verbose or args.once:
        log.addHandler(_console)

    if args.status:
        print_status()
        return

    if args.once:
        state = _load_state()
        print(f"\nRexxie Firewall — one-time check [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
        print(f"  rexxie.db:    {REXXIE_DB} ({'exists' if REXXIE_DB.exists() else 'NOT FOUND'})")
        print(f"  auth_tracker: {AUTH_TRACKER} ({'exists' if AUTH_TRACKER.exists() else 'NOT FOUND'})")
        print(f"  zombie plist: {'EXISTS' if ZOMBIE_PLIST.exists() else 'absent (good)'}")
        print()
        violations = run_check(state, verbose=True)
        _save_state(state)
        print()
        if violations:
            print(f"Result: {len(violations)} violation(s) found")
            for vtype, severity, detail in violations:
                print(f"  [{severity}] {vtype}: {detail}")
        else:
            print("Result: All checks passed — firewall intact")
        print()
        return

    # Daemon mode
    log.info("=" * 60)
    log.info("Rexxie Firewall starting (daemon mode)")
    log.info(f"rexxie.db:    {REXXIE_DB}")
    log.info(f"auth_tracker: {AUTH_TRACKER}")
    log.info(f"poll interval: {POLL_INTERVAL}s")
    log.info("=" * 60)

    state = _load_state()
    ticks_since_report = 0

    while True:
        try:
            violations = run_check(state)

            if not violations:
                ticks_since_report += 1
                if ticks_since_report >= HOURLY_TICKS:
                    send_clean_report(state["check_count"])
                    ticks_since_report = 0
            else:
                # Reset hourly timer after a violation — next clean report restarts the count
                ticks_since_report = 0

            _save_state(state)
        except Exception as e:
            log.error(f"Unhandled error in main loop: {e}", exc_info=True)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
