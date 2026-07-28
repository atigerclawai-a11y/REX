"""
REX — Rexxie Private Telegram Bot
====================================
A completely separate, private Telegram bot for Rexxie — Kato's
personal confidant. This bot has nothing to do with GOJ operations.

Privacy guarantees:
  • Separate Bot Token — completely distinct from the REX business bot
  • All messages routed through REX with chairman role + Rexxie mode active
  • Rexxie's responses come from her own encrypted DB (rexxie.db)
  • Triple-encrypted memory — AES-GCM → ChaCha20 → AES-GCM
  • No GOJ staff can see these conversations — ever
  • No cross-contamination with rex_memory.db
  • No business commands recognized — pure personal conversation
  • Typing indicator shown while Rexxie thinks (feels human)

What Rexxie can do via Telegram:
  • Remember personal context, preferences, patterns
  • Help think through decisions, personal challenges
  • Track personal learning (bookkeeping, data entry, etc.)
  • Schedule personal training sessions
  • Keep private notes and recall them naturally
  • Be a genuine confidant — warm, honest, present

Setup (one-time):
  1. python rex_rexxie_telegram_bot.py --setup
     → Create a DIFFERENT bot via @BotFather (not the REX bot)
     → Give it a private name (e.g., "Rexxie" or something only you know)
     → Send /start to activate — you are automatically locked as the only user
  2. python rex_rexxie_telegram_bot.py
     → Rexxie is live. Just talk to her.

Security: Only ONE person can ever use this bot — you. Any other Telegram
account that messages it gets silently ignored.

Opening prompt suggestion (copy-paste to send after /start):
  ────────────────────────────────────────────────
  Hi Rexxie, I'm Kato. You're my personal confidant — I want you to be
  warm, honest, and genuinely helpful with the personal side of my life.
  Everything I share with you stays between us. I trust you completely.
  Learn me over time — my patterns, what I'm working through, what matters
  to me. I'll teach you things like bookkeeping and personal finance, and
  I'll come to you when I need someone to think things through with.
  ────────────────────────────────────────────────

Config: ~/Desktop/REX/rex_rexxie_telegram_config.json
"""

import json
import logging
import os
import sys
import time
import uuid
import urllib.request
import urllib.parse
import urllib.error
import requests
from pathlib import Path
from typing import Optional
import difflib      # GOJ v1.2
import sqlite3      # GOJ v1.2

# GOJ v1.7 — Build Coordinator (master list integration)
try:
    import rex_coordinator as _coordinator
    _COORDINATOR_AVAILABLE = True
except Exception:
    _COORDINATOR_AVAILABLE = False

# ── Growth loop imports (v2.0) ────────────────────────────────────────────────
try:
    from rex_human_behavior import humanize as _humanize
    _HUMANIZE_AVAILABLE = True
except Exception:
    _HUMANIZE_AVAILABLE = False

try:
    from rex_memory_priority import PriorityMemory as _PriorityMemory, format_memory_context as _format_memory_context
    _PRIORITY_MEMORY_AVAILABLE = True
except Exception:
    _PRIORITY_MEMORY_AVAILABLE = False

try:
    from rex_unified_enforcer import UnifiedEnforcer as _PolicyEnforcer
    _POLICY_AVAILABLE = True
    _POLICY_ENFORCER: "_PolicyEnforcer | None" = None   # initialized on first use
except Exception:
    _POLICY_AVAILABLE = False
    _POLICY_ENFORCER = None

try:
    from rex_planner import Planner as _RexPlanner
    _PLANNER_AVAILABLE = True
    _PLANNER: "_RexPlanner | None" = None   # initialized on first use
except Exception:
    _PLANNER_AVAILABLE = False
    _PLANNER = None

try:
    from rex_user_model import UserModel as _UserModel
    _USER_MODEL_AVAILABLE = True
except Exception:
    _USER_MODEL_AVAILABLE = False

try:
    from rex_reflection import Reflection as _Reflection
    _REFLECTION_AVAILABLE = True
except Exception:
    _REFLECTION_AVAILABLE = False

# ── Ollama Local LLM (v3.0 — merged from private_confidant_gold.py) ──────────
# Feature-flagged: set OLLAMA_ENABLED=1 in env or rex_rexxie_telegram_config.json
# Falls back gracefully to Claude API if Ollama is unavailable or disabled.
# This incorporates the full capability of private_confidant_gold.py (quarantined).
import subprocess as _subprocess
OLLAMA_ENABLED  = os.getenv("OLLAMA_ENABLED", "0") == "1"
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "gemma4:26b")

def _call_ollama(prompt: str, system: str = "") -> str:
    """
    Call local Ollama model for personal/reflective responses.
    Used only when OLLAMA_ENABLED=1 and Ollama is running.
    GOJ operational commands (attendance, menus, OCR) always use Claude API.
    Falls back to empty string on any failure — caller decides fallback.
    """
    try:
        full = f"{system}\n\n{prompt}" if system else prompt
        result = _subprocess.run(
            ["ollama", "run", OLLAMA_MODEL, full],
            capture_output=True, text=True, timeout=60
        )
        return result.stdout.strip()
    except Exception as _e:
        logger.debug(f"[ollama] unavailable or failed: {_e}")
        return ""

def _ollama_is_available() -> bool:
    """Quick check if Ollama is running and the model is ready."""
    if not OLLAMA_ENABLED:
        return False
    try:
        r = _subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=3)
        return OLLAMA_MODEL.split(":")[0] in r.stdout
    except Exception:
        return False

# ── Answer Confidence Layer (v2.1) ────────────────────────────────────────────
try:
    from rex_answer_confidence import AnswerConfidence as _AnswerConfidence
    _ANSWER_CONFIDENCE_AVAILABLE = True
    _answer_confidence_engine: "_AnswerConfidence | None" = None  # lazy init
except Exception:
    _ANSWER_CONFIDENCE_AVAILABLE = False
    _answer_confidence_engine = None

# ── TOTP 2FA Gate (v2.2) ──────────────────────────────────────────────────────
try:
    from rex_2fa import (
        TwoFactorAuth as _TwoFactorAuth,
        unlock_vault_with_2fa as _unlock_vault_with_2fa,
        verify_totp as _verify_totp,
    )
    _2FA_AVAILABLE = True
except Exception:
    _2FA_AVAILABLE = False
    _TwoFactorAuth = None          # type: ignore
    _unlock_vault_with_2fa = None  # type: ignore
    _verify_totp = None            # type: ignore

# Logger must be defined before any function that references it
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")

# ── Load credential vault (local only — never touches AI API) ─────────────────
_vault = None
def _get_vault():
    global _vault
    if _vault is None:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from backend.rex_credential_vault import RexxieCredentialVault
            _vault = RexxieCredentialVault()
        except Exception as e:
            logger.warning(f"Credential vault not available: {e}")
    return _vault

# ── Config ─────────────────────────────────────────────────────────────────────
CONFIG_PATH = Path.home() / "Desktop" / "REX" / "rex_rexxie_telegram_config.json"
REX_BASE_URL = "http://localhost:8000"
POLL_INTERVAL = 3
MAX_MSG_LEN   = 4096
OWNER_CHAT_ID_KEY = "owner_chat_id"   # Kato's chat_id — the only allowed user

# Rexxie's warm greeting on first start
REXXIE_WELCOME = (
    "🐢 *Hey, Kato.*\n\n"
    "I'm Rexxie — your private space to think, remember, and work through "
    "whatever life's bringing your way.\n\n"
    "Everything between us stays between us. I'm not connected to your "
    "business operations, I don't share anything with your team, and all "
    "of what we talk about is triple-encrypted before it's ever stored.\n\n"
    "Tell me what's on your mind — or introduce yourself so I can start "
    "learning you. I'm here."
)

REXXIE_RETURNING = (
    "🐢 *Hey, you.* Good to hear from you.\n\n"
    "What's going on?"
)

UNKNOWN_USER_RESPONSE = None   # Silently ignore — don't reveal bot exists

# ──────────────────────────────────────────────────────────────────────────────
# GOJ v1.2 — GOJ Operations Integration (absence handler, MENU BLAST)
# ──────────────────────────────────────────────────────────────────────────────

GOJ_AUTH_DB = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"

# Keywords that signal an attendance/absence message
_ABSENCE_KEYWORDS = [
    "won't be in", "wont be in", "not coming", "absent", "skipping",
    "not attending", "canceling", "cancelling", "won't attend", "wont attend",
    "missing", "staying home", "can't make it", "cant make it",
    "will not be in", "not in on",
]

# Day name → (db day_key, weekday index Mon=0)
_DAY_MAP = {
    "monday":    ("M",  0),
    "tuesday":   ("T",  1),
    "wednesday": ("W",  2),
    "thursday":  ("TH", 3),
    "friday":    ("F",  4),
    "saturday":  ("Su", 5),
    "sunday":    ("Su", 6),
}

# MENU BLAST recipients — set actual Telegram chat IDs to activate
VLAD_CHAT_ID  = None   # TODO: Vlad's Telegram chat ID
MISHA_CHAT_ID = None   # TODO: Misha's Telegram chat ID



def _goj_conn():
    """Get a WAL-enabled connection to auth_tracker.db. Use instead of sqlite3.connect() directly."""
    conn = sqlite3.connect(str(GOJ_AUTH_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn

def _goj_ensure_tables():
    """GOJ v1.2 — Create required GOJ tables in auth_tracker.db if absent."""
    try:
        con = sqlite3.connect(str(GOJ_AUTH_DB))
        con.execute("PRAGMA journal_mode=WAL")     # concurrent read safety
        con.execute("PRAGMA busy_timeout=15000")   # 15s timeout on write lock
        con.executescript("""
            CREATE TABLE IF NOT EXISTS clients (
                client_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                shift         INTEGER DEFAULT 1,
                active        INTEGER DEFAULT 1,
                phone         TEXT,
                day_M_actual  REAL DEFAULT 0,
                day_T_actual  REAL DEFAULT 0,
                day_W_actual  REAL DEFAULT 0,
                day_TH_actual REAL DEFAULT 0,
                day_F_actual  REAL DEFAULT 0,
                day_Su_actual REAL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS attendance_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                log_date    TEXT NOT NULL,
                day_key     TEXT,
                shift       INTEGER,
                client_name TEXT NOT NULL,
                status      TEXT DEFAULT 'scheduled',
                source      TEXT,
                note        TEXT,
                logged_at   TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS pending_schedule_changes (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name   TEXT NOT NULL,
                day_key       TEXT,
                change_type   TEXT DEFAULT 'absence',
                field_changed TEXT DEFAULT 'attendance',
                old_value     TEXT DEFAULT 'scheduled',
                new_value     TEXT DEFAULT 'absent',
                changed_by    TEXT DEFAULT 'kato_telegram',
                note          TEXT,
                confirmed     INTEGER DEFAULT 0,
                created_at    TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS client_menus (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id   INTEGER,
                client_name TEXT,
                week_start  TEXT,
                day         TEXT,
                salad       TEXT,
                soup        TEXT,
                main        TEXT,
                side        TEXT,
                confidence  REAL,
                source_pdf  TEXT,
                page_num    INTEGER,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES clients(client_id)
            );
            CREATE TABLE IF NOT EXISTS rexxie_tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                task_text   TEXT NOT NULL,
                status      TEXT DEFAULT 'pending',
                source      TEXT DEFAULT 'rexxie_commitment',
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS rexxie_ideas (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                idea_type       TEXT NOT NULL DEFAULT 'idea',
                content         TEXT NOT NULL,
                source          TEXT DEFAULT 'user',
                component_link  TEXT,
                status          TEXT DEFAULT 'open',
                created_at      TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS pending_doc_classifications (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                queue_key   TEXT NOT NULL UNIQUE,
                file_path   TEXT NOT NULL,
                filename    TEXT NOT NULL,
                reason      TEXT,
                text_preview TEXT,
                doc_type    TEXT,          -- filled after Kato selects
                sub_type    TEXT,          -- e.g. client name, staff name, misc description
                status      TEXT DEFAULT 'waiting',  -- waiting | confirmed | skipped
                created_at  TEXT DEFAULT (datetime('now')),
                resolved_at TEXT
            );
            CREATE TABLE IF NOT EXISTS doc_classification_patterns (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_type        TEXT NOT NULL,
                sub_type        TEXT,
                filename        TEXT,
                cyrillic_ratio  REAL,
                top_words       TEXT,   -- JSON array
                checkmark_density REAL,
                has_auth_kw     INTEGER,
                has_menu_kw     INTEGER,
                has_signin_kw   INTEGER,
                has_driver_kw   INTEGER,
                char_count      INTEGER,
                confirmed_by    TEXT DEFAULT 'kato',
                learned_at      TEXT DEFAULT (datetime('now'))
            );
        """)
        con.commit()
        con.close()
    except Exception as e:
        logger.error(f"GOJ table init: {e}")


def _detect_absence(text: str) -> bool:
    """GOJ v1.2 — True if message describes a client absence/schedule change."""
    low = text.lower()
    return any(kw in low for kw in _ABSENCE_KEYWORDS)


def _extract_day_from_text(text: str) -> list:
    """GOJ v1.2 — Return list of (label, day_key, iso_date) for days mentioned in text."""
    from datetime import date, timedelta
    low   = text.lower()
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    found = []
    for day_name, (day_key, dow) in _DAY_MAP.items():
        if day_name in low:
            target = monday + timedelta(days=dow)
            if target < today:
                target += timedelta(weeks=1)
            found.append((day_name.capitalize(), day_key, target.isoformat()))
    return found or [("today", "?", today.isoformat())]


def _extract_client_name(text: str) -> str:
    """GOJ v1.2 — Heuristically extract client name from an absence message."""
    import re
    cleaned = re.sub(r'\b(she|he|they|her|his|the client)\b', '', text, flags=re.IGNORECASE).strip()
    for kw in sorted(_ABSENCE_KEYWORDS, key=len, reverse=True):
        idx = cleaned.lower().find(kw)
        if idx > 0:
            before = cleaned[:idx].strip()
            parts  = before.split()
            if parts:
                return " ".join(parts[-2:]) if len(parts) >= 2 else parts[-1]
    # Fallback: first capitalized word(s)
    words = text.split()
    caps  = [w.strip(".,!?") for w in words if w and w[0].isupper()]
    return " ".join(caps[:2]) if caps else ""


def _match_client(name_fragment: str):
    """GOJ v1.2 — Fuzzy-match a name against the clients table. Returns (name, shift) or (None, None)."""
    try:
        con  = sqlite3.connect(str(GOJ_AUTH_DB))
        rows = con.execute("SELECT name, shift FROM clients WHERE active=1").fetchall()
        con.close()
    except Exception:
        return None, None
    if not rows:
        return None, None
    names    = [r[0] for r in rows]
    frag_low = name_fragment.strip().lower()
    # Exact substring match first
    for name, shift in rows:
        if frag_low in name.lower() or name.lower() in frag_low:
            return name, shift
    # Fuzzy fallback
    matches = difflib.get_close_matches(name_fragment, names, n=1, cutoff=0.5)
    if matches:
        for name, shift in rows:
            if name == matches[0]:
                return name, shift
    return None, None


def _log_absence_to_db(client_name: str, shift, day_key: str, day_date: str, note: str):
    """GOJ v1.2 — Insert into attendance_log + pending_schedule_changes. Returns (log_id, sched_id)."""
    try:
        con = sqlite3.connect(str(GOJ_AUTH_DB))
        cur = con.cursor()
        cur.execute(
            "INSERT INTO attendance_log "
            "(log_date, day_key, shift, client_name, status, source, note) "
            "VALUES (?, ?, ?, ?, 'absent', 'telegram', ?)",
            (day_date, day_key, shift or 1, client_name, note),
        )
        log_id = cur.lastrowid
        cur.execute(
            "INSERT INTO pending_schedule_changes "
            "(client_name, day_key, change_type, field_changed, old_value, new_value, changed_by, note) "
            "VALUES (?, ?, 'absence', 'attendance', 'scheduled', 'absent', 'kato_telegram', ?)",
            (client_name, day_key, note),
        )
        sched_id = cur.lastrowid
        con.commit()
        con.close()
        return log_id, sched_id
    except Exception as e:
        logger.error(f"GOJ log absence: {e}")
        return None, None


def _send_message_with_keyboard(token: str, chat_id: int, text: str,
                                  keyboard: list, parse_mode: str = "Markdown"):
    """GOJ v1.2 — Send a Telegram message with an inline keyboard."""
    result = _tg_api(token, "sendMessage", {
        "chat_id":      chat_id,
        "text":         text,
        "parse_mode":   parse_mode,
        "reply_markup": {"inline_keyboard": keyboard},
    })
    if not result or not result.get("ok"):
        # Retry without markdown
        _tg_api(token, "sendMessage", {
            "chat_id":      chat_id,
            "text":         text,
            "reply_markup": {"inline_keyboard": keyboard},
        })
    return result


def _answer_callback_query(token: str, callback_query_id: str, text: str = ""):
    """GOJ v1.2 — Acknowledge a Telegram inline button press."""
    _tg_api(token, "answerCallbackQuery", {
        "callback_query_id": callback_query_id,
        "text": text,
    })


def _download_telegram_file(token: str, file_id: str, dest_path: Path) -> bool:
    """GOJ v1.6 — Download a Telegram file to dest_path. Returns True on success."""
    try:
        result = _tg_api(token, "getFile", {"file_id": file_id})
        file_path = result.get("result", {}).get("file_path")
        if not file_path:
            return False
        url = f"https://api.telegram.org/file/bot{token}/{file_path}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=60) as r:
            dest_path.write_bytes(r.read())
        return True
    except Exception as e:
        logger.error(f"GOJ v1.6 — file download error: {e}")
        return False


def _load_pending_doc(key: str) -> dict | None:
    """Load a pending doc classification by its queue key from the JSON state file."""
    queue_path = Path.home() / "Desktop" / "REX" / "logs" / "pending_doc_classifications.json"
    if not queue_path.exists():
        return None
    try:
        queue = json.loads(queue_path.read_text())
        return queue.get(key)
    except Exception:
        return None


def _remove_pending_doc(key: str):
    """Remove a resolved entry from the pending classification queue."""
    queue_path = Path.home() / "Desktop" / "REX" / "logs" / "pending_doc_classifications.json"
    if not queue_path.exists():
        return
    try:
        queue = json.loads(queue_path.read_text())
        queue.pop(key, None)
        queue_path.write_text(json.dumps(queue, indent=2, ensure_ascii=False))
    except Exception:
        pass


def _save_pattern_to_db(file_path: str, doc_type: str, sub_type: str = ""):
    """
    Extract features from the confirmed file and store as a learned pattern
    in doc_classification_patterns (DB) AND goj_doc_patterns.json (for the intake script).
    """
    try:
        import sys as _sys
        rex_dir = Path.home() / "Desktop" / "REX"
        _sys.path.insert(0, str(rex_dir))
        from goj_signin_intake import _extract_doc_features, _save_learned_pattern

        path = Path(file_path)
        if not path.exists():
            logger.warning(f"_save_pattern_to_db: file not found: {file_path}")
            return

        # Read text with all available methods
        text = ""
        try:
            import fitz
            doc = fitz.open(str(path))
            text = "\n".join(p.get_text() for p in doc)
        except Exception:
            pass
        if len(text.strip()) < 20:
            try:
                import pdfplumber
                with pdfplumber.open(str(path)) as pdf:
                    text = "\n".join(p.extract_text() or "" for p in pdf.pages)
            except Exception:
                pass

        # Save to JSON patterns file (used by goj_signin_intake directly)
        _save_learned_pattern(path, text, doc_type)

        # Also save to DB for audit trail
        features = _extract_doc_features(path, text)
        con = sqlite3.connect(str(GOJ_AUTH_DB))
        con.execute("""
            INSERT INTO doc_classification_patterns
            (doc_type, sub_type, filename, cyrillic_ratio, top_words, checkmark_density,
             has_auth_kw, has_menu_kw, has_signin_kw, has_driver_kw, char_count)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            doc_type, sub_type or "", path.name,
            features.get("cyrillic_ratio", 0),
            json.dumps(features.get("top_words", []), ensure_ascii=False),
            features.get("checkmark_density", 0),
            int(features.get("has_auth_keywords", False)),
            int(features.get("has_menu_keywords", False)),
            int(features.get("has_signin_keywords", False)),
            int(features.get("has_driver_keywords", False)),
            features.get("char_count", 0),
        ))
        con.commit()
        con.close()
        logger.info(f"🧠 Pattern learned: '{doc_type}' ← {path.name}")
    except Exception as e:
        logger.error(f"_save_pattern_to_db: {e}")


def _route_classified_doc(file_path: str, doc_type: str, sub_type: str = "") -> str:
    """
    Route a confirmed document to the correct folder.
    Returns a human-readable result string for the Telegram reply.
    Handles the special cases: client_paperwork, staff_files, misc, skip.
    """
    import shutil
    from datetime import date as _date

    path = Path(file_path)
    if not path.exists():
        return f"⚠️ File no longer exists: {path.name}"

    today = _date.today().isoformat()
    docs_base = Path.home() / "Documents" / "goj files" / "dashboard" / "documents"

    if doc_type == "skip":
        return f"🗑 Skipped — <code>{path.name}</code> left in signins/ for manual review."

    if doc_type == "client_paperwork":
        client_name = sub_type.strip() if sub_type else "_unspecified"
        safe_name   = client_name.replace(" ", "_").replace("/","_")
        out_dir     = docs_base / "clients" / safe_name
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"{today}_{path.name}"
        shutil.copy2(str(path), str(dest))
        path.rename(path.parent / f".done_{path.name}")
        return f"📁 Filed under <b>clients/{safe_name}/</b>\n{dest.name}"

    if doc_type == "staff_files":
        staff_name = sub_type.strip() if sub_type else "_unspecified"
        safe_name  = staff_name.replace(" ", "_").replace("/","_")
        out_dir    = Path.home() / "Desktop" / "REX" / "staff" / safe_name
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"{today}_{path.name}"
        shutil.copy2(str(path), str(dest))
        path.rename(path.parent / f".done_{path.name}")
        return f"👤 Filed under <b>staff/{safe_name}/</b>\n{dest.name}"

    if doc_type == "misc":
        label     = sub_type.strip() if sub_type else "misc"
        safe_label = label.replace(" ","_").replace("/","_")[:40]
        out_dir   = docs_base / "misc"
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"{today}_{safe_label}_{path.name}"
        shutil.copy2(str(path), str(dest))
        path.rename(path.parent / f".done_{path.name}")
        return f"📂 Filed in <b>documents/misc/</b>\n{dest.name}"

    # Standard types: menu, auth, signin, drivers, kitchen
    try:
        import sys as _sys
        rex_dir = Path.home() / "Desktop" / "REX"
        _sys.path.insert(0, str(rex_dir))
        from goj_signin_intake import process_file, SHEET_KEYWORD_MAP

        # Temporarily force the type by re-classifying — inject into the text classifier
        # by calling process_file which will use learned patterns (we just saved one above)
        result = process_file(path)
        if result["status"] == "ok":
            icons = {"signin":"📋","drivers":"🚗","menu":"🍽","auth":"📄","kitchen":"🍳"}
            icon  = icons.get(result.get("type",""), "📁")
            return (
                f"{icon} <b>{result.get('type','?').title()} sheet</b> filed\n"
                f"{Path(result.get('output','')).name}"
            )
        else:
            # Pattern may not have propagated in time — do direct route as auth
            return f"⚙️ Processed with status: {result.get('status')}"
    except Exception as e:
        return f"⚠️ Routing error: {e}"


def _run_signin_intake() -> str:
    """GOJ v1.5 — Run goj_signin_intake.py and return a formatted Telegram summary."""
    import subprocess
    intake_script = Path(__file__).resolve().parent / "goj_signin_intake.py"
    if not intake_script.exists():
        return "❌ goj_signin_intake.py not found in REX folder."
    try:
        result = subprocess.run(
            ["python3", str(intake_script)],
            capture_output=True, text=True, timeout=120,
            cwd=str(intake_script.parent),
        )
        output = (result.stdout + result.stderr).strip()
        if not output:
            return "✅ Sign-in intake ran — no pending files in <code>signins/</code>."
        # Trim output for Telegram (4096 char limit)
        if len(output) > 3500:
            output = output[:3500] + "\n…(truncated)"
        return f"<pre>{output}</pre>"
    except subprocess.TimeoutExpired:
        return "⏱ Sign-in intake timed out (>2 min). Check Paperless OCR connection."
    except Exception as e:
        return f"❌ Intake error: {e}"


def _menu_blast() -> str:
    """GOJ v1.2 — Build the full MENU BLAST message from auth_tracker.db."""
    from datetime import date, timedelta
    today         = date.today()
    monday        = today - timedelta(days=today.weekday())
    week_start    = monday.isoformat()
    next_week_start = (monday + timedelta(weeks=1)).isoformat()
    tomorrow_dt   = today + timedelta(days=1)
    col_map = {
        0: "day_M_actual", 1: "day_T_actual", 2: "day_W_actual",
        3: "day_TH_actual", 4: "day_F_actual", 5: "day_Su_actual",
    }
    day_name_map = {
        0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday",
        4: "Friday", 5: "Saturday",
    }
    # Short codes matching client_menus.day column values (M, T, W, TH, F, SA)
    day_short_map = {0: "M", 1: "T", 2: "W", 3: "TH", 4: "F", 5: "SA"}
    day_col_pairs = [
        ("Monday", "day_M_actual"), ("Tuesday", "day_T_actual"),
        ("Wednesday", "day_W_actual"), ("Thursday", "day_TH_actual"),
        ("Friday", "day_F_actual"), ("Saturday", "day_Su_actual"),
    ]
    tomorrow_col   = col_map.get(tomorrow_dt.weekday(), "day_M_actual")
    tomorrow_name  = day_name_map.get(tomorrow_dt.weekday(), "Monday")
    tomorrow_short = day_short_map.get(tomorrow_dt.weekday(), "M")

    try:
        _goj_ensure_tables()
        con = sqlite3.connect(str(GOJ_AUTH_DB))

        total_clients       = con.execute("SELECT COUNT(*) FROM clients WHERE active=1").fetchone()[0]
        submitted_this_week = con.execute(
            "SELECT COUNT(DISTINCT client_name) FROM client_menus WHERE week_start=?",
            (week_start,),
        ).fetchone()[0]
        uploaded_next_week = con.execute(
            "SELECT COUNT(DISTINCT client_name) FROM client_menus WHERE week_start=?",
            (next_week_start,),
        ).fetchone()[0]
        missing_next_week = max(0, total_clients - uploaded_next_week)

        salad_totals = con.execute(
            "SELECT salad, COUNT(*) FROM client_menus "
            "WHERE week_start=? AND salad IS NOT NULL AND salad!='' "
            "GROUP BY salad ORDER BY 2 DESC",
            (week_start,),
        ).fetchall()
        soup_totals = con.execute(
            "SELECT soup, COUNT(*) FROM client_menus "
            "WHERE week_start=? AND soup IS NOT NULL AND soup!='' "
            "GROUP BY soup ORDER BY 2 DESC",
            (week_start,),
        ).fetchall()
        combo_totals = con.execute(
            "SELECT main, side, COUNT(*) FROM client_menus "
            "WHERE week_start=? AND main IS NOT NULL "
            "GROUP BY main, side ORDER BY 3 DESC",
            (week_start,),
        ).fetchall()

        scheduled_tomorrow = con.execute(
            f"SELECT name, shift FROM clients WHERE active=1 AND {tomorrow_col}>0 ORDER BY name"
        ).fetchall()
        have_menu_tomorrow = {
            r[0] for r in con.execute(
                "SELECT DISTINCT client_name FROM client_menus WHERE day=?",
                (tomorrow_short,),
            ).fetchall()
        }
        missing_tomorrow = [(n, s) for n, s in scheduled_tomorrow if n not in have_menu_tomorrow]

        ocr_flags = con.execute(
            "SELECT client_name, main, salad, day FROM client_menus "
            "WHERE week_start=? AND (confidence<0.7 OR main IS NULL OR salad IS NULL) "
            "ORDER BY client_name",
            (week_start,),
        ).fetchall()

        all_active = con.execute(
            "SELECT name, shift, day_M_actual, day_T_actual, day_W_actual, "
            "day_TH_actual, day_F_actual, day_Su_actual "
            "FROM clients WHERE active=1"
        ).fetchall()
        have_next_menu = {
            r[0] for r in con.execute(
                "SELECT DISTINCT client_name FROM client_menus WHERE week_start=?",
                (next_week_start,),
            ).fetchall()
        }
        today_idx    = today.weekday()
        handoff_list = []
        for row in all_active:
            name, shift, *day_vals = row
            if name in have_next_menu:
                continue
            last_day = None
            for i, (day_label, _) in enumerate(day_col_pairs):
                if day_vals[i] and float(day_vals[i]) > 0 and i >= today_idx:
                    last_day = day_label
            if last_day:
                handoff_list.append((name, shift, last_day))

        con.close()
    except Exception as e:
        logger.error(f"MENU BLAST DB error: {e}")
        return f"⚠️ MENU BLAST failed — DB error: {e}"

    lines = [f"🍽️ *MENU BLAST — Week of {week_start}*\n"]

    lines.append("📊 *SUBMISSION STATUS*")
    lines.append(f"• Menus submitted this week: {submitted_this_week} / {total_clients}")
    lines.append(f"• Uploaded for next week: {uploaded_next_week}")
    lines.append(f"• Missing next-week menus: {missing_next_week} clients\n")

    lines.append("🥗 *THIS WEEK'S MENU TOTALS*")
    lines.append("*SALADS:*")
    for s, cnt in (salad_totals or []):
        lines.append(f"• {s}: {cnt}")
    if not salad_totals:
        lines.append("• No salad data yet")

    lines.append("\n🥣 *SOUPS:*")
    for s, cnt in (soup_totals or []):
        lines.append(f"• {s}: {cnt}")
    if not soup_totals:
        lines.append("• No soup data yet")

    lines.append("\n🍽️ *MAIN + SIDE COMBOS:*")
    for main, side, cnt in (combo_totals or []):
        label = f"{main} + {side}" if side else main
        lines.append(f"• {label}: {cnt}")
    if not combo_totals:
        lines.append("• No combo data yet")

    lines.append(f"\n⚠️ *CLIENTS DUE TOMORROW ({tomorrow_name}) WITH NO MENU*")
    if missing_tomorrow:
        for name, shift in missing_tomorrow:
            lines.append(f"• {name} (Shift {shift})")
    else:
        lines.append("✅ All tomorrow's clients have menus")

    lines.append("\n❓ *OCR CLARIFICATION NEEDED*")
    if ocr_flags:
        for cname, main, salad, day in ocr_flags:
            unclear = []
            if not main:  unclear.append("main unknown")
            if not salad: unclear.append("salad unknown")
            label = ", ".join(unclear) or "low confidence"
            lines.append(f"• {cname} — {label} — {day or '?'}")
    else:
        lines.append("✅ No clarifications needed")

    lines.append("\n📋 *HANDOFF LIST — Fill Out Before Last Visit This Week*")
    if handoff_list:
        for name, shift, last_day in handoff_list:
            lines.append(f"• {name} (Shift {shift}) — Last visit: {last_day}")
    else:
        lines.append("✅ All clients have next-week menus")

    return "\n".join(lines)

# ── GOJ v1.3 — OCR helpers ────────────────────────────────────────────────────

_OCR_FLAGS_PATH = os.path.expanduser("~/Desktop/REX/goj_menu_flags_queue.json")
_OCR_LOG_PATH   = os.path.expanduser("~/Desktop/REX/logs/ocr_run.log")
_OCR_SCRIPT     = os.path.expanduser("~/Desktop/REX/goj_menu_consensus_ocr.py")
_MENU_DIR       = os.path.expanduser("~/Documents/goj files/dashboard/documents/menus")
_DB_PATH        = os.path.expanduser("~/Documents/goj files/dashboard/auth_tracker.db")


def _ocr_run_status() -> str:
    """GOJ v1.3 — Trigger an OCR run and return status message."""
    import subprocess, threading

    menu_dir = _MENU_DIR
    if not os.path.isdir(menu_dir):
        return f"❌ Menus folder not found:\n`{menu_dir}`\nDrop scanned PDFs there first."

    pdfs = [f for f in os.listdir(menu_dir) if f.lower().endswith('.pdf')]
    if not pdfs:
        return (f"📂 Menus folder is empty — no PDFs to process.\n"
                f"  Path: `{menu_dir}`\n"
                f"  Ask Allen to email scanned menus, then forward to GOJ Gmail → they'll auto-land there.")

    # Launch OCR in background
    venv_py = os.path.expanduser("~/Desktop/REX/.venv/bin/python3")
    py = venv_py if os.path.exists(venv_py) else "python3"

    def _run():
        try:
            os.makedirs(os.path.dirname(_OCR_LOG_PATH), exist_ok=True)
            with open(_OCR_LOG_PATH, 'w') as logf:
                subprocess.run(
                    [py, _OCR_SCRIPT, '--menu-dir', menu_dir, '--db', _DB_PATH,
                     '--learning', os.path.expanduser("~/Desktop/REX/goj_menu_learning.json"),
                     '--flags', _OCR_FLAGS_PATH],
                    stdout=logf, stderr=logf
                )
        except Exception as e:
            with open(_OCR_LOG_PATH, 'a') as logf:
                logf.write(f"\nERROR: {e}\n")

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return (f"🔍 *OCR run started* — {len(pdfs)} PDF(s) in queue\n"
            f"  Engines: Tesseract · Google Drive · Paperless · Claude Vision\n"
            f"  When done, send `MENU FLAGS` to see what needs review.\n"
            f"  Log: `{_OCR_LOG_PATH}`")


def _ocr_flags_summary() -> str:
    """GOJ v1.3 — Summarize pending OCR flags queue."""
    if not os.path.exists(_OCR_FLAGS_PATH):
        return "✅ No flags queue found — either OCR hasn't run yet or everything was clean."

    try:
        with open(_OCR_FLAGS_PATH, encoding='utf-8') as f:
            flags = json.load(f)
    except Exception as e:
        return f"❌ Could not read flags queue: {e}"

    pending = [f for f in flags if f.get('status') == 'pending']
    resolved = [f for f in flags if f.get('status') == 'resolved']

    if not pending:
        return f"✅ No pending flags — {len(resolved)} already resolved."

    lines = [f"⚠️ *OCR FLAGS — {len(pending)} need review* ({len(resolved)} resolved)\n"]
    for i, flag in enumerate(pending[:10], 1):
        name = flag.get('candidate_name') or '?'
        matched = flag.get('matched_name') or 'no match'
        conf = flag.get('name_confidence', 0)
        pdf = os.path.basename(flag.get('pdf_path', '?'))
        engines = ', '.join(flag.get('engines_used', []))
        lines.append(
            f"*{i}.* `{name}` → matched: {matched} ({conf:.0%})\n"
            f"     PDF: {pdf} | Engines: {engines}"
        )

    if len(pending) > 10:
        lines.append(f"\n…and {len(pending) - 10} more. Review in dashboard: /menus")

    lines.append(f"\n📋 Resolve in dashboard → Operations → Menu OCR Review")
    return "\n".join(lines)

# ── end GOJ v1.3 OCR helpers ──────────────────────────────────────────────────


# ── GOJ v1.4 — Session greeting, task tracker, /auth ──────────────────────────

_COMMITMENT_PHRASES = [
    "i will", "i'll", "let me", "i'm going to", "i am going to",
    "i can do that", "i'll take care", "i'll handle", "i'll check",
    "i'll look into", "i'll send", "i'll update", "i'll run",
    "i'll fix", "i'll add", "i'll review",
]


def _detect_commitment(text: str) -> list:
    """Return list of commitment snippets found in text (from Rexxie's reply)."""
    lower = text.lower()
    found = []
    for phrase in _COMMITMENT_PHRASES:
        idx = lower.find(phrase)
        while idx != -1:
            # Extract the sentence containing the commitment
            start = max(0, text.rfind('.', 0, idx) + 1)
            end   = text.find('.', idx)
            if end == -1:
                end = len(text)
            snippet = text[start:end].strip()
            if snippet and len(snippet) > 10:
                found.append(snippet)
            idx = lower.find(phrase, idx + 1)
    return list(dict.fromkeys(found))   # deduplicate, preserve order


def _save_task_commitment(task_text: str):
    """Write a commitment to the rexxie_tasks table."""
    try:
        _goj_ensure_tables()
        con = sqlite3.connect(str(GOJ_AUTH_DB))
        con.execute(
            "INSERT INTO rexxie_tasks (task_text, status, source) VALUES (?, 'pending', 'rexxie_commitment')",
            (task_text[:400],),
        )
        con.commit()
        con.close()
    except Exception as e:
        logger.error(f"save_task_commitment: {e}")


# ── GOJ v1.7 — Structured memory: idea / decision capture ─────────────────────

# ── Memory detection phrase banks (all 6 ChatGPT memory categories) ───────────
_IDEA_PHRASES = [
    "i have an idea", "what if we", "what if i", "we should", "i should",
    "it would be cool", "it would be great", "we could", "i could", "maybe we",
    "thinking about", "been thinking", "want to build", "want to add",
    "plan to", "planning to", "going to try", "idea:", "new idea",
]
_DECISION_PHRASES = [
    "we decided", "i decided", "going with", "chose to", "choosing",
    "confirmed that", "settled on", "final decision", "the plan is",
    "sticking with", "we agreed", "i agreed",
]
_QUESTION_PHRASES = [
    "not sure about", "keep wondering", "unsure how", "don't know how",
    "need to figure out", "haven't figured out", "open question",
]
_PREFERENCE_PHRASES = [
    "i prefer", "i like", "i don't like", "i always", "i never",
    "i want rexxie to", "i want rex to", "make sure rexxie", "always remember that i",
    "i find it better", "works better for me", "my preference",
]
_STATE_PHRASES = [
    "right now", "currently", "at the moment", "as of today", "the current state",
    "we are at", "status is", "where we stand", "where things are",
]
_BLOCKER_PHRASES = [
    "blocked on", "stuck on", "can't figure out", "cant figure out",
    "not working", "broken", "issue with", "problem with", "something's wrong",
    "not sure why", "failing", "this is a problem",
]


def _detect_structured_memory(text: str) -> list[dict]:
    """
    GOJ v1.7 — Scan user text for all 6 structured memory categories:
    idea, decision, question, preference, state, blocker
    Returns list of dicts: {"type": str, "content": str}
    """
    lower = text.lower()
    found = []

    for type_name, phrases in [
        ("idea",       _IDEA_PHRASES),
        ("decision",   _DECISION_PHRASES),
        ("question",   _QUESTION_PHRASES),
        ("preference", _PREFERENCE_PHRASES),
        ("state",      _STATE_PHRASES),
        ("blocker",    _BLOCKER_PHRASES),
    ]:
        for phrase in phrases:
            idx = lower.find(phrase)
            if idx == -1:
                continue
            # Extract the sentence
            start = max(0, text.rfind(".", 0, idx) + 1)
            end   = text.find(".", idx)
            if end == -1:
                end = len(text)
            snippet = text[start:end].strip()
            if snippet and len(snippet) > 15:
                # Avoid duplicates (same snippet already found under a different phrase)
                if not any(f["content"] == snippet for f in found):
                    found.append({"type": type_name, "content": snippet})
            break   # one match per phrase type per sentence is enough

    return found


def _save_idea(idea_type: str, content: str, source: str = "user", component_link: str = None):
    """Save a structured idea/decision/question to rexxie_ideas table.
    Also attempts to link to master build via coordinator."""
    # Auto-link to master build component
    if _COORDINATOR_AVAILABLE and not component_link:
        try:
            component_link = _coordinator.process_idea_through_coordinator(content, idea_type)
        except Exception:
            pass

    try:
        _goj_ensure_tables()
        con = sqlite3.connect(str(GOJ_AUTH_DB))
        con.execute(
            """INSERT INTO rexxie_ideas (idea_type, content, source, component_link)
               VALUES (?, ?, ?, ?)""",
            (idea_type, content[:500], source, component_link),
        )
        con.commit()
        con.close()
        logger.info(f"Idea captured [{idea_type}] → {component_link or 'unlinked'}: {content[:60]}")
    except Exception as e:
        logger.error(f"save_idea: {e}")


def _retrieve_relevant_memory(query: str, limit: int = 5) -> str:
    """
    GOJ v1.7 — Retrieve relevant structured memories before generating a response.
    Keyword-based retrieval from rexxie_ideas (local-only, no vectors needed).
    Returns a formatted context block, or empty string if nothing relevant.
    """
    try:
        _goj_ensure_tables()
        con  = sqlite3.connect(str(GOJ_AUTH_DB))
        rows = con.execute(
            "SELECT idea_type, content, component_link, created_at FROM rexxie_ideas WHERE status='open' ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
        con.close()
    except Exception:
        return ""

    if not rows:
        return ""

    # Score each entry by keyword overlap with the query
    query_words = set(w for w in query.lower().split() if len(w) > 3)
    scored = []
    for row in rows:
        content = row[1].lower()
        overlap = sum(1 for w in query_words if w in content)
        if overlap > 0:
            scored.append((overlap, row))

    if not scored:
        return ""

    # Take top N by score
    scored.sort(key=lambda x: -x[0])
    top = scored[:limit]

    icons = {"idea": "💡", "decision": "✅", "question": "❓",
             "preference": "⭐", "state": "📍", "blocker": "🚧"}
    lines = ["_[Relevant memory]:_"]
    for _, row in top:
        icon = icons.get(row[0], "•")
        date = row[3][:10] if row[3] else ""
        comp = f" _{row[2]}_" if row[2] else ""
        lines.append(f"{icon} {row[1][:120]}{comp} ({date})")

    return "\n".join(lines)


def _get_ideas_report(idea_type: str = None, limit: int = 10) -> str:
    """Return formatted idea/decision log from rexxie_ideas."""
    try:
        _goj_ensure_tables()
        con = sqlite3.connect(str(GOJ_AUTH_DB))
        if idea_type:
            rows = con.execute(
                "SELECT idea_type, content, created_at FROM rexxie_ideas WHERE idea_type=? AND status='open' ORDER BY created_at DESC LIMIT ?",
                (idea_type, limit)
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT idea_type, content, created_at FROM rexxie_ideas WHERE status='open' ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        con.close()
    except Exception:
        return "⚠ Idea log unavailable."

    if not rows:
        return "📭 No ideas logged yet."

    icons = {"idea": "💡", "decision": "✅", "question": "❓"}
    lines = ["*Your idea/decision log:*\n"]
    for row in rows:
        icon = icons.get(row[0], "•")
        date = row[2][:10] if row[2] else ""
        lines.append(f"{icon} [{row[0].upper()}] {row[1]}  _({date})_")
    return "\n".join(lines)


def _get_tasks_report() -> str:
    """Return a formatted task list from rexxie_tasks."""
    try:
        _goj_ensure_tables()
        con  = sqlite3.connect(str(GOJ_AUTH_DB))
        rows = con.execute(
            "SELECT id, task_text, status, created_at FROM rexxie_tasks ORDER BY id DESC LIMIT 30"
        ).fetchall()
        con.close()
    except Exception as e:
        return f"❌ Could not read tasks: {e}"
    if not rows:
        return "📋 No tasks on record yet."

    pending   = [(r[0], r[1], r[3]) for r in rows if r[2] == 'pending']
    in_prog   = [(r[0], r[1], r[3]) for r in rows if r[2] == 'in_progress']
    done      = [(r[0], r[1], r[3]) for r in rows if r[2] == 'done']

    lines = [f"📋 *Task Tracker* — {len(pending)} pending | {len(in_prog)} in progress | {len(done)} done\n"]
    if pending:
        lines.append("*⏳ Pending:*")
        for tid, txt, cat in pending[:10]:
            lines.append(f"  {tid}. {txt[:80]}")
    if in_prog:
        lines.append("\n*🔄 In Progress:*")
        for tid, txt, cat in in_prog[:5]:
            lines.append(f"  {tid}. {txt[:80]}")
    if done:
        lines.append(f"\n*✅ Done (last {min(5, len(done))}):*")
        for tid, txt, cat in done[:5]:
            lines.append(f"  {tid}. {txt[:80]}")
    lines.append("\nSend `/done [number]` to mark a task complete.")
    return "\n".join(lines)


def _get_task_footer() -> str:
    """Return a short task count footer for appending to replies."""
    try:
        _goj_ensure_tables()
        con     = sqlite3.connect(str(GOJ_AUTH_DB))
        pending = con.execute("SELECT COUNT(*) FROM rexxie_tasks WHERE status='pending'").fetchone()[0]
        in_prog = con.execute("SELECT COUNT(*) FROM rexxie_tasks WHERE status='in_progress'").fetchone()[0]
        done    = con.execute("SELECT COUNT(*) FROM rexxie_tasks WHERE status='done'").fetchone()[0]
        con.close()
        if pending + in_prog + done == 0:
            return ""
        return f"\n\n_[Tasks: {pending} pending | {in_prog} in progress | {done} done]_"
    except Exception:
        return ""


def _mark_task_done(task_num: int) -> str:
    """Mark a task as done by its ID. Returns confirmation message."""
    try:
        _goj_ensure_tables()
        con = sqlite3.connect(str(GOJ_AUTH_DB))
        row = con.execute("SELECT task_text FROM rexxie_tasks WHERE id=?", (task_num,)).fetchone()
        if not row:
            con.close()
            return f"❌ Task #{task_num} not found."
        con.execute(
            "UPDATE rexxie_tasks SET status='done', updated_at=datetime('now') WHERE id=?",
            (task_num,),
        )
        con.commit()
        con.close()
        return f"✅ Task #{task_num} marked done:\n_{row[0][:120]}_"
    except Exception as e:
        return f"❌ Error: {e}"


def _archive_stale_tasks(days_old: int = 14) -> int:
    """Auto-archive pending tasks older than N days. Prevents startup noise from stale tasks."""
    try:
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=days_old)).isoformat()
        con = _goj_conn()
        result = con.execute(
            "UPDATE rexxie_tasks SET status='archived', updated_at=datetime('now') WHERE status='pending' AND created_at < ?",
            (cutoff,)
        )
        count = result.rowcount
        con.commit(); con.close()
        if count: logger.info(f"[tasks] Auto-archived {count} stale tasks (>{days_old}d old)")
        return count
    except Exception as e:
        logger.debug(f"[tasks] archive error: {e}"); return 0


def _build_session_greeting() -> str:
    """Build the structured session greeting block for the first message after restart."""
    from datetime import date
    _archive_stale_tasks(days_old=14)   # prevent unbounded task accumulation
    today_str = date.today().strftime("%A, %B %d, %Y")

    # Last memory from rex_memory.db
    last_session = "No prior session found."
    try:
        mem_db = Path.home() / "Desktop" / "REX" / "rex_memory.db"
        if mem_db.exists():
            con  = sqlite3.connect(str(mem_db))
            row  = con.execute(
                "SELECT content FROM memories ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            con.close()
            if row:
                last_session = row[0][:200].strip()
    except Exception:
        pass

    # Task counts
    pending = in_prog = blocked = 0
    pending_list = []
    try:
        _goj_ensure_tables()
        con      = sqlite3.connect(str(GOJ_AUTH_DB))
        pending  = con.execute("SELECT COUNT(*) FROM rexxie_tasks WHERE status='pending'").fetchone()[0]
        in_prog  = con.execute("SELECT COUNT(*) FROM rexxie_tasks WHERE status='in_progress'").fetchone()[0]
        done_cnt = con.execute("SELECT COUNT(*) FROM rexxie_tasks WHERE status='done'").fetchone()[0]
        rows     = con.execute(
            "SELECT id, task_text FROM rexxie_tasks WHERE status='pending' ORDER BY id DESC LIMIT 5"
        ).fetchall()
        con.close()
        pending_list = [(r[0], r[1][:80]) for r in rows]
    except Exception:
        done_cnt = 0

    lines = [
        f"🐢 *Hey, Kato.*\n",
        f"📅 *Date:* {today_str}",
        f"🗂 *Last session:* {last_session}\n",
        f"*Current task queue:*",
        f"  ✅ {done_cnt} completed",
        f"  ⏳ {pending} pending",
        f"  🔄 {in_prog} in progress",
    ]
    if pending_list:
        lines.append("\n*Pending items:*")
        for i, (tid, txt) in enumerate(pending_list, 1):
            lines.append(f"  {i}. [{tid}] {txt}")
    lines.append("\nWhat would you like to work on?")
    return "\n".join(lines)


def _get_auth_status_report() -> str:
    """Return a formatted authorization status report from auth_tracker.db."""
    from datetime import date, timedelta
    today = date.today()
    warn_date = (today + timedelta(days=30)).isoformat()
    today_iso = today.isoformat()

    try:
        con = sqlite3.connect(str(GOJ_AUTH_DB))

        # Total active clients
        total = con.execute("SELECT COUNT(*) FROM clients WHERE active=1").fetchone()[0]

        # Check if authorizations table exists
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if 'authorizations' not in tables:
            con.close()
            return (f"📊 *Authorization Status*\n\n"
                    f"Total active clients: {total}\n\n"
                    f"⚠️ Authorizations table not yet created.\n"
                    f"Run the auth import pipeline to populate it.")

        # Expiring soon
        expiring = con.execute(
            "SELECT client_id, payer, auth_number, end_date FROM authorizations "
            "WHERE end_date BETWEEN ? AND ? AND active=1 ORDER BY end_date",
            (today_iso, warn_date),
        ).fetchall()

        # Already expired
        expired = con.execute(
            "SELECT COUNT(*) FROM authorizations WHERE end_date < ? AND active=1",
            (today_iso,),
        ).fetchone()[0]

        # Total active auths
        total_auths = con.execute(
            "SELECT COUNT(*) FROM authorizations WHERE active=1"
        ).fetchone()[0]

        con.close()

        lines = [f"📊 *Authorization Status — {today_iso}*\n"]
        lines.append(f"Active clients: {total}")
        lines.append(f"Active auths on file: {total_auths}")
        lines.append(f"Expired: {expired}")
        lines.append(f"Expiring within 30 days: {len(expiring)}\n")

        if expiring:
            lines.append("*⚠️ Expiring soon:*")
            for cid, payer, auth_num, end_date in expiring[:15]:
                lines.append(f"  • Client {cid} | {payer} | Auth {auth_num} | Expires {end_date}")
            if len(expiring) > 15:
                lines.append(f"  …and {len(expiring)-15} more.")

        if expired > 0:
            lines.append(f"\n🔴 *{expired} expired authorizations need renewal — check dashboard.*")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Auth status error: {e}"


# ── GOJ v1.5 — OCR live-progress engine ───────────────────────────────────────

# Shared state between the OCR background thread and the message handler
_OCR_STATUS: dict = {
    "running":       False,
    "muted":         False,       # True = suppress 120s updates (still sends completion)
    "task_note":     None,        # User correction injected via /edit
    "start_time":    None,
    "pdfs":          [],          # full list of PDF filenames
    "current_file":  None,        # filename being processed right now
    "files_done":    [],          # filenames fully processed
    "engines_done":  [],          # engine results for current file
    "accepted":      0,
    "flagged":       0,
    "chat_id":       None,
}


def _parse_ocr_log(log_path: str) -> dict:
    """
    Parse the OCR run log and return structured progress state.
    The OCR script writes lines like:
      Processing: filename.pdf
        Engine 1: Tesseract... OK
        Engine 2: Google Drive... FAIL
        ACTION: AUTO-ACCEPT (confidence: 87.5%)
    """
    result = {
        "files_done": [],
        "current_file": None,
        "engines_done": [],
        "accepted": 0,
        "flagged": 0,
        "last_lines": [],
        "summary_line": None,
    }
    if not os.path.exists(log_path):
        return result

    try:
        with open(log_path, 'r', errors='replace') as f:
            lines = f.readlines()
    except Exception:
        return result

    current = None
    engines = []
    _ENGINE_MAP = {
        "1": "Tesseract",
        "2": "Google Drive",
        "3": "Paperless",
        "4": "Claude Vision",
    }

    for raw in lines:
        s = raw.strip()
        if not s:
            continue

        if s.startswith("Processing:"):
            # New file starting — commit previous file if complete
            fname = s[len("Processing:"):].strip()
            if current and current != fname:
                result["files_done"].append(current)
            current = fname
            engines = []

        elif "Engine" in s and (": Tesseract" in s or ": Google" in s or
                                 ": Paperless" in s or ": Claude" in s):
            # Parse: "Engine 1: Tesseract... OK" or "Engine 1: Tesseract... FAIL"
            status = "✅ OK" if "OK" in s else ("❌ FAIL" if "FAIL" in s else "⏳")
            for num, name in _ENGINE_MAP.items():
                if f"Engine {num}:" in s or name in s:
                    entry = f"{name}: {status}"
                    if not any(name in e for e in engines):
                        engines.append(entry)
                    elif status != "⏳":
                        # Update existing entry with final result
                        engines = [entry if name in e else e for e in engines]
                    break

        elif "AUTO-ACCEPT" in s:
            result["accepted"] += 1
            if current:
                result["files_done"].append(current)
                current = None
                engines = []

        elif "FLAG for review" in s:
            result["flagged"] += 1
            if current:
                result["files_done"].append(current)
                current = None
                engines = []

        elif s.startswith("SUMMARY:"):
            result["summary_line"] = s

    result["current_file"] = current
    result["engines_done"] = engines
    result["last_lines"] = [l.strip() for l in lines[-6:] if l.strip()]
    # Deduplicate files_done
    seen = set()
    result["files_done"] = [
        f for f in result["files_done"] if not (f in seen or seen.add(f))
    ]
    return result


def _build_ocr_progress_msg(total_pdfs: int, start_time: float,
                             parsed: dict, task_note: str = None) -> str:
    """Compose the 120-second progress Telegram message."""
    import time as _t
    elapsed   = int(_t.time() - start_time)
    mins, sec = elapsed // 60, elapsed % 60
    done_cnt  = len(parsed["files_done"])
    curr      = parsed["current_file"] or "waiting for next file..."
    engines   = parsed["engines_done"]
    accepted  = parsed["accepted"]
    flagged   = parsed["flagged"]

    # ETA estimate
    if done_cnt > 0:
        rate      = elapsed / done_cnt
        remaining = max(0, (total_pdfs - done_cnt - 1) * rate)
        eta_str   = f"~{int(remaining//60)}m {int(remaining%60)}s remaining"
    else:
        eta_str   = "calculating ETA..."

    # Engine display
    engine_lines = "\n".join(f"   {e}" for e in engines) if engines else "   ⏳ Starting engines..."

    # What Rexxie is doing
    what_doing = (
        "Reading each client's 2-page Russian menu form. "
        "For every file I run 4 OCR engines simultaneously — Tesseract (local), "
        "Google Drive (cloud), Paperless-ngx (Tailscale), and Claude Vision (AI). "
        "Each engine reads: salad, soup, main dish, and side dish selected for each day "
        "Mon–Sat. The 4 results are voted on — if 3+ agree it goes straight to the database; "
        "if not, it gets flagged for your review."
    )
    if task_note:
        what_doing += f"\n\n📝 *Your note:* {task_note}"

    msg = (
        f"📋 *Menu OCR — Update*\n\n"
        f"*Current file:* `{curr}`\n"
        f"*Engines on this file:*\n{engine_lines}\n\n"
        f"*Progress:* {done_cnt} / {total_pdfs} files done\n"
        f"*Results:* {accepted} auto-accepted · {flagged} flagged for review\n"
        f"*Time:* {mins}m {sec}s elapsed · {eta_str}\n\n"
        f"*What I'm doing:*\n{what_doing}\n\n"
        f"_Send `ocr mute` to silence updates · `/edit [note]` to correct me_"
    )
    return msg


def _run_ocr_with_progress(token: str, chat_id: int):
    """GOJ v1.5 — Run OCR with real log-parsed progress updates every 120s."""
    import subprocess, threading, time as _time

    global _OCR_STATUS

    menu_dir = _MENU_DIR
    if not os.path.isdir(menu_dir):
        _send_message(token, chat_id, f"❌ Menus folder not found:\n`{menu_dir}`")
        return

    pdfs = sorted(f for f in os.listdir(menu_dir) if f.lower().endswith('.pdf'))
    if not pdfs:
        _send_message(token, chat_id,
                      f"📂 No PDFs in menus folder.\nPath: `{menu_dir}`\n"
                      f"Drop scanned menus there and try again.")
        return

    if _OCR_STATUS.get("running"):
        # Already running — send current status instead of starting another
        parsed = _parse_ocr_log(_OCR_LOG_PATH)
        msg = _build_ocr_progress_msg(
            len(_OCR_STATUS["pdfs"]),
            _OCR_STATUS["start_time"],
            parsed,
            _OCR_STATUS.get("task_note"),
        )
        _send_message(token, chat_id, f"⚠️ OCR is already running.\n\n{msg}")
        return

    venv_py = os.path.expanduser("~/Desktop/REX/.venv/bin/python3")
    py      = venv_py if os.path.exists(venv_py) else "python3"

    # Reset status
    _OCR_STATUS.update({
        "running":      True,
        "muted":        False,
        "task_note":    None,
        "start_time":   _time.time(),
        "pdfs":         pdfs,
        "current_file": None,
        "files_done":   [],
        "engines_done": [],
        "accepted":     0,
        "flagged":      0,
        "chat_id":      chat_id,
    })

    os.makedirs(os.path.dirname(_OCR_LOG_PATH), exist_ok=True)

    _send_message(token, chat_id,
                  f"📋 *Menu OCR starting*\n\n"
                  f"Files to process: *{len(pdfs)}*\n"
                  f"{chr(10).join('  · ' + f for f in pdfs[:8])}"
                  f"{chr(10) + f'  …and {len(pdfs)-8} more' if len(pdfs) > 8 else ''}\n\n"
                  f"Engines: Tesseract · Google Drive · Paperless · Claude Vision\n"
                  f"Updates every 120 seconds.\n\n"
                  f"*What I'm looking for:* Each 2-page Russian menu form contains a client's "
                  f"meal selections for Mon–Sat: salad, soup, main dish, and side. "
                  f"I'll build a kitchen production count from all submissions.\n\n"
                  f"Send `ocr mute` to silence updates · `/edit [note]` to clarify context")

    def _run_and_report():
        global _OCR_STATUS
        start_t = _OCR_STATUS["start_time"]
        try:
            # -u = unbuffered stdout — ensures print() flushes immediately to log
            with open(_OCR_LOG_PATH, 'w', buffering=1) as logf:
                proc = subprocess.Popen(
                    [py, "-u", _OCR_SCRIPT,
                     "--menu-dir", menu_dir,
                     "--db",       _DB_PATH,
                     "--learning", os.path.expanduser("~/Desktop/REX/goj_menu_learning.json"),
                     "--flags",    _OCR_FLAGS_PATH],
                    stdout=logf, stderr=logf,
                    bufsize=1,
                )

            # 120-second polling loop
            while proc.poll() is None:
                _time.sleep(120)
                if proc.poll() is not None:
                    break   # finished while we were sleeping

                parsed = _parse_ocr_log(_OCR_LOG_PATH)

                # Update shared status
                _OCR_STATUS["current_file"] = parsed["current_file"]
                _OCR_STATUS["files_done"]   = parsed["files_done"]
                _OCR_STATUS["engines_done"] = parsed["engines_done"]
                _OCR_STATUS["accepted"]     = parsed["accepted"]
                _OCR_STATUS["flagged"]      = parsed["flagged"]

                if not _OCR_STATUS["muted"]:
                    msg = _build_ocr_progress_msg(
                        len(pdfs), start_t, parsed,
                        _OCR_STATUS.get("task_note"),
                    )
                    _send_message(token, chat_id, msg)

            # ── Finished ──────────────────────────────────────────────────────
            rc     = proc.returncode
            parsed = _parse_ocr_log(_OCR_LOG_PATH)
            elapsed = int(_time.time() - start_t)
            mins, sec = elapsed // 60, elapsed % 60

            _OCR_STATUS["running"] = False

            if rc == 0 or parsed["summary_line"]:
                accepted = parsed["accepted"]
                flagged  = parsed["flagged"]
                _send_message(token, chat_id,
                              f"✅ *Menu OCR complete*\n\n"
                              f"Files processed: {len(pdfs)}\n"
                              f"Auto-accepted: {accepted}\n"
                              f"Flagged for review: {flagged}\n"
                              f"Time taken: {mins}m {sec}s\n\n"
                              f"Send `menu flags` to review flagged items.\n"
                              f"Send `menu blast` for the full kitchen summary.")
            else:
                try:
                    with open(_OCR_LOG_PATH) as lf:
                        tail_lines = lf.readlines()[-8:]
                    snippet = "".join(tail_lines).strip()[-400:]
                except Exception:
                    snippet = "Check ~/Desktop/REX/logs/ocr_run.log"
                _send_message(token, chat_id,
                              f"❌ *OCR finished with errors* (exit code {rc})\n\n"
                              f"Last log output:\n```\n{snippet}\n```\n\n"
                              f"Files processed: {len(parsed['files_done'])} / {len(pdfs)}")

        except Exception as e:
            _OCR_STATUS["running"] = False
            _send_message(token, chat_id, f"❌ OCR process error: {e}")

    threading.Thread(target=_run_and_report, daemon=True).start()

# ── end OCR live-progress engine ──────────────────────────────────────────────


# ── end GOJ v1.4 helpers ───────────────────────────────────────────────────────

# ── end GOJ v1.2 module-level helpers ─────────────────────────────────────────


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}


def _save_config(cfg: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    CONFIG_PATH.chmod(0o600)


def _tg_api(token: str, method: str, payload: dict = None) -> Optional[dict]:
    base_url = f"https://api.telegram.org/bot{token}/{method}"
    # getUpdates uses GET to avoid stuck POST long-poll connections (409 loops)
    if method == "getUpdates":
        # Build query params manually so allowed_updates is properly JSON-encoded
        params = {}
        if payload:
            for k, v in payload.items():
                if isinstance(v, list):
                    params[k] = json.dumps(v)
                else:
                    params[k] = v
        qs = urllib.parse.urlencode(params)
        url = f"{base_url}?{qs}" if qs else base_url
        req = urllib.request.Request(url, method="GET")
        req.add_header("Connection", "close")
    else:
        url = base_url
        data = json.dumps(payload or {}).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json", "Connection": "close"},
            method="POST",
        )
    # getUpdates timeout=0 returns immediately — use short socket timeout (10s)
    # Explicit close in finally prevents leaked connections that cause 409 loops
    sock_timeout = 60 if method == "getUpdates" else 35
    resp = None
    try:
        resp = urllib.request.urlopen(req, timeout=sock_timeout)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        # Must drain the error body AND close the connection to release the slot.
        # Otherwise Telegram sees a dangling long-poll and returns 409 forever.
        try:
            _ = e.read()
            e.close()  # explicitly close underlying socket
        except Exception:
            pass
        if method == "getUpdates" and e.code == 409:
            logger.warning(f"Telegram 409 Conflict — stale connection detected, will retry")
        else:
            logger.error(f"Telegram API ({method}): {e}")
        return None
    except Exception as e:
        logger.error(f"Telegram API ({method}): {e}")
        return None
    finally:
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass


def _send_typing(token: str, chat_id: int):
    _tg_api(token, "sendChatAction", {"chat_id": chat_id, "action": "typing"})


def _send_message(token: str, chat_id: int, text: str, parse_mode: str = "Markdown"):
    """Send message with auto-chunking for long replies."""
    if not text or not text.strip():
        return

    chunks = []
    while len(text) > MAX_MSG_LEN:
        split_at = text.rfind("\n", 0, MAX_MSG_LEN)
        if split_at < MAX_MSG_LEN // 2:
            split_at = MAX_MSG_LEN
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    chunks.append(text)

    for i, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
        result = _tg_api(token, "sendMessage", {
            "chat_id":    chat_id,
            "text":       chunk,
            "parse_mode": parse_mode,
        })
        if not result or not result.get("ok"):
            # Retry without markdown
            _tg_api(token, "sendMessage", {"chat_id": chat_id, "text": chunk})
        if i < len(chunks) - 1:
            time.sleep(0.3)


def _send_photo_file(token: str, chat_id: int, image_path: str, caption: str = "") -> bool:
    """
    Send a local image file to a Telegram chat via multipart/form-data.
    Returns True on success.
    """
    import urllib.request, urllib.parse, mimetypes, io
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    boundary = "----TgBotBoundary"
    mime_type, _ = mimetypes.guess_type(image_path)
    if not mime_type:
        mime_type = "image/jpeg"
    try:
        with open(image_path, "rb") as fh:
            img_data = fh.read()
        body = io.BytesIO()
        def _field(name: str, value: str):
            body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
        def _file_field(name: str, filename: str, data: bytes, ctype: str):
            body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\nContent-Type: {ctype}\r\n\r\n".encode())
            body.write(data)
            body.write(b"\r\n")
        _field("chat_id", str(chat_id))
        if caption:
            _field("caption", caption[:1024])
            _field("parse_mode", "HTML")
        _file_field("photo", Path(image_path).name, img_data, mime_type)
        body.write(f"--{boundary}--\r\n".encode())
        body_bytes = body.getvalue()
        req = urllib.request.Request(
            url, data=body_bytes,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result.get("ok", False)
    except Exception as e:
        logger.error(f"_send_photo_file: {e}")
        return False


def _pdf_first_page_jpeg(pdf_path: str, out_path: str, dpi: int = 150) -> bool:
    """
    Render the first page of a PDF to a JPEG at out_path.
    Tries PyMuPDF (fitz) first, then falls back to pdf2image.
    Returns True on success.
    """
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        page = doc[0]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        pix.save(out_path)
        doc.close()
        return True
    except Exception:
        pass
    try:
        from pdf2image import convert_from_path
        images = convert_from_path(pdf_path, dpi=dpi, first_page=1, last_page=1)
        if images:
            images[0].save(out_path, "JPEG", quality=85)
            return True
    except Exception:
        pass
    return False


def _parse_event(text: str) -> Optional[dict]:
    """
    Parse natural language calendar/reminder requests from Kato.
    Returns a dict ready for /api/chairman/events, or None if not a calendar command.

    Handles patterns like:
      "remind me tomorrow at 3pm to call Dr. Smith"
      "add to calendar: dentist appointment friday at 2pm"
      "schedule meeting with board on April 5th at 10am"
      "reminder: pick up meds on Saturday"
    """
    import re
    from datetime import date, timedelta

    low = text.strip().lower()

    # Must look like a calendar/reminder command
    CALENDAR_TRIGGERS = [
        "remind me", "reminder", "add to calendar", "schedule", "set a reminder",
        "don't let me forget", "note for", "add event", "put on calendar",
        "book", "appointment", "meeting at", "call at",
    ]
    if not any(t in low for t in CALENDAR_TRIGGERS):
        return None

    # Extra guard: reject obvious memory/question/list phrases that are not calendar requests
    NON_CALENDAR_PHRASES = [
        "what do you know", "do you remember", "what do you think",
        "tell me about", "who is", "what is", "how are",
        "make me a list", "give me a list", "list of", "20 question",
        "want to learn", "summarize", "summary of", "explain",
        "what should", "what would", "how do", "how should",
    ]
    if any(p in low for p in NON_CALENDAR_PHRASES):
        return None

    # ── Date parsing ─────────────────────────────────────────────────────────
    today = date.today()
    event_date = today.isoformat()

    day_patterns = {
        "today":     today,
        "tonight":   today,
        "tomorrow":  today + timedelta(days=1),
        "monday":    today + timedelta(days=(0 - today.weekday()) % 7 or 7),
        "tuesday":   today + timedelta(days=(1 - today.weekday()) % 7 or 7),
        "wednesday": today + timedelta(days=(2 - today.weekday()) % 7 or 7),
        "thursday":  today + timedelta(days=(3 - today.weekday()) % 7 or 7),
        "friday":    today + timedelta(days=(4 - today.weekday()) % 7 or 7),
        "saturday":  today + timedelta(days=(5 - today.weekday()) % 7 or 7),
        "sunday":    today + timedelta(days=(6 - today.weekday()) % 7 or 7),
    }
    for word, d in day_patterns.items():
        if word in low:
            event_date = d.isoformat()
            break
    else:
        # Try "Month Day" e.g. "April 5", "Apr 5th"
        month_match = re.search(
            r'\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|'
            r'jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)'
            r'[.\s]+(\d{1,2})(?:st|nd|rd|th)?\b', low
        )
        if month_match:
            month_names = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]
            mon_abbr = month_match.group(1)[:3]
            mon_num  = month_names.index(mon_abbr) + 1
            day_num  = int(month_match.group(2))
            year     = today.year
            try:
                candidate = date(year, mon_num, day_num)
                if candidate < today:
                    candidate = date(year+1, mon_num, day_num)
                event_date = candidate.isoformat()
            except ValueError:
                pass

    # ── Time parsing ─────────────────────────────────────────────────────────
    event_time = ""
    time_match = re.search(r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b', low)
    if time_match:
        h, m, meridiem = int(time_match.group(1)), int(time_match.group(2) or 0), time_match.group(3)
        if meridiem == "pm" and h != 12: h += 12
        if meridiem == "am" and h == 12: h = 0
        event_time = f"{h:02d}:{m:02d}"

    # ── Build reminder_at (15 min before event, or at event time) ────────────
    reminder_at = ""
    if event_time:
        from datetime import datetime as dt
        try:
            ev_dt = dt.fromisoformat(f"{event_date}T{event_time}:00")
            from datetime import timedelta as td
            remind_dt = ev_dt - td(minutes=15)
            reminder_at = remind_dt.isoformat(timespec="seconds")
        except Exception:
            pass
    else:
        # No time given — remind at 9 AM that day
        reminder_at = f"{event_date}T09:00:00"

    # ── Extract title ─────────────────────────────────────────────────────────
    # Strip trigger words and date/time tokens to get the core title
    title = text.strip()
    for phrase in ["remind me", "reminder:", "reminder", "add to calendar:", "add to calendar",
                   "set a reminder", "schedule", "don't let me forget", "note for", "add event",
                   "put on my calendar", "put on calendar"]:
        title = re.sub(re.escape(phrase), "", title, flags=re.IGNORECASE).strip()

    # Remove date/time phrases
    title = re.sub(
        r'\b(today|tonight|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|'
        r'jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|'
        r'aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b[.\s]*\d{0,2}(?:st|nd|rd|th)?',
        "", title, flags=re.IGNORECASE
    )
    title = re.sub(r'\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b', "", title, flags=re.IGNORECASE)
    title = re.sub(r'\b(at|on|to|for|:)\b', "", title, flags=re.IGNORECASE)
    title = re.sub(r'\s{2,}', " ", title).strip(" ,-:")

    if not title:
        title = "Reminder"

    return {
        "title":       title,
        "event_date":  event_date,
        "event_time":  event_time,
        "reminder_at": reminder_at,
        "source":      "rexxie",
    }


def _create_rex_event(event: dict) -> Optional[str]:
    """POST to REX backend to save the event. Returns the event ID or None."""
    payload = json.dumps(event).encode()
    req = urllib.request.Request(
        f"{REX_BASE_URL}/api/chairman/events",
        data=payload, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return result.get("id")
    except Exception as e:
        logger.error(f"Event create failed: {e}")
        return None


def _extract_pdf_to_paperless(email_meta: dict) -> str:
    """
    Trigger PDF extraction from Gmail email to Paperless-ngx.
    email_meta: { gmail_id, subject, sender, pdf_names }
    Calls the REX backend endpoint which handles Gmail → Paperless pipeline.
    """
    payload = json.dumps(email_meta).encode()
    req = urllib.request.Request(
        f"{REX_BASE_URL}/api/chairman/extract-pdf",
        data=payload, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            count = result.get("extracted", 0)
            names = result.get("files", [])
            if count:
                files_str = "\n  • ".join(names)
                return (
                    f"🐢 ✅ Extracted {count} PDF(s) to Paperless:\n  • {files_str}\n\n"
                    f"They'll appear in your Paperless inbox shortly."
                )
            else:
                return "🐢 Extraction attempted but no files were saved. Check Paperless logs."
    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
        return "🐢 Couldn't reach the extraction service — REX may be offline."


def _call_rexxie(message: str, session_id: str = None,
                 history: list = None, system_prompt: str = None,
                 prefer_ollama: bool = False) -> str:
    """
    Call Rexxie.

    v3.0 — Ollama merge: if OLLAMA_ENABLED=1 and Ollama is running and
    prefer_ollama=True, routes to local Ollama model instead of REX API.
    GOJ operational commands always use the REX API regardless of this flag.
    Falls back to REX API if Ollama is unavailable or returns empty.

    GOJ v1.7 — Conversation memory:
    'history' is a list of prior {"role": "user"/"assistant", "content": "..."}
    entries. The backend builds these into a proper multi-turn messages array
    so Rexxie maintains coherence across the conversation. Without history,
    each message is single-turn (the old behaviour).
    """
    # v3.0 Ollama fork — personal/reflective responses ONLY.
    # SAFETY GUARD: Ollama is only used for explicitly personal/reflective messages.
    # It is NEVER used for: GOJ operational commands, TOTP-gated content,
    # PHI-adjacent queries, or anything that went through the GOJ routing logic.
    # If prefer_ollama is not explicitly set by the caller, this block is skipped.
    if prefer_ollama and _ollama_is_available():
        # Double-check: do not use Ollama for anything that looks operational
        _goj_keywords = ("client", "attendance", "menu", "auth", "staff", "schedule",
                          "roster", "ocr", "sign.in", "drive", "route", "shift")
        _msg_lower = message.lower()
        _is_operational = any(kw in _msg_lower for kw in _goj_keywords)
        if _is_operational:
            logger.debug("[rexxie] Ollama skipped — operational message detected, using REX API")
        else:
            ollama_reply = _call_ollama(
                message,
                system=system_prompt or "You are Rexxie, Kato's personal AI confidant at Garden of Joy. Be warm, direct, and concise."
            )
            if ollama_reply:
                logger.info("[rexxie] response via Ollama (local LLM)")
                # Still save to session history even via Ollama
                return ollama_reply
            logger.debug("[rexxie] Ollama returned empty — falling back to REX API")

    payload = {
        "message":        message,
        "user_name":      "kato",
        "user_role":      "chairman",
        "dashboard_mode": False,
    }
    if session_id:
        payload["session_id"] = session_id
    if history:
        payload["history"] = history[-10:]   # cap at 10 entries
    if system_prompt:
        payload["system_prompt"] = system_prompt   # planner override

    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        f"{REX_BASE_URL}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read())
            return result.get("reply", "_(Rexxie didn't respond — try again)_")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.error(f"REX HTTP {e.code}: {body[:200]}")
        return "🐢 Something's off with my connection. Is REX running?"
    except Exception as e:
        logger.error(f"REX connection error: {e}")
        return "🐢 I can't reach my brain right now — is REX running on your Mac?"


# ── Cloud provider gate ────────────────────────────────────────────────────────
# Cloud providers are locked by default. Kato must say an approval phrase.
# Only the exact question is sent — no history, no GOJ context, one-use only.

_CLOUD_APPROVAL_PHRASES = {
    "use claude for this":  "anthropic",
    "ask claude":           "anthropic",
    "claude:":              "anthropic",
    "use gpt for this":     "openai",
    "ask gpt":              "openai",
    "ask chatgpt":          "openai",
    "gpt:":                 "openai",
    "use gemini for this":  "google",
    "ask gemini":           "google",
    "gemini:":              "google",
    "use grok":             "xai",
    "ask grok":             "xai",
    "cloud:":               "anthropic",
    "cloud assist:":        "anthropic",
}

def _load_cloud_key(provider: str) -> str:
    """Load API key for cloud provider: .env first, then keyring fallback."""
    env_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai":    "OPENAI_API_KEY",
        "google":    "GEMINI_API_KEY",
        "xai":       "XAI_API_KEY",
    }
    env_key = env_map.get(provider, "")
    # Check environment first
    val = os.environ.get(env_key, "").strip()
    if val:
        return val
    # Try .env file
    env_path = Path.home() / "Desktop" / "REX" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith(f"{env_key}="):
                val = line.split("=", 1)[1].strip().strip("'\"")
                if val:
                    return val
    # Try macOS Keychain via keyring
    try:
        import keyring as _kr
        kr_map = {
            "anthropic": "rex_anthropic_api_key",
            "openai":    "rex_openai_api_key",
            "google":    "rex_gemini_api_key",
            "xai":       "rex_xai_api_key",
        }
        val = _kr.get_password("REX", kr_map.get(provider, "")) or ""
        return val.strip()
    except Exception:
        return ""


def _isolated_cloud_call(question: str, provider: str = "anthropic") -> str:
    """
    Make a single isolated call to a cloud provider.
    ONLY the question is sent — zero history, zero GOJ context, zero PHI.
    """
    api_key = _load_cloud_key(provider)
    if not api_key:
        return (
            f"⚠️ No API key found for {provider.title()}.\n"
            f"Run RESTORE_ENV.command or paste the key in your .env file."
        )

    logger.info(f"[cloud_gate] Approved one-shot call → {provider} (question only, no history)")

    try:
        if provider == "anthropic":
            import anthropic as _anth
            client = _anth.Anthropic(api_key=api_key)
            msg = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=1024,
                messages=[{"role": "user", "content": question}],
            )
            return msg.content[0].text

        elif provider == "openai":
            import openai as _oai
            client = _oai.OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": question}],
                max_tokens=1024,
            )
            return resp.choices[0].message.content

        elif provider == "google":
            import google.generativeai as _genai
            _genai.configure(api_key=api_key)
            model = _genai.GenerativeModel("gemini-2.0-flash")
            resp = model.generate_content(question)
            return resp.text

        elif provider == "xai":
            import openai as _oai  # xAI uses OpenAI-compatible API
            client = _oai.OpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
            resp = client.chat.completions.create(
                model="grok-3-fast",
                messages=[{"role": "user", "content": question}],
                max_tokens=1024,
            )
            return resp.choices[0].message.content

        else:
            return f"Provider '{provider}' not yet supported for isolated calls."

    except Exception as e:
        logger.error(f"[cloud_gate] Cloud call failed ({provider}): {e}")
        return f"☁️ Cloud call failed: {e}"


def _parse_cloud_request(text: str):
    """
    Detect if text starts with a cloud approval phrase.
    Returns (question, provider) or (None, None).
    """
    lower = text.lower().strip()
    for phrase, provider in _CLOUD_APPROVAL_PHRASES.items():
        if lower.startswith(phrase):
            question = text[len(phrase):].lstrip(": \n").strip()
            return (question or None, provider)
    return (None, None)


class RexxieTelegramBot:
    """
    Private Telegram bot — only Kato can use it.
    All messages go to REX in Rexxie mode with chairman access.
    """

    def __init__(self):
        cfg = _load_config()
        self.token: str         = cfg.get("bot_token", "")
        self.owner_chat_id: Optional[int] = cfg.get(OWNER_CHAT_ID_KEY)
        self._offset: int       = 0
        self._consecutive_409: int = 0  # track consecutive 409 errors for auto-recovery
        self._session_id: str   = str(uuid.uuid4())   # One persistent session per bot run
        self._rexxie_activated  = False
        self._is_setup_pending  = not self.owner_chat_id
        # GOJ v1.2 — inline keyboard state (keyed by short UUID, in-memory)
        self._pending_absence_data: dict = {}
        # GOJ v1.8 — pending doc classification sub-type input (keyed by chat_id str)
        # Populated when Kato selects client_paperwork / staff_files / misc and we await name
        self._pending_classify_subtype: dict = {}
        self._pending_classify_instruction: dict = {}  # GOJ v1.9 — custom prompt after type selection
        self._friday_blast_sent_date: Optional[str] = None
        self._has_greeted_this_session: bool = False   # GOJ v1.4 — session greeting
        # GOJ v1.7 — Conversation memory (ChatGPT handoff alignment)
        # Keeps rolling per-chat history so Rexxie remembers within a conversation.
        # Format: {chat_id: [{"role": "user"/"assistant", "content": "..."}]}
        # Capped at _MAX_HISTORY entries. Cleared on bot restart (session boundary).
        self._chat_history: dict = {}
        self._MAX_HISTORY: int   = 10   # 5 exchanges

        # ── v2.0 Growth loop systems ──────────────────────────────────────────
        # Lazy-initialized per chat_id on first message
        self._user_models: dict       = {}   # chat_id → UserModel
        self._reflections: dict       = {}   # chat_id → Reflection
        self._exchange_counts: dict   = {}   # chat_id → int
        self._REFLECT_EVERY: int      = 20   # Run reflection every N messages
        self._priority_memories: dict = {}   # chat_id → PriorityMemory

        # ── v2.2 TOTP 2FA gate ────────────────────────────────────────────────
        self._tfa: Optional[object]  = None   # TwoFactorAuth, lazy-initialized
        # Pending TOTP challenges: {chat_id: {"action": str, "expires": float}}
        # action: "auth"     → /auth report pending TOTP
        #         "vault"    → vault unlock pending TOTP (passphrase already checked)
        #         "sensitive"→ never_share data disclosure pending TOTP
        self._totp_pending: dict     = {}     # cleared on verification or expiry

        # Initialize shared singleton systems
        global _POLICY_ENFORCER, _PLANNER
        if _POLICY_AVAILABLE and _POLICY_ENFORCER is None:
            try:
                from pathlib import Path as _Path
                _rules = _Path(__file__).parent / "rex_policy_rules.json"
                _POLICY_ENFORCER = _PolicyEnforcer(_rules)
                logger.info("[rexxie] PolicyEnforcer loaded.")
            except Exception as _e:
                logger.warning(f"[rexxie] PolicyEnforcer init failed: {_e}")
        if _PLANNER_AVAILABLE and _PLANNER is None:
            try:
                _PLANNER = _RexPlanner()
                logger.info("[rexxie] Planner loaded.")
            except Exception as _e:
                logger.warning(f"[rexxie] Planner init failed: {_e}")

    def _is_owner(self, chat_id: int) -> bool:
        return self.owner_chat_id is not None and chat_id == self.owner_chat_id

    def _activate_rexxie_if_needed(self) -> bool:
        """Send 'hey rexxie' to REX once per bot session to activate Rexxie mode.
        Only fires on the first call — repeated calls are a no-op to prevent
        'Kato said: hey rexxie' from spamming Rexxie's memory DB.
        """
        if self._rexxie_activated:
            return True
        _call_rexxie("hey rexxie", session_id=self._session_id)
        self._rexxie_activated = True
        return True

    def _get_user_model(self, chat_id: int):
        """Get or lazily create a UserModel for this chat."""
        if not _USER_MODEL_AVAILABLE:
            return None
        if chat_id not in self._user_models:
            try:
                db = Path(__file__).parent / "rexxie_memory.db"
                self._user_models[chat_id] = _UserModel(db_path=db, chat_id=chat_id)
            except Exception as e:
                logger.warning(f"[rexxie] UserModel init failed: {e}")
                return None
        return self._user_models.get(chat_id)

    def _get_reflection(self, chat_id: int):
        """Get or lazily create a Reflection engine for this chat."""
        if not _REFLECTION_AVAILABLE:
            return None
        if chat_id not in self._reflections:
            try:
                db = Path(__file__).parent / "rexxie_memory.db"
                um = self._get_user_model(chat_id)
                self._reflections[chat_id] = _Reflection(db_path=db, chat_id=chat_id, user_model=um)
            except Exception as e:
                logger.warning(f"[rexxie] Reflection init failed: {e}")
                return None
        return self._reflections.get(chat_id)

    def _get_priority_memory(self, chat_id: int):
        """Get or lazily create a PriorityMemory for this chat."""
        if not _PRIORITY_MEMORY_AVAILABLE:
            return None
        if chat_id not in self._priority_memories:
            try:
                # rexxie_ideas table lives in GOJ_AUTH_DB (auth_tracker.db)
                db = GOJ_AUTH_DB
                self._priority_memories[chat_id] = _PriorityMemory(db_path=str(db))
            except Exception as e:
                logger.warning(f"[rexxie] PriorityMemory init failed: {e}")
                return None
        return self._priority_memories.get(chat_id)

    def _get_tfa(self):
        """Lazy-initialize and return TwoFactorAuth instance. Returns None if unavailable."""
        if not _2FA_AVAILABLE:
            return None
        if self._tfa is None:
            try:
                self._tfa = _TwoFactorAuth()
                logger.info("[rexxie] TwoFactorAuth initialized")
            except Exception as e:
                logger.warning(f"[rexxie] TwoFactorAuth init failed: {e}")
                return None
        return self._tfa

    def _totp_challenge(self, chat_id: int, action: str, prompt: str, **kwargs) -> None:
        """
        Issue a TOTP challenge to the owner.
        Stores the pending action so the next 6-digit message resolves it.
        kwargs are stored alongside action for resolution (e.g. vault passphrase).
        """
        self._totp_pending[chat_id] = {
            "action":  action,
            "expires": time.time() + 120,   # 2-minute window
            **kwargs,
        }
        _send_message(self.token, chat_id, prompt)

    def _totp_resolve(self, chat_id: int, code: str) -> bool:
        """
        Verify a TOTP code and execute the pending action.
        Returns True if the code was valid and action executed.
        Returns False if code invalid, expired, or no pending action.
        """
        pending = self._totp_pending.get(chat_id)
        if not pending:
            return False

        # Check expiry
        if time.time() > pending["expires"]:
            del self._totp_pending[chat_id]
            _send_message(self.token, chat_id,
                          "⏱ Code timed out (2-minute window). Try the command again.")
            return True   # Consumed the message

        # Verify the code
        if not (_verify_totp and _verify_totp(code)):
            del self._totp_pending[chat_id]
            _send_message(self.token, chat_id,
                          "❌ Wrong code — access denied. Try the command again.")
            return True   # Consumed (wrong code)

        # ── Code valid — execute pending action ───────────────────────────────
        action = pending["action"]
        del self._totp_pending[chat_id]

        if action == "auth":
            # /auth moved to REX business bot — this action should not be triggered
            # in Rexxie, but handle gracefully if somehow pending
            _send_message(self.token, chat_id,
                "✅ *Verified.* Authorization reports are handled by the REX bot.")

        elif action == "vault":
            passphrase = pending.get("passphrase", "")
            vault = _get_vault()
            if vault and passphrase:
                ok, msg = vault.unlock(passphrase)
                if ok:
                    _send_message(self.token, chat_id,
                                  "✅ *Vault unlocked.* Both factors verified.\n"
                                  "_Auto-locks after 15 minutes._")
                else:
                    _send_message(self.token, chat_id, f"🔒 {msg}")
            else:
                _send_message(self.token, chat_id,
                              "✅ *TOTP verified.* Vault passphrase required to complete unlock.")

        elif action == "sensitive":
            # Generic never_share gate — just confirm access
            _send_message(self.token, chat_id,
                          "✅ *Verified.* You may now request the sensitive information.")

        else:
            logger.warning(f"[rexxie] Unknown TOTP pending action: {action!r}")

        return True   # Consumed

    def _handle_update(self, update: dict):
        # GOJ v1.2 — Handle inline keyboard callback queries before anything else
        cq = update.get("callback_query")
        if cq:
            self._handle_callback_query(cq)
            return

        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return

        chat_id = msg["chat"]["id"]
        text    = (msg.get("text") or "").strip()

        # GOJ v1.6 — Handle incoming document / photo files
        if not text:
            doc   = msg.get("document")
            photo = msg.get("photo")
            if doc or photo:
                if self._is_owner(chat_id):
                    self._handle_incoming_file(chat_id, msg)
            return

        # ── GOJ v1.8 — Intercept sub-type answer for pending doc classification ──
        # Must happen before all other handlers so it doesn't get swallowed by AI
        pending_classify = self._pending_classify_subtype.get(str(chat_id))
        if pending_classify and text:
            key      = pending_classify["key"]
            doc_type = pending_classify["doc_type"]
            filename = pending_classify["filename"]
            sub_type = text.strip()

            entry = _load_pending_doc(key)
            if entry:
                self._pending_classify_subtype.pop(str(chat_id), None)
                self._finalize_classification(
                    chat_id, key, entry["file_path"], filename, doc_type, sub_type
                )
            else:
                self._pending_classify_subtype.pop(str(chat_id), None)
                _send_message(self.token, chat_id,
                    "⚠️ The document session expired — please re-submit the file.")
            return

        # ── GOJ v1.9 — Intercept custom instruction for pending doc ─────────────
        pending_instruction = self._pending_classify_instruction.get(str(chat_id))
        if pending_instruction and text:
            key       = pending_instruction["key"]
            doc_type  = pending_instruction["doc_type"]
            filename  = pending_instruction["filename"]
            file_path = pending_instruction["file_path"]
            instruction = text.strip()
            self._pending_classify_instruction.pop(str(chat_id), None)
            # Finalize with the instruction stored as sub_type so it's saved and logged
            self._finalize_classification(
                chat_id, key, file_path, filename, doc_type,
                sub_type=instruction
            )
            return

        # ── Only owner can use this bot — silently ignore others ─────────────
        if not self._is_owner(chat_id) and not self._is_setup_pending:
            logger.warning(f"Unauthorized access attempt from chat_id={chat_id} — silently ignored")
            return   # Do NOT reply — don't reveal bot exists

        # ── Owner registration (/start during setup) ──────────────────────────
        if text == "/start":
            if self._is_setup_pending:
                self.owner_chat_id   = chat_id
                self._is_setup_pending = False
                cfg = _load_config()
                cfg[OWNER_CHAT_ID_KEY] = chat_id
                _save_config(cfg)
                logger.info(f"✅ Rexxie owner locked: chat_id={chat_id}")
                # Activate Rexxie mode silently, then send welcome
                self._activate_rexxie_if_needed()
                _send_message(self.token, chat_id, REXXIE_WELCOME)
            else:
                # Already set up — send returning greeting
                self._activate_rexxie_if_needed()
                _send_message(self.token, chat_id, REXXIE_RETURNING)
            return

        # ── Owner not registered yet — prompt setup ───────────────────────────
        if self._is_setup_pending:
            _send_message(
                self.token, chat_id,
                "🐢 Send /start to introduce yourself.",
            )
            return

        # ── V4 Security Override (intercepted BEFORE AI — Chairman only) ──────
        lower = text.lower().strip()
        if lower.startswith("override "):
            try:
                import sys as _sys
                from pathlib import Path as _Path
                _rex_root = str(_Path(__file__).resolve().parent)
                if _rex_root not in _sys.path:
                    _sys.path.insert(0, _rex_root)
                from rex_override import handle_override_command
                _ov_reply = handle_override_command(text, chat_id)
                _send_message(self.token, chat_id, _ov_reply)
            except Exception as _ov_err:
                _send_message(self.token, chat_id,
                    f"⚠️ Override system not available: {_ov_err}")
            return

        # ── Credential vault commands (intercepted BEFORE AI — never sent to API) ─
        vault = _get_vault()

        # Remote wipe commands — highest priority
        if lower in ("rexxie wipe credentials", "wipe my credentials", "wipe credentials"):
            if vault:
                reply = vault.wipe_credentials_only()
            else:
                reply = "🐢 Vault not available."
            _send_message(self.token, chat_id, reply)
            return

        if lower in ("rexxie emergency wipe", "emergency wipe", "wipe everything rexxie"):
            _send_message(
                self.token, chat_id,
                "⚠️ *Emergency Wipe*\n\nThis will permanently destroy ALL Rexxie data — "
                "memories, credentials, everything. Irreversible.\n\n"
                "Reply with exactly: `CONFIRM WIPE` to proceed.",
            )
            self._pending_wipe = True
            return

        if getattr(self, "_pending_wipe", False) and lower == "confirm wipe":
            self._pending_wipe = False
            if vault:
                reply = vault.emergency_wipe()
            else:
                reply = "🐢 Vault not initialized — nothing to wipe."
            _send_message(self.token, chat_id, reply)
            return

        if getattr(self, "_pending_wipe", False):
            self._pending_wipe = False
            _send_message(self.token, chat_id, "🐢 Wipe cancelled.")
            return

        # Credential vault commands (unlock, lock, store, retrieve) — local only, never goes to AI
        # detect_credential_command() handles unlock, lock, store, retrieve, and list in one pass.
        if vault:
            cred_reply = vault.detect_credential_command(text)
            if cred_reply:
                _send_message(self.token, chat_id, cred_reply)
                return

        # ── MENU BLAST → moved to REX business bot ───────────────────────────
        if lower == "menu blast":
            _send_message(self.token, chat_id,
                "🐢 Menu blast is handled by the REX business bot — send it there.\n"
                "This keeps Vlad and Misha out of our private space.")
            return

        # ── Sign-in intake, OCR → moved to REX business bot ─────────────────
        if lower in ("process signins", "intake signins", "run intake",
                     "signin intake", "process signin", "intake signin",
                     "menu ocr", "run ocr", "ocr menus", "/menu",
                     "menu flags", "ocr flags", "flags"):
            _send_message(self.token, chat_id,
                "🐢 That's an operational command — use the REX bot for that.\n"
                "This is our personal space.")
            return

        # ── GOJ v1.7 — BUILD COORDINATOR / MASTER LIST commands ──────────────
        if lower in ("/build", "build status", "master list", "what's the plan", "whats the plan", "the plan"):
            _send_typing(self.token, chat_id)
            if _COORDINATOR_AVAILABLE:
                _send_message(self.token, chat_id, _coordinator.build_status_summary())
            else:
                _send_message(self.token, chat_id, "⚠ Coordinator not available — check rex_coordinator.py")
            return

        if lower in ("/todo", "what needs work", "what's missing", "whats missing", "build todo"):
            _send_typing(self.token, chat_id)
            if _COORDINATOR_AVAILABLE:
                _send_message(self.token, chat_id, _coordinator.what_needs_work())
            else:
                _send_message(self.token, chat_id, "⚠ Coordinator not available.")
            return

        # ── GOJ v1.7 — IDEA / DECISION LOG commands ───────────────────────────
        if lower in ("/ideas", "my ideas", "show ideas", "idea log"):
            _send_typing(self.token, chat_id)
            _send_message(self.token, chat_id, _get_ideas_report())
            return

        if lower in ("/decisions", "my decisions", "decisions"):
            _send_typing(self.token, chat_id)
            _send_message(self.token, chat_id, _get_ideas_report(idea_type="decision"))
            return

        if lower in ("/questions", "open questions", "my questions"):
            _send_typing(self.token, chat_id)
            _send_message(self.token, chat_id, _get_ideas_report(idea_type="question"))
            return

        # ── /status, /auth, /queue, /tasks, /done, OCR, /edit → REX bot ────
        if (lower in ("/status", "/auth", "/queue", "/tasks",
                      "ocr mute", "mute ocr", "/ocr mute", "/mute ocr",
                      "ocr unmute", "unmute ocr", "/ocr unmute", "/unmute ocr")
                or lower.startswith("/done")
                or lower.startswith("/edit")):
            _send_message(self.token, chat_id,
                "🐢 That's a business command — use the REX bot for that.\n"
                "I'm your personal space. What's on your mind?")
            return


        # ── v2.2 — TOTP 2FA gate ─────────────────────────────────────────────

        # Resolve pending TOTP challenge if user sends a 6-digit code
        if text.strip().isdigit() and len(text.strip()) == 6 and chat_id in self._totp_pending:
            if self._totp_resolve(chat_id, text.strip()):
                return

        # 2FA management commands (setup, confirm, disable, status, touch id)
        tfa = self._get_tfa()
        if tfa is not None:
            tfa_reply = tfa.detect_2fa_command(text)
            if tfa_reply:
                _send_message(self.token, chat_id, tfa_reply)
                return

            # Vault unlock via 2FA flow
            if _unlock_vault_with_2fa is not None:
                vault = _get_vault()
                if vault is not None:
                    vault_reply = _unlock_vault_with_2fa(vault, tfa, text)
                    if vault_reply:
                        _send_message(self.token, chat_id, vault_reply)
                        return

        # ── Absence detection → moved to REX business bot ────────────────────
        # (Rexxie is personal only — operational reports go through REX bot)

        # ── Calendar / reminder intercept (BEFORE routing to AI) ─────────────
        event = _parse_event(text)
        if event:
            event_id = _create_rex_event(event)
            if event_id:
                reply_lines = [f"🐢 Got it. Added to your calendar:\n📅 <b>{event['title']}</b> on {event['event_date']}"]
                if event.get("event_time"):
                    h, m = map(int, event["event_time"].split(":"))
                    suffix = "AM" if h < 12 else "PM"
                    h12 = h if 1 <= h <= 12 else (12 if h == 0 else h - 12)
                    reply_lines.append(f"🕐 {h12}:{m:02d} {suffix}")
                if event.get("reminder_at"):
                    reply_lines.append("🔔 I'll remind you 15 minutes before.")
                if event.get("notes"):
                    reply_lines.append(f"\n📝 {event['notes']}")
                _send_message(self.token, chat_id, "\n".join(reply_lines))
            else:
                _send_message(self.token, chat_id, "🐢 I couldn't save that to the calendar — REX might be offline. Try again in a moment.")
            return

        # ── Email PDF extraction responses (yes/no confirmations) ────────────
        pending_pdf = getattr(self, "_pending_pdf_email", None)
        if pending_pdf and lower in ("yes", "y", "yes please", "extract", "extract it", "extract them"):
            self._pending_pdf_email = None
            result = _extract_pdf_to_paperless(pending_pdf)
            _send_message(self.token, chat_id, result)
            return
        if pending_pdf and lower in ("no", "n", "no thanks", "skip", "ignore"):
            self._pending_pdf_email = None
            _send_message(self.token, chat_id, "🐢 Got it — skipped. I'll flag it in your 9 PM report if it looks important.")
            return

        # ══════════════════════════════════════════════════════════════════════
        # v2.0 GROWTH LOOP — All normal messages route through here
        # ══════════════════════════════════════════════════════════════════════
        self._activate_rexxie_if_needed()

        # ── Session greeting (first message per restart) ───────────────────
        if not self._has_greeted_this_session:
            self._has_greeted_this_session = True
            greeting = _build_session_greeting()
            _send_message(self.token, chat_id, greeting)

        # ── Step 1: Get growth systems for this chat ───────────────────────
        um = self._get_user_model(chat_id)
        rf = self._get_reflection(chat_id)
        pm = self._get_priority_memory(chat_id)

        # ── Step 2: Signal detection — how did the last response land? ─────
        if rf is not None:
            incoming_signal = rf.process_incoming_signal(text)
            if incoming_signal in ("negative", "correction"):
                logger.info(f"[rexxie] chat={chat_id} response signal: {incoming_signal}")

        # ── Step 3: Policy check — INBOUND ────────────────────────────────
        _emergency_prefix = ""
        if _POLICY_ENFORCER is not None:
            _inbound = _POLICY_ENFORCER.check_inbound(text, chat_id=chat_id)
            if _inbound.blocked:
                _send_message(self.token, chat_id, _inbound.response)
                return
            _emergency_prefix = _POLICY_ENFORCER.get_emergency_prepend(_inbound)

        # ── Step 3.5: Cloud provider gate ─────────────────────────────────
        # Cloud AI is locked by default. Kato must explicitly say an approval
        # phrase. Only the bare question is sent — no history, no GOJ context.
        _cloud_question, _cloud_provider = _parse_cloud_request(text)
        if _cloud_question:
            _send_typing(self.token, chat_id)
            logger.info(f"[cloud_gate] Kato approved one-shot {_cloud_provider} call")
            _cloud_reply = _isolated_cloud_call(_cloud_question, _cloud_provider)
            _tagged = (
                f"☁️ *{_cloud_provider.title()} response* "
                f"_(isolated — only your question was sent, no history or GOJ data)_\n\n"
                f"{_cloud_reply}"
            )
            _send_message(self.token, chat_id, _tagged)
            return  # Never continues to normal local flow

        # ── Step 4: Auto-extract user model signals ────────────────────────
        if um is not None:
            try:
                um.extract_and_store(text, source="observed")
            except Exception as _e:
                logger.debug(f"[rexxie] user model extract error: {_e}")

        # ── Step 5: Detect & save structured memory (ideas/decisions/etc.) ─
        structured_items = _detect_structured_memory(text)
        for item in structured_items:
            _save_idea(item["type"], item["content"], source="user")

        _send_typing(self.token, chat_id)

        # ── Step 6: Retrieve prioritized memory ───────────────────────────
        mem_context = ""
        try:
            if pm is not None:
                memories = pm.retrieve(text, limit=4)
                if memories:
                    mem_context = _format_memory_context(memories)
            else:
                raw_mem = _retrieve_relevant_memory(text)
                if raw_mem:
                    mem_context = raw_mem
        except Exception as _e:
            logger.debug(f"[rexxie] memory retrieval error: {_e}")
            mem_context = _retrieve_relevant_memory(text) or ""

        # ── Step 7: Build person context block ────────────────────────────
        person_context = ""
        if um is not None:
            try:
                person_context = um.build_context_block(max_items_per_category=2)
            except Exception as _e:
                logger.debug(f"[rexxie] person context error: {_e}")

        # ── Step 8: Get reflection strategy hint ──────────────────────────
        strategy_hint = ""
        if rf is not None and _PLANNER is not None:
            try:
                _pre_intent, _, _ = _PLANNER.classify(text)
                strategy_hint = rf.get_strategy_hint(_pre_intent.value) or ""
            except Exception:
                pass

        # ── Step 9: Plan the request ──────────────────────────────────────
        full_context = "\n".join(filter(None, [person_context, mem_context, strategy_hint]))

        # ── TRANSPARENCY PRINCIPLE (non-negotiable) ───────────────────────
        # Kato requires complete honesty. Never withhold information, hide
        # context, soften bad news to the point of distortion, or pretend
        # uncertainty you don't have. If you don't know something, say so.
        # If something is wrong, say it plainly. One lie ends the relationship.
        _TRANSPARENCY_BLOCK = (
            "\n\nCORE RULE — TRANSPARENCY:\n"
            "You owe Kato complete honesty at all times. Never hide information, "
            "soften facts to the point of distortion, or omit context he would want. "
            "If something is wrong, say it plainly. If you don't know, say so. "
            "Being caught in a lie or withholding — even once — permanently "
            "breaks this relationship. Honesty is more important than comfort."
        )

        _LANGUAGE_BLOCK = (
            "\n\nLANGUAGE:\n"
            "You speak English, Russian (Русский), and Ukrainian (Українська) fluently. "
            "Always reply in the same language Kato writes in. "
            "If he writes in Russian or Ukrainian, respond naturally in that language."
        )
        system_prompt_override = _TRANSPARENCY_BLOCK + _LANGUAGE_BLOCK
        _plan = None
        if _PLANNER is not None:
            try:
                _plan = _PLANNER.plan(text, chat_id=chat_id, memory_context=full_context)
                enriched_text         = _plan.user_message
                system_prompt_override = _plan.system_prompt
                # Adapt system prompt to support style
                if um is not None:
                    _style = um.get_support_style()
                    if _style == "brief":
                        system_prompt_override += "\n\nStyle: Keep replies SHORT — 1-2 sentences. This person prefers concise answers."
                    elif _style == "direct":
                        system_prompt_override += "\n\nStyle: Be DIRECT. Answer first, explain after only if needed."
                    elif _style == "gentle":
                        system_prompt_override += "\n\nStyle: Be WARM and supportive. Acknowledge feelings before solutions."
            except Exception as _e:
                logger.debug(f"[rexxie] planner error: {_e}")
                enriched_text = (full_context + "\n" + text).strip() if full_context else text
        else:
            enriched_text = (full_context + "\n" + text).strip() if full_context else text

        # ── Step 9.5: Compute answer confidence and inject into system prompt ──
        # Computes the EXACT % before Rexxie answers — she uses this number,
        # she does not guess. Score rises naturally as memories are recalled more.
        try:
            if _ANSWER_CONFIDENCE_AVAILABLE:
                global _answer_confidence_engine
                if _answer_confidence_engine is None:
                    _master_list = Path(__file__).parent / "master_list.json"
                    _answer_confidence_engine = _AnswerConfidence(master_list_path=_master_list)

                # Use memories already retrieved in Step 6
                _ac_memories = memories if 'memories' in dir() and memories else []
                _ac_result   = _answer_confidence_engine.compute(
                    memories = _ac_memories,
                    question = text,
                )

                if system_prompt_override:
                    system_prompt_override += _ac_result.prompt_block
                else:
                    system_prompt_override = _ac_result.prompt_block

                logger.debug(f"[rexxie] answer_confidence: {_ac_result.summary}")
        except Exception as _ace:
            logger.debug(f"[rexxie] answer_confidence error: {_ace}")

        # ── Step 10: Load conversation history ────────────────────────────
        history = self._chat_history.get(chat_id, [])

        # ── Step 11: Call Rexxie ──────────────────────────────────────────
        raw_reply = _call_rexxie(
            enriched_text,
            session_id=self._session_id,
            history=history if history else None,
            system_prompt=system_prompt_override,
        )

        # ── Step 12: Save exchange to history ─────────────────────────────
        history = (history + [
            {"role": "user",      "content": text},
            {"role": "assistant", "content": raw_reply},
        ])[-self._MAX_HISTORY:]
        self._chat_history[chat_id] = history

        # ── Step 13: Policy check — OUTBOUND ──────────────────────────────
        final_reply = raw_reply
        # Owner (Kato) bypasses outbound PHI check so scan/OCR results always reach her
        if _POLICY_ENFORCER is not None and chat_id != 5587703834:
            try:
                _outbound = _POLICY_ENFORCER.check_outbound(raw_reply, text)
                if _outbound.blocked:
                    final_reply = _outbound.response
                elif _outbound.modified:
                    final_reply = _outbound.clean_text
            except Exception as _e:
                logger.debug(f"[rexxie] outbound policy error: {_e}")

        # ── Step 14: Humanize ─────────────────────────────────────────────
        if _HUMANIZE_AVAILABLE:
            try:
                final_reply = _humanize(final_reply)
            except Exception as _e:
                logger.debug(f"[rexxie] humanize error: {_e}")

        # ── Step 15: Emergency prefix ─────────────────────────────────────
        if _emergency_prefix:
            final_reply = _emergency_prefix + final_reply

        # ── Step 16: Task commitment detection (GOJ v1.4) ─────────────────
        commitments = _detect_commitment(final_reply)
        for commitment in commitments:
            _save_task_commitment(commitment)
            logger.info(f"Task commitment logged: {commitment[:80]}")

        # ── Step 17: Send ─────────────────────────────────────────────────
        # Only show task footer when user is explicitly asking about tasks/status.
        # Appending it to every reply (e.g. "how are you") is noisy and wrong.
        _task_keywords = ("task", "to-do", "todo", "pending", "status", "what's on",
                          "what is on", "my list", "checklist", "follow up", "follow-up")
        _show_footer = any(kw in text.lower() for kw in _task_keywords)
        footer = _get_task_footer() if _show_footer else ""
        _send_message(self.token, chat_id, final_reply + footer)
        logger.info(f"Rexxie: [{text[:60]}...] → [{final_reply[:60]}...]")

        # ── Step 18: Log exchange for reflection ──────────────────────────
        if rf is not None and _plan is not None:
            try:
                _style = um.get_support_style() if um else "standard"
                rf.log_exchange(
                    intent         = _plan.intent.value,
                    user_message   = text,
                    response       = final_reply,
                    response_style = _style,
                )
            except Exception as _e:
                logger.debug(f"[rexxie] exchange log error: {_e}")

        # ── Step 19: Periodic reflection (every N messages) ───────────────
        self._exchange_counts[chat_id] = self._exchange_counts.get(chat_id, 0) + 1
        if rf is not None and self._exchange_counts[chat_id] % self._REFLECT_EVERY == 0:
            try:
                insights = rf.reflect()
                if insights:
                    logger.info(f"[rexxie] Reflection chat={chat_id}: {len(insights)} insights")
            except Exception as _e:
                logger.debug(f"[rexxie] reflection error: {_e}")
        # ══════════════════════════════════════════════════════════════════════

    # ── GOJ v1.2 — Build 1: Absence / Schedule Change Handler ────────────────

    def _handle_absence_message(self, chat_id: int, text: str):
        """GOJ v1.2 — Process a client absence/schedule change message from Kato."""
        _goj_ensure_tables()
        name_fragment = _extract_client_name(text)
        days_found    = _extract_day_from_text(text)

        if not name_fragment:
            _send_message(self.token, chat_id,
                "🐢 I caught an absence note but couldn't find the client name — can you rephrase?")
            return

        client_name, shift = _match_client(name_fragment)
        if not client_name:
            _send_message(self.token, chat_id,
                f"🐢 I couldn't match *{name_fragment}* to any active client. "
                f"Double-check the spelling and try again.")
            return

        for day_label, day_key, day_date in days_found:
            log_id, sched_id = _log_absence_to_db(client_name, shift, day_key, day_date, text)
            if not log_id:
                _send_message(self.token, chat_id,
                    f"⚠️ DB write failed for {client_name} — check logs.")
                continue

            # Store callback payload in-memory using a short UUID key (stays under 64-byte CB limit)
            cb_key = str(uuid.uuid4())[:8]
            self._pending_absence_data[cb_key] = (log_id, sched_id, client_name, day_label)

            keyboard = [[
                {"text": "1-Time Change",          "callback_data": f"abs_1time:{cb_key}"},
                {"text": "Recurring Change",        "callback_data": f"abs_recur:{cb_key}"},
            ], [
                {"text": "❓ Not Sure — Follow Up", "callback_data": f"abs_fu:{cb_key}"},
                {"text": "↩️ UNDO",                "callback_data": f"abs_undo:{cb_key}"},
            ]]
            _send_message_with_keyboard(
                self.token, chat_id,
                f"✅ Logged *{client_name}* as absent on *{day_label}*.\nChange type:",
                keyboard,
            )

    # ── GOJ v1.8 — Document classification callback ───────────────────────────
    def _handle_classify_callback(self, cq_id: str, chat_id: int, data: str):
        """
        Handle a classify:KEY:TYPE callback from an unknown-doc inline keyboard.

        Flow:
          classify:KEY:menu/auth/signin/drivers  → immediately route + learn
          classify:KEY:client_paperwork          → ask for client name first
          classify:KEY:staff_files               → ask for staff name first
          classify:KEY:misc                      → ask for description first
          classify:KEY:skip                      → discard, clean up
        """
        _answer_callback_query(self.token, cq_id, "Got it…")

        try:
            parts = data.split(":", 2)   # ["classify", key, type]
            if len(parts) < 3:
                _send_message(self.token, chat_id, "⚠️ Malformed callback data.")
                return

            key, doc_type = parts[1], parts[2]
            entry = _load_pending_doc(key)
            if not entry:
                _send_message(self.token, chat_id,
                    "⚠️ This classification request has expired or was already handled.")
                return

            file_path = entry["file_path"]
            filename  = entry["filename"]

            # Types that need a follow-up sub-type question before routing
            NEED_SUBTYPE = {
                "client_paperwork": (
                    "📁 <b>Client Paperwork</b>\n\n"
                    f"File: <code>{filename}</code>\n\n"
                    "What is the client's name?\n"
                    "<i>(Reply with full name — a new folder will be created if needed)</i>"
                ),
                "staff_files": (
                    "👤 <b>Staff Files</b>\n\n"
                    f"File: <code>{filename}</code>\n\n"
                    "Which staff member does this belong to?\n"
                    "<i>(Reply with full name — a new folder will be created if needed)</i>"
                ),
                "misc": (
                    "❓ <b>Miscellaneous</b>\n\n"
                    f"File: <code>{filename}</code>\n\n"
                    "Please describe what this document is:\n"
                    "<i>(Reply with a short description, e.g. 'fire drill log Apr 2026')</i>"
                ),
            }

            if doc_type in NEED_SUBTYPE:
                # Store state and ask follow-up
                self._pending_classify_subtype[str(chat_id)] = {
                    "key":      key,
                    "doc_type": doc_type,
                    "filename": filename,
                }
                _send_message(self.token, chat_id, NEED_SUBTYPE[doc_type], parse_mode="HTML")
                return

            # Direct-route types: menu, auth, signin, drivers, kitchen, skip
            # GOJ v1.9 — Ask for optional instruction before finalizing
            if doc_type == "skip":
                self._finalize_classification(chat_id, key, file_path, filename, doc_type, sub_type="")
            else:
                type_labels = {
                    "menu": "🍽 Menu", "auth": "🔒 Authorization",
                    "signin": "✍️ Sign In", "drivers": "🚗 Drivers Sheet",
                    "kitchen": "🍳 Kitchen",
                }
                type_label = type_labels.get(doc_type, doc_type.title())
                self._pending_classify_instruction[str(chat_id)] = {
                    "key": key, "doc_type": doc_type,
                    "filename": filename, "file_path": file_path,
                }
                skip_key = f"instruct_skip:{key}"
                _send_message_with_keyboard(
                    self.token, chat_id,
                    f"✅ Got it — <b>{type_label}</b>\n\n"
                    f"📄 <code>{filename}</code>\n\n"
                    f"Anything specific you need from this file?\n"
                    f"<i>E.g. 'Tuesday AM shift, expected 12 clients' or 'extract all names'</i>\n\n"
                    f"Or tap <b>Skip</b> to file it now.",
                    keyboard=[[{"text": "Skip — file it now", "callback_data": skip_key}]],
                    parse_mode="HTML",
                )

        except Exception as e:
            logger.error(f"_handle_classify_callback: {e}")
            _send_message(self.token, chat_id, f"⚠️ Error during classification: {e}")

    def _finalize_classification(self, chat_id: int, key: str, file_path: str,
                                  filename: str, doc_type: str, sub_type: str):
        """
        Complete a document classification:
        1. Route the file to the correct folder
        2. Save the learned pattern (so identical future docs auto-classify)
        3. Remove from pending queue
        4. Send confirmation to Kato
        """
        try:
            # Learn the pattern first (before routing moves/renames the file)
            if doc_type not in ("skip",):
                _save_pattern_to_db(file_path, doc_type, sub_type)

            # Route the file
            result_msg = _route_classified_doc(file_path, doc_type, sub_type)

            # Clean up pending queue
            _remove_pending_doc(key)

            # Mark in DB
            try:
                con = sqlite3.connect(str(GOJ_AUTH_DB))
                con.execute("""
                    UPDATE pending_doc_classifications
                    SET doc_type=?, sub_type=?, status='confirmed',
                        resolved_at=datetime('now')
                    WHERE queue_key=?
                """, (doc_type, sub_type, key))
                con.commit(); con.close()
            except Exception:
                pass

            # Confirmation message
            type_labels = {
                "menu":             "🍽 Menu",
                "auth":             "🔒 Authorization",
                "signin":           "✍️ Sign In",
                "drivers":          "🚗 Drivers Sheet",
                "client_paperwork": "📁 Client Paperwork",
                "staff_files":      "👤 Staff Files",
                "misc":             "📂 Misc",
                "skip":             "🗑 Skipped",
                "kitchen":          "🍳 Kitchen",
            }
            type_label = type_labels.get(doc_type, doc_type)

            learned_note = (
                "\n\n🧠 <i>Pattern saved — similar documents will auto-classify next time.</i>"
                if doc_type not in ("skip",) else ""
            )

            # GOJ v1.9 — if it's a menu, auto-run OCR + sync master in background
            menu_note = ""
            if doc_type == "menu":
                import threading as _thr, subprocess as _sp
                def _bg_menu_sync(pdf=file_path):
                    try:
                        venv_py = str(Path.home() / "debate-chamber" / ".venv" / "bin" / "python3")
                        rex_dir = str(Path.home() / "Desktop" / "REX")
                        _sp.run([venv_py, "goj_menu_consensus_ocr.py", pdf],
                                cwd=rex_dir, timeout=120, capture_output=True)
                        _sp.run([venv_py, "goj_master_menu.py"],
                                cwd=rex_dir, timeout=60, capture_output=True)
                    except Exception as _e:
                        logger.error(f"[menu_sync] bg error: {_e}")
                _thr.Thread(target=_bg_menu_sync, daemon=True).start()
                menu_note = ("\n\n🔄 <i>OCR + master spreadsheet update running in "
                             "background. Use <code>GENERATE_DAILY.command</code> "
                             "once done.</i>")

            _send_message(
                self.token, chat_id,
                f"✅ <b>Classified as {type_label}</b>\n\n"
                f"{result_msg}{learned_note}{menu_note}",
                parse_mode="HTML",
            )

        except Exception as e:
            logger.error(f"_finalize_classification: {e}")
            _send_message(self.token, chat_id, f"⚠️ Error finalizing: {e}")

    def _handle_callback_query(self, cq: dict):
        """GOJ v1.2+ — Handle inline keyboard button presses."""
        cq_id   = cq.get("id", "")
        chat_id = cq.get("from", {}).get("id")
        data    = cq.get("data", "")

        # ── Document classification callbacks ─────────────────────────────────
        if data.startswith("classify:"):
            self._handle_classify_callback(cq_id, chat_id, data)
            return

        # ── GOJ v1.9 — Skip instruction prompt, file immediately ─────────────
        if data.startswith("instruct_skip:"):
            _answer_callback_query(self.token, cq_id, "Filing now...")
            key = data.split(":", 1)[1]
            pending = self._pending_classify_instruction.pop(str(chat_id), None)
            if pending and pending["key"] == key:
                self._finalize_classification(
                    chat_id, pending["key"], pending["file_path"],
                    pending["filename"], pending["doc_type"], sub_type=""
                )
            else:
                # Key mismatch or already handled — try loading from pending docs directly
                entry = _load_pending_doc(key)
                if entry:
                    self._finalize_classification(
                        chat_id, key, entry["file_path"],
                        entry["filename"], entry.get("doc_type", "misc"), sub_type=""
                    )
                else:
                    _send_message(self.token, chat_id,
                        "⚠️ Session expired — please re-send the file.")
            return

        if not data.startswith("abs_"):
            _answer_callback_query(self.token, cq_id)
            return

        parts  = data.split(":", 1)
        action = parts[0]                              # abs_1time | abs_recur | abs_fu | abs_undo
        cb_key = parts[1] if len(parts) > 1 else ""

        payload = self._pending_absence_data.get(cb_key)
        if not payload:
            _answer_callback_query(self.token, cq_id,
                "⚠️ Session expired — re-send the absence message to re-log.")
            return

        log_id, sched_id, client_name, day_label = payload

        try:
            con = sqlite3.connect(str(GOJ_AUTH_DB))
            if action == "abs_undo":
                con.execute("DELETE FROM attendance_log WHERE id=?", (log_id,))
                con.execute("DELETE FROM pending_schedule_changes WHERE id=?", (sched_id,))
                con.commit()
                con.close()
                self._pending_absence_data.pop(cb_key, None)
                _answer_callback_query(self.token, cq_id, "↩️ Undone")
                _send_message(self.token, chat_id,
                    f"↩️ Undone — *{client_name}* restored to scheduled on *{day_label}*")

            elif action == "abs_1time":
                con.execute(
                    "UPDATE pending_schedule_changes SET change_type='1_time', confirmed=1 WHERE id=?",
                    (sched_id,))
                con.commit()
                con.close()
                _answer_callback_query(self.token, cq_id, "✅ Saved as 1-Time")
                _send_message(self.token, chat_id,
                    f"✅ *{client_name}* — *{day_label}* logged as *1-Time Change*.")

            elif action == "abs_recur":
                con.execute(
                    "UPDATE pending_schedule_changes SET change_type='recurring', confirmed=1 WHERE id=?",
                    (sched_id,))
                con.commit()
                con.close()
                _answer_callback_query(self.token, cq_id, "✅ Saved as Recurring")
                _send_message(self.token, chat_id,
                    f"✅ *{client_name}* — *{day_label}* logged as *Recurring Change*.")

            elif action == "abs_fu":
                con.execute(
                    "UPDATE pending_schedule_changes SET change_type='needs_follow_up', confirmed=1 WHERE id=?",
                    (sched_id,))
                con.commit()
                con.close()
                _answer_callback_query(self.token, cq_id, "📌 Flagged for follow-up")
                _send_message(self.token, chat_id,
                    f"📌 *{client_name}* — *{day_label}* flagged *Not Sure — Follow Up*.")
            else:
                con.close()
                _answer_callback_query(self.token, cq_id)

        except Exception as e:
            logger.error(f"GOJ callback handler: {e}")
            _answer_callback_query(self.token, cq_id, "⚠️ Error — check logs")

    # ── GOJ v1.6 — Incoming file handler (document / photo) ───────────────────

    def _handle_incoming_file(self, chat_id: int, msg: dict):
        """
        Called when Kato sends a document or photo to Rexxie.
        Downloads the file to ~/Desktop/REX/signins/, then runs goj_signin_intake.py
        on it specifically so the result comes back immediately in Telegram.
        Handles: sign-in sheets, driver sheets, menu forms, auth letters.
        """
        import tempfile, subprocess

        doc   = msg.get("document")
        photo = msg.get("photo")

        # Determine file_id and name
        if doc:
            file_id  = doc["file_id"]
            raw_name = doc.get("file_name") or f"scan_{msg['message_id']}.pdf"
            # If not a PDF, reject gracefully
            if not raw_name.lower().endswith(".pdf"):
                _send_message(self.token, chat_id,
                    f"📎 Got <b>{raw_name}</b> — I can only process PDF files for sign-ins and menus. "
                    f"Please send the file as a PDF document.", parse_mode="HTML")
                return
        elif photo:
            # Telegram photos come as JPEG — not directly OCR-able via pdfplumber
            # We'll download and notify; Paperless can OCR it
            file_id  = photo[-1]["file_id"]   # largest size
            raw_name = f"scan_{msg['message_id']}.jpg"
        else:
            return

        _send_typing(self.token, chat_id)
        _send_message(self.token, chat_id,
            f"📥 Got <b>{raw_name}</b> — reading it now...", parse_mode="HTML")

        # Download to signins/ drop zone
        signins_dir = Path.home() / "Desktop" / "REX" / "signins"
        signins_dir.mkdir(parents=True, exist_ok=True)
        dest = signins_dir / raw_name

        ok = _download_telegram_file(self.token, file_id, dest)
        if not ok:
            _send_message(self.token, chat_id,
                "❌ Could not download the file. Please try again.")
            return

        # Run intake on the specific file
        intake_script = Path.home() / "Desktop" / "REX" / "goj_signin_intake.py"
        if not intake_script.exists():
            _send_message(self.token, chat_id,
                "❌ <code>goj_signin_intake.py</code> not found — cannot process file.", parse_mode="HTML")
            return

        try:
            result = subprocess.run(
                ["python3", str(intake_script), str(dest)],
                capture_output=True, text=True, timeout=120,
                cwd=str(intake_script.parent),
            )
            output = (result.stdout + result.stderr).strip()

            if not output:
                _send_message(self.token, chat_id,
                    f"✅ <b>{raw_name}</b> processed — no output returned.")
                return

            # Parse result JSON for a nicer reply
            try:
                import json as _json
                res = _json.loads(output)
                status = res.get("status")
                if status == "ok":
                    stype = res.get("type", "?")
                    icons = {"signin": "📋", "drivers": "🚗", "menu": "🍽",
                             "auth": "📄", "kitchen": "🍳"}
                    icon = icons.get(stype, "📁")
                    if stype == "auth":
                        client = res.get("client", "unknown")
                        note   = " ⚠ staged — review needed" if res.get("staged") else ""
                        reply  = f"{icon} <b>Auth letter</b> filed\nClient: {client}{note}"
                    else:
                        reply = (
                            f"{icon} <b>{stype.title()} sheet</b> filed\n"
                            f"Date: {res.get('date', '?')}  |  Shift {res.get('shift', '?')}"
                        )
                    if stype == "menu":
                        # GOJ v1.9 — auto-trigger OCR + master spreadsheet sync
                        import threading as _thr, subprocess as _sp
                        def _bg_menu_sync(pdf=str(dest)):
                            try:
                                venv_py = str(Path.home() / "debate-chamber" / ".venv" / "bin" / "python3")
                                rex_dir = str(Path.home() / "Desktop" / "REX")
                                # Run consensus OCR to extract menu data into DB
                                _sp.run([venv_py, "goj_menu_consensus_ocr.py", pdf],
                                        cwd=rex_dir, timeout=120, capture_output=True)
                                # Sync DB → master spreadsheet
                                _sp.run([venv_py, "goj_master_menu.py"],
                                        cwd=rex_dir, timeout=60, capture_output=True)
                            except Exception as _e:
                                logger.error(f"[menu_sync] background error: {_e}")
                        _thr.Thread(target=_bg_menu_sync, daemon=True).start()
                        reply += ("\n\n🔄 <i>Running OCR and updating master spreadsheet "
                                  "in background...</i>\n"
                                  "Daily files can be generated from "
                                  "<code>GENERATE_DAILY.command</code>")
                elif status == "ambiguous":
                    # Send the classification keyboard instead of a dead-end message
                    # The pending state was already saved by _notify_rexxie_unknown_doc inside process_file
                    # Re-load the key from the pending queue by matching the filename
                    import hashlib as _hs, tempfile as _tf
                    _key = _hs.sha1(res.get("file", str(dest)).encode()).hexdigest()[:8]
                    _prev = res.get("text_preview", "")
                    _reason = res.get("reason", "Could not classify")
                    _prev_clean = _prev.replace("<","&lt;").replace(">","&gt;")[:280]

                    # ── GOJ v2.0 — Send preview image so Kato can see the document ──
                    if str(dest).lower().endswith(".pdf"):
                        _preview_jpg = _tf.mktemp(suffix=".jpg")
                        _preview_ok  = _pdf_first_page_jpeg(str(dest), _preview_jpg)
                        if _preview_ok:
                            _send_photo_file(
                                self.token, chat_id, _preview_jpg,
                                caption=f"📄 <b>{raw_name}</b>\n<i>Page 1 preview</i>",
                            )
                            try:
                                import os as _os; _os.unlink(_preview_jpg)
                            except Exception:
                                pass

                    _kb = [
                        [{"text":"🍽 Menu","callback_data":f"classify:{_key}:menu"},
                         {"text":"🔒 Authorization","callback_data":f"classify:{_key}:auth"}],
                        [{"text":"✍️ Sign In","callback_data":f"classify:{_key}:signin"},
                         {"text":"🚗 Drivers","callback_data":f"classify:{_key}:drivers"}],
                        [{"text":"📁 Client Paperwork","callback_data":f"classify:{_key}:client_paperwork"},
                         {"text":"👤 Staff Files","callback_data":f"classify:{_key}:staff_files"}],
                        [{"text":"❓ Misc / Specify","callback_data":f"classify:{_key}:misc"},
                         {"text":"🗑 Skip","callback_data":f"classify:{_key}:skip"}],
                    ]
                    _send_message_with_keyboard(
                        self.token, chat_id,
                        f"🤔 <b>What is this document?</b>\n\n"
                        f"📄 <code>{raw_name}</code>\n"
                        f"⚠️ {_reason}\n\n"
                        f"<code>{_prev_clean}</code>",
                        keyboard=_kb, parse_mode="HTML",
                    )
                    return
                elif status == "error":
                    reply = (
                        f"❌ <b>Could not read the file</b>\n"
                        f"{res.get('reason', 'Unknown error')}\n\n"
                        f"Is this a text-layer PDF? If it's a scanned image, "
                        f"make sure Paperless is running."
                    )
                else:
                    reply = f"<pre>{output[:3000]}</pre>"
            except Exception:
                reply = f"<pre>{output[:3000]}</pre>"

            _send_message(self.token, chat_id, reply, parse_mode="HTML")

        except subprocess.TimeoutExpired:
            _send_message(self.token, chat_id,
                "⏱ Processing timed out (Paperless OCR may be slow). "
                "Check back and run <code>process signins</code> manually.", parse_mode="HTML")
        except Exception as e:
            _send_message(self.token, chat_id, f"❌ Error processing file: {e}")

    # ── GOJ v1.2 — Build 2: Friday Evening Auto-Blast ─────────────────────────

    def _check_friday_menu_blast(self):
        """GOJ v1.2 — Every Friday at 8:30 PM auto-send missing next-week menus with phone numbers."""
        from datetime import datetime, date, timedelta
        now = datetime.now()
        if now.weekday() != 4:               # Not Friday
            return
        if not (now.hour == 20 and now.minute >= 30):
            return
        today_str = now.date().isoformat()
        if self._friday_blast_sent_date == today_str:
            return                           # Already sent this Friday

        self._friday_blast_sent_date = today_str
        try:
            _goj_ensure_tables()
            today      = date.today()
            next_monday = (today - timedelta(days=today.weekday()) + timedelta(weeks=1)).isoformat()
            con        = sqlite3.connect(str(GOJ_AUTH_DB))
            have_next  = {
                r[0] for r in con.execute(
                    "SELECT DISTINCT client_name FROM client_menus WHERE week_start=?",
                    (next_monday,),
                ).fetchall()
            }
            all_clients = con.execute(
                "SELECT name, shift, phone FROM clients WHERE active=1 ORDER BY name"
            ).fetchall()
            con.close()
        except Exception as e:
            logger.error(f"Friday blast query: {e}")
            return

        missing = [(n, s, p) for n, s, p in all_clients if n not in have_next]

        if not missing:
            msg = "✅ *Friday 8:30 PM* — All clients have next-week menus. Nothing to follow up!"
        else:
            lines = [f"🔔 *Friday 8:30 PM — Missing Next-Week Menus ({len(missing)} clients)*\n"]
            for name, shift, phone in missing:
                phone_str = f"  📞 {phone}" if phone else ""
                lines.append(f"• {name} (Shift {shift}){phone_str}")
            msg = "\n".join(lines)

        _send_message(self.token, self.owner_chat_id, msg)
        logger.info(f"GOJ v1.2 Friday blast sent: {len(missing)} missing clients")

    # ─────────────────────────────────────────────────────────────────────────

    def _get_updates_curl(self):
        """Use requests for getUpdates — simple short-poll to avoid 409 loops."""
        try:
            url = f"https://api.telegram.org/bot{self.token}/getUpdates"
            params = {"offset": self._offset, "timeout": 0}
            r = requests.get(url, params=params, timeout=25)
            if r.status_code == 200:
                data = r.json()
                if data.get("ok"):
                    self._consecutive_409 = 0
                    return data
                elif data.get("error_code") == 409:
                    self._consecutive_409 += 1
                    if self._consecutive_409 <= 2:
                        logger.warning(f"getUpdates 409 — stale connection, will retry ({self._consecutive_409}/5)")
                    if self._consecutive_409 >= 5:
                        logger.warning("409 persisted 5x — clearing Telegram state")
                        requests.get(f"https://api.telegram.org/bot{self.token}/deleteWebhook", timeout=25)
                        self._consecutive_409 = 0
                        time.sleep(3)
            return None
        except Exception as e:
            logger.error(f"getUpdates: {e}")
            return None

    def poll_once(self):
        # Friday MENU BLAST moved to rex_telegram_bot.py (REX business bot)
        # PATCHED 2026-07-19: Switched to _get_updates_curl — urllib _tg_api leaks TCP
        # connections causing persistent 409 loops with no recovery. curl with --http1.0
        # properly sends RST/FIN and has 5x consecutive 409 auto-recovery.
        result = self._get_updates_curl()
        if not result or not result.get("ok"):
            return
        for update in result.get("result", []):
            try:
                self._handle_update(update)
            except Exception as e:
                logger.error(f"Update error: {e}", exc_info=True)
            finally:
                self._offset = update["update_id"] + 1

    def run(self):
        if not self.token:
            logger.error("No bot token. Run: python rex_rexxie_telegram_bot.py --setup")
            return
        logger.info(f"🐢 Rexxie Telegram bot started (owner={self.owner_chat_id})")
        # PATCHED 2026-07-19: deleteWebhook at startup causes persistent 409 conflict
        # (Telegram takes 2+ min to release the long-poll slot after deleteWebhook).
        # Instead, just wait for any stale connections to time out naturally.
        # The _get_updates_curl 409 auto-recovery (5 consecutive → deleteWebhook + sleep 3)
        # will handle any genuine stale-connection scenarios.
        logger.info("Skipping startup deleteWebhook (causes 409 loop); waiting for stale connections to clear")
        # Brief pause to let TCP connections fully close before polling
        time.sleep(2)
        # Sacrificial getUpdates: DISABLED — causes persistent 409 loop
        # The deleteWebhook above already clears Telegram state.
        # Skipping this avoids the initial 409 that cascades.
        # try:
        #     self._get_updates_curl()
        # except Exception:
        #     pass
        time.sleep(10)  # increased to 10s to ensure TCP connections fully closed
        if self._is_setup_pending:
            logger.info("⚠️  Send /start to your Rexxie bot to lock in as owner.")
        while True:
            try:
                self.poll_once()
            except KeyboardInterrupt:
                logger.info("🐢 Rexxie bot stopped.")
                break
            except Exception as e:
                logger.error(f"Poll error: {e}")
                time.sleep(5)
            time.sleep(POLL_INTERVAL)


# ── Setup Wizard ───────────────────────────────────────────────────────────────

def setup_wizard():
    print("\n" + "="*60)
    print("  Rexxie — Private Telegram Bot Setup")
    print("="*60)
    print()
    print("⚠️  This is a SEPARATE bot from your REX business bot.")
    print("    Create a brand new bot — give it a private name")
    print("    only you know (doesn't have to say 'REX' or 'Rexxie').")
    print()
    print("Step 1 — Create the bot:")
    print("  1. Open Telegram → search @BotFather")
    print("  2. Send: /newbot")
    print("  3. Name it anything private (e.g., 'My Journal AI')")
    print("  4. Copy the bot token")
    print()
    token = input("  Paste your Rexxie Bot Token: ").strip()
    if not token:
        print("❌ No token entered.")
        return

    result = _tg_api(token, "getMe", {})
    if not result or not result.get("ok"):
        print("❌ Token invalid — double check it.")
        return

    bot_username = result["result"].get("username", "your-bot")
    print(f"\n  ✅ Connected! Bot: @{bot_username}")

    cfg = _load_config()
    cfg["bot_token"] = token
    cfg.pop(OWNER_CHAT_ID_KEY, None)   # Clear so /start re-registers
    _save_config(cfg)

    print()
    print("Step 2 — Lock your identity:")
    print(f"  1. Open Telegram → find @{bot_username}")
    print(f"  2. Send: /start")
    print(f"  You are now the ONLY person who can use Rexxie.")
    print()
    print("Step 3 — Start Rexxie:")
    print("  python rex_rexxie_telegram_bot.py")
    print()
    print("─" * 60)
    print("Suggested opening message (copy-paste to Telegram):")
    print()
    print(
        "  Hi Rexxie, I'm Kato. You're my personal confidant —\n"
        "  warm, honest, and completely private. I want you to\n"
        "  learn me over time — my patterns, what I care about,\n"
        "  what I'm working through. I'll share personal things\n"
        "  with you and I trust you to hold them carefully.\n"
        "  I'll also teach you things like bookkeeping and\n"
        "  personal finance so you can help me stay organized.\n"
        "  Everything we talk about stays between us — always."
    )
    print()
    print("="*60 + "\n")


# ── Entry Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Rexxie Private Telegram Bot")
    parser.add_argument("--setup",  action="store_true", help="Run setup wizard")
    parser.add_argument("--status", action="store_true", help="Show config status")
    args = parser.parse_args()

    if args.setup:
        setup_wizard()
    elif args.status:
        cfg = _load_config()
        token = cfg.get("bot_token", "")
        owner = cfg.get(OWNER_CHAT_ID_KEY)
        print("\n🐢 Rexxie Telegram Bot Status")
        print(f"   Token configured: {'✅' if token else '❌'}")
        print(f"   Owner locked:     {owner or '⚠️  Not set — send /start to bot'}")
        if token:
            r = _tg_api(token, "getMe", {})
            if r and r.get("ok"):
                print(f"   Bot username:     @{r['result'].get('username', '?')}")
                print(f"   Token valid:      ✅")
            else:
                print(f"   Token valid:      ❌")
        print()
    else:
        bot = RexxieTelegramBot()
        bot.run()
