#!/usr/bin/env python3.11
"""
CC_ocr_oversight_agent.py — GHS OCR Quality-Control Layer
==========================================================
Strict quality-control on top of the existing 4-engine OCR pipeline.
Reads GOJ menu-scan PDFs, validates extracted food selections against the
canonical menu item list, and corrects low-confidence rows in auth_tracker.db.

Usage:
    python3 CC_ocr_oversight_agent.py               # --scan (default)
    python3 CC_ocr_oversight_agent.py --audit        # confidence tier report
    python3 CC_ocr_oversight_agent.py --fix-all      # re-process all LOW rows

What it does (--scan):
  1. SCAN      — finds unprocessed PDFs or rows with confidence < 0.75
  2. RE-PROCESS — runs Claude Vision (claude-sonnet-4-6) as authoritative engine
  3. VALIDATE  — fuzzy-matches items vs CC_menu_constants (85% threshold, rapidfuzz)
  4. WRITE     — updates client_menus only if new confidence > existing (never downgrades)
  5. REPORT    — sends Telegram summary to Kato

PAUSE RULE (Kato directive 2026-06-04):
    Any uncertainty → send Telegram PAUSE to Kato BEFORE acting.
    Format: "⚠️ OCR AGENT PAUSE — [reason]. Options: A) … or B) … Awaiting your call."
    If Telegram unreachable → log to ocr_oversight_pauses.json and HALT that item.
    Never write uncertain data to auth_tracker.db.
"""

import argparse
import base64
import json
import logging
import os
import re
import sqlite3
import sys
import urllib.request
import urllib.error
from datetime import datetime, date, timedelta
from pathlib import Path

# Import the Telegram image-send fallback so PAUSE messages include the problematic page
from CC_ocr_telegram_fallback import flag_for_review

# ── Paths ──────────────────────────────────────────────────────────────────────
REX_DIR   = Path(__file__).resolve().parent
DB_PATH   = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"

# PDFs may land in either location depending on which pipeline deposited them
MENUS_DIRS = [
    Path.home() / "Documents" / "goj files" / "dashboard" / "documents" / "menus",
    REX_DIR / "menus",
]

TG_CFG_PATH = REX_DIR / "rex_rexxie_telegram_config.json"
LOG_PATH    = REX_DIR / "logs" / "ocr_oversight.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_PATH), encoding="utf-8"),
    ],
)
log = logging.getLogger("ocr-oversight")

# ── Menu constants (CC_menu_constants.py is canonical source of truth) ─────────
sys.path.insert(0, str(REX_DIR))
try:
    from CC_menu_constants import (
        SALADS, SOUPS, MAINS_P1, MAINS_P2, ALL_MAINS, SIDES, DAYS, DAY_MAP
    )
    ALL_VALID_ITEMS = SALADS + SOUPS + ALL_MAINS + SIDES
    log.info(
        f"Menu constants: {len(SALADS)} salads | {len(SOUPS)} soups | "
        f"{len(ALL_MAINS)} mains | {len(SIDES)} sides"
    )
except ImportError as e:
    log.error(f"Cannot import CC_menu_constants: {e}")
    sys.exit(1)

# ── Vision config ──────────────────────────────────────────────────────────────
CLAUDE_MODEL      = "claude-sonnet-4-6"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

# ── Thresholds ─────────────────────────────────────────────────────────────────
CONFIDENCE_LOW    = 0.75   # rows below this are candidates for re-processing
CONFIDENCE_HIGH   = 0.90   # rows at or above this are considered HIGH tier
FUZZY_THRESHOLD   = 85     # minimum rapidfuzz score (0–100) to accept a menu item match
NAME_PAUSE_SCORE  = 0.80   # client-name match below this → PAUSE before writing
NAME_HALT_SCORE   = 0.65   # client-name match below this → cannot continue at all

# ── Vision prompt ──────────────────────────────────────────────────────────────
_VISION_PROMPT = """\
You are reading a scanned Garden of Joy Adult Day Care weekly menu selection form.
The form is handwritten Russian. Extract ALL food selections marked by the client for the week.

Known valid items (use EXACT spelling):
САЛАТЫ (salads): {salads}
СУПЫ (soups): {soups}
ГЛАВНОЕ БЛЮДО (mains): {mains}
ГАРНИР (sides): {sides}

Days — ПН=Monday(M), ВТ=Tuesday(T), СР=Wednesday(W), ЧТ=Thursday(TH),
        ПТ=Friday(F), СБ=Saturday(SA)

Return ONLY valid JSON, no prose:
{{
  "client_name": "as written on form header or null",
  "week_indicator": "date or text in Неделя field or null",
  "page_type": "p1 or p2 or combined",
  "days": {{
    "M":  {{"salad": null, "soup": null, "main": null, "side": null}},
    "T":  {{"salad": null, "soup": null, "main": null, "side": null}},
    "W":  {{"salad": null, "soup": null, "main": null, "side": null}},
    "TH": {{"salad": null, "soup": null, "main": null, "side": null}},
    "F":  {{"salad": null, "soup": null, "main": null, "side": null}},
    "SA": {{"salad": null, "soup": null, "main": null, "side": null}}
  }},
  "conflicts": [],
  "confidence": 0.0,
  "notes": ""
}}

Rules:
- Use EXACT Russian names from the lists above — match as closely as possible
- confidence = your overall confidence in the reads (0.0–1.0)
- p1 forms: salad/soup/main visible. p2 forms: main continuation + side. combined: all fields
- Set null for fields not visible or not checked on this page
- If two items are checked in the same cell, record the more clearly marked one in the day
  and describe both in conflicts[]
- Return ONLY the JSON object, no markdown fences or extra text\
"""


# ══════════════════════════════════════════════════════════════════════════════
# TELEGRAM  ───────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def _tg_send(text: str) -> bool:
    """Send text to Kato via @Hermes_Cloud_May_bot. Returns True on success."""
    if not TG_CFG_PATH.exists():
        log.warning("Telegram config not found — cannot send notification")
        return False
    try:
        cfg     = json.loads(TG_CFG_PATH.read_text())
        token   = cfg.get("bot_token", "")
        chat_id = cfg.get("owner_chat_id", 0)
    except Exception as e:
        log.warning(f"Telegram config parse error: {e}")
        return False
    if not token or not chat_id:
        log.warning("Telegram token or chat_id missing in config")
        return False
    payload = json.dumps({
        "chat_id":    chat_id,
        "text":       text,
        "parse_mode": "HTML",
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            ok = json.loads(resp.read()).get("ok", False)
            if ok:
                log.info("Telegram: sent OK")
            return bool(ok)
    except Exception as e:
        log.warning(f"Telegram send failed: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# PAUSE / HALT  ────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

class _PauseHalt(Exception):
    """
    Raised when the agent cannot proceed with one item due to uncertainty.
    Callers catch this and skip the item — they do NOT re-raise unless the
    uncertainty prevents ALL further work (e.g. missing client_id).
    """


def _pause_and_halt(
    reason: str,
    options: list[str],
    context: dict | None = None,
    pdf_path: Path | None = None,
    page_num: int | None = None,
) -> None:
    """
    Kato's 2026-06-04 directive implementation:
      1. Build a PAUSE message and send to Kato via Telegram.
         If a PDF path + page is given, ALSO send the rendered page image
         so Kato can see exactly what Rexxie is confused about.
      2. If Telegram is unreachable, write to ocr_oversight_pauses.json and log.
      3. Raise _PauseHalt — caller decides whether to continue with the next item.
    Never writes uncertain data.
    """
    opt_text = " or ".join(f"{chr(65+i)}) {o}" for i, o in enumerate(options))
    tg_msg = (
        f"⚠️ <b>OCR AGENT PAUSE</b> — {reason}.\n"
        f"Options: {opt_text}. Awaiting your call."
    )
    if context:
        ctx_lines = "\n".join(f"  {k}: {v}" for k, v in context.items())
        tg_msg += f"\n\nContext:\n{ctx_lines}"

    log.warning(f"PAUSE: {reason}")

    # If we have the PDF + page — send the IMAGE with the question as caption
    # so Kato can SEE the problematic area, not just read text about it
    sent = False
    if pdf_path and page_num is not None and pdf_path.exists():
        result = flag_for_review(
            source="ocr_oversight",
            file_path=pdf_path,
            reason=reason,
            partial=context or {},
            bot="rex_of_gold",
            page_num=page_num,
        )
        sent = result.get("ok", False)
        if not sent:
            log.warning("flag_for_review failed — falling back to text-only Telegram")
    else:
        sent = _tg_send(tg_msg)

    if not sent:
        # Telegram unreachable — write to pause log and HALT
        _write_pause_log(reason, options, context)
        log.error(
            "HALT: Telegram unreachable. Uncertainty logged to ocr_oversight_pauses.json. "
            "Will not write uncertain data."
        )

    raise _PauseHalt(reason)


def _write_pause_log(reason: str, options: list[str], context: dict | None) -> None:
    pause_log = LOG_PATH.parent / "ocr_oversight_pauses.json"
    pauses: list = []
    if pause_log.exists():
        try:
            pauses = json.loads(pause_log.read_text())
        except Exception:
            pauses = []
    pauses.append({
        "timestamp": datetime.now().isoformat(),
        "type":      "PAUSE_HALT",
        "reason":    reason,
        "options":   options,
        "context":   context or {},
    })
    pause_log.write_text(json.dumps(pauses, indent=2, ensure_ascii=False))
    log.error(f"Pause entry written to {pause_log}")


# ══════════════════════════════════════════════════════════════════════════════
# AUDIT TABLE  ────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def _ensure_audit_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ocr_oversight_audit (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            action          TEXT    NOT NULL,
            pdf_name        TEXT,
            client_id       INTEGER,
            client_name     TEXT,
            week_start      TEXT,
            day             TEXT,
            field           TEXT,
            old_value       TEXT,
            new_value       TEXT,
            old_confidence  REAL,
            new_confidence  REAL,
            flagged         INTEGER DEFAULT 0,
            flag_reason     TEXT,
            created_at      TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


def _audit(conn: sqlite3.Connection, action: str, **kwargs) -> None:
    """Write one row to ocr_oversight_audit."""
    _ensure_audit_table(conn)
    fields = [
        "action", "pdf_name", "client_id", "client_name", "week_start", "day",
        "field", "old_value", "new_value", "old_confidence", "new_confidence",
        "flagged", "flag_reason",
    ]
    row = {f: kwargs.get(f) for f in fields}
    row["action"] = action
    col_list     = ", ".join(fields)
    placeholders = ", ".join(f":{f}" for f in fields)
    conn.execute(
        f"INSERT INTO ocr_oversight_audit ({col_list}) VALUES ({placeholders})",
        row,
    )
    conn.commit()


# ══════════════════════════════════════════════════════════════════════════════
# FUZZY VALIDATION  ───────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def _best_fuzzy_match(value: str, valid_list: list[str]) -> tuple[str | None, float]:
    """
    Find the best match for `value` in `valid_list` using rapidfuzz.
    Falls back to difflib if rapidfuzz is unavailable.
    Returns (best_match, score_0_to_100).
    """
    try:
        from rapidfuzz import fuzz, process as rfp
        result = rfp.extractOne(value, valid_list, scorer=fuzz.token_sort_ratio)
        if result:
            return result[0], float(result[1])
        return None, 0.0
    except ImportError:
        import difflib
        matches = difflib.get_close_matches(value, valid_list, n=1, cutoff=0.5)
        if matches:
            score = difflib.SequenceMatcher(None, value.lower(), matches[0].lower()).ratio() * 100
            return matches[0], score
        return None, 0.0


def validate_item(
    value: str | None,
    category: str,
) -> tuple[str | None, float, bool, str]:
    """
    Validate one extracted menu item against the known-valid list for that category.

    Returns:
        canonical_value  — corrected item string (or original if unmatched)
        match_score      — 0.0–1.0 (1.0 for null/skip, actual fuzzy score otherwise)
        is_valid         — True if score ≥ FUZZY_THRESHOLD
        note             — human-readable description
    """
    if not value:
        return None, 1.0, True, "null/skipped"

    valid_map: dict[str, list[str]] = {
        "salad": SALADS,
        "soup":  SOUPS,
        "main":  ALL_MAINS,
        "side":  SIDES,
    }
    valid_list = valid_map.get(category, ALL_VALID_ITEMS)
    best, score = _best_fuzzy_match(value, valid_list)

    if score >= FUZZY_THRESHOLD:
        return best, score / 100.0, True, f"matched '{best}' at {score:.0f}%"

    return value, score / 100.0, False, (
        f"no match ≥{FUZZY_THRESHOLD}% (best: '{best}' at {score:.0f}%)"
    )


# ══════════════════════════════════════════════════════════════════════════════
# CLIENT MATCHING  ────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def _match_client(
    raw_name: str,
    conn: sqlite3.Connection,
) -> tuple[int | None, str | None, float]:
    """
    Fuzzy-match raw_name to the clients table.
    Returns (client_id, db_name, score_0_to_1).
    """
    if not raw_name or not raw_name.strip():
        return None, None, 0.0

    cur = conn.cursor()
    try:
        cur.execute("SELECT client_id, name FROM clients WHERE active=1")
    except sqlite3.OperationalError:
        try:
            cur.execute("SELECT client_id, name FROM clients")
        except Exception:
            return None, None, 0.0

    candidates = cur.fetchall()
    if not candidates:
        return None, None, 0.0

    query = raw_name.strip()
    try:
        from rapidfuzz import fuzz, process as rfp
        result = rfp.extractOne(
            query, [c[1] for c in candidates],
            scorer=fuzz.token_sort_ratio,
        )
        if result:
            matched_name, score, idx = result
            return candidates[idx][0], matched_name, score / 100.0
    except ImportError:
        import difflib
        names = [c[1] for c in candidates]
        matches = difflib.get_close_matches(query, names, n=1, cutoff=0.5)
        if matches:
            for cid, cname in candidates:
                if cname == matches[0]:
                    s = difflib.SequenceMatcher(None, query.lower(), cname.lower()).ratio()
                    return cid, cname, s

    return None, None, 0.0


# ══════════════════════════════════════════════════════════════════════════════
# WEEK INFERENCE  ─────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def _infer_week_start(week_indicator: str | None = None) -> str:
    """
    LOCKED RULE (from goj_menu_ocr.py / CC_ocr_worker.py):
    Menus scanned during the current week are ALWAYS for NEXT WEEK.
    week_indicator (text on the form) is stored in notes but never used to
    determine week_start.
    """
    today      = date.today()
    days_ahead = 7 - today.weekday()
    if today.weekday() == 0:  # today IS Monday → still use NEXT Monday
        days_ahead = 7
    next_monday = today + timedelta(days=days_ahead)
    # Defensive guard
    while next_monday <= today:
        next_monday += timedelta(days=7)
    if week_indicator:
        log.debug(
            f"week_indicator '{week_indicator}' noted but not used for week_start (locked rule)"
        )
    return next_monday.isoformat()


# ══════════════════════════════════════════════════════════════════════════════
# PDF → BASE64  ───────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def _pdf_page_to_b64(pdf_path: Path, page_num: int, dpi: int = 150) -> str | None:
    """Convert a single PDF page to base64-encoded JPEG for Vision API."""
    try:
        import fitz  # PyMuPDF
        doc  = fitz.open(str(pdf_path))
        if page_num >= len(doc):
            doc.close()
            return None
        page = doc[page_num]
        mat  = fitz.Matrix(dpi / 72, dpi / 72)
        pix  = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        data = base64.b64encode(pix.tobytes("jpeg", jpg_quality=85)).decode()
        doc.close()
        return data
    except ImportError:
        log.error("PyMuPDF (fitz) not installed — run: pip install pymupdf")
        return None
    except Exception as e:
        log.error(f"PDF page {page_num} to b64 failed: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# CLAUDE VISION  ──────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def _call_vision(image_b64: str, api_key: str) -> dict | None:
    """Call Claude Vision and parse the JSON response."""
    payload = json.dumps({
        "model":      CLAUDE_MODEL,
        "max_tokens": 1500,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type":   "image",
                    "source": {
                        "type":       "base64",
                        "media_type": "image/jpeg",
                        "data":       image_b64,
                    },
                },
                {
                    "type": "text",
                    "text": _VISION_PROMPT.format(
                        salads=", ".join(SALADS),
                        soups=", ".join(SOUPS),
                        mains=", ".join(ALL_MAINS),
                        sides=", ".join(SIDES),
                    ),
                },
            ],
        }],
    }).encode()

    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=payload,
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read())
            text = data["content"][0]["text"].strip()
            # Strip markdown fences if model wraps in ```json … ```
            if text.startswith("```"):
                text = re.sub(r"^```[a-z]*\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
            return json.loads(text)
    except urllib.error.HTTPError as e:
        body = e.read()[:300]
        log.error(f"Vision API HTTP {e.code}: {body}")
        return None
    except Exception as e:
        log.error(f"Vision API call failed: {e}")
        return None


def _get_api_key() -> str | None:
    """Resolve Anthropic API key from env → .env files."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    for env_path in [
        REX_DIR / ".env",
        Path.home() / ".hermes" / "profiles" / "cloud" / ".env",
        Path.home() / "Documents" / "goj files" / ".env",
    ]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("ANTHROPIC_API_KEY="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        return val
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 1 · SCAN  ───────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def scan(
    conn: sqlite3.Connection,
    fix_all: bool = False,
) -> dict:
    """
    Identify PDFs that need (re-)processing.

    Returns:
        {
            "unprocessed":   [Path, ...],          # PDFs with no rows in client_menus
            "low_confidence": [(Path, min_conf), ...],  # PDFs with min conf < 0.75
        }
    """
    cur = conn.cursor()

    # Gather every PDF from all known menus directories
    all_pdfs: list[Path] = []
    for mdir in MENUS_DIRS:
        if mdir.exists():
            found = sorted(mdir.glob("*.pdf"))
            log.info(f"SCAN: {len(found)} PDFs in {mdir}")
            all_pdfs.extend(found)

    log.info(f"SCAN: {len(all_pdfs)} total PDFs across all directories")

    # PDFs already represented in client_menus (keyed by source_pdf filename)
    try:
        cur.execute("""
            SELECT source_pdf, MIN(COALESCE(confidence, 0)) AS min_conf
            FROM client_menus
            WHERE source_pdf IS NOT NULL
            GROUP BY source_pdf
        """)
        processed: dict[str, float] = {row[0]: row[1] for row in cur.fetchall()}
    except sqlite3.OperationalError:
        processed = {}  # table doesn't exist yet — all PDFs are unprocessed

    unprocessed:    list[Path]               = []
    low_confidence: list[tuple[Path, float]] = []

    for pdf in all_pdfs:
        name = pdf.name
        if name not in processed:
            unprocessed.append(pdf)
            log.info(f"  UNPROCESSED: {name}")
        elif processed[name] < CONFIDENCE_LOW or fix_all:
            low_confidence.append((pdf, processed[name]))
            log.info(f"  LOW CONF:    {name}  (min={processed[name]:.2f})")

    log.info(
        f"SCAN complete: {len(unprocessed)} unprocessed, "
        f"{len(low_confidence)} low-confidence (threshold={CONFIDENCE_LOW})"
    )
    return {"unprocessed": unprocessed, "low_confidence": low_confidence}


# ══════════════════════════════════════════════════════════════════════════════
# 2 · RE-PROCESS  ─────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def reprocess_pdf(
    pdf_path: Path,
    api_key:  str,
) -> list[dict]:
    """
    Run Claude Vision on every page of the PDF and return a flat list of
    day-records, one per (day, client) found.

    Each record:
        client_name, week_indicator, day, salad, soup, main, side,
        confidence, conflicts, source_page
    """
    log.info(f"RE-PROCESS: {pdf_path.name}")

    try:
        import fitz
        doc     = fitz.open(str(pdf_path))
        n_pages = len(doc)
        doc.close()
    except Exception as e:
        log.error(f"Cannot open {pdf_path.name}: {e}")
        return []

    log.info(f"  {n_pages} page(s)")

    # Call Vision on each page; collect structured results
    pages_data: list[dict] = []
    for page_num in range(n_pages):
        img_b64 = _pdf_page_to_b64(pdf_path, page_num)
        if not img_b64:
            log.warning(f"  Page {page_num}: image conversion failed — skipping")
            continue
        result = _call_vision(img_b64, api_key)
        if not result:
            log.warning(f"  Page {page_num}: Vision returned no result")
            continue
        result["_page_num"] = page_num
        pages_data.append(result)
        log.info(
            f"  Page {page_num}: client='{result.get('client_name')}' "
            f"conf={result.get('confidence', 0):.2f} type={result.get('page_type')}"
        )

    if not pages_data:
        log.warning(f"  No usable Vision results for {pdf_path.name}")
        return []

    # Merge consecutive page pairs (p1 + p2 are two halves of one client's form)
    # Heuristic: p1 carries the client name; p2 is a continuation with no header.
    # We merge day-data from both pages, taking non-null values with priority to p1.
    records: list[dict] = []
    i = 0
    while i < len(pages_data):
        p1 = pages_data[i]

        # Decide whether the NEXT page is the p2 continuation of THIS form
        p2: dict | None = None
        if (i + 1 < len(pages_data)
                and not pages_data[i + 1].get("client_name")  # p2 has no name header
                and pages_data[i + 1].get("page_type") == "p2"):
            p2 = pages_data[i + 1]
            i += 2
        else:
            i += 1

        client_name    = (p1.get("client_name") or "").strip()
        week_indicator = p1.get("week_indicator") or (p2.get("week_indicator") if p2 else None)
        conf_p1        = float(p1.get("confidence") or 0.0)
        conf_p2        = float(p2.get("confidence") or conf_p1) if p2 else conf_p1
        confidence     = (conf_p1 + conf_p2) / 2 if p2 else conf_p1
        conflicts      = list(p1.get("conflicts") or []) + list((p2.get("conflicts") or []) if p2 else [])

        for day in DAYS:
            d1 = (p1.get("days") or {}).get(day) or {}
            d2 = ((p2.get("days") or {}).get(day) or {}) if p2 else {}

            merged = {
                "salad": d1.get("salad") or d2.get("salad"),
                "soup":  d1.get("soup")  or d2.get("soup"),
                "main":  d1.get("main")  or d2.get("main"),
                "side":  d1.get("side")  or d2.get("side"),
            }

            # Only emit a record if at least one field is filled
            if any(v for v in merged.values()):
                records.append({
                    "client_name":    client_name,
                    "week_indicator": week_indicator,
                    "day":            day,
                    "salad":          merged["salad"],
                    "soup":           merged["soup"],
                    "main":           merged["main"],
                    "side":           merged["side"],
                    "confidence":     confidence,
                    "conflicts":      conflicts,
                    "source_page":    p1["_page_num"],
                })

    log.info(f"  Extracted {len(records)} day-records from {pdf_path.name}")
    return records


# ══════════════════════════════════════════════════════════════════════════════
# 3 · VALIDATE  ───────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def validate_record(
    record:   dict,
    conn:     sqlite3.Connection,
    pdf_name: str,
    pdf_path: Path | None = None,
) -> dict:
    """
    Validate one day-record:
      a) Fuzzy-match each food item against valid options
      b) Match client name to the clients table
      c) Assign week_start (locked rule)

    Raises _PauseHalt if uncertain about any critical field.
    Returns the enriched record with client_id, canonical items, _anomalies.

    When pdf_path is provided, PAUSE messages include a rendered image
    of the problematic page so Kato can see exactly what Rexxie is confused about.
    """
    anomalies: list[str] = []
    source_page = record.get("source_page", 0)  # 0-indexed page number

    # ── a) Validate each food field ────────────────────────────────────────────
    for field, category in [("salad", "salad"), ("soup", "soup"), ("main", "main"), ("side", "side")]:
        raw = record.get(field)
        if not raw:
            continue  # null is fine — client didn't select this category today
        canonical, score, is_valid, note = validate_item(raw, category)
        if is_valid:
            record[field] = canonical  # canonicalize to exact known form
        else:
            # Item doesn't match anything in the menu — PAUSE before touching DB
            _pause_and_halt(
                reason=(
                    f"Extracted '{raw}' ({field}) for client '{record.get('client_name')}' "
                    f"day {record.get('day')} (PDF: {pdf_name}) — {note}"
                ),
                options=[
                    f"Accept best match '{canonical}' and write it",
                    "Write null for this field and flag for manual review",
                    "Skip this entire day-record",
                ],
                context={
                    "pdf":        pdf_name,
                    "day":        record.get("day"),
                    "field":      field,
                    "raw_value":  raw,
                    "best_match": canonical,
                    "score":      f"{score*100:.0f}%",
                },
                pdf_path=pdf_path,
                page_num=source_page + 1,  # pdftoppm is 1-indexed
            )
            # If we get here Telegram sent successfully — PAUSE raised _PauseHalt anyway
            # (unreachable, but keeps the linter happy)
            record[field] = None
            anomalies.append(f"{field}='{raw}' ({note})")

    # ── b) Log conflicts (informational, not a halt) ───────────────────────────
    if record.get("conflicts"):
        anomalies.append(f"conflicts: {record['conflicts']}")

    # ── c) Match client name to DB ─────────────────────────────────────────────
    raw_name = (record.get("client_name") or "").strip()
    client_id, db_name, name_score = _match_client(raw_name, conn)

    # Cannot identify client at all — hard halt, cannot write without client_id
    if client_id is None or name_score < NAME_HALT_SCORE:
        _pause_and_halt(
            reason=(
                f"Cannot identify client from name '{raw_name}' on PDF '{pdf_name}' "
                f"(best DB match: {db_name!r} at {name_score:.0%}). "
                "Cannot write without a confirmed client_id."
            ),
            options=[
                "Manually confirm client_id and re-run with an override",
                "Skip this PDF entirely",
            ],
            context={
                "pdf":           pdf_name,
                "raw_name":      raw_name,
                "best_db_name":  db_name,
                "score":         f"{name_score:.0%}",
            },
            pdf_path=pdf_path,
            page_num=source_page + 1,  # pdftoppm is 1-indexed
        )
        # _PauseHalt raised above — re-raise so caller skips this PDF entirely
        raise _PauseHalt(f"unidentifiable client '{raw_name}'")

    # Low-confidence name match — warn Kato before writing to a possibly wrong client
    if name_score < NAME_PAUSE_SCORE:
        _pause_and_halt(
            reason=(
                f"Client name match is uncertain: '{raw_name}' → '{db_name}' "
                f"at {name_score:.0%}. Writing to wrong client corrupts their food order."
            ),
            options=[
                f"Confirm match to '{db_name}' (client_id={client_id}) and proceed",
                "Skip this day-record and flag PDF for manual review",
            ],
            context={
                "pdf":              pdf_name,
                "raw_name":         raw_name,
                "matched_db_name":  db_name,
                "client_id":        client_id,
                "score":            f"{name_score:.0%}",
            },
            pdf_path=pdf_path,
            page_num=source_page + 1,  # pdftoppm is 1-indexed
        )

    record["client_id"]   = client_id
    record["client_name"] = db_name  # store canonical DB name, not raw OCR text

    # ── d) Assign week_start (locked rule) ─────────────────────────────────────
    record["week_start"] = _infer_week_start(record.get("week_indicator"))

    record["_anomalies"] = anomalies
    return record


# ══════════════════════════════════════════════════════════════════════════════
# 4 · WRITE  ──────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def write_record(
    record:   dict,
    pdf_name: str,
    conn:     sqlite3.Connection,
) -> str:
    """
    Upsert one validated day-record to client_menus.

    Rules:
      - NEVER downgrade confidence — only write if new conf > existing conf.
      - Never DELETE — only UPDATE or INSERT.
      - Uses column `main` (never `main_dish`).
      - Every write produces an audit row in ocr_oversight_audit.

    Returns: "inserted" | "updated" | "skipped"
    """
    cur        = conn.cursor()
    client_id  = record["client_id"]
    week_start = record["week_start"]
    day        = record["day"]
    confidence = float(record.get("confidence") or 0.0)

    # Look for an existing row for this (client, week, day)
    cur.execute("""
        SELECT id, main, salad, soup, side, confidence
        FROM   client_menus
        WHERE  client_id=? AND week_start=? AND day=?
    """, (client_id, week_start, day))
    existing = cur.fetchone()

    if existing:
        row_id, old_main, old_salad, old_soup, old_side, old_conf = existing
        old_conf = float(old_conf or 0.0)

        # Never downgrade
        if confidence <= old_conf:
            log.info(
                f"  SKIP {record['client_name']} {day}: "
                f"new conf {confidence:.2f} ≤ existing {old_conf:.2f}"
            )
            _audit(conn, "SKIPPED_LOWER_CONFIDENCE",
                   pdf_name=pdf_name, client_id=client_id,
                   client_name=record["client_name"],
                   week_start=week_start, day=day,
                   old_confidence=old_conf, new_confidence=confidence)
            return "skipped"

        # Update with better data — use COALESCE so we don't null-out fields
        # that the old pipeline filled but this page didn't cover
        cur.execute("""
            UPDATE client_menus
            SET    salad       = COALESCE(?, salad),
                   soup        = COALESCE(?, soup),
                   main        = COALESCE(?, main),
                   side        = COALESCE(?, side),
                   confidence  = ?,
                   source_pdf  = ?,
                   source      = 'ocr-oversight',
                   notes       = COALESCE(notes, '') ||
                                 ' | oversight-updated ' || datetime('now')
            WHERE  id = ?
        """, (
            record.get("salad"), record.get("soup"),
            record.get("main"),  record.get("side"),
            confidence, pdf_name, row_id,
        ))
        conn.commit()

        _audit(conn, "UPDATED",
               pdf_name=pdf_name, client_id=client_id,
               client_name=record["client_name"],
               week_start=week_start, day=day, field="main",
               old_value=old_main, new_value=record.get("main"),
               old_confidence=old_conf, new_confidence=confidence)
        log.info(
            f"  UPDATE {record['client_name']} {day}: "
            f"conf {old_conf:.2f}→{confidence:.2f}  main='{record.get('main')}'"
        )
        return "updated"

    else:
        # New row — INSERT
        anomaly_note = (
            f"inserted by ocr-oversight | anomalies: {record.get('_anomalies', [])}"
        )
        cur.execute("""
            INSERT INTO client_menus
              (client_id, client_name, week_start, day,
               salad, soup, main, side,
               confidence, source_pdf, source, notes, created_at)
            VALUES (?,?,?,?,  ?,?,?,?,  ?,?,?,?, datetime('now'))
        """, (
            client_id, record["client_name"], week_start, day,
            record.get("salad"), record.get("soup"),
            record.get("main"),  record.get("side"),
            confidence, pdf_name, "ocr-oversight", anomaly_note,
        ))
        conn.commit()

        _audit(conn, "INSERTED",
               pdf_name=pdf_name, client_id=client_id,
               client_name=record["client_name"],
               week_start=week_start, day=day,
               new_value=record.get("main"), new_confidence=confidence)
        log.info(
            f"  INSERT {record['client_name']} {day} conf={confidence:.2f} "
            f"main='{record.get('main')}'"
        )
        return "inserted"


# ══════════════════════════════════════════════════════════════════════════════
# 5 · REPORT  ─────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def send_report(stats: dict) -> None:
    """Send Telegram summary to Kato via @Hermes_Cloud_May_bot."""
    flagged   = stats.get("flagged", [])
    anomalies = stats.get("anomalies", [])

    flag_block = ""
    if flagged:
        lines = "\n".join(
            f"  • {f['pdf']} — {f['reason'][:80]}" for f in flagged[:20]
        )
        if len(flagged) > 20:
            lines += f"\n  … and {len(flagged)-20} more (see logs)"
        flag_block = f"\n\n<b>🔴 Flagged for manual review:</b>\n{lines}"

    anomaly_block = ""
    if anomalies:
        lines = "\n".join(f"  • {a[:100]}" for a in anomalies[:10])
        if len(anomalies) > 10:
            lines += f"\n  … and {len(anomalies)-10} more"
        anomaly_block = f"\n\n<b>⚠️ Anomalies:</b>\n{lines}"

    msg = (
        f"📋 <b>OCR Oversight Report</b>\n"
        f"──────────────────────────\n"
        f"📂 PDFs scanned:          {stats.get('pdfs_scanned', 0)}\n"
        f"🔄 Re-processed (low ℂ): {stats.get('reprocessed', 0)}\n"
        f"✅ Validated clean:       {stats.get('validated_clean', 0)}\n"
        f"⬆️  DB rows updated:       {stats.get('updated', 0)}\n"
        f"➕ DB rows inserted:      {stats.get('inserted', 0)}\n"
        f"⏭️  Skipped (conf OK):     {stats.get('skipped', 0)}\n"
        f"🔴 Flagged for review:   {len(flagged)}"
        f"{flag_block}{anomaly_block}"
    )
    _tg_send(msg)
    log.info("Telegram report sent")


# ══════════════════════════════════════════════════════════════════════════════
# --audit mode  ───────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def run_audit_report(conn: sqlite3.Connection) -> None:
    """Print confidence tier breakdown to stdout."""
    cur = conn.cursor()

    # Check table exists
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='client_menus'"
    )
    if not cur.fetchone():
        print("\n⚠️  client_menus table not found in auth_tracker.db")
        print(f"   DB path checked: {DB_PATH}")
        print("   Run the full OCR pipeline first, then re-run --audit.\n")
        return

    cur.execute("SELECT COUNT(*) FROM client_menus")
    total = cur.fetchone()[0]

    if total == 0:
        print("\nℹ️  client_menus table exists but has 0 rows.\n")
        return

    cur.execute("SELECT COUNT(*) FROM client_menus WHERE confidence >= ?", (CONFIDENCE_HIGH,))
    high = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM client_menus WHERE confidence >= ? AND confidence < ?",
        (CONFIDENCE_LOW, CONFIDENCE_HIGH),
    )
    medium = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM client_menus WHERE confidence IS NULL OR confidence < ?",
        (CONFIDENCE_LOW,),
    )
    low = cur.fetchone()[0]

    div = "═" * 60
    print(f"\n{div}")
    print(f"  GHS OCR Oversight — Confidence Audit Report")
    print(f"  {date.today().isoformat()}  ·  auth_tracker.db")
    print(div)
    print(f"\n  Total client_menus rows : {total}")
    print()
    print(f"  🟢 HIGH   (≥ {CONFIDENCE_HIGH:.2f})          : "
          f"{high:>5} rows   ({high/total*100:5.1f}%)")
    print(f"  🟡 MEDIUM ({CONFIDENCE_LOW:.2f} – {CONFIDENCE_HIGH:.2f})    : "
          f"{medium:>5} rows   ({medium/total*100:5.1f}%)")
    print(f"  🔴 LOW    (< {CONFIDENCE_LOW:.2f} or NULL)   : "
          f"{low:>5} rows   ({low/total*100:5.1f}%)")
    print()

    if low > 0:
        print(f"  🔴 LOW confidence detail (up to 50):")
        cur.execute("""
            SELECT   client_name,
                     week_start,
                     COUNT(*)              AS n,
                     AVG(COALESCE(confidence, 0)) AS avg_conf
            FROM     client_menus
            WHERE    confidence IS NULL OR confidence < ?
            GROUP BY client_name, week_start
            ORDER BY avg_conf ASC
            LIMIT    50
        """, (CONFIDENCE_LOW,))
        for client_name, week_start, n, avg_conf in cur.fetchall():
            name_col = (client_name or "(unknown)").ljust(36)
            print(f"    • {name_col}  wk={week_start}  n={n}  avg={avg_conf:.2f}")
        if low > 50:
            print(f"    … and {low-50} more")
        print()

    # Oversight audit log summary
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='ocr_oversight_audit'"
    )
    if cur.fetchone():
        cur.execute("SELECT COUNT(*) FROM ocr_oversight_audit")
        audit_total = cur.fetchone()[0]
        print(f"  Oversight audit log entries: {audit_total}")
        if audit_total > 0:
            cur.execute("""
                SELECT action, COUNT(*) AS n
                FROM   ocr_oversight_audit
                GROUP  BY action
                ORDER  BY n DESC
            """)
            for action, n in cur.fetchall():
                print(f"    {action:<35} {n}")
    else:
        print("  (No oversight audit log yet — run --scan first)")

    print(f"\n{div}\n")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN SCAN FLOW  ─────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def run_scan(fix_all: bool = False) -> None:
    """Full SCAN → RE-PROCESS → VALIDATE → WRITE → REPORT pipeline."""

    # Pre-flight checks
    api_key = _get_api_key()
    if not api_key:
        log.error("ANTHROPIC_API_KEY not found")
        print("❌ ANTHROPIC_API_KEY not set. Cannot run Vision re-processing.")
        print("   Set it: export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    if not DB_PATH.exists():
        log.error(f"Database not found: {DB_PATH}")
        print(f"❌ auth_tracker.db not found at:\n   {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    _ensure_audit_table(conn)

    stats: dict = {
        "pdfs_scanned":    0,
        "reprocessed":     0,
        "validated_clean": 0,
        "updated":         0,
        "inserted":        0,
        "skipped":         0,
        "flagged":         [],
        "anomalies":       [],
    }

    # ── 1. SCAN ────────────────────────────────────────────────────────────────
    scan_result = scan(conn, fix_all=fix_all)
    targets: list[tuple[Path, float | None]] = (
        [(p, None) for p in scan_result["unprocessed"]] +
        [(p, c)    for p, c in scan_result["low_confidence"]]
    )
    stats["pdfs_scanned"] = len(targets)

    if not targets:
        msg = (
            "✅ Nothing to re-process — all PDFs meet the confidence threshold "
            f"(≥ {CONFIDENCE_LOW})."
        )
        log.info(msg)
        print(msg)
        run_audit_report(conn)
        conn.close()
        return

    log.info(f"Processing {len(targets)} PDF(s)")

    for pdf_path, existing_conf in targets:
        pdf_name = pdf_path.name
        log.info(f"{'─'*60}")
        log.info(f"{pdf_name}  (existing_min_conf={existing_conf})")

        if not pdf_path.exists():
            log.warning(f"PDF file not found on disk: {pdf_path}")
            stats["flagged"].append({"pdf": pdf_name, "reason": "file not found on disk"})
            _audit(conn, "MISSING_FILE", pdf_name=pdf_name,
                   flag_reason="PDF path in DB but file not on disk", flagged=1)
            continue

        # ── 2. RE-PROCESS ──────────────────────────────────────────────────────
        stats["reprocessed"] += 1
        records = reprocess_pdf(pdf_path, api_key)

        if not records:
            reason = "Vision extracted 0 day-records"
            log.warning(f"  {pdf_name}: {reason}")
            stats["flagged"].append({"pdf": pdf_name, "reason": reason})
            _audit(conn, "REPROCESS_EMPTY", pdf_name=pdf_name,
                   flag_reason=reason, flagged=1)
            continue

        pdf_all_clean = True

        for record in records:
            # ── 3. VALIDATE ────────────────────────────────────────────────────
            try:
                validated = validate_record(record, conn, pdf_name, pdf_path=pdf_path)
            except _PauseHalt as exc:
                reason = str(exc)
                log.warning(f"  PAUSE/HALT on {pdf_name} {record.get('day')}: {reason}")
                stats["flagged"].append({"pdf": pdf_name, "reason": reason})
                pdf_all_clean = False
                _audit(conn, "PAUSE_HALT",
                       pdf_name=pdf_name,
                       client_name=record.get("client_name"),
                       day=record.get("day"),
                       flag_reason=reason, flagged=1)
                continue

            if validated.get("_anomalies"):
                for a in validated["_anomalies"]:
                    stats["anomalies"].append(
                        f"{pdf_name} / {validated.get('day')}: {a}"
                    )
                pdf_all_clean = False

            # ── 4. WRITE ───────────────────────────────────────────────────────
            result = write_record(validated, pdf_name, conn)
            stats[result] = stats.get(result, 0) + 1

        if pdf_all_clean:
            stats["validated_clean"] += 1

    conn.close()

    # ── 5. REPORT ──────────────────────────────────────────────────────────────
    send_report(stats)

    # ── stdout summary ─────────────────────────────────────────────────────────
    div = "═" * 52
    print(f"\n{div}")
    print(f"  OCR Oversight Scan Complete  —  {date.today().isoformat()}")
    print(div)
    print(f"  PDFs scanned:         {stats['pdfs_scanned']}")
    print(f"  Re-processed:         {stats['reprocessed']}")
    print(f"  Validated clean:      {stats['validated_clean']}")
    print(f"  DB rows updated:      {stats['updated']}")
    print(f"  DB rows inserted:     {stats['inserted']}")
    print(f"  Skipped (conf OK):    {stats['skipped']}")
    print(f"  Flagged for review:   {len(stats['flagged'])}")
    print(f"  Anomalies found:      {len(stats['anomalies'])}")
    if stats["flagged"]:
        print(f"\n  🔴 Flagged PDFs:")
        for f in stats["flagged"]:
            print(f"    • {f['pdf']}: {f['reason'][:80]}")
    if stats["anomalies"]:
        print(f"\n  ⚠️  Anomalies:")
        for a in stats["anomalies"][:15]:
            print(f"    • {a[:100]}")
    print(f"\n  Full log: {LOG_PATH}\n")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT  ────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="GHS OCR Oversight Agent — quality control for GOJ menu scans",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 CC_ocr_oversight_agent.py           # scan (default)\n"
            "  python3 CC_ocr_oversight_agent.py --audit   # confidence report\n"
            "  python3 CC_ocr_oversight_agent.py --fix-all # re-process all LOW rows\n"
        ),
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Print confidence tier report (no DB writes)",
    )
    parser.add_argument(
        "--fix-all",
        dest="fix_all",
        action="store_true",
        help="Re-process ALL low-confidence (< 0.75) entries",
    )
    args = parser.parse_args()

    if args.audit:
        if not DB_PATH.exists():
            print(f"❌ Database not found: {DB_PATH}")
            sys.exit(1)
        conn = sqlite3.connect(str(DB_PATH))
        run_audit_report(conn)
        conn.close()
    elif args.fix_all:
        run_scan(fix_all=True)
    else:
        run_scan(fix_all=False)


if __name__ == "__main__":
    main()
