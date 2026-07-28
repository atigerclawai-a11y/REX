"""
GOJ Menu Confirm Handler
========================
Processes Kato's menu corrections from Telegram.

After goj_menu_flag_reporter.py sends flags, Kato replies to Rexxie:

  To confirm a guess:   menu fix: flag_id=42 confirm
  To correct a name:    menu fix: flag_id=42 name=John Smith
  To correct + items:   menu fix: flag_id=42 name=Maria Ivanova items=Borscht,Chicken,Rice
  To skip:              menu fix: flag_id=42 skip

This script:
  1. Polls Rexxie's Telegram bot for recent messages
  2. Parses any "menu fix:" commands
  3. Updates GOJ_Menu_Orders.json with confirmed data
  4. Updates goj_menu_learning.json with name/item corrections
  5. Marks flags as resolved in goj_menu_flags_queue.json

Run after Kato has replied:
    cd ~/Desktop/REX && source .venv/bin/activate
    python goj_menu_confirm_handler.py

Or run with --poll to check continuously for 10 minutes:
    python goj_menu_confirm_handler.py --poll
"""

import json
import logging
import re
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime
from difflib import get_close_matches

# Item-category lookup for "fix: [day] [item]" command
try:
    from CC_menu_constants import SALADS, SOUPS, ALL_MAINS as _MAINS, SIDES as _SIDES
    _ITEM_CATEGORIES: dict = {}
    for _s in SALADS:   _ITEM_CATEGORIES[_s] = "salad"
    for _s in SOUPS:    _ITEM_CATEGORIES[_s] = "soup"
    for _m in _MAINS:   _ITEM_CATEGORIES[_m] = "main"
    for _s in _SIDES:   _ITEM_CATEGORIES[_s] = "side"
    _ALL_KNOWN_ITEMS = list(_ITEM_CATEGORIES.keys())
except ImportError:
    _ITEM_CATEGORIES  = {}
    _ALL_KNOWN_ITEMS  = []

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("confirm_handler")

# ─── Paths ────────────────────────────────────────────────────────────────────
REX_DIR        = Path.home() / "Desktop" / "REX"
FLAGS_FILE     = REX_DIR / "goj_menu_flags_queue.json"
ORDERS_FILE    = REX_DIR / "GOJ_Menu_Orders.json"
LEARNING_FILE  = REX_DIR / "goj_menu_learning.json"
REXXIE_CONFIG  = REX_DIR / "rex_rexxie_telegram_config.json"
OFFSET_FILE    = REX_DIR / ".goj_menu_tg_offset"   # tracks last Telegram update_id

# ─── Telegram helpers ─────────────────────────────────────────────────────────

def tg_api(token: str, method: str, params: dict = None) -> dict:
    url  = f"https://api.telegram.org/bot{token}/{method}"
    data = (json.dumps(params or {}).encode() if params else None)
    req  = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        log.error(f"Telegram API error ({method}): {e}")
        return {}


def get_updates(token: str, offset: int = 0) -> list[dict]:
    result = tg_api(token, "getUpdates", {"offset": offset, "timeout": 5})
    return result.get("result", [])


def send_message(token: str, chat_id: int, text: str) -> bool:
    r = tg_api(token, "sendMessage", {"chat_id": chat_id, "text": text})
    return r.get("ok", False)


# ─── Parse commands — natural language + structured ──────────────────────────

# File to track the last flag sent to Kato (for context-aware replies)
LAST_FLAG_FILE = REX_DIR / ".goj_menu_last_flag"

COMMAND_RE = re.compile(
    r'menu\s+fix\s*:\s*flag_id\s*=\s*(\S+)'
    r'(?:\s+name\s*=\s*([^,\n]+?))?'
    r'(?:\s+items\s*=\s*([^\n]+?))?'
    r'(?:\s+(confirm|skip))?'
    r'\s*$',
    re.IGNORECASE
)

# Natural language patterns
SKIP_WORDS   = re.compile(
    r'^(skip|pass|next|no\s+idea|don\'?t\s+know|can\'?t\s+tell|not\s+sure|unknown|unclear|idk|nope|no)[\s\.!]*$',
    re.IGNORECASE
)
CONFIRM_WORDS = re.compile(
    r'^(yes|correct|right|confirm|ok|okay|yep|yeah|that\'?s\s+right|confirmed|good|perfect|✓|👍)[\s\.!]*$',
    re.IGNORECASE
)
# Patterns like "that's Nina Ivanova" / "it's Ivanova Nina" / "this is Maria"
NAME_PHRASE_RE = re.compile(
    r"(?:that'?s|it'?s|this\s+is|her\s+name\s+is|the\s+name\s+is|name\s*[:=]\s*|it\s+is)\s+"
    r"([A-Za-zА-Яа-яёЁ][A-Za-zА-Яа-яёЁ\-]+(?:\s+[A-Za-zА-Яа-яёЁ][A-Za-zА-Яа-яёЁ\-]+){1,3})",
    re.IGNORECASE
)
# Flag reference: "flag 3" or "#3" or "3:" at the start
FLAG_REF_RE = re.compile(r'^(?:flag\s*#?|#)(\d+)', re.IGNORECASE)
# Bare number at start: "3 Ivanova Nina" or "3: skip"
BARE_NUM_RE = re.compile(r'^(\d+)\s*[:\-\.\s]\s*(.+)$')

# "fix: monday Борщ зеленый" or "fix: M котлеты"
FIX_ITEM_RE = re.compile(
    r'^fix\s*:\s*'
    r'(M|T|W|TH|F|SA|monday|tuesday|wednesday|thursday|friday|saturday'
    r'|пн|вт|ср|чт|пт|сб|пон|вто|сре|чет|пят|суб)'
    r'\s+(.+)$',
    re.IGNORECASE,
)
_FIX_DAY_MAP: dict = {
    "m": "M",  "monday": "M",    "пн": "M",  "пон": "M",
    "t": "T",  "tuesday": "T",   "вт": "T",  "вто": "T",
    "w": "W",  "wednesday": "W", "ср": "W",  "сре": "W",
    "th": "TH","thursday": "TH", "чт": "TH", "чет": "TH",
    "f": "F",  "friday": "F",    "пт": "F",  "пят": "F",
    "sa": "SA","saturday": "SA", "сб": "SA", "суб": "SA",
}


def get_last_sent_flag_id() -> str | None:
    """Return the flag_id of the most recently sent flag."""
    if LAST_FLAG_FILE.exists():
        try:
            return LAST_FLAG_FILE.read_text().strip() or None
        except Exception:
            pass
    return None


def set_last_sent_flag_id(flag_id: str):
    LAST_FLAG_FILE.write_text(str(flag_id))


def get_next_pending_flag(flags: list) -> dict | None:
    """Return the oldest unsent/unresolved flag."""
    for f in flags:
        if not f.get("resolved") and f.get("sent_to_kato"):
            return f
    return None


def parse_command(text: str, flags: list) -> dict | None:
    """
    Parse Kato's reply — natural language OR structured 'menu fix:' format.
    Returns dict with: flag_id, action, name, items
    Returns None if message doesn't look like a menu reply.
    """
    text = text.strip()

    # ── Structured format (always wins if present) ───────────────────────────
    m = COMMAND_RE.search(text)
    if m:
        flag_id     = m.group(1).strip()
        name        = (m.group(2) or "").strip() or None
        items_raw   = (m.group(3) or "").strip() or None
        action_word = (m.group(4) or "").strip().lower() or None
        action = "skip" if action_word == "skip" else \
                 "confirm" if action_word == "confirm" else \
                 "correct" if name else "unknown"
        items = [i.strip() for i in items_raw.split(",")] if items_raw else []
        return {"flag_id": flag_id, "action": action, "name": name, "items": items}

    # ── Natural language — need to figure out which flag this is for ──────────
    # Determine target flag_id from context
    flag_id = None

    # "flag 3: ..." or "#3 ..." pattern
    fm = FLAG_REF_RE.match(text)
    if fm:
        flag_id = fm.group(1)
        text = text[fm.end():].strip().lstrip(":- ")

    # "3: Ivanova Nina" or "3 skip"
    if flag_id is None:
        bm = BARE_NUM_RE.match(text)
        if bm:
            flag_id = bm.group(1)
            text = bm.group(2).strip()

    # Fall back to last sent flag
    if flag_id is None:
        flag_id = get_last_sent_flag_id()
        if flag_id is None:
            pending = get_next_pending_flag(flags)
            flag_id = str(pending["flag_id"]) if pending else None

    if flag_id is None:
        return None

    # ── Determine action from remaining text ─────────────────────────────────
    if SKIP_WORDS.match(text):
        return {"flag_id": flag_id, "action": "skip", "name": None, "items": []}

    if CONFIRM_WORDS.match(text):
        return {"flag_id": flag_id, "action": "confirm", "name": None, "items": []}

    # "that's Nina Ivanova" / "it's Ivanova Nina"
    np = NAME_PHRASE_RE.search(text)
    if np:
        return {"flag_id": flag_id, "action": "correct", "name": np.group(1).strip(), "items": []}

    # Bare name: 2-4 words, all letters — "Ivanova Nina" or "Nina Ivanova"
    words = text.split()
    if 2 <= len(words) <= 4 and all(re.match(r'^[A-Za-zА-Яа-яёЁ\-\.]+$', w) for w in words):
        return {"flag_id": flag_id, "action": "correct", "name": text, "items": []}

    # "fix: monday Борщ зеленый" — short item correction for a specific day
    fx = FIX_ITEM_RE.match(text)
    if fx:
        day_raw  = fx.group(1).lower().strip()
        item_val = fx.group(2).strip()
        day_code = _FIX_DAY_MAP.get(day_raw, day_raw.upper())
        return {
            "flag_id": flag_id,
            "action":  "fix_item",
            "day":     day_code,
            "item":    item_val,
            "name":    None,
            "items":   [],
        }

    return None


# ─── Apply corrections ────────────────────────────────────────────────────────

def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return default


def save_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def apply_command(cmd: dict, flags: list, orders: dict, learning: dict,
                  owner_chat_id: int) -> str:
    flag_id = str(cmd["flag_id"])
    flag    = next((f for f in flags if str(f.get("flag_id")) == flag_id), None)

    if not flag:
        return f"⚠️ Flag ID {flag_id} not found."

    if flag.get("resolved"):
        return f"ℹ️ Flag {flag_id} already resolved."

    action = cmd["action"]

    if action == "skip":
        flag["resolved"]  = True
        flag["resolution"] = "skipped"
        flag["resolved_at"] = datetime.now().isoformat()
        return f"⏭️ Flag {flag_id} skipped."

    if action == "confirm":
        # Use the guessed name as-is
        confirmed_name = flag.get("matched_name", "")
        if not confirmed_name:
            return f"⚠️ Flag {flag_id} has no matched name to confirm."
        cmd["name"] = confirmed_name
        action = "correct"

    if action == "correct":
        correct_name = cmd.get("name") or ""
        if not correct_name:
            return f"⚠️ Flag {flag_id} requires a name."

        # Learn: OCR candidate → correct name
        ocr_candidate = (flag.get("candidate_name") or "").lower()
        if ocr_candidate and correct_name:
            learning.setdefault("name_corrections", {})[ocr_candidate] = correct_name
            log.info(f"  📚 Learned: '{ocr_candidate}' → '{correct_name}'")
            # Layer 2/3: also update learning manager (client_name_map + engine_stats)
            try:
                from CC_ocr_learning_manager import load_store, save_store, record_correction
                _lstore = load_store(str(LEARNING_FILE))
                _lstore = record_correction(_lstore, ocr_candidate, correct_name, "name",
                                            engine_verdicts=None)
                save_store(str(LEARNING_FILE), _lstore)
            except Exception as _le:
                log.warning(f"Learning manager name update failed: {_le}")

        # Build selections — use provided items or fall back to OCR-detected
        selections = flag.get("selections", {})
        if cmd.get("items"):
            selections = {"Corrected": {"items": cmd["items"]}}

        # Determine client ID — try to find from orders or use doc_id as temp
        client_id = flag.get("client_id") or f"manual_{flag_id}"

        # Save to orders
        key = f"{client_id}_{flag.get('created', 'unknown')}"
        orders[key] = {
            "client_id":     client_id,
            "client_name":   correct_name,
            "week_of":       flag.get("created", ""),
            "doc_id":        flag.get("doc_id"),
            "selections":    selections,
            "confidence":    1.0,
            "auto_approved": False,
            "kato_reviewed": True,
            "reviewed_at":   datetime.now().isoformat(),
        }

        # Learn item corrections if provided
        if cmd.get("items"):
            ocr_sel = flag.get("selections", {})
            if ocr_sel:
                learning.setdefault("item_corrections", {})[flag_id] = {
                    "ocr_selections": ocr_sel,
                    "correct_items":  cmd["items"],
                    "client_name":    correct_name,
                }

        flag["resolved"]   = True
        flag["resolution"] = "corrected"
        flag["resolved_at"] = datetime.now().isoformat()
        flag["final_name"] = correct_name

        learning["stats"]["total_confirmed"] = learning.get("stats", {}).get("total_confirmed", 0) + 1

        return f"✅ Flag {flag_id} resolved — {correct_name} added to menu orders."

    if action == "fix_item":
        day       = cmd.get("day", "")
        item_raw  = (cmd.get("item") or "").strip()
        if not day or not item_raw:
            return f"⚠️ fix: command missing day or item — e.g. 'fix: monday Борщ зеленый'"

        # Resolve to canonical item name via exact match then fuzzy fallback
        item_canon = item_raw
        item_field = _ITEM_CATEGORIES.get(item_raw)
        if item_field is None and _ALL_KNOWN_ITEMS:
            matches = get_close_matches(item_raw, _ALL_KNOWN_ITEMS, n=1, cutoff=0.6)
            if matches:
                item_canon = matches[0]
                item_field = _ITEM_CATEGORIES.get(item_canon)

        # Find the OCR value that was there before (for learning diff)
        day_data  = (flag.get("days") or {}).get(day, {})
        ocr_val   = day_data.get(item_field) if item_field else None
        if ocr_val is None:
            # Fall back to first non-null value in that day
            for _f, _v in day_data.items():
                if _v:
                    ocr_val = _v
                    if item_field is None:
                        item_field = _f
                    break

        # Update flag days with corrected value
        flag_days = flag.setdefault("days", {}).setdefault(day, {})
        if item_field:
            flag_days[item_field] = item_canon

        flag["resolved"]    = True
        flag["resolution"]  = "item_corrected"
        flag["resolved_at"] = datetime.now().isoformat()

        # Learn the correction
        if ocr_val and ocr_val != item_canon:
            learning.setdefault("item_corrections", {})[ocr_val] = item_canon
            log.info(f"  📚 Learned item: '{ocr_val}' → '{item_canon}' ({day}/{item_field})")
            try:
                from CC_ocr_learning_manager import load_store, save_store, record_correction
                _lstore = load_store(str(LEARNING_FILE))
                _lstore = record_correction(_lstore, ocr_val, item_canon, "item",
                                            engine_verdicts=None)
                save_store(str(LEARNING_FILE), _lstore)
            except Exception as _le:
                log.warning(f"Learning manager item update failed: {_le}")

        return f"✅ Fixed {day} {item_field or 'item'} → {item_canon}."

    return f"⚠️ Unknown action '{action}' for flag {flag_id}."


# ─── Main ─────────────────────────────────────────────────────────────────────

def process_once(token: str, owner_chat_id: int) -> int:
    """Poll Telegram once, process any menu fix commands. Returns count processed."""
    # Load current offset
    offset = 0
    if OFFSET_FILE.exists():
        try:
            offset = int(OFFSET_FILE.read_text().strip())
        except Exception:
            pass

    updates = get_updates(token, offset)
    if not updates:
        return 0

    flags    = load_json(FLAGS_FILE, [])
    orders   = load_json(ORDERS_FILE, {})
    learning = load_json(LEARNING_FILE, {"name_corrections": {}, "item_corrections": {}, "stats": {}})

    processed = 0
    for update in updates:
        update_id = update.get("update_id", 0)
        offset    = max(offset, update_id + 1)

        msg = update.get("message") or update.get("edited_message")
        if not msg:
            continue

        # Only process messages from Kato
        from_id = msg.get("from", {}).get("id")
        if from_id != owner_chat_id:
            continue

        text = msg.get("text", "").strip()
        cmd  = parse_command(text, flags)
        if not cmd:
            continue

        log.info(f"Processing command: {text[:80]}")
        reply = apply_command(cmd, flags, orders, learning, owner_chat_id)
        send_message(token, owner_chat_id, reply)
        log.info(f"  → {reply}")
        processed += 1

    if processed > 0:
        save_json(FLAGS_FILE, flags)
        save_json(ORDERS_FILE, orders)
        save_json(LEARNING_FILE, learning)
        log.info(f"Saved updates: {processed} command(s) processed.")

    # Save new offset
    OFFSET_FILE.write_text(str(offset))
    return processed


def main():
    poll_mode = "--poll" in sys.argv

    cfg = load_json(REXXIE_CONFIG, {})
    if not cfg:
        log.error(f"Rexxie config not found at {REXXIE_CONFIG}")
        return

    token   = cfg.get("token") or cfg.get("bot_token") or cfg.get("rexxie_token")
    chat_id = cfg.get("owner_chat_id")

    if not token or not chat_id:
        log.error("Missing token or owner_chat_id in Rexxie config.")
        return

    if poll_mode:
        log.info("=== GOJ Menu Confirm Handler (poll mode — 10 min) ===")
        deadline = time.time() + 600  # 10 minutes
        while time.time() < deadline:
            count = process_once(token, chat_id)
            if count:
                log.info(f"Processed {count} command(s)")
            time.sleep(3)
        log.info("Poll window closed.")
    else:
        log.info("=== GOJ Menu Confirm Handler (single pass) ===")
        count = process_once(token, chat_id)
        log.info(f"Done. {count} command(s) processed.")


if __name__ == "__main__":
    main()
