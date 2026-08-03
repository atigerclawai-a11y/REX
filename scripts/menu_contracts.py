#!/usr/bin/env python3
"""Write-time contract gate for GOJ client_menus (Kato-approved 2026-07-28).

Every INSERT/UPDATE into client_menus MUST pass through validate_row().
Violations are never silently dropped — they go to menu_quarantine (payload + reason + ts).

Enforced contracts:
  1. shift IN ('1','2')                        (kills day-letter-in-shift bug)
  2. all 4 dish cells non-null / non-empty     (kills incomplete-row bug)
  3. every dish IN locked catalog AND right category (week30_dishes.json, 42 dishes)
  4. menu_date weekday matches a day the client is scheduled
     (auth_tracker.db clients.day_X_actual IN (1,2)) — EXEMPT when
     source_sheet='ocr_scan' (form-day rows may be off-schedule)
  5. no duplicate (client,date,shift): on conflict ocr_scan WINS over
     fallback/house sources; anything else -> quarantine.

Stdlib only. Light RAM (catalog + schedule cached once per process).
REBUILT 2026-08-03 from Blue #191 recovered strings + locked-dish-catalog-v8 skill
(original deleted in the 05:01 scripts/ wipe).
"""
import json
import re
import sqlite3
from datetime import date
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parent / 'week30_dishes.json'
ALIASES_PATH = Path(__file__).resolve().parent / 'dish_aliases.json'
AUTH_DB = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'

FIELD2CAT = {
    'salad': 'САЛАТЫ',
    'soup': 'СУПЫ',
    'main': 'ГЛАВНОЕ',
    'side': 'ГАРНИР',
}

WEEKDAY_COL = {
    0: 'day_M_actual',
    1: 'day_T_actual',
    2: 'day_W_actual',
    3: 'day_TH_actual',
    4: 'day_F_actual',
    6: 'day_Su_actual',
}
VALID_SHIFTS = ('1', '2')
OCR = 'ocr_scan'

QUARANTINE_DDL = """CREATE TABLE IF NOT EXISTS menu_quarantine (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_name TEXT, menu_date TEXT, shift TEXT,
    salad TEXT, soup TEXT, main TEXT, side TEXT,
    source_sheet TEXT, reason TEXT, ts TEXT DEFAULT (datetime('now'))
)"""

_dish2field = None
_schedule = None


def _load_aliases():
    """dish value → canonical locked name (per category). Best-effort."""
    global _aliases
    try:
        _aliases = json.loads(ALIASES_PATH.read_text(encoding='utf-8'))
    except Exception:
        _aliases = {}


def canon(n):
    return ' '.join(sorted(re.sub(r'\b\d{5,}\b', '', n).lower().replace('-', ' ').split()))


def _load_catalog():
    """Build dish→field map from week30_dishes.json (42 locked dishes)."""
    global _dish2field
    if _dish2field is not None:
        return _dish2field
    _dish2field = {}
    try:
        cat = json.loads(CATALOG_PATH.read_text(encoding='utf-8'))
    except Exception:
        cat = {}
    for field, cat_name in FIELD2CAT.items():
        for dish in cat.get(cat_name, []):
            _dish2field[dish] = field
    _load_aliases()
    return _dish2field


def _load_schedule():
    """Client → set of weekdays scheduled (0=Mon..6=Sun). Cached once."""
    global _schedule
    if _schedule is not None:
        return _schedule
    _schedule = {}
    try:
        a = sqlite3.connect(f'file:{AUTH_DB}?mode=ro', uri=True)
        for r in a.execute('SELECT name, day_M_actual, day_T_actual, day_W_actual, day_TH_actual, day_F_actual, day_Su_actual FROM clients WHERE active=1'):
            _schedule[canon(r[0])] = {wd for wd, col in WEEKDAY_COL.items() if r[col] in (1, 2)}
        a.close()
    except Exception:
        pass
    return _schedule


def reset_caches():
    """Tests only: drop cached catalog/schedule after swapping AUTH_DB."""
    global _dish2field, _schedule
    _dish2field = None
    _schedule = None


def ensure_quarantine(db_conn):
    db_conn.execute(QUARANTINE_DDL)


def quarantine_row(db_conn, client_name, menu_date, shift, salad, soup, main, side, source_sheet, reason):
    ensure_quarantine(db_conn)
    db_conn.execute(
        'INSERT INTO menu_quarantine (client_name, menu_date, shift, salad, soup, main, side, source_sheet, reason) '
        'VALUES (?,?,?,?,?,?,?,?,?)',
        (client_name, menu_date, str(shift), salad, soup, main, side, source_sheet, reason))


def _canonical_dish(field, value):
    """Map alias/shorthand → locked catalog name; return (name, ok)."""
    if not value:
        return value, False
    v = str(value).strip()
    d2f = _load_catalog()
    if v in d2f and d2f[v] == field:
        return v, True
    aliases = _aliases.get(field, {}) if _aliases else {}
    canon_v = aliases.get(v)
    if canon_v and d2f.get(canon_v) == field:
        return canon_v, True
    # strip ' без …' suffix and retry exact
    stripped = re.sub(r'\s+без\s+.*$', '', v).strip()
    if stripped != v:
        return _canonical_dish(field, stripped)
    return v, False


def validate_row(client_name, menu_date, shift, salad, soup, main, side, source_sheet, db_conn):
    """Returns (ok, violations, action).
    ok=True  -> safe to write; action is 'insert' or 'replace' (delete existing first).
    ok=False -> do NOT write; caller must quarantine_row() with '; '.join(violations).
    """
    violations = []
    shift = str(shift)
    dishes = {'salad': salad, 'soup': soup, 'main': main, 'side': side}

    if shift not in VALID_SHIFTS:
        violations.append(f'bad_shift:{shift!r}')

    for field, value in dishes.items():
        if value is None or str(value).strip() == '':
            violations.append(f'empty_{field}')
        else:
            name, ok = _canonical_dish(field, value)
            if not ok:
                violations.append(f'non_catalog_{field}:{value!r}')
            elif name != str(value).strip():
                violations.append(f'wrong_category_{field}:{value!r}->{name!r}')

    # schedule check (EXEMPT for ocr_scan)
    if source_sheet != OCR:
        try:
            wd = date.fromisoformat(menu_date).weekday()
        except Exception:
            violations.append(f'bad_date:{menu_date!r}')
            wd = None
        if wd is not None:
            if wd not in WEEKDAY_COL:
                violations.append(f'no_service_weekday:{menu_date} weekday={wd}')
            else:
                sched = _load_schedule().get(canon(client_name))
                if not sched:
                    violations.append(f'no_roster_match:{client_name}')
                elif wd not in sched:
                    violations.append(f'off_schedule:{client_name} weekday={wd}')

    # duplicate (client,date,shift) check
    old = db_conn.execute(
        'SELECT source_sheet FROM client_menus WHERE client_name=? AND menu_date=? AND shift=?',
        (client_name, menu_date, shift)).fetchone()
    action = 'insert'
    if old is not None:
        if old[0] == OCR and source_sheet == OCR:
            action = 'insert'  # idempotent re-apply
        elif source_sheet == OCR:
            action = 'replace'  # ocr_scan WINS over fallback/house
        else:
            violations.append(f'duplicate:{client_name} {menu_date} shift={shift}')

    return (len(violations) == 0), violations, action
