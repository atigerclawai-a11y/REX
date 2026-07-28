#!/usr/bin/env python3
"""goj_menu_form_parser.py — Parse MinerU markdown from scanned GOJ menu forms
into structured per-client, per-day food selections.

The GOJ menu form is a 2-page Russian form per client:
  p1: САЛАТЫ / СУПЫ / ГЛАВНОЕ БЛЮДО (start)
  p2: ГЛАВНОЕ БЛЮДО (continued) / ГАРНИР
Each item row has 5 day columns (ПН ВТ СР ЧТ ПТ = Mon-Fri). A handwritten
checkmark in a day cell = client wants that item that day.

MinerU renders checkmarks as arbitrary chars (0,O,V,X,①,②,√,↑,↓,★,©,Φ,D,8,W...)
and empty checkboxes as □. Table layouts vary:
  variant A: [item][d1][d2][d3][d4][d5]          (cells 1-5)
  variant B: [item][d1][][d2][][d3][][d4][][d5]  (days at odd indices,
             header row carries ПН/ВТ/СР/ЧТ/ПТ as separate cells)

Usage:
  python3 goj_menu_form_parser.py <mineru.md> [--json]
Library:
  from goj_menu_form_parser import parse_menu_md, ROSTER
"""

import json
import re
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

HOME = Path.home()
AUTH_DB = HOME / "Documents/goj files/dashboard/auth_tracker.db"

# ── Checkmark detection ──────────────────────────────────────────────────────
# MinerU maps handwritten marks to many glyphs; the printed empty box is □.
# Rule: stripped cell empty or all-□ → NOT checked. Anything else short → checked.
_EMPTY_RE = re.compile(r"^[\s□_\-—.,;:|]*$")

def is_checked(cell: str) -> bool:
    c = (cell or "").strip()
    if not c or _EMPTY_RE.match(c):
        return False
    # Long strings are OCR garbage bleed, not a single check cell
    if len(c) > 4:
        return False
    # Pure Latin words (e.g. "cYlowbl") are not marks
    if re.fullmatch(r"[A-Za-z]{3,}", c):
        return False
    return True

# ── Item dictionaries (canonical names) ──────────────────────────────────────
SALADS = ["Оливье", "Сало", "Квашеная капуста", "Свекла", "Винегрет",
          "Салат Днестр", "Салат из баклажан", "Селедка", "Салат весенний"]
SOUPS = ["Борщ зеленый", "Борщ красный", "Гороховый суп", "Грибной суп",
         "Куриный суп", "Овощной суп", "Харчо"]
MAINS = ["Баса с помидорами", "Блины с мясом", "Блины с творогом",
         "Вареники с картошкой", "Голубцы", "Гуляш", "Дорадо запеченая",
         "Жульен", "Котлеты куриные", "Курица в терияки", "Куриные крылышки",
         "Пельмени", "Поперечка", "Салмон", "Свиная отбивная",
         "Цыпленок табака", "Чалахач", "Чебуреки", "Шницель куриный", "Паста"]
SIDES = ["Тушеная капуста", "Картошка", "Картошка по деревенски",
         "Картошка фри", "Паста", "Гречка", "Пюре", "Фасоль",
         "Стручковая фасоль"]

# OCR garbling → canonical
ITEM_FIX = {
    "фуняш": "Гуляш", "фвляш": "Гуляш", "фуляш": "Гуляш", "фыняш": "Гуляш",
    "фолубцы": "Голубцы", "голубцы": "Голубцы",
    "шницель": "Шницель куриный", "дорадо": "Дорадо запеченая",
    "котл. кур": "Котлеты куриные", "вар.кар": "Вареники с картошкой",
    "св. отбив": "Свиная отбивная", "бл. твор": "Блины с творогом",
    "бл. мясо": "Блины с мясом", "туш. кап.": "Тушеная капуста",
    "картошка по деревенски": "Картошка по деревенски",
    "ол": "Оливье", "вин": "Винегрет", "свкл": "Свекла",
    "куp": "Куриный суп",
}

ALL_ITEMS = {}
for _cat, _items in (("salad", SALADS), ("soup", SOUPS), ("main", MAINS), ("side", SIDES)):
    for _it in _items:
        ALL_ITEMS[_it.lower()] = (_cat, _it)

SECTION_MAP = {
    "салат": "salad", "суп": "soup", "cyп": "soup", "cуп": "soup",
    "главн": "main", "блюдо": "main", "гарнир": "side",
}

DAY_LABELS = {"пн": 0, "вт": 1, "bt": 1, "ср": 2, "cp": 2, "чт": 3, "4t": 3, "пт": 4, "птcaлаты": 4}
DAY_CODES = ["M", "T", "W", "TH", "F"]

def norm_text(s: str) -> str:
    s = s.strip().lower().replace("ё", "е")
    s = re.sub(r"[\s.,;:_\-—()'\"]+", " ", s)
    return s.strip()

def match_item(cell: str):
    """Match a cell to a known menu item. Returns (category, canonical) or None."""
    t = norm_text(cell)
    if not t or len(t) < 2:
        return None
    if t in ITEM_FIX:
        fixed = ITEM_FIX[t]
        return ALL_ITEMS.get(fixed.lower())
    if t in ALL_ITEMS:
        return ALL_ITEMS[t]
    # prefix match either direction (OCR truncation)
    for key, val in ALL_ITEMS.items():
        if len(t) >= 4 and (key.startswith(t) or t.startswith(key)):
            return val
    for key, val in ITEM_FIX.items():
        if len(t) >= 4 and (key.startswith(t) or t.startswith(key)):
            return ALL_ITEMS.get(val.lower())
    return None

def detect_section(cell: str):
    t = norm_text(cell)
    for key, sec in SECTION_MAP.items():
        if key in t:
            return sec
    return None

# ── Table extraction ─────────────────────────────────────────────────────────
def iter_rows(md_text: str):
    """Yield cell-lists for every <tr> in the markdown."""
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", md_text, re.DOTALL | re.IGNORECASE):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.DOTALL | re.IGNORECASE)
        yield [re.sub(r"<[^>]+>", "", c).strip() for c in cells]

# ── Client name extraction ───────────────────────────────────────────────────
def extract_names(md_text: str):
    """Yield (position, raw_name) for each client anchor in document order."""
    anchors = []
    for m in re.finditer(r"[Ии]мя[:_\s]+([A-Za-zА-Яа-яЁё\-]+(?:\s+[A-Za-zА-Яа-яЁё\-]+){1,3})", md_text):
        anchors.append((m.start(), m.group(1)))
    for m in re.finditer(r"Week\s+\d+\s*[.•·]\s*([A-Za-zА-Яа-яЁё\-]+(?:\s+[A-Za-zА-Яа-яЁё\-]+){1,3})", md_text):
        anchors.append((m.start(), m.group(1)))
    for m in re.finditer(r"Go[jj]\s*[•·]\s*([A-Za-zА-Яа-яЁё\-]+(?:\s+[A-Za-zА-Яа-яЁё\-]+){1,3})\s*[•·]", md_text):
        anchors.append((m.start(), m.group(1)))
    for m in re.finditer(r"Week of [\d-]+\s*\|\s*([A-Za-zА-Яа-яЁё\-]+(?:\s+[A-Za-zА-Яа-яЁё\-]+){1,3})\s*\|", md_text):
        anchors.append((m.start(), m.group(1)))
    anchors.sort()
    return anchors

def clean_name(raw: str) -> str:
    n = re.sub(r"\s*(П[HНH]|BT|ВТ|CP|СР|4T|ЧТ|ПТ|САЛАТЫ|CYПb).*$", "", raw).strip()
    n = re.sub(r"\s{2,}", " ", n).strip(" _.,;:")
    return n

# ── Roster ───────────────────────────────────────────────────────────────────
def load_roster():
    if not AUTH_DB.exists():
        return [], {}
    conn = sqlite3.connect(str(AUTH_DB))
    rows = conn.execute("SELECT name FROM clients WHERE active=1 ORDER BY name").fetchall()
    conn.close()
    roster = [r[0] for r in rows if r[0]]
    norm = {}
    for n in roster:
        key = norm_text(n).replace(" ", "")
        norm[key] = n
    return roster, norm

# ── Homoglyph + junk handling for OCR name matching (added 2026-07-26) ──────
# OCR mixes Cyrillic lookalikes into Latin names ("Shteуman" with Cyrillic у).
# Fold Cyrillic homoglyphs → Latin for MATCHING ONLY (stored data untouched).
_CYR2LAT = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "в": "b", "н": "h", "к": "k", "м": "m", "т": "t", "і": "i", "ѕ": "s",
    "А": "a", "Е": "e", "О": "o", "Р": "p", "С": "c", "У": "y", "Х": "x",
    "В": "b", "Н": "h", "К": "k", "М": "m", "Т": "t", "І": "i", "Ѕ": "s",
})
# Header/day words that bleed into OCR'd name fields
_JUNK_RE = re.compile(
    r"\s*(неделя|нeдenя|недen|heдenя|недея|главное|салаты|суп|гарнир|"
    r"пн|вт|ср|чт|пт|сб|вс|пh|bt|cp|4t|пt)\b.*$", re.IGNORECASE)


def _lev(a: str, b: str, cap: int = 3) -> int:
    """Bounded Levenshtein; returns cap+1 when distance exceeds cap."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        row_min = i
        for j, cb in enumerate(b, 1):
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            cur.append(v)
            row_min = min(row_min, v)
        if row_min > cap:
            return cap + 1
        prev = cur
    return prev[-1]


# ── Human-confirmed name aliases (2026-07-26 garbled review) ────────────────
# Kato reviewed each garbled name against the source scan; these win over all
# fuzzy matching. Keys are the raw OCR'd client names as parsed.
_ALIAS_FILE = Path(__file__).with_name("goj_name_aliases.json")

def _load_aliases() -> dict:
    if not _ALIAS_FILE.exists():
        return {}
    try:
        return json.loads(_ALIAS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def fuzzy_roster(name: str, roster: list, norm: dict):
    if not name:
        return None

    def key_of(s: str) -> str:
        return norm_text(s).translate(_CYR2LAT).replace(" ", "")

    # 0. human-confirmed aliases — exact and folded-key lookup
    aliases = _load_aliases()
    if name in aliases:
        return aliases[name]
    akey = key_of(_JUNK_RE.sub("", name).strip(" _.,;:") or name)
    for k, v in aliases.items():
        if key_of(_JUNK_RE.sub("", k).strip(" _.,;:") or k) == akey:
            return v

    cleaned = _JUNK_RE.sub("", name).strip(" _.,;:") or name
    key = key_of(cleaned)
    if key in norm:
        return norm[key]
    # token containment (homoglyph-folded, junk-stripped)
    toks = [t for t in norm_text(cleaned).translate(_CYR2LAT).split() if len(t) >= 3]
    if toks:
        for r in roster:
            rl = norm_text(r).translate(_CYR2LAT)
            if all(t in rl for t in toks):
                return r
    # unique last-name containment
    last = toks[-1] if toks else key
    cands = [r for r in roster if last and last in norm_text(r).translate(_CYR2LAT)]
    if len(cands) == 1:
        return cands[0]
    # Levenshtein fallback on folded key — unique best only, conservative:
    # accept dist<=1 always; dist<=2 only for long keys with clear margin.
    if len(key) >= 6:
        scored = sorted((( _lev(key, key_of(r), cap=3), r) for r in roster),
                        key=lambda x: x[0])
        if scored:
            best_d, best_r = scored[0]
            second_d = scored[1][0] if len(scored) > 1 else 99
            if best_d == 0:
                return best_r
            if best_d == 1 and second_d >= 2:
                return best_r
            if best_d == 2 and len(key) >= 9 and second_d >= 4:
                return best_r
    return None

# ── Week / shift extraction ──────────────────────────────────────────────────
def extract_week(md_text: str, fallback_monday: date = None):
    """Menu week for a scanned form.

    KATO'S RULE (2026-07-26): forms received during week N are orders FOR
    week N+1 — GOJ fills menus one week ahead. The scan/received date
    (fallback_monday, from the doc-ID filename) is authoritative: a form
    may carry a stale printed header from an earlier week, but whatever
    arrives this week feeds next week's kitchen. Header text is only a
    fallback when no filename date exists.
    """
    if fallback_monday:
        return fallback_monday + timedelta(days=7)
    base = None
    m = re.search(r"Week of (\d{4}-\d{2}-\d{2})", md_text)
    if m:
        try:
            base = date.fromisoformat(m.group(1))
        except ValueError:
            pass
    if base is None:
        m = re.search(r"Week\s+#?:?\s*(\d{1,2})\b", md_text)
        if m:
            wk = int(m.group(1))
            try:
                base = date.fromisocalendar(2026, wk, 1)
            except ValueError:
                pass
    return base + timedelta(days=7) if base else None


def week_from_filename(name: str):
    """Scan doc IDs embed timestamp: doc00601020260721143000 → 2026-07-21.
    Returns the Monday of that scan's week."""
    m = re.search(r"(20\d{2})(\d{2})(\d{2})\d{6}", name)
    if not m:
        return None
    try:
        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return d - timedelta(days=d.weekday())
    except ValueError:
        return None

def extract_shift(md_text: str):
    m = re.search(r"Shift[:\s]+(\d)", md_text)
    if m:
        return m.group(1)
    m = re.search(r"[·•.]\s*Shift\s+(\d)", md_text)
    if m:
        return m.group(1)
    return None

# ── Core parser ──────────────────────────────────────────────────────────────
def parse_menu_md(md_path, roster=None, norm=None, fallback_monday=None):
    """Parse one MinerU markdown file.
    Returns dict: {clients: {raw_name: {matched, shift, days: {day_idx: {cat: item}}}},
                   week_start, default_shift, stats}
    """
    md_text = Path(md_path).read_text(encoding="utf-8", errors="replace")
    week_start = extract_week(md_text, fallback_monday)
    default_shift = extract_shift(md_text)

    anchors = extract_names(md_text)

    # Walk rows, tracking current client / section / day-index layout
    clients = {}
    current_client = None
    current_section = None
    day_idx_layout = None  # list of cell indices for ПН..ПТ when known

    def ensure_client(raw):
        nonlocal current_client
        name = clean_name(raw)
        if name and name != current_client:
            current_client = name
            if name not in clients:
                clients[name] = {"shift": None, "days": {i: {} for i in range(5)}}

    # Anchor positions tell us where names change; iterate rows with text pos
    row_iter = list(iter_rows(md_text))
    # Rebuild an approximate position map by scanning sequentially
    pos = 0
    anchor_i = 0
    for cells in row_iter:
        joined = " ".join(cells)
        # advance anchors up to this row
        row_pos = md_text.find(joined[:40], pos) if joined.strip() else pos
        if row_pos < 0:
            row_pos = pos
        while anchor_i < len(anchors) and anchors[anchor_i][0] <= row_pos + 1:
            ensure_client(anchors[anchor_i][1])
            anchor_i += 1
        pos = row_pos + 1

        if not cells:
            continue

        # Section headers (may be embedded in header blob or standalone row)
        for c in cells[:2]:
            sec = detect_section(c)
            if sec:
                current_section = sec
                break

        # Day-label header → learn layout (variant B)
        labels = []
        for i, c in enumerate(cells):
            key = norm_text(c).replace(" ", "")
            if key in DAY_LABELS:
                labels.append((i, DAY_LABELS[key]))
        if len(labels) >= 4:
            labels.sort()
            layout = [None] * 5
            for i, d in labels:
                if layout[d] is None:
                    layout[d] = i
            day_idx_layout = layout
            continue

        # Item rows — item name may be in cell 0 or cell 1 (leading empty cell)
        if current_client is None:
            continue
        item = None
        name_i = -1
        for ci in range(min(2, len(cells))):
            if cells[ci].strip():
                item = match_item(cells[ci])
                if item:
                    name_i = ci
                    break
        if not item:
            continue

        cat, canonical = item
        section = cat or current_section
        if section is None:
            continue

        # Day cells
        if day_idx_layout and len(cells) > max(i for i in day_idx_layout if i is not None):
            day_cells = {d: cells[i] for d, i in enumerate(day_idx_layout) if i is not None}
        else:
            # variant A: 5 cells right after the name cell
            rest = cells[name_i + 1:name_i + 6]
            day_cells = {d: rest[d] for d in range(len(rest))}

        for d, cell in day_cells.items():
            if d > 4:
                continue
            if is_checked(cell):
                clients[current_client]["days"][d].setdefault(section, canonical)

    # Apply default shift from doc footer
    for info in clients.values():
        info["shift"] = default_shift

    total_sel = 0
    matched = 0
    out_clients = {}
    for raw, info in clients.items():
        mname = fuzzy_roster(raw, roster or [], norm or {}) if roster is not None else None
        if mname:
            matched += 1
        sel = sum(len(v) for v in info["days"].values())
        total_sel += sel
        out_clients[raw] = {"matched": mname, "shift": info["shift"], "days": info["days"],
                            "selections": sel}
    stats = {"clients": len(clients), "matched": matched, "selections": total_sel,
             "week_start": str(week_start) if week_start else None,
             "default_shift": default_shift}
    return {"clients": out_clients, "stats": stats}


def rows_for_db(parsed, shift_lookup=None):
    """Flatten parsed result into client_menus rows.
    shift_lookup(client_name, day_code) -> '1'/'2' or None (from auth_tracker).
    Yields (client_name, menu_date, day_code, shift, salad, soup, main, side).
    """
    ws = parsed["stats"].get("week_start")
    if not ws:
        return []
    week_monday = date.fromisoformat(ws)
    rows = []
    for raw, info in parsed["clients"].items():
        client = info["matched"] or raw
        for d, cats in info["days"].items():
            if not cats:
                continue
            menu_date = week_monday + timedelta(days=d)
            day_code = DAY_CODES[d]
            shift = info["shift"]
            if not shift and shift_lookup:
                shift = shift_lookup(client, day_code)
            if not shift:
                shift = "1"
            rows.append((client, str(menu_date), day_code, shift,
                         cats.get("salad"), cats.get("soup"),
                         cats.get("main"), cats.get("side")))
    return rows


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 goj_menu_form_parser.py <mineru.md> [--json]")
        sys.exit(1)
    roster, norm = load_roster()
    result = parse_menu_md(sys.argv[1], roster, norm)
    print(f"Week: {result['stats']['week_start']}  Shift: {result['stats']['default_shift']}")
    print(f"Clients: {result['stats']['clients']}  Matched: {result['stats']['matched']}  "
          f"Selections: {result['stats']['selections']}")
    if "--json" in sys.argv:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        for raw, info in list(result["clients"].items())[:8]:
            print(f"\n  {raw} → {info['matched'] or 'NO MATCH'} ({info['selections']} sel)")
            for d in range(5):
                if info["days"][d]:
                    print(f"    {DAY_CODES[d]}: {info['days'][d]}")
