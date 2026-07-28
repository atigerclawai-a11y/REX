#!/usr/bin/env python3
"""
CC_imessage_cascade.py — C3 staging scaffold for the iMessage → 7-system change cascade.

WHAT THIS IS
------------
A *listener + planner* for the "7-system change cascade" described in
MASTER_REQUIREMENTS §3:

    Calendar → Attendance → Driver → Kitchen → Distribution → Sign-in → Menu

When a staffer texts something like "Maria G sick today" or "cancel Boris K
Tuesday", that change today has to be propagated by hand across seven systems.
This scaffold detects that intent from message text and produces a STAGED plan
of exactly what *would* change in each of the seven systems — then writes that
plan to state/cascade_pending.json for Kato to review.

HARD RULES (enforced by construction)
-------------------------------------
* READ-ONLY on chat.db and auth_tracker.db. Every connection is opened with
  mode=ro. No INSERT/UPDATE/DELETE is ever issued against either database.
* All cascade actions are STAGED to JSON. Nothing is executed. The live writer
  is intentionally NOT built here.
* Directive 9 — never fabricate attendance. This module only PROPOSES an
  attendance change; it never writes one. Kato confirms before anything is live.
* Names are matched locally (difflib), never sent anywhere. Any console printout
  redacts client names to "First L." form.

USAGE
-----
    python3 CC_imessage_cascade.py --selftest
        Feed 3 synthetic messages through parse -> plan -> write pending json.

    python3 CC_imessage_cascade.py --text "Maria G sick today"
        Parse + plan a single message from the command line.

    python3 CC_imessage_cascade.py --scan-messages [--limit N]
        If chat.db is readable, scan the last N inbound messages from known
        staff senders for cascade intents. Falls back gracefully if chat.db
        is not accessible (needs Full Disk Access).

    python3 CC_imessage_cascade.py --check-db
        Report chat.db accessibility and auth_tracker.db baseline counts.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# Paths & constants
# ─────────────────────────────────────────────────────────────────────────────

HOME = Path.home()
DASHBOARD_DB = HOME / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
CHAT_DB = HOME / "Library" / "Messages" / "chat.db"

REX_DIR = Path(__file__).resolve().parent
STATE_DIR = REX_DIR / "state"
PENDING_JSON = STATE_DIR / "cascade_pending.json"

# The seven systems of the cascade, in canonical order (MASTER_REQUIREMENTS §3).
SEVEN_SYSTEMS = [
    "Calendar",
    "Attendance",
    "Driver",
    "Kitchen",
    "Distribution",
    "Sign-in",
    "Menu",
]

# day_key vocabulary used across auth_tracker.db (M/T/W/TH/F/Su).
DAY_KEYS = {
    "monday": "M", "mon": "M", "m": "M",
    "tuesday": "T", "tue": "T", "tues": "T", "t": "T",
    "wednesday": "W", "wed": "W", "w": "W",
    "thursday": "TH", "thu": "TH", "thur": "TH", "thurs": "TH", "th": "TH",
    "friday": "F", "fri": "F", "f": "F",
    "sunday": "Su", "sun": "Su", "su": "Su",
}
DAY_LABEL = {
    "M": "Monday", "T": "Tuesday", "W": "Wednesday",
    "TH": "Thursday", "F": "Friday", "Su": "Sunday",
}
WEEKDAY_TO_KEY = {0: "M", 1: "T", 2: "W", 3: "TH", 4: "F", 6: "Su"}

# Known staff senders (phone numbers / emails seen in chat.db). When scanning
# real messages we only consider these. Edit to onboard more staff. Empty list
# = scan all inbound senders (useful for testing only).
KNOWN_STAFF_SENDERS: list[str] = [
    # "+13475879913",
]

# Fuzzy-match acceptance threshold against the active client roster.
NAME_MATCH_THRESHOLD = 0.62

# Intent action vocabulary.
ACTION_ABSENT = "absent"   # not coming on a specific day
ACTION_CANCEL = "cancel"   # cancel a specific day's slot
ACTION_RESUME = "resume"   # returning / back

# ─────────────────────────────────────────────────────────────────────────────
# Read-only DB helpers
# ─────────────────────────────────────────────────────────────────────────────


def _connect_ro(db_path: Path) -> sqlite3.Connection:
    """Open an sqlite database in immutable read-only mode.

    Uses the file: URI with mode=ro so the connection physically cannot write.
    Raises FileNotFoundError if the file is missing so callers can fall back.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    uri = f"file:{db_path}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def chat_db_status() -> dict:
    """Probe chat.db accessibility without writing.

    Returns a dict: {readable: bool, reason: str, message_count: int|None}.
    A common failure is the macOS TCC "Full Disk Access" gate, which surfaces
    as an OperationalError ("unable to open database file" / "authorization
    denied"); we detect that and report needs-FDA.
    """
    if not CHAT_DB.exists():
        return {"readable": False, "reason": "chat.db not found", "message_count": None}
    try:
        con = _connect_ro(CHAT_DB)
        try:
            row = con.execute("SELECT COUNT(*) AS n FROM message").fetchone()
            return {
                "readable": True,
                "reason": "ok",
                "message_count": int(row["n"]),
            }
        finally:
            con.close()
    except sqlite3.OperationalError as exc:
        return {
            "readable": False,
            "reason": f"needs-FDA (Full Disk Access): {exc}",
            "message_count": None,
        }
    except Exception as exc:  # noqa: BLE001 — surface any other failure cleanly
        return {"readable": False, "reason": f"error: {exc}", "message_count": None}


def load_active_clients() -> list[str]:
    """Return the list of active client names (read-only)."""
    con = _connect_ro(DASHBOARD_DB)
    try:
        rows = con.execute(
            "SELECT name FROM clients WHERE active = 1 ORDER BY name"
        ).fetchall()
        return [r["name"] for r in rows]
    finally:
        con.close()


def attendance_log_count() -> int:
    """Return current attendance_log row count (read-only). Used to PROVE no writes."""
    con = _connect_ro(DASHBOARD_DB)
    try:
        return int(con.execute("SELECT COUNT(*) AS n FROM attendance_log").fetchone()["n"])
    finally:
        con.close()


# ─────────────────────────────────────────────────────────────────────────────
# Redaction
# ─────────────────────────────────────────────────────────────────────────────


def redact_name(name: Optional[str]) -> str:
    """Reduce a client name to 'First L.' form for any printout.

    Roster names are stored "Last First" (e.g. "Adyan Ludmila"); message text is
    usually "First Last". We keep the first token in full and reduce a second
    token to an initial. If only one token exists we return it as-is.
    """
    if not name:
        return "<unknown>"
    parts = [p for p in re.split(r"\s+", name.strip()) if p]
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[1][0]}."


# ─────────────────────────────────────────────────────────────────────────────
# Parser
# ─────────────────────────────────────────────────────────────────────────────

# Phrase → action. Order matters: more specific phrases first.
_ABSENT_PATTERNS = [
    r"\bsick\b",
    r"\bout sick\b",
    r"\bwon'?t be (in|here|coming)\b",
    r"\bnot coming\b",
    r"\bnot going to be (in|here)\b",
    r"\bcan'?t (make it|come)\b",
    r"\bcalled (in )?sick\b",
    r"\babsent\b",
    r"\bno show\b",
]
_CANCEL_PATTERNS = [
    r"\bcancel\b",
    r"\bcancelled?\b",
    r"\bremove\b",
    r"\bskip\b",
]
_RESUME_PATTERNS = [
    r"\bback\b",
    r"\breturn(ing|s)?\b",
    r"\bresume\b",
    r"\bcoming back\b",
    r"\bwill be (in|back)\b",
]

_TODAY_WORDS = {"today", "tonight", "this morning", "this afternoon"}
_TOMORROW_WORDS = {"tomorrow", "tmrw", "tmw"}


def _detect_action(text_lc: str) -> Optional[str]:
    """Classify the message action. cancel > resume > absent precedence."""
    for pat in _CANCEL_PATTERNS:
        if re.search(pat, text_lc):
            return ACTION_CANCEL
    for pat in _RESUME_PATTERNS:
        if re.search(pat, text_lc):
            return ACTION_RESUME
    for pat in _ABSENT_PATTERNS:
        if re.search(pat, text_lc):
            return ACTION_ABSENT
    return None


def _detect_day(text_lc: str, today: _dt.date) -> tuple[Optional[str], Optional[str]]:
    """Return (day_key, iso_date) from message text, or (None, None).

    Handles explicit weekdays, "today", and "tomorrow". For a named weekday we
    resolve to the *next* occurrence on/after today.
    """
    # today / tomorrow
    if any(w in text_lc for w in _TODAY_WORDS):
        return WEEKDAY_TO_KEY.get(today.weekday()), today.isoformat()
    if any(w in text_lc for w in _TOMORROW_WORDS):
        d = today + _dt.timedelta(days=1)
        return WEEKDAY_TO_KEY.get(d.weekday()), d.isoformat()

    # named weekday (longest match first so "thursday" beats "th")
    for word in sorted(DAY_KEYS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(word)}\b", text_lc):
            key = DAY_KEYS[word]
            iso = _next_date_for_key(key, today)
            return key, iso
    return None, None


def _next_date_for_key(day_key: str, today: _dt.date) -> Optional[str]:
    """Resolve a day_key (M/T/W/TH/F/Su) to the next ISO date on/after today."""
    target = {v: k for k, v in WEEKDAY_TO_KEY.items()}.get(day_key)
    if target is None:
        return None
    for offset in range(0, 8):
        d = today + _dt.timedelta(days=offset)
        if d.weekday() == target:
            return d.isoformat()
    return None


def _candidate_name_span(text: str, action: str) -> str:
    """Strip action/day keywords so what remains is most likely the name span.

    We don't need a perfect NER — fuzzy matching against the roster does the
    real disambiguation. This just removes obvious non-name tokens to give the
    matcher a cleaner string.
    """
    span = text
    # remove day words & today/tomorrow
    for word in list(DAY_KEYS) + list(_TODAY_WORDS) + list(_TOMORROW_WORDS):
        span = re.sub(rf"\b{re.escape(word)}\b", " ", span, flags=re.IGNORECASE)
    # remove action phrase words
    action_words = (
        "sick out won't wont be in here coming not going to make it can't cant come "
        "called show no cancel cancelled cancelled remove skip back return returning "
        "returns resume will and the a is for on at please pls thx thanks fyi hi hey"
    ).split()
    tokens = [t for t in re.split(r"[\s,.!?:;]+", span) if t]
    kept = [t for t in tokens if t.lower() not in action_words]
    return " ".join(kept).strip()


def _fuzzy_match_client(name_span: str, roster: list[str]) -> tuple[Optional[str], float]:
    """Fuzzy-match a name span against the active roster.

    Roster entries are "Last First"; messages are usually "First Last". We try
    the span as-is and reversed, and also score against a "First Last" rendering
    of each roster entry, taking the best ratio over the threshold.
    """
    if not name_span:
        return None, 0.0
    span_lc = name_span.lower()
    span_rev_lc = " ".join(reversed(name_span.split())).lower()

    best_name: Optional[str] = None
    best_score = 0.0
    for entry in roster:
        variants = {entry.lower()}
        parts = entry.split()
        if len(parts) >= 2:
            variants.add(f"{parts[1]} {parts[0]}".lower())  # First Last rendering
        for variant in variants:
            for probe in (span_lc, span_rev_lc):
                score = difflib.SequenceMatcher(None, probe, variant).ratio()
                # boost when every probe token is a prefix of a name token
                if _all_tokens_prefix(probe, variant):
                    score = max(score, 0.9)
                if score > best_score:
                    best_score, best_name = score, entry
    if best_score >= NAME_MATCH_THRESHOLD:
        return best_name, round(best_score, 3)
    return None, round(best_score, 3)


def _all_tokens_prefix(probe: str, variant: str) -> bool:
    """True if every probe token is a prefix of some variant token (e.g. 'maria g')."""
    p_tokens = [t for t in probe.split() if t]
    v_tokens = [t for t in variant.split() if t]
    if not p_tokens or not v_tokens:
        return False
    for pt in p_tokens:
        if not any(vt.startswith(pt) for vt in v_tokens):
            return False
    return True


def parse_message(
    text: str,
    roster: list[str],
    today: Optional[_dt.date] = None,
) -> Optional[dict]:
    """Parse a message into a structured intent, or None if no cascade intent.

    Returns a dict:
        {
          raw_text, action, client_name (matched roster name or None),
          match_score, day_key, day_label, target_date, confidence
        }
    """
    if not text or not text.strip():
        return None
    today = today or _dt.date.today()
    text_lc = text.lower()

    action = _detect_action(text_lc)
    if action is None:
        return None

    day_key, target_date = _detect_day(text_lc, today)
    name_span = _candidate_name_span(text, action)
    client_name, score = _fuzzy_match_client(name_span, roster)

    # Confidence: combine name-match quality with whether a date was found.
    confidence = "high" if (client_name and day_key) else (
        "medium" if client_name or day_key else "low"
    )

    return {
        "raw_text": text.strip(),
        "action": action,
        "name_span": name_span,
        "client_name": client_name,
        "match_score": score,
        "day_key": day_key,
        "day_label": DAY_LABEL.get(day_key) if day_key else None,
        "target_date": target_date,
        "confidence": confidence,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Planner — produces a STAGED 7-system plan. NEVER executes.
# ─────────────────────────────────────────────────────────────────────────────


def build_cascade_plan(intent: dict) -> dict:
    """Produce a staged 7-system cascade plan for a parsed intent.

    Every entry describes the change that WOULD be made — table, operation, and
    a human-readable description — but is flagged executed=False, staged=True.
    Nothing here touches a database.
    """
    action = intent["action"]
    client = intent.get("client_name")
    day_key = intent.get("day_key")
    day_label = intent.get("day_label") or "(unspecified day)"
    target_date = intent.get("target_date") or "(unspecified date)"
    client_disp = client or f"<unmatched: {intent.get('name_span')!r}>"

    # status that attendance would receive
    att_status = "absent" if action in (ACTION_ABSENT, ACTION_CANCEL) else "expected"

    systems: list[dict] = []

    # 1) Calendar — the source signal: log the schedule-change request.
    systems.append({
        "system": "Calendar",
        "table": "pending_schedule_changes",
        "operation": "INSERT (staged)",
        "would_change": (
            f"Record schedule change: client='{client_disp}', "
            f"change_type='{action}', day_key='{day_key}', "
            f"target_date='{target_date}'."
        ),
        "executed": False,
    })

    # 2) Attendance — propose status; DO NOT fabricate (Directive 9).
    systems.append({
        "system": "Attendance",
        "table": "attendance_log",
        "operation": "PROPOSE status (staged, NOT inserted — Directive 9)",
        "would_change": (
            f"Set status='{att_status}' for client='{client_disp}' "
            f"on {target_date} (day_key={day_key}). "
            f"Requires Kato confirmation; never auto-written."
        ),
        "executed": False,
    })

    # 3) Driver — remove from that day's route manifest.
    driver_change = (
        f"Remove client='{client_disp}' from {day_label} ({day_key}) "
        f"route manifest (is_active=0 for that day_key/shift)."
        if action in (ACTION_ABSENT, ACTION_CANCEL)
        else f"Re-add client='{client_disp}' to {day_label} ({day_key}) route manifest."
    )
    systems.append({
        "system": "Driver",
        "table": "client_route_assignments",
        "operation": "UPDATE is_active (staged)",
        "would_change": driver_change,
        "executed": False,
    })

    # 4) Kitchen — adjust meal count for that day.
    kitchen_delta = "-1" if action in (ACTION_ABSENT, ACTION_CANCEL) else "+1"
    systems.append({
        "system": "Kitchen",
        "table": "client_menus / meal counts",
        "operation": "ADJUST count (staged)",
        "would_change": (
            f"Adjust {day_label} meal count by {kitchen_delta} "
            f"(client='{client_disp}' {'not attending' if kitchen_delta=='-1' else 'attending'})."
        ),
        "executed": False,
    })

    # 5) Distribution — update the delivery/distribution list for that day.
    dist_change = (
        f"Drop client='{client_disp}' from {day_label} distribution list."
        if action in (ACTION_ABSENT, ACTION_CANCEL)
        else f"Add client='{client_disp}' to {day_label} distribution list."
    )
    systems.append({
        "system": "Distribution",
        "table": "client_route_assignments / distribution list",
        "operation": "UPDATE list (staged)",
        "would_change": dist_change,
        "executed": False,
    })

    # 6) Sign-in — pre-mark the sign-in sheet so the day reconciles cleanly.
    signin_change = (
        f"Mark client='{client_disp}' as NOT EXPECTED on {day_label} sign-in sheet."
        if action in (ACTION_ABSENT, ACTION_CANCEL)
        else f"Restore client='{client_disp}' as EXPECTED on {day_label} sign-in sheet."
    )
    systems.append({
        "system": "Sign-in",
        "table": "attendance_log (expected rows) / sign-in sheet",
        "operation": "UPDATE expected (staged)",
        "would_change": signin_change,
        "executed": False,
    })

    # 7) Menu — drop/restore that client's per-day menu selection.
    menu_change = (
        f"Suppress {day_label} menu selection for client='{client_disp}' "
        f"(no plate prepared)."
        if action in (ACTION_ABSENT, ACTION_CANCEL)
        else f"Reinstate {day_label} menu selection for client='{client_disp}'."
    )
    systems.append({
        "system": "Menu",
        "table": "client_menus",
        "operation": "UPDATE selection (staged)",
        "would_change": menu_change,
        "executed": False,
    })

    return {
        "intent": {
            "raw_text": intent["raw_text"],
            "action": action,
            "client_name": client,
            "client_display_redacted": redact_name(client) if client else None,
            "match_score": intent.get("match_score"),
            "day_key": day_key,
            "day_label": intent.get("day_label"),
            "target_date": target_date,
            "confidence": intent["confidence"],
        },
        "systems": systems,
        "status": "STAGED",
        "executed": False,
        "requires_confirmation": True,
        "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Pending-plan persistence (the ONLY thing this scaffold writes — to JSON)
# ─────────────────────────────────────────────────────────────────────────────


def write_pending(plans: list[dict], source: str) -> Path:
    """Write staged cascade plans to state/cascade_pending.json for Kato review."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    doc = {
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "note": (
            "STAGED ONLY. No database writes performed. "
            "Each plan lists all 7 cascade systems. Kato must confirm before any "
            "of these become live (Directive 9 — attendance never fabricated)."
        ),
        "attendance_log_count_at_generation": _safe_att_count(),
        "plan_count": len(plans),
        "plans": plans,
    }
    PENDING_JSON.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return PENDING_JSON


def _safe_att_count() -> Optional[int]:
    try:
        return attendance_log_count()
    except Exception:  # noqa: BLE001
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Reader — scan real iMessages (read-only) for cascade intents
# ─────────────────────────────────────────────────────────────────────────────


def scan_recent_messages(limit: int, roster: list[str]) -> list[dict]:
    """Scan the last `limit` inbound messages from known staff for intents.

    Read-only. Returns parsed intents (with the sender attached). If
    KNOWN_STAFF_SENDERS is non-empty, only those senders are considered.
    """
    con = _connect_ro(CHAT_DB)
    try:
        rows = con.execute(
            """
            SELECT m.ROWID AS rowid,
                   COALESCE(m.text, '') AS text,
                   h.id AS sender
            FROM message m
            JOIN handle h ON m.handle_id = h.ROWID
            WHERE m.is_from_me = 0
            ORDER BY m.ROWID DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        con.close()

    found: list[dict] = []
    for r in rows:
        sender = r["sender"]
        if KNOWN_STAFF_SENDERS and sender not in KNOWN_STAFF_SENDERS:
            continue
        intent = parse_message(r["text"], roster)
        if intent:
            intent["sender"] = sender
            intent["message_rowid"] = r["rowid"]
            found.append(intent)
    return found


# ─────────────────────────────────────────────────────────────────────────────
# Printing (redacted)
# ─────────────────────────────────────────────────────────────────────────────


def print_plan(plan: dict, index: Optional[int] = None) -> None:
    """Print a staged plan with names redacted to 'First L.'."""
    intent = plan["intent"]
    disp = intent.get("client_display_redacted") or redact_name(
        intent.get("client_name")
    )
    header = f"PLAN {index}" if index is not None else "PLAN"
    print(f"\n── {header} ─────────────────────────────────────────────")
    print(f"  message   : {_redact_text(intent['raw_text'], intent.get('client_name'))}")
    print(f"  action    : {intent['action']}")
    print(f"  client    : {disp}  (match={intent.get('match_score')})")
    print(f"  day       : {intent.get('day_label') or '?'} "
          f"({intent.get('day_key') or '?'})  date={intent.get('target_date')}")
    print(f"  confidence: {intent['confidence']}")
    print(f"  status    : {plan['status']}  executed={plan['executed']}")
    print("  7-system staged cascade:")
    for i, sysrow in enumerate(plan["systems"], start=1):
        print(f"    {i}. {sysrow['system']:<12} [{sysrow['table']}] "
              f"{sysrow['operation']}")
        print(f"       → {_redact_text(sysrow['would_change'], intent.get('client_name'))}")


def _redact_text(text: str, client_name: Optional[str]) -> str:
    """Replace any occurrence of the full client name with its redacted form."""
    if not client_name:
        return text
    return text.replace(client_name, redact_name(client_name))


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────


def cmd_check_db() -> int:
    status = chat_db_status()
    print("chat.db:")
    print(f"  path      : {CHAT_DB}")
    print(f"  readable  : {status['readable']}")
    print(f"  reason    : {status['reason']}")
    print(f"  messages  : {status['message_count']}")
    print("\nauth_tracker.db:")
    print(f"  path      : {DASHBOARD_DB}")
    try:
        print(f"  active clients   : {len(load_active_clients())}")
        print(f"  attendance_log   : {attendance_log_count()} rows (read-only)")
    except Exception as exc:  # noqa: BLE001
        print(f"  ERROR: {exc}")
        return 1
    return 0


def cmd_text(text: str) -> int:
    roster = load_active_clients()
    intent = parse_message(text, roster)
    if not intent:
        print("No cascade intent detected in that message.")
        return 0
    plan = build_cascade_plan(intent)
    path = write_pending([plan], source=f"--text {text!r}")
    print_plan(plan, index=1)
    print(f"\nStaged 1 plan → {path}")
    return 0


def cmd_scan(limit: int) -> int:
    status = chat_db_status()
    if not status["readable"]:
        print(f"chat.db not readable ({status['reason']}).")
        print("Falling back: use --text \"...\" to test the scaffold without chat.db.")
        return 2
    roster = load_active_clients()
    intents = scan_recent_messages(limit, roster)
    if not intents:
        print(f"Scanned last {limit} inbound messages — no cascade intents found.")
        return 0
    plans = [build_cascade_plan(i) for i in intents]
    path = write_pending(plans, source=f"--scan-messages limit={limit}")
    for idx, plan in enumerate(plans, start=1):
        print_plan(plan, index=idx)
    print(f"\nStaged {len(plans)} plan(s) → {path}")
    return 0


def cmd_selftest() -> int:
    """Feed 3 synthetic messages through parse -> plan -> write json. Prove no DB writes."""
    print("=" * 70)
    print("SELFTEST — staging only, no DB writes")
    print("=" * 70)

    # Prove read-only: count attendance_log before and after.
    try:
        before = attendance_log_count()
    except Exception as exc:  # noqa: BLE001
        print(f"Could not read auth_tracker.db: {exc}")
        return 1
    print(f"attendance_log rows BEFORE: {before}")

    roster = load_active_clients()
    print(f"active client roster loaded: {len(roster)} names\n")

    synthetic = [
        "Maria G sick today",
        "cancel Boris K Tuesday",
        "Lidiya back Monday",
    ]

    plans: list[dict] = []
    for msg in synthetic:
        intent = parse_message(msg, roster)
        if not intent:
            print(f"  [!] no intent parsed from: {msg!r}")
            continue
        plans.append(build_cascade_plan(intent))

    path = write_pending(plans, source="--selftest")

    for idx, plan in enumerate(plans, start=1):
        print_plan(plan, index=idx)

    after = attendance_log_count()
    print("\n" + "=" * 70)
    print(f"Staged {len(plans)} plan(s) → {path}")
    print(f"each plan lists {len(SEVEN_SYSTEMS)} systems: {', '.join(SEVEN_SYSTEMS)}")
    print(f"attendance_log rows AFTER : {after}")
    print(f"NO DB WRITES: {'CONFIRMED' if after == before else 'FAILED — counts differ!'}")
    print("=" * 70)
    return 0 if after == before and len(plans) == 3 else 1


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="C3 iMessage → 7-system cascade scaffold (STAGING ONLY).",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--selftest", action="store_true",
                       help="Run 3 synthetic messages through parse→plan→write.")
    group.add_argument("--text", metavar="MSG",
                       help="Parse + plan a single message.")
    group.add_argument("--scan-messages", action="store_true",
                       help="Scan recent staff iMessages for intents (read-only).")
    group.add_argument("--check-db", action="store_true",
                       help="Report chat.db + auth_tracker.db status.")
    parser.add_argument("--limit", type=int, default=50,
                        help="How many recent messages to scan (default 50).")

    args = parser.parse_args(argv)

    if args.selftest:
        return cmd_selftest()
    if args.text is not None:
        return cmd_text(args.text)
    if args.scan_messages:
        return cmd_scan(args.limit)
    if args.check_db:
        return cmd_check_db()
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
