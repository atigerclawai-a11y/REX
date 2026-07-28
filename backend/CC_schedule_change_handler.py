"""
CC_schedule_change_handler.py — GOJ Schedule Change Handler
============================================================
Parses natural language schedule changes from Telegram messages and
executes the actual DB writes. Wired into Rexxie's detect_command().

Handles:
  • Day swaps       "Ivanova is coming Tuesday instead of Wednesday"
  • Absences        "Ivanova won't be here Thursday" / "Ivanova absent Friday"
  • Day additions   "Ivanova is also coming Monday this week"
  • Day removals    "Ivanova not coming Friday"
  • Present/arrived "Ivanova arrived" / "Ivanova is here today"

DB writes:
  • clients.day_X_actual  — for day swaps/additions/removals
  • pending_schedule_changes — every change, confirmed=0 until 9pm
  • attendance_log         — for absences and confirmed arrivals

9pm confirmation flow:
  • Query pending_schedule_changes WHERE confirmed=0
  • Ask: one-time or recurring?
  • Recurring (confirmed=1): also update day_X_base to match _actual
  • One-time  (confirmed=2): revert day_X_actual back to day_X_base
"""

import re
import sqlite3
import difflib
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"

# ── Day name → key mapping ───────────────────────────────────────────────────
DAY_ALIASES: dict[str, str] = {
    # English
    'monday': 'M',    'mon': 'M',
    'tuesday': 'T',   'tue': 'T',   'tues': 'T',
    'wednesday': 'W', 'wed': 'W',
    'thursday': 'TH', 'thu': 'TH',  'thur': 'TH', 'thurs': 'TH',
    'friday': 'F',    'fri': 'F',
    'saturday': 'Su', 'sat': 'Su',
    # Russian
    'понедельник': 'M', 'пн': 'M',
    'вторник': 'T',     'вт': 'T',
    'среда': 'W',       'ср': 'W',
    'четверг': 'TH',    'чт': 'TH',
    'пятница': 'F',     'пт': 'F',
    'суббота': 'Su',    'сб': 'Su',
    # Abbreviations and shorthand
    'm': 'M', 't': 'T', 'w': 'W', 'th': 'TH', 'f': 'F', 'su': 'Su', 'sa': 'Su',
}

DAY_LABEL = {'M': 'Monday', 'T': 'Tuesday', 'W': 'Wednesday',
             'TH': 'Thursday', 'F': 'Friday', 'Su': 'Saturday'}

# ── Pattern groups ───────────────────────────────────────────────────────────
# Intent: SWAP  — "X coming DAY instead of DAY" / "X switching from DAY to DAY"
SWAP_PATTERNS = [
    r'(.+?)\s+(?:is\s+)?coming\s+(\w+)\s+instead\s+of\s+(\w+)',
    r'(.+?)\s+(?:is\s+)?coming\s+(\w+)\s+not\s+(\w+)',
    r'(.+?)\s+switching\s+from\s+(\w+)\s+to\s+(\w+)',
    r'(.+?)\s+moving\s+from\s+(\w+)\s+to\s+(\w+)',
    r'move\s+(.+?)\s+from\s+(\w+)\s+to\s+(\w+)',
    r'(.+?)\s+instead\s+of\s+(\w+)\s+coming\s+(\w+)',
]

# Intent: ABSENT — "X won't be here DAY" / "X absent DAY" / "X not coming DAY"
ABSENT_PATTERNS = [
    r'(.+?)\s+(?:won\'t|will\s+not|wont)\s+be\s+(?:here|in|coming)\s+(?:on\s+)?(\w+)',
    r'(.+?)\s+(?:is\s+)?(?:not\s+coming|not\s+in)\s+(?:on\s+)?(\w+)',
    r'(.+?)\s+(?:is\s+)?absent\s+(?:on\s+)?(\w+)',
    r'(.+?)\s+(?:is\s+)?out\s+(?:on\s+)?(\w+)',
    r'(.+?)\s+not\s+here\s+(\w+)',           # "X not here DAY" (requires 'not')
    r'(.+?)\s+пропустит\s+(\w+)',            # Russian: "will skip [day]"
    r'(.+?)\s+не\s+придёт\s+(\w+)',          # Russian: "won't come [day]"
]

# Intent: ADD — "X also coming DAY" / "X adding DAY"
ADD_PATTERNS = [
    r'(.+?)\s+(?:is\s+)?also\s+coming\s+(?:on\s+)?(\w+)',
    r'(.+?)\s+adding\s+(\w+)',
    r'(.+?)\s+(?:will\s+)?come\s+(?:on\s+)?(\w+)\s+(?:too|also|as\s+well)',
    r'add\s+(.+?)\s+(?:on\s+|to\s+)?(\w+)',
    r'(.+?)\s+придёт\s+и\s+в\s+(\w+)',  # Russian: "also coming on [day]"
]

# Intent: REMOVE — "X not coming Friday anymore" / "X removing Friday"
REMOVE_PATTERNS = [
    r'(.+?)\s+(?:is\s+)?removing\s+(\w+)',
    r'(.+?)\s+dropping\s+(\w+)',
    r'(.+?)\s+no\s+longer\s+coming\s+(?:on\s+)?(\w+)',
    r'(.+?)\s+not\s+coming\s+(?:on\s+)?(\w+)\s+anymore',
]

# Intent: PRESENT — "Ivanova is here" / "Ivanova arrived"
PRESENT_PATTERNS = [
    r'(.+?)\s+(?:is\s+)?(?:here|arrived|in|showed\s+up|showed up)',
    r'(.+?)\s+(?:came|came\s+in)',
]


def _parse_day(word: str) -> Optional[str]:
    """Convert a day word to its key ('M', 'T', etc.)."""
    return DAY_ALIASES.get(word.lower().strip())


def _fuzzy_match_client(name_hint: str, clients: list[dict],
                         threshold: float = 0.60) -> Optional[dict]:
    """Fuzzy-match a name hint against the clients list. Returns best match or None."""
    name_hint = name_hint.strip().lower()
    if not name_hint:
        return None

    best_score = 0.0
    best_client = None
    for c in clients:
        cname = c['name'].lower()
        # Full name match
        score = difflib.SequenceMatcher(None, name_hint, cname).ratio()
        # Partial — last name only
        parts = cname.split()
        if parts:
            last_score = difflib.SequenceMatcher(None, name_hint, parts[0]).ratio()
            score = max(score, last_score + 0.1 if last_score > 0.7 else last_score)
        # First name only
        if len(parts) > 1:
            first_score = difflib.SequenceMatcher(None, name_hint, parts[1]).ratio()
            score = max(score, first_score)
        if score > best_score:
            best_score = score
            best_client = c

    if best_score >= threshold and best_client:
        return best_client
    return None


def _load_clients(conn: sqlite3.Connection) -> list[dict]:
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT client_id, name, shift,
               day_M_actual, day_M_base,
               day_T_actual, day_T_base,
               day_W_actual, day_W_base,
               day_TH_actual, day_TH_base,
               day_F_actual, day_F_base,
               day_Su_actual, day_Su_base
        FROM clients WHERE active=1
    """)
    return [dict(r) for r in cur.fetchall()]


def _log_pending_change(cur: sqlite3.Cursor, client_id: int, client_name: str,
                         change_type: str, field_changed: str,
                         old_value: str, new_value: str,
                         day_key: str, note: str = '') -> int:
    cur.execute("""
        INSERT INTO pending_schedule_changes
            (client_id, client_name, change_type, field_changed,
             old_value, new_value, changed_by, day_key, note, confirmed)
        VALUES (?, ?, ?, ?, ?, ?, 'Rexxie', ?, ?, 0)
    """, (client_id, client_name, change_type, field_changed,
          old_value, new_value, day_key, note))
    return cur.lastrowid


def _log_attendance(cur: sqlite3.Cursor, log_date: str, day_key: str,
                    shift: int, client_name: str, status: str, note: str = ''):
    # Upsert — avoid duplicate entries for same client+date
    cur.execute("""
        INSERT INTO attendance_log (log_date, day_key, shift, client_name, status, source, note)
        VALUES (?, ?, ?, ?, ?, 'telegram', ?)
        ON CONFLICT DO NOTHING
    """, (log_date, day_key, shift or 0, client_name, status, note))


def _today_day_key() -> str:
    """Return today's day key (M/T/W/TH/F/Su)."""
    keys = ['M', 'T', 'W', 'TH', 'F', 'Su', 'Su']
    return keys[date.today().weekday()]


def _next_occurrence(day_key: str) -> date:
    """Return the next date (from today) that falls on day_key."""
    target_wday = {'M': 0, 'T': 1, 'W': 2, 'TH': 3, 'F': 4, 'Su': 5}[day_key]
    today = date.today()
    days_ahead = (target_wday - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


# ── Main handler class ───────────────────────────────────────────────────────

class ScheduleChangeHandler:
    """
    Detects and executes schedule changes from natural language.
    Call detect_and_execute(text) — returns a reply string if a change
    was detected, or None if the message isn't a schedule change.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    # ── Public API ──────────────────────────────────────────────────────────

    def detect_and_execute(self, text: str) -> Optional[str]:
        """
        Try to parse text as a schedule change.
        Returns a confirmation string if a change was detected + executed,
        None if no schedule change was found.
        """
        result = self._parse(text)
        if not result:
            return None

        intent   = result['intent']
        name_hint = result['name_hint']
        from_day  = result.get('from_day')
        to_day    = result.get('to_day')

        conn = self._conn()
        clients = _load_clients(conn)
        client = _fuzzy_match_client(name_hint, clients)

        if not client:
            conn.close()
            return (
                f"⚠️ Couldn't find a client matching **{name_hint}**. "
                f"Try a last name or full name."
            )

        cname = client['name']
        cid   = client['client_id']
        shift = client.get('shift') or 0
        cur   = conn.cursor()
        today_str  = date.today().isoformat()
        today_key  = _today_day_key()

        try:
            reply = ''

            if intent == 'swap' and from_day and to_day:
                reply = self._execute_swap(cur, client, from_day, to_day, today_str, today_key)

            elif intent == 'absent':
                absent_day = to_day or from_day or today_key
                reply = self._execute_absent(cur, client, absent_day, today_str)

            elif intent == 'add' and to_day:
                reply = self._execute_add(cur, client, to_day, today_str)

            elif intent == 'remove' and (from_day or to_day):
                remove_day = from_day or to_day
                reply = self._execute_remove(cur, client, remove_day, today_str)

            elif intent == 'present':
                reply = self._execute_present(cur, client, today_key, today_str)

            else:
                conn.close()
                return None

            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Schedule change DB error: {e}")
            conn.close()
            return f"⚠️ DB error applying change: {e}"

        conn.close()
        return reply

    def get_pending_report(self) -> str:
        """
        Build the 9pm pending changes report.
        Returns a formatted string listing all unconfirmed changes.
        """
        conn = self._conn()
        cur  = conn.cursor()
        cur.execute("""
            SELECT id, client_name, change_type, field_changed,
                   old_value, new_value, day_key, note, changed_at
            FROM pending_schedule_changes
            WHERE confirmed = 0
            ORDER BY changed_at ASC
        """)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()

        if not rows:
            return "✅ No pending schedule changes tonight — all clear."

        lines = [f"📋 **Pending Schedule Changes ({len(rows)})**\n"]
        lines.append("Reply with the change ID + 'once' or 'permanent' to confirm.\n")
        for r in rows:
            day_label = DAY_LABEL.get(r['day_key'], r['day_key'])
            ct = r['change_type']
            if ct == 'day_swap':
                desc = (f"moved from {DAY_LABEL.get(r['old_value'], r['old_value'])} "
                        f"→ {DAY_LABEL.get(r['new_value'], r['new_value'])}")
            elif ct == 'absent':
                desc = f"absent {day_label}"
            elif ct == 'day_add':
                desc = f"added {day_label}"
            elif ct == 'day_remove':
                desc = f"removed {day_label}"
            elif ct == 'present':
                desc = f"confirmed present {day_label}"
            else:
                desc = f"{ct}: {r['field_changed']} {r['old_value']}→{r['new_value']}"
            note = f" ({r['note']})" if r['note'] else ''
            lines.append(f"  [{r['id']}] **{r['client_name']}** — {desc}{note}")

        lines.append("\nExample: `[3] once` or `[3] permanent`")
        return "\n".join(lines)

    def confirm_change(self, change_id: int, recurring: bool) -> str:
        """
        Confirm a pending change as one-time or recurring.
        - recurring=True  → update _base to match _actual; confirmed=1
        - recurring=False → revert _actual back to _base; confirmed=2
        """
        conn = self._conn()
        cur  = conn.cursor()
        cur.execute("""
            SELECT id, client_id, client_name, change_type, field_changed,
                   old_value, new_value, day_key
            FROM pending_schedule_changes WHERE id=? AND confirmed=0
        """, (change_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return f"⚠️ No pending change found with ID {change_id}."

        row = dict(row)
        cid   = row['client_id']
        cname = row['client_name']
        ct    = row['change_type']
        now_str = datetime.utcnow().isoformat()

        try:
            if recurring:
                # Make permanent: also update _base to match _actual
                if ct == 'day_swap':
                    old_day = row['old_value']
                    new_day = row['new_value']
                    cur.execute(f"UPDATE clients SET day_{old_day}_base=0, day_{new_day}_base=1 WHERE client_id=?", (cid,))
                elif ct == 'day_add':
                    day_key = row['day_key']
                    cur.execute(f"UPDATE clients SET day_{day_key}_base=1 WHERE client_id=?", (cid,))
                elif ct == 'day_remove':
                    day_key = row['day_key']
                    cur.execute(f"UPDATE clients SET day_{day_key}_base=0 WHERE client_id=?", (cid,))
                cur.execute(
                    "UPDATE pending_schedule_changes SET confirmed=1, confirmed_at=? WHERE id=?",
                    (now_str, change_id)
                )
                label = "**permanent**"
            else:
                # One-time: revert _actual back to _base
                if ct == 'day_swap':
                    old_day = row['old_value']
                    new_day = row['new_value']
                    # Revert: old_actual=1, new_actual=0 (back to base)
                    cur.execute(f"UPDATE clients SET day_{old_day}_actual=1, day_{new_day}_actual=0 WHERE client_id=?", (cid,))
                elif ct == 'day_add':
                    day_key = row['day_key']
                    cur.execute(f"UPDATE clients SET day_{day_key}_actual=0 WHERE client_id=?", (cid,))
                elif ct == 'day_remove':
                    day_key = row['day_key']
                    cur.execute(f"UPDATE clients SET day_{day_key}_actual=1 WHERE client_id=?", (cid,))
                cur.execute(
                    "UPDATE pending_schedule_changes SET confirmed=2, confirmed_at=? WHERE id=?",
                    (now_str, change_id)
                )
                label = "**one-time** (schedule reverts next week)"

            conn.commit()
        except Exception as e:
            conn.rollback()
            conn.close()
            return f"⚠️ Error confirming change: {e}"

        conn.close()
        day_label = DAY_LABEL.get(row['day_key'], row['day_key'])
        return f"✓ [{change_id}] **{cname}** — confirmed {label}."

    def detect_confirm_command(self, text: str) -> Optional[str]:
        """
        Detect '(once|permanent|recurring|one-time)' after a change ID bracket.
        Returns reply string or None.
        """
        m = re.search(r'\[(\d+)\]\s*(once|one.time|permanent|recurring|perm)', text, re.IGNORECASE)
        if not m:
            # Also detect plain "3 once" or "3 permanent"
            m = re.search(r'\b(\d+)\s+(once|one.time|permanent|recurring|perm)\b', text, re.IGNORECASE)
        if not m:
            return None

        change_id = int(m.group(1))
        keyword   = m.group(2).lower()
        recurring = keyword in ('permanent', 'recurring', 'perm')
        return self.confirm_change(change_id, recurring)

    # ── Intent parsers ──────────────────────────────────────────────────────

    def _parse(self, text: str) -> Optional[dict]:
        """Try all pattern groups. Returns intent dict or None."""
        t = text.strip()

        # 1. Swap (most specific — requires two days)
        for pat in SWAP_PATTERNS:
            m = re.search(pat, t, re.IGNORECASE)
            if m:
                g = m.groups()
                day1 = _parse_day(g[1]) if len(g) > 1 else None
                day2 = _parse_day(g[2]) if len(g) > 2 else None
                if day1 and day2:
                    # "coming DAY1 instead of DAY2" → to=DAY1, from=DAY2
                    if 'instead' in pat or re.search(r'\bnot\b', pat):
                        return {'intent': 'swap', 'name_hint': g[0].strip(),
                                'to_day': day1, 'from_day': day2}
                    else:
                        return {'intent': 'swap', 'name_hint': g[0].strip(),
                                'from_day': day1, 'to_day': day2}

        # 2. Add
        for pat in ADD_PATTERNS:
            m = re.search(pat, t, re.IGNORECASE)
            if m:
                g = m.groups()
                day = _parse_day(g[1] if len(g) > 1 else g[0])
                name = g[0].strip() if len(g) > 1 else g[1].strip()
                if day:
                    return {'intent': 'add', 'name_hint': name, 'to_day': day}

        # 3. Remove
        for pat in REMOVE_PATTERNS:
            m = re.search(pat, t, re.IGNORECASE)
            if m:
                g = m.groups()
                day = _parse_day(g[1] if len(g) > 1 else g[0])
                name = g[0].strip()
                if day:
                    return {'intent': 'remove', 'name_hint': name, 'from_day': day}

        # 4. Present — check BEFORE absent so "X is here" routes correctly
        _NEG = re.compile(r"\b(not|won't|wont|will\s+not|didn't|doesn't|no|never)\b", re.IGNORECASE)
        for pat in PRESENT_PATTERNS:
            m = re.search(pat, t, re.IGNORECASE)
            if m:
                name = m.group(1).strip()
                # Skip if any negation appears before "here/arrived" in the full match
                if _NEG.search(m.group(0)):
                    continue
                # Strip trailing noise words to clean the name
                name = re.sub(r'\s+(is|has|just|already)$', '', name, flags=re.IGNORECASE)
                if len(name) > 3:
                    return {'intent': 'present', 'name_hint': name}

        # 5. Absent
        for pat in ABSENT_PATTERNS:
            m = re.search(pat, t, re.IGNORECASE)
            if m:
                g = m.groups()
                day = _parse_day(g[1]) if len(g) > 1 else None
                name = g[0].strip()
                return {'intent': 'absent', 'name_hint': name, 'to_day': day}

        return None

    # ── DB executors ────────────────────────────────────────────────────────

    def _execute_swap(self, cur, client, from_day, to_day, today_str, today_key) -> str:
        cid   = client['client_id']
        cname = client['name']
        shift = client.get('shift') or 0

        # Guard: from_day must be currently scheduled
        if not client.get(f'day_{from_day}_actual'):
            return (
                f"⚠️ **{cname}** isn't currently scheduled for "
                f"{DAY_LABEL.get(from_day, from_day)} — nothing to swap from."
            )

        # Apply _actual change
        cur.execute(
            f"UPDATE clients SET day_{from_day}_actual=0, day_{to_day}_actual=1 WHERE client_id=?",
            (cid,)
        )

        # Log to pending_schedule_changes
        _log_pending_change(
            cur, cid, cname,
            change_type='day_swap',
            field_changed=f'day_{from_day}_actual→day_{to_day}_actual',
            old_value=from_day,
            new_value=to_day,
            day_key=to_day,
            note=f"Swapped {DAY_LABEL[from_day]} → {DAY_LABEL[to_day]}",
        )

        # Log absence from from_day if that day is today or upcoming this week
        target_date = _next_occurrence(from_day)
        _log_attendance(cur, target_date.isoformat(), from_day, shift, cname,
                        'absent', note=f'Day swap to {DAY_LABEL[to_day]}')

        from_label = DAY_LABEL.get(from_day, from_day)
        to_label   = DAY_LABEL.get(to_day, to_day)
        return (
            f"✓ **{cname}** moved {from_label} → {to_label}.\n"
            f"Sheets updated. I'll ask tonight: one-time or recurring?"
        )

    def _execute_absent(self, cur, client, day_key, today_str) -> str:
        cid   = client['client_id']
        cname = client['name']
        shift = client.get('shift') or 0
        day_label = DAY_LABEL.get(day_key, day_key)

        target_date = _next_occurrence(day_key)
        if day_key == _today_day_key():
            target_date = date.today()

        _log_attendance(cur, target_date.isoformat(), day_key, shift, cname,
                        'absent', note='Called in absent via Telegram')
        _log_pending_change(
            cur, cid, cname,
            change_type='absent',
            field_changed='attendance_log',
            old_value='expected',
            new_value='absent',
            day_key=day_key,
        )

        return (
            f"✓ **{cname}** marked absent {day_label} "
            f"({target_date.strftime('%b %d')}).\n"
            f"Logged. I'll note it in tonight's report."
        )

    def _execute_add(self, cur, client, day_key, today_str) -> str:
        cid   = client['client_id']
        cname = client['name']
        day_label = DAY_LABEL.get(day_key, day_key)

        if client.get(f'day_{day_key}_actual'):
            return f"ℹ️ **{cname}** is already scheduled for {day_label}."

        cur.execute(
            f"UPDATE clients SET day_{day_key}_actual=1 WHERE client_id=?", (cid,)
        )
        _log_pending_change(
            cur, cid, cname,
            change_type='day_add',
            field_changed=f'day_{day_key}_actual',
            old_value='0',
            new_value='1',
            day_key=day_key,
            note=f'Added {day_label}',
        )

        return (
            f"✓ **{cname}** added to {day_label}.\n"
            f"Tonight I'll ask: one-time or recurring?"
        )

    def _execute_remove(self, cur, client, day_key, today_str) -> str:
        cid   = client['client_id']
        cname = client['name']
        day_label = DAY_LABEL.get(day_key, day_key)

        if not client.get(f'day_{day_key}_actual'):
            return f"ℹ️ **{cname}** isn't currently scheduled for {day_label}."

        cur.execute(
            f"UPDATE clients SET day_{day_key}_actual=0 WHERE client_id=?", (cid,)
        )
        _log_pending_change(
            cur, cid, cname,
            change_type='day_remove',
            field_changed=f'day_{day_key}_actual',
            old_value='1',
            new_value='0',
            day_key=day_key,
            note=f'Removed {day_label}',
        )

        return (
            f"✓ **{cname}** removed from {day_label}.\n"
            f"Tonight I'll ask: one-time or recurring?"
        )

    def _execute_present(self, cur, client, day_key, today_str) -> str:
        cid   = client['client_id']
        cname = client['name']
        shift = client.get('shift') or 0
        day_label = DAY_LABEL.get(day_key, day_key)

        _log_attendance(cur, today_str, day_key, shift, cname,
                        'attended', note='Confirmed present via Telegram')
        _log_pending_change(
            cur, cid, cname,
            change_type='present',
            field_changed='attendance_log',
            old_value='expected',
            new_value='attended',
            day_key=day_key,
        )

        return f"✓ **{cname}** — confirmed present today ({day_label})."
