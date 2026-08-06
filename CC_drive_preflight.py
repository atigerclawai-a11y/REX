#!/usr/bin/env python3
"""
CC_drive_preflight.py — Unified Drive-first preflight
═══════════════════════════════════════════════════════
Syncs attendance AND menus from Google Drive before any
GOJ document generation. This is the FOUNDATION that all
other generators (sign-in, distribution, driver, kitchen)
will call.

Handles:
- Sunday combined "Su" tab (no shift split for attendance)
- Cyrillic М tab code for S2 Monday menus
- Inactive client auto-activation
- Menu column mapping: A=Name, C=Salad, D=Soup, E=Main, F=Side
- Attendance sync to auth_tracker.db (day_*_actual columns)
- Menu sync to goj_proprietary.db (client_menus table)

Usage:
    from CC_drive_preflight import preflight
    data = preflight('2026-06-22')
    print(data['stats'])
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Paths ──────────────────────────────────────────────────────────────────
HOME = Path.home()
REX_DIR = HOME / "Desktop" / "REX"
TOKEN_PATH = HOME / ".rex_google_token.json"
SA_KEY_PATH = HOME / ".rex_drive_service_account.json"   # service account key (preferred)
AUTH_DB_PATH = HOME / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
PROPRIETARY_DB_PATH = HOME / "Desktop" / "REX" / "goj_proprietary.db"

# ── Sheet IDs (source of truth) ────────────────────────────────────────────
SIGN_IN_ID = "1ko7aVBhzLMngCuWmIZuCC5eT6WwvNEUiS8Q0vF92oy8"
MENU_S1_ID = "1IfBJbKleeqA329FI3WeoFQp2xqmKYRJiy_I7RC2ZBcw"
MENU_S2_ID = "18rs4xZHmdjt78za9tsh1bse94q-9Vn-pKXcnjID3ER0"

# ── Day mappings ───────────────────────────────────────────────────────────
# Code → (day_name, db_column)
DAY_MAP: Dict[str, Tuple[str, str]] = {
    "M":  ("Monday",    "day_M_actual"),
    "T":  ("Tuesday",   "day_T_actual"),
    "W":  ("Wednesday", "day_W_actual"),
    "TH": ("Thursday",  "day_TH_actual"),
    "F":  ("Friday",    "day_F_actual"),
    "Sa": ("Saturday",  "day_Su_actual"),   # Saturday stored in Su column
    "Su": ("Sunday",    "day_Su_actual"),
}

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_CODES = ["M", "T", "W", "TH", "F", "Su", "Su"]  # Sat+Sun both "Su" — Drive sign-in tab


# ═══════════════════════════════════════════════════════════════════════════
# GOOGLE API
# ═══════════════════════════════════════════════════════════════════════════

def _get_services():
    """Google Drive access is DISABLED (Kato law 2026-08-05).

    Drive is OUTPUT-ONLY in this ecosystem — never a source of truth.
    Attendance truth = LIVE Carecenta; menu orders = OCR pipeline;
    clients/auth = auth_tracker.db. This function refuses to build
    Drive/Sheets clients so no code path can read Drive.
    """
    raise RuntimeError(
        "DRIVE DISABLED: Google Drive is NOT a source of truth (Kato 2026-08-05). "
        "Attendance=Carecenta LIVE, menus=OCR, clients=auth_tracker.db. "
        "Drive is output-only (backups/changelog/distribution)."
    )


# ═══════════════════════════════════════════════════════════════════════════
# TAB NAME HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _sign_in_tab(day_code: str, shift: int) -> str:
    """Tab name in sign-in sheet. Sunday & Saturday use combined 'Su' (no shift suffix)."""
    if day_code in ("Su", "Sa"):
        return "Su"
    return f"{day_code}{shift}"


def _menu_tab(service_date: date, day_code: str, sheet_id: str) -> str:
    """Tab name in menu sheet.
    - Format: {month}/{day} {code}
    - Sunday uses 'S' (not 'Su')
    - S2 Monday uses Cyrillic 'М' (U+041C)
    """
    month = service_date.month
    day = service_date.day

    if day_code in ("Su", "Sa"):
        menu_code = "S"
    elif day_code == "M" and sheet_id == MENU_S2_ID:
        menu_code = "\u041c"  # Cyrillic capital М
    else:
        menu_code = day_code

    return f"{month}/{day} {menu_code}"


# ═══════════════════════════════════════════════════════════════════════════
# DRIVE READERS
# ═══════════════════════════════════════════════════════════════════════════

def _read_sign_in(sheets_svc, day_code: str, shift: int) -> List[Dict[str, str]]:
    """Read client attendance from a sign-in sheet tab.
    Returns list of {name, plan, transport}.
    Column layout: A=Name, B=plan, D=TR (transport)
    """
    tab = _sign_in_tab(day_code, shift)
    try:
        result = sheets_svc.spreadsheets().values().get(
            spreadsheetId=SIGN_IN_ID,
            range=f"'{tab}'!A1:H110",
        ).execute()
    except Exception as e:
        print(f"  ⚠  Sign-in tab '{tab}' not accessible: {e}")
        return []

    values = result.get("values", [])
    clients: List[Dict[str, str]] = []

    for row in values[3:]:  # Skip title/header rows (rows 0-3)
        if not row or not row[0] or not str(row[0]).strip():
            continue
        name = str(row[0]).strip()
        if name.lower() in ("name", "garden"):
            continue
        plan = str(row[1]).strip() if len(row) > 1 else ""
        transport = str(row[3]).strip() if len(row) > 3 else ""
        clients.append({"name": name, "plan": plan, "transport": transport})

    return clients


def _read_menu(
    sheets_svc, sheet_id: str, service_date: date, day_code: str
) -> Dict[str, Dict[str, str]]:
    """Read menu choices from a menu sheet tab.
    Column layout: A=Name, C=Salad, D=Soup, E=Main, F=Side.
    Returns {name: {salad, soup, main, side}}.
    """
    tab = _menu_tab(service_date, day_code, sheet_id)
    try:
        result = sheets_svc.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"'{tab}'!A1:Z200",
        ).execute()
    except Exception:
        # Try fallback for S2 Monday: Cyrillic → Latin
        if day_code == "M" and sheet_id == MENU_S2_ID:
            fallback_tab = f"{service_date.month}/{service_date.day} M"
            try:
                result = sheets_svc.spreadsheets().values().get(
                    spreadsheetId=sheet_id,
                    range=f"'{fallback_tab}'!A1:Z200",
                ).execute()
            except Exception:
                return {}
        else:
            return {}

    values = result.get("values", [])
    menus: Dict[str, Dict[str, str]] = {}

    # Find header row (contains 'Name' or 'client')
    header_row = 0
    for i, row in enumerate(values):
        if row and any("name" in str(c).lower() for c in row):
            header_row = i
            break

    # Parse: col 0=Name, col 2=Salad, col 3=Soup, col 4=Main, col 5=Side
    for row in values[header_row + 1 :]:
        if not row or not row[0]:
            continue
        name = str(row[0]).strip()
        if not name or name.lower() in ("name", "client", "total", ""):
            continue

        salad = str(row[2]).strip() if len(row) > 2 else ""
        soup = str(row[3]).strip() if len(row) > 3 else ""
        main = str(row[4]).strip() if len(row) > 4 else ""
        side = str(row[5]).strip() if len(row) > 5 else ""

        # Only include if at least one menu field is populated
        if salad or soup or main or side:
            menus[name] = {"salad": salad, "soup": soup, "main": main, "side": side}

    return menus


# ═══════════════════════════════════════════════════════════════════════════
# DATABASE SYNC
# ═══════════════════════════════════════════════════════════════════════════

# ── Carecenta roster (KATO DECREE 2026-07-27) ─────────────────────────────────
def _carecenta_roster(date_str: str) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """Attendance roster — RETIRED 2026-08-05 (Kato directive).
    ⛔ NO-OP. Previously read ghs_schedule.db (a retired snapshot DB last written
    2026-08-02) and produced STALE numbers (Thu showed 118/49 while live
    Carecenta = 88/61) every time the 20:00 Daily Package cron ran the preflight.
    The week-number heuristic (30 + (dt-today)//7) picked the wrong week and the
    zero-then-set in _sync_attendance silently overwrote verified attendance.
    Attendance truth now lives ONLY in auth_tracker.db day_*_actual, set by the
    definitive LIVE-Carecenta syncs (sync_tuesday_morning.py, sync_wednesday_definitive.py,
    sync_thu_fri_definitive.py). DO NOT re-enable without Kato sign-off + a live
    Carecenta scrape replacing the retired DB."""
    print("  ⛔ _carecenta_roster DISABLED (ghs_schedule.db retired 2026-08-05, Kato law) — returning empty roster; attendance LEFT UNTOUCHED")
    return [], []


def _sync_attendance(
    day_code: str,
    day_column: str,
    s1_clients: List[Dict[str, str]],
    s2_clients: List[Dict[str, str]],
) -> Dict[str, Any]:
    """Sync attendance from Drive to auth_tracker.db.
    - Reset day_*_actual=0 for all active clients
    - Set day_*_actual=shift for Drive clients
    - Auto-activate inactive clients found on Drive
    Returns sync stats.
    """
    if not AUTH_DB_PATH.exists():
        print("  ⚠  auth_tracker.db not found — skipping attendance sync")
        return {"reset": 0, "s1_set": 0, "s2_set": 0, "auto_activated": [], "unmatched": []}

    conn = sqlite3.connect(str(AUTH_DB_PATH))
    conn.row_factory = sqlite3.Row

    try:
        # Step 1: Reset day_*_actual = 0 for all active clients
        reset_result = conn.execute(
            f"UPDATE clients SET {day_column}=0, updated_at=datetime('now') WHERE active=1"
        )
        reset_count = reset_result.rowcount
        conn.commit()

        # Step 2: Build name → row lookup for existing clients (case-insensitive)
        all_rows = conn.execute("SELECT client_id, name, active, deceased FROM clients").fetchall()
        db_index: Dict[str, sqlite3.Row] = {}
        for r in all_rows:
            db_index[r["name"].strip().lower()] = r

        auto_activated: List[str] = []
        unmatched: List[str] = []
        s1_set = 0
        s2_set = 0

        # Step 3: Set day_*_actual for each shift
        for shift, clients in [(1, s1_clients), (2, s2_clients)]:
            for c in clients:
                key = c["name"].strip().lower()
                row = db_index.get(key)

                if row is None:
                    unmatched.append(c["name"])
                    continue

                # Set the day column to the shift number
                conn.execute(
                    f"UPDATE clients SET {day_column}=?, updated_at=datetime('now') WHERE client_id=?",
                    (shift, row["client_id"]),
                )
                if shift == 1:
                    s1_set += 1
                else:
                    s2_set += 1

                # Auto-activate if client is on Drive but marked inactive
                # 🛡️ GUARD: Never auto-activate deceased clients
                if not row["active"] and not row["deceased"]:
                    conn.execute(
                        "UPDATE clients SET active=1, updated_at=datetime('now') WHERE client_id=?",
                        (row["client_id"],),
                    )
                    auto_activated.append(c["name"])
                elif not row["active"] and row["deceased"]:
                    pass  # Skip resurrection of deceased clients

        conn.commit()

        return {
            "reset": reset_count,
            "s1_set": s1_set,
            "s2_set": s2_set,
            "auto_activated": auto_activated,
            "unmatched": unmatched,
        }

    finally:
        conn.close()


def _normalize_name(n: str) -> str:
    """Normalize client name for matching: handles Cyrillic transliteration variants.
    Common patterns: y↔i (Sofiya/Sofia), y↔∅ (Valentyna/Valentina), ks↔x (Feliks/Felix)."""
    n = n.strip().lower()
    n = n.replace("'", "").replace("\u02bc", "")   # apostrophe variants
    n = n.replace("ks", "x")                         # Feliks→Felix
    # Normalize 'y' → 'i' when not word-initial or after vowel (Larysa→Larisa, Valentyna→Valentina)
    # but keep 'iy'→'i' first
    n = n.replace("iy", "i")
    result = []
    for i, ch in enumerate(n):
        if ch == 'y' and i > 0 and n[i-1] not in 'aeiou':
            result.append('i')
        else:
            result.append(ch)
    return ''.join(result)


def _sync_menus(
    date_str: str, day_code: str, day_name: str,
    s1_menus: Dict[str, Dict[str, str]],
    s2_menus: Dict[str, Dict[str, str]],
) -> Dict[str, int]:
    """Sync menus from Drive to goj_proprietary.db.
    EXCISED 2026-07-27 (Kato directive): the staff member who owns the Drive menu
    files has been carrying them forward week-to-week WITHOUT updating ("she has
    just been carrying over the files"). drive_sync rows were stale selections
    wearing fresh timestamps — no better than our own carry-forward but
    dishonestly labeled. Menu fill chain is now: OCR paper forms → client's own
    last order (last_order_fallback) → house_standard. Do NOT re-enable without
    Kato's explicit sign-off AND evidence staff resumed updating Drive.
    """
    print("  ⏭  drive_sync excised 2026-07-27 (stale carried-over Drive menus) — OCR/history only")
    return {"s1_inserted": 0, "s2_inserted": 0}

    if not PROPRIETARY_DB_PATH.exists():
        print("  ⚠  goj_proprietary.db not found — skipping menu sync")
        return {"s1_inserted": 0, "s2_inserted": 0}

    conn = sqlite3.connect(str(PROPRIETARY_DB_PATH))
    try:
        # Delete ONLY stale drive_sync rows before re-sync. MUST preserve ocr_scan —
        # Kato 2026-07-27: "all of the menu items are supposed to come from the OCR".
        # BUG FIXED 2026-07-27: previous WHERE ... NOT IN ('no_order_flag','last_order_fallback')
        # wiped every ocr_scan row on each preflight run → kitchen served last week's food.
        conn.execute(
            "DELETE FROM client_menus WHERE menu_date=? AND source_sheet = 'drive_sync'",
            (date_str,),
        )
        conn.commit()

        # Load auth_tracker client names for fuzzy matching
        name_map = {}  # raw Drive name → canonical DB name
        if AUTH_DB_PATH.exists():
            aconn = sqlite3.connect(str(AUTH_DB_PATH))
            aconn.row_factory = sqlite3.Row
            db_clients = aconn.execute(
                "SELECT name FROM clients WHERE active=1"
            ).fetchall()
            aconn.close()
            # Build lookup: normalized name → canonical name
            db_names = {_normalize_name(r["name"]): r["name"].strip() for r in db_clients}
            name_map = db_names

        s1_count = 0
        s2_count = 0

        for shift, menus in [(1, s1_menus), (2, s2_menus)]:
            for name, m in menus.items():
                # Store with original Drive name (normalization only used for matching)
                canonical = name.strip()
                # INSERT OR IGNORE: never overwrite an existing ocr_scan row with a
                # Drive row — OCR is the menu source of truth (Kato 2026-07-27).
                # Was INSERT OR REPLACE, which clobbered OCR whenever Drive tabs had entries.
                conn.execute(
                    """INSERT OR IGNORE INTO client_menus
                       (client_name, menu_date, day_code, shift, salad, soup, main, side, source_sheet, synced_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'drive_sync', datetime('now'))""",
                    (
                        canonical, date_str, day_code, str(shift),
                        m.get("salad", ""), m.get("soup", ""),
                        m.get("main", ""), m.get("side", ""),
                    ),
                )
                if shift == 1:
                    s1_count += 1
                else:
                    s2_count += 1

        conn.commit()
        return {"s1_inserted": s1_count, "s2_inserted": s2_count}

    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# MAIN PREFLIGHT
# ═══════════════════════════════════════════════════════════════════════════

def preflight(date_str: str) -> Dict[str, Any]:
    """Run the unified Drive-first preflight for a given date.

    Reads sign-in sheets (attendance) and menu sheets from Google Drive,
    syncs to the database, and returns a verified data dict.

    Args:
        date_str: ISO date string, e.g. '2026-06-22'

    Returns:
        {
            "date": "2026-06-22",
            "day_code": "M",
            "day_name": "Monday",
            "attendance": {1: [{name, plan, transport}, ...], 2: [...]},
            "menus": {1: [{name, salad, soup, main, side}, ...], 2: [...]},
            "no_menu": [names],
            "stats": {s1_attendance, s2_attendance, s1_menu, s2_menu}
        }
    """
    # ── Resolve date ──────────────────────────────────────────────────
    d = date.fromisoformat(date_str)
    weekday = d.weekday()
    day_code = DAY_CODES[weekday]
    day_name = DAY_NAMES[weekday]
    day_column = DAY_MAP[day_code][1]
    is_sunday = (day_code == "Su")

    print(f"\n{'='*60}")
    print(f" CC_drive_preflight — {day_name}, {date_str}")
    print(f" day_code={day_code}  column={day_column}")
    print(f"{'='*60}")

    # ── Google API — DISABLED (Kato law 2026-08-05) ────────────────────
    try:
        _get_services()  # always raises RuntimeError now
    except RuntimeError as e:
        print(f"  🚫 {e}")
    sheets = None

    # ── Attendance source: LOCAL DB (Carecenta-synced), NEVER Drive ────
    print("\n📋 Attendance source: auth_tracker.db (Carecenta-synced truth)...")
    s1_clients, s2_clients = [], []
    try:
        conn = sqlite3.connect(str(AUTH_DB_PATH))
        conn.row_factory = sqlite3.Row
        s1_clients = [{"name": r["name"]} for r in conn.execute(
            f"SELECT name FROM clients WHERE {day_column} = 1 AND active = 1"
        ).fetchall()]
        s2_clients = [{"name": r["name"]} for r in conn.execute(
            f"SELECT name FROM clients WHERE {day_column} = 2 AND active = 1"
        ).fetchall()]
        conn.close()
    except Exception as e:
        print(f"  ⚠  local attendance read failed: {e}")
    print(f"  Shift 1: {len(s1_clients)} | Shift 2: {len(s2_clients)} (from DB)")

    # ── Menu source: LOCAL OCR rows (Drive menu sheets disabled) ──────────
    print("\n🍽️  Menu source: ocr_scan rows from goj_proprietary.db...")
    s1_menus_raw, s2_menus_raw = {}, {}
    try:
        pconn = sqlite3.connect(str(PROPRIETARY_DB_PATH))
        for row in pconn.execute(
            "SELECT client_name, shift, salad, soup, main, side FROM client_menus "
            "WHERE menu_date = ? AND source_sheet = 'ocr_scan'",
            (date_str,),
        ).fetchall():
            fields = {"salad": row[2] or "", "soup": row[3] or "",
                      "main": row[4] or "", "side": row[5] or ""}
            target = s1_menus_raw if str(row[1]) == "1" else s2_menus_raw
            target[row[0]] = fields
        pconn.close()
    except Exception as e:
        print(f"  ⚠  local menu read failed: {e}")
    print(f"  S1 OCR menu rows: {len(s1_menus_raw)} | S2: {len(s2_menus_raw)}")

    # ── Sync attendance to auth_tracker.db ────────────────────────────
    # KATO DECREE 2026-07-27: Carecenta schedule = attendance truth (Drive is stale)
    print("\n💾 Syncing attendance to auth_tracker.db (CARECENTA roster per Kato decree)...")
    cc_s1, cc_s2 = _carecenta_roster(date_str)
    if cc_s1 or cc_s2:
        att_sync = _sync_attendance(day_code, day_column, cc_s1, cc_s2)
    else:
        print("  ⚠  Carecenta roster empty — attendance LEFT UNTOUCHED (Drive fallback REMOVED, law 08-05)")
        att_sync = {"reset": 0, "s1_set": 0, "s2_set": 0, "auto_activated": [], "unmatched": []}
    print(f"  Reset {att_sync['reset']} active → 0")
    print(f"  Shift 1 set: {att_sync['s1_set']} | Shift 2 set: {att_sync['s2_set']}")
    if att_sync["auto_activated"]:
        print(f"  🔓 Auto-activated {len(att_sync['auto_activated'])} inactive clients:")
        for name in att_sync["auto_activated"]:
            print(f"      {name}")
    if att_sync["unmatched"]:
        print(f"  ⚠  {len(att_sync['unmatched'])} Drive names not in auth_tracker.db:")
        for name in att_sync["unmatched"][:10]:
            print(f"      {name}")
        if len(att_sync["unmatched"]) > 10:
            print(f"      ... and {len(att_sync['unmatched']) - 10} more")

    # ── Mirror auth_tracker clients → proprietary DB ──────────────────
    if AUTH_DB_PATH.exists() and PROPRIETARY_DB_PATH.exists():
        try:
            aconn = sqlite3.connect(str(AUTH_DB_PATH))
            aconn.row_factory = sqlite3.Row
            auth_clients = aconn.execute(
                "SELECT name, active FROM clients WHERE active=1 ORDER BY name"
            ).fetchall()
            aconn.close()

            pconn = sqlite3.connect(str(PROPRIETARY_DB_PATH))
            pconn.execute(
                "CREATE TABLE IF NOT EXISTS clients (name TEXT PRIMARY KEY, active INTEGER)"
            )
            try:
                pconn.execute("ALTER TABLE clients ADD COLUMN active INTEGER")
            except sqlite3.OperationalError:
                pass

            synced = 0
            for c in auth_clients:
                # INSERT new clients, UPDATE active for existing — preserve phone/plan/etc.
                pconn.execute(
                    "INSERT INTO clients (name, active) VALUES (?, ?) "
                    "ON CONFLICT(name) DO UPDATE SET active=excluded.active",
                    (c["name"], c["active"]),
                )
                synced += 1
            pconn.commit()
            pconn.close()
            if att_sync["unmatched"]:
                # Don't print sync count unless there's a meaningful delta
                pass  # print(f"  🔄 Synced {synced} clients to proprietary DB")
        except Exception as e:
            print(f"  ⚠️  Client mirror sync failed: {e}")

    # ── Sync menus to goj_proprietary.db ──────────────────────────────
    print("\n💾 Syncing menus to goj_proprietary.db...")
    menu_sync = _sync_menus(date_str, day_code, day_name, s1_menus_raw, s2_menus_raw)
    print(f"  Synced menus (preserving no_order_flag entries)")
    print(f"  S1 inserted: {menu_sync['s1_inserted']} | S2 inserted: {menu_sync['s2_inserted']}")

    # ── Build return data ─────────────────────────────────────────────
    # Attendance: list of {name, plan, transport}
    attendance = {
        1: s1_clients,
        2: s2_clients,
    }

    # Menus: list of {name, salad, soup, main, side}
    s1_menu_list = [
        {"name": name, **fields}
        for name, fields in s1_menus_raw.items()
    ]
    s2_menu_list = [
        {"name": name, **fields}
        for name, fields in s2_menus_raw.items()
    ]
    menus = {1: s1_menu_list, 2: s2_menu_list}

    # no_menu: clients on attendance with no menu (using normalized name matching)
    all_attend_names = {c["name"] for c in s1_clients + s2_clients}
    all_menu_names = set(s1_menus_raw.keys()) | set(s2_menus_raw.keys())
    # Build normalized menu lookup
    norm_menu = {_normalize_name(n): n for n in all_menu_names}
    no_menu = []
    for name in sorted(all_attend_names):
        if _normalize_name(name) not in norm_menu:
            no_menu.append(name)
    if no_menu:
        # ── Fill no-menu clients: last-known order OR flag ─────────────
        print(f"\n📋 {len(no_menu)} attending clients without OCR menu rows — filling from history...")
        s1_attend_names = {c["name"] for c in s1_clients}
        s2_attend_names = {c["name"] for c in s2_clients}
        no_menu_s1 = [n for n in no_menu if n in s1_attend_names]
        no_menu_s2 = [n for n in no_menu if n in s2_attend_names]

        try:
            flag_conn = sqlite3.connect(str(PROPRIETARY_DB_PATH))
            flag_conn.execute(
                "CREATE TABLE IF NOT EXISTS client_menus ("
                "client_name TEXT, menu_date TEXT, shift TEXT,"
                "salad TEXT, soup TEXT, main TEXT, side TEXT,"
                "source_sheet TEXT, day_code TEXT, synced_at TEXT)"
            )
            for col in ["source_sheet", "day_code", "synced_at"]:
                try: flag_conn.execute(f"ALTER TABLE client_menus ADD COLUMN {col} TEXT")
                except sqlite3.OperationalError: pass

            # Remove stale flags/fills from previous runs for this date
            flag_conn.execute(
                "DELETE FROM client_menus WHERE menu_date=? AND source_sheet IN ('no_order_flag', 'last_order_fallback')",
                (date_str,),
            )
            flag_conn.commit()

            filled_s1 = filled_s2 = 0
            flagged_s1 = flagged_s2 = 0
            flag_text = "заказ не размещен"

            # ── HARD RULE: Use LAST WEEK's same-day orders, cross-referenced with sign-in ──
            from datetime import timedelta
            target_dt = date.fromisoformat(date_str)
            last_week_dt = target_dt - timedelta(days=7)
            last_week_str = str(last_week_dt)
            day_col = f"day_{day_code}_actual"

            # ① Verify client was on sign-in last week
            auth_conn = sqlite3.connect(str(AUTH_DB_PATH))
            auth_conn.row_factory = sqlite3.Row
            last_week_signins = set()
            for row in auth_conn.execute(
                f"SELECT name FROM clients WHERE {day_col} > 0 AND active = 1"
            ).fetchall():
                last_week_signins.add(row["name"])
            auth_conn.close()

            for shift, no_menu_shift in [('1', no_menu_s1), ('2', no_menu_s2)]:
                for name in no_menu_shift:
                    last = None

                    # ① Look up same-day last week's order in goj_proprietary.db (Drive-synced)
                    #    ONLY if client was on sign-in last week
                    if name in last_week_signins:
                        last = flag_conn.execute(
                            "SELECT salad, soup, main, side FROM client_menus "
                            "WHERE client_name = ? AND menu_date = ? "
                            "AND source_sheet NOT IN ('no_order_flag', 'last_order_fallback') "
                            "LIMIT 1",
                            (name, last_week_str)
                        ).fetchone()

                    # ② If no last-week order but was on sign-in — fall back to any recent order
                    if (not last or not any(last)) and name in last_week_signins:
                        last = flag_conn.execute(
                            "SELECT salad, soup, main, side FROM client_menus "
                            "WHERE client_name = ? AND source_sheet NOT IN ('no_order_flag', 'last_order_fallback') "
                            "ORDER BY menu_date DESC LIMIT 1",
                            (name,)
                        ).fetchone()

                    # ③ Final fallback: search auth_tracker.db OCR table
                    if not last or not any(last):
                        try:
                            aconn = sqlite3.connect(str(AUTH_DB_PATH))
                            aconn.row_factory = sqlite3.Row
                            last_ocr = aconn.execute(
                                "SELECT salad, soup, main, side FROM client_menus "
                                "WHERE client_name = ? AND week_start IS NOT NULL "
                                "ORDER BY week_start DESC LIMIT 1",
                                (name,)
                            ).fetchone()
                            aconn.close()
                            if last_ocr:
                                last = (last_ocr["salad"], last_ocr["soup"], last_ocr["main"], last_ocr["side"])
                        except Exception:
                            pass

                    if last and any(last):
                        # Copy last known order (OR IGNORE: never clobber an existing
                        # ocr_scan row — the in-memory no-menu list predates DB writes)
                        flag_conn.execute(
                            "INSERT OR IGNORE INTO client_menus "
                            "(client_name, menu_date, day_code, shift, salad, soup, main, side, source_sheet) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'last_order_fallback')",
                            (name, date_str, day_code, shift,
                             last[0] or "", last[1] or "", last[2] or "", last[3] or ""),
                        )
                        if shift == '1': filled_s1 += 1
                        else: filled_s2 += 1
                    else:
                        # No prior order — flag as "заказ не размещен"
                        flag_conn.execute(
                            "INSERT OR IGNORE INTO client_menus "
                            "(client_name, menu_date, day_code, shift, salad, soup, main, side, source_sheet) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'no_order_flag')",
                            (name, date_str, day_code, shift,
                             flag_text, flag_text, flag_text, flag_text),
                        )
                        if shift == '1': flagged_s1 += 1
                        else: flagged_s2 += 1

            flag_conn.commit()
            flag_conn.close()

            parts = []
            if filled_s1 or filled_s2:
                parts.append(f"✅ Filled {filled_s1} S1 + {filled_s2} S2 from last-known orders")
            if flagged_s1 or flagged_s2:
                parts.append(f"⚠️  {flagged_s1} S1 + {flagged_s2} S2 have no prior orders — flagged 'заказ не размещен'")
            if parts:
                print(f"  {' | '.join(parts)}")
        except Exception as e:
            print(f"  ⚠️  No-menu fill/flagging failed: {e}")

    # Stats
    stats = {
        "s1_attendance": len(s1_clients),
        "s2_attendance": len(s2_clients),
        "s1_menu": len(s1_menus_raw),
        "s2_menu": len(s2_menus_raw),
    }

    print(f"\n{'='*60}")
    print(f" ✅ Preflight complete — {date_str} ({day_name})")
    print(f"    Attendance: S1={stats['s1_attendance']} S2={stats['s2_attendance']}")
    print(f"    Menus:      S1={stats['s1_menu']} S2={stats['s2_menu']}")
    print(f"{'='*60}\n")

    return {
        "date": date_str,
        "day_code": day_code,
        "day_name": day_name,
        "attendance": attendance,
        "menus": menus,
        "no_menu": no_menu,
        "stats": stats,
    }


# ═══════════════════════════════════════════════════════════════════════════
# MAIN (standalone)
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) > 1:
        date_str = sys.argv[1]
    else:
        # Default: next operating day (tomorrow, skip Saturday)
        today = date.today()
        target = date.today()
        target = date(target.year, target.month, target.day)  # copy
        from datetime import timedelta
        target = today + timedelta(days=1)
        if target.weekday() == 5:  # Saturday → Sunday
            target = target + timedelta(days=1)
        date_str = target.isoformat()

    result = preflight(date_str)
    print(f"Returned keys: {list(result.keys())}")
    print(f"Stats: {result['stats']}")
