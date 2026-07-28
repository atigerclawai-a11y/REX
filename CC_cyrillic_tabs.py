#!/usr/bin/env python3
"""
CC_cyrillic_tabs.py — Cyrillic Tab Normalization for GOJ Menu Sheets
═══════════════════════════════════════════════════════════════════════
Normalizes day codes for Google Sheets menu tabs across both shifts.
Google Sheets S2 tabs for Monday use CYRILLIC М (U+041C), not Latin M.
All other days across both shifts use Latin day codes.

Rules:
  S1: All Latin codes (M, T, W, TH, F, Sa, S)
  S2: Monday = Cyrillic М, others Latin. Sunday has NO S2 tab.

Usage:
  from CC_cyrillic_tabs import get_menu_tab_code, get_menu_tab_name

  code = get_menu_tab_code("M", shift=2)  # → "М" (Cyrillic)
  name = get_menu_tab_name(date_obj, shift=2)  # → "6/23 М"
"""

from datetime import date
from typing import Optional

# ── Latin to Cyrillic mapping for Monday (S2 only) ──────────────────
CYRILLIC_M = "\u041C"  # Cyrillic capital EM (М)

# ── Day code mappings ───────────────────────────────────────────────
# S1: ALL Latin codes — never uses Cyrillic
S1_DAY_CODES = {
    0: "M",    # Monday
    1: "T",    # Tuesday
    2: "W",    # Wednesday
    3: "TH",   # Thursday
    4: "F",    # Friday
    5: "Sa",   # Saturday
    6: "S",    # Sunday (menu tabs use "S", NOT "Su")
}

# S2: Monday = Cyrillic М, all others Latin. Sunday = NO TAB.
S2_DAY_CODES = {
    0: CYRILLIC_M,  # Monday → Cyrillic М
    1: "T",          # Tuesday → Latin T
    2: "W",          # Wednesday → Latin W
    3: "TH",         # Thursday → Latin TH
    4: "F",          # Friday → Latin F
    5: "Sa",         # Saturday → Latin Sa
    6: None,         # Sunday → NO S2 tab
}

# ── Full day name mapping ───────────────────────────────────────────
DAY_NAMES = {
    0: "Monday", 1: "Tuesday", 2: "Wednesday",
    3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday",
}

# ── Reverse lookup: ANY day code (Latin or Cyrillic) → weekday int ──
# Supports fuzzy matching: "M", "М", "T", "W", "TH", "F", "Sa", "S", "Su"
_REVERSE_DAY_MAP = {
    "M": 0, "М": 0,          # Latin M + Cyrillic М → Monday
    "T": 1,
    "W": 2,
    "TH": 3, "Th": 3, "th": 3,
    "F": 4,
    "SA": 5, "Sa": 5, "sa": 5,
    "S": 6, "SU": 6, "Su": 6, "su": 6,
}


def get_menu_tab_code(day_code: str, shift: int) -> Optional[str]:
    """
    Normalize a day code for menu tab construction.

    Args:
        day_code: Latin day code ("M", "T", "W", "TH", "F", "Sa", "S" or "Su")
        shift: 1 or 2

    Returns:
        Normalized day code for the menu tab, or None if no tab exists.
        S2 Monday returns Cyrillic "М".
        S2 Sunday returns None (no tab).

    >>> get_menu_tab_code("M", 1)   # S1 Monday → "M"
    'M'
    >>> get_menu_tab_code("M", 2)   # S2 Monday → Cyrillic М
    'М'
    >>> get_menu_tab_code("Su", 1)  # S1 Sunday → "S"
    'S'
    >>> get_menu_tab_code("Su", 2)  # S2 Sunday → None (no tab)
    """
    # Normalize day_code to an integer
    day_code_upper = day_code.upper()
    weekday = _REVERSE_DAY_MAP.get(day_code_upper)
    if weekday is None:
        raise ValueError(f"Unknown day code: {day_code}")

    if shift == 1:
        return S1_DAY_CODES[weekday]
    elif shift == 2:
        return S2_DAY_CODES[weekday]
    else:
        raise ValueError(f"Invalid shift: {shift}. Must be 1 or 2.")


def get_menu_tab_name(service_date: date, shift: int) -> Optional[str]:
    """
    Build a complete menu tab name like "6/23 M" or "6/23 М".

    Args:
        service_date: The date of service
        shift: 1 or 2

    Returns:
        Tab name string, or None if no tab exists for this day+shift.

    >>> from datetime import date
    >>> get_menu_tab_name(date(2026, 6, 22), 1)  # Monday S1
    '6/22 M'
    >>> get_menu_tab_name(date(2026, 6, 22), 2)  # Monday S2 → Cyrillic
    '6/22 М'
    """
    month = service_date.month
    day = service_date.day
    weekday = service_date.weekday()

    if shift == 1:
        tab_code = S1_DAY_CODES[weekday]
    elif shift == 2:
        tab_code = S2_DAY_CODES[weekday]
        if tab_code is None:
            return None  # No S2 tab on Sunday
    else:
        raise ValueError(f"Invalid shift: {shift}")

    return f"{month}/{day} {tab_code}"


def normalize_tab_name(tab_name: str, shift: int) -> Optional[str]:
    """
    Given a raw tab name (possibly using wrong day code), normalize it.

    Useful when scanning sheet metadata and you find tabs with mixed
    Latin/Cyrillic codes.

    Args:
        tab_name: Raw tab name like "6/22 M" or "6/22 М" or "6/22 W"
        shift: 1 or 2

    Returns:
        Canonical tab name, or None if no tab exists.

    >>> normalize_tab_name("6/22 M", 2)   # Latin M on S2 → should be Cyrillic
    '6/22 М'
    >>> normalize_tab_name("6/22 М", 1)   # Cyrillic М on S1 → should be Latin
    '6/22 M'
    >>> normalize_tab_name("6/22 T", 2)   # Latin T on S2 → correct
    '6/22 T'
    """
    import re
    m = re.match(r"(\d+)/(\d+)\s+(.+)", tab_name)
    if not m:
        return None

    month, day_str, code = m.groups()
    code_upper = code.upper()
    weekday = _REVERSE_DAY_MAP.get(code_upper)
    if weekday is None:
        return None

    if shift == 1:
        normalized_code = S1_DAY_CODES[weekday]
    else:
        normalized_code = S2_DAY_CODES[weekday]
        if normalized_code is None:
            return None

    return f"{month}/{day_str} {normalized_code}"


def has_s2_tab(weekday: int) -> bool:
    """Check if S2 has a menu tab for this weekday. Sunday (6) = False."""
    return S2_DAY_CODES.get(weekday) is not None


def is_cyrillic_monday(code: str) -> bool:
    """Check if a day code string is the Cyrillic М (Monday)."""
    return code == CYRILLIC_M


# ── Convenience: all possible tab codes for scanning ─────────────────
def all_possible_tab_codes(weekday: int) -> list:
    """
    Return all possible tab codes for a given weekday across both shifts.
    Useful for fuzzy-matching tab names from sheet metadata.

    >>> all_possible_tab_codes(0)  # Monday
    ['M', 'М']
    >>> all_possible_tab_codes(2)  # Wednesday
    ['W']
    """
    codes = set()
    s1 = S1_DAY_CODES.get(weekday)
    s2 = S2_DAY_CODES.get(weekday)
    if s1:
        codes.add(s1)
    if s2:
        codes.add(s2)
    return sorted(codes)


# ── Self-test ────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Cyrillic Tab Normalization Tests ===\n")

    test_date = date(2026, 6, 22)  # Monday
    print(f"Test date: {test_date} ({DAY_NAMES[test_date.weekday()]})")

    for shift in [1, 2]:
        code = get_menu_tab_code("M", shift)
        tab = get_menu_tab_name(test_date, shift)
        print(f"  Shift {shift}: code='{code}' (repr: {repr(code)}), tab='{tab}'")

    print(f"\n  has_s2_tab(6) [Sunday] = {has_s2_tab(6)}")
    print(f"  has_s2_tab(0) [Monday] = {has_s2_tab(0)}")

    print("\n  All possible codes for Monday:", all_possible_tab_codes(0))

    # Show all days
    print("\n  Full table:")
    for wd in range(7):
        s1 = S1_DAY_CODES[wd]
        s2 = S2_DAY_CODES[wd]
        print(f"    {DAY_NAMES[wd]:10s}  S1={s1!r:4s}  S2={s2!r:4s}")

    print("\n=== All tests passed ===")
