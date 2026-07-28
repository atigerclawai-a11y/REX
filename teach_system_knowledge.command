#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  TEACH REX + REXXIE — System Knowledge from Master Handoff Document
#  Writes structured knowledge about the GOJ / REX system into:
#    • Rexxie: rexxie_memory.db → rex_user_model table (direct DB write)
#    • REX:    http://localhost:8000/api/memory (encrypted, via backend API)
#  Safe to run multiple times — skips duplicates for Rexxie, REX deduplicates too.
# ═══════════════════════════════════════════════════════════════════════════════

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'; BOLD='\033[1m'

REX_DIR="$HOME/Desktop/REX"
VENV_PYTHON="$REX_DIR/.venv/bin/python"
[ ! -f "$VENV_PYTHON" ] && VENV_PYTHON="$HOME/debate-chamber/.venv/bin/python3"

echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}  📚 Teaching REX + Rexxie — GOJ System Knowledge${NC}"
echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

"$VENV_PYTHON" << 'PYTHON_EOF'
import sqlite3, json, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path

REX_DIR    = Path.home() / "Desktop" / "REX"
REXXIE_DB  = REX_DIR / "rexxie_memory.db"
CHAT_ID    = 5587703834
REX_URL    = "http://localhost:8000/api/memory"
NOW        = datetime.utcnow().isoformat()

# ─────────────────────────────────────────────────────────────────────────────
#  ALL FACTS — (category, content, tier) for Rexxie
#              (mem_type, content, tags)  for REX
#  Shared list: each entry teaches both bots the same thing in the right format.
# ─────────────────────────────────────────────────────────────────────────────

KNOWLEDGE = [

    # ── IDENTITY & CONTEXT ────────────────────────────────────────────────────
    ("identity", "fact",
     "Kato is the Chairman of Garden of Joy (GOJ) Adult Day Care Center. He is the only person with Chairman-level access to REX and Rexxie.",
     3, ["kato", "chairman", "goj", "identity"]),

    ("identity", "fact",
     "Garden of Joy (GOJ) is an adult day care center. It serves elderly clients who attend on scheduled days, receive meals, and are transported by assigned drivers.",
     3, ["goj", "adult day care", "clients", "overview"]),

    ("language", "preference",
     "Kato writes in English, Russian, and Ukrainian. Always reply in the exact language he writes in — no translation, no asking. Just mirror his language automatically.",
     3, ["language", "russian", "ukrainian", "english"]),

    # ── SYSTEM ARCHITECTURE ───────────────────────────────────────────────────
    ("context", "fact",
     "The REX system has five components: (1) REX Backend on port 8000 — the AI brain. (2) GOJ Dashboard on port 8080 — web interface for staff. (3) Rexxie Telegram Bot — Kato's personal confidant. (4) REX Telegram Bot — occupational assistant. (5) GOJ Scheduler — runs 6 automatic jobs daily.",
     3, ["architecture", "system", "components", "ports"]),

    ("context", "fact",
     "REX Backend runs at http://localhost:8000. GOJ Dashboard runs at http://localhost:8080. Both must be running for the system to work. Paperless-NGX is at http://100.99.86.60:8000 via Tailscale.",
     2, ["urls", "ports", "localhost", "paperless"]),

    ("context", "fact",
     "Rexxie and REX Telegram bot MUST use different Telegram bot tokens. If they share the same token, both get HTTP 409 Conflict errors and neither responds. Each bot has its own @username on Telegram.",
     3, ["telegram", "conflict", "409", "tokens", "critical"]),

    # ── OCR SYSTEM ────────────────────────────────────────────────────────────
    ("context", "fact",
     "REX uses 4 OCR engines in waterfall order: (1) pdfplumber/pymupdf — reads embedded text layer, instant, offline. (2) Tesseract — local OCR using eng+rus language config, reads English and Russian, offline. (3) Paperless-NGX — network OCR via Tailscale. (4) Claude Vision (Haiku) — AI handwriting reader, last resort, reads English/Russian/Ukrainian.",
     3, ["ocr", "engines", "waterfall", "tesseract", "claude vision", "paperless"]),

    ("context", "fact",
     "OCR engine selection rule: each engine is tried in order. The first engine that returns more than 30 characters of text wins. Claude Vision is only used if all three others fail. If everything fails, the file stays unprocessed and Rexxie sends Kato a Telegram alert.",
     3, ["ocr", "waterfall", "30 characters", "threshold", "fallback"]),

    ("context", "fact",
     "Claude Vision is the handwriting reader. It uses claude-haiku-4-5-20251001 model and the ANTHROPIC_API_KEY from ~/Desktop/REX/.env. It handles handwriting, low-quality scans, rotated pages, and mixed printed+handwritten forms. PHI documents (sign-in sheets with client names) are NOT sent to Claude Vision.",
     3, ["handwriting", "claude vision", "haiku", "anthropic", "phi", "privacy"]),

    ("context", "fact",
     "Tesseract OCR requires: (1) brew install tesseract tesseract-lang — system install. (2) pip install pdf2image pytesseract Pillow — Python packages. (3) poppler installed via brew for PDF-to-image conversion. If pdf2image module is missing, Tesseract AND Claude Vision both fail. Fix: double-click install_ocr_deps.command.",
     3, ["tesseract", "pdf2image", "poppler", "installation", "ocr fix"]),

    ("context", "fact",
     "Menus are written in Russian. OCR must use lang='eng+rus' for Tesseract. Menu food items include: салат, борщ, суп, котлеты, пельмени, гречка, пюре, вареники, голубцы, гуляш, шницель. Russian weekdays: Пн=Monday, Вт=Tuesday, Ср=Wednesday, Чт=Thursday, Пт=Friday.",
     3, ["menus", "russian", "food items", "weekdays", "ocr language"]),

    ("context", "fact",
     "Checkmarks on menu forms that OCR recognizes as 'selected': ✓ x X v V + √ ☑ L л — all map to the client choosing that meal item.",
     2, ["menus", "checkmarks", "ocr", "meal selection"]),

    # ── DOCUMENT INTAKE ───────────────────────────────────────────────────────
    ("context", "fact",
     "All scanned documents must be dropped into ~/Desktop/REX/signins/ — this is the universal drop zone. Run: python3 goj_signin_intake.py to process them. Use --watch flag for continuous monitoring every 10 seconds. Use --dry-run to preview without moving files.",
     3, ["intake", "drop zone", "signins folder", "scanning"]),

    ("context", "fact",
     "Document types and their output folders: Sign-in sheets → ~/Desktop/REX/ named GOJ_M_S1_Monday_signin.pdf. Driver sheets → ~/Desktop/REX/ named GOJ_M_S1_Monday_drivers.pdf. Menus → ~/Documents/goj files/dashboard/documents/menus/ named menu_2026-04-14_S1.pdf. Auth docs → ~/Documents/goj files/dashboard/documents/authorization/{ClientName}/",
     3, ["document types", "file naming", "output folders", "signin", "driver", "menu", "auth"]),

    ("context", "fact",
     "Sign-in sheet detection keywords: SIGN-IN SHEET, SIGN IN SHEET, GARDEN OF JOY ADULT DAY CARE CENTER, Insurance Plan, Total present, Staff signature. Driver sheet keywords: ROUTE, Driver Name, Driver Signature, Total clients. Menu keywords: Russian food words (борщ, суп, котлета) and Russian weekday abbreviations (Пн, Вт, Ср).",
     2, ["document detection", "keywords", "classification"]),

    ("context", "fact",
     "Authorization document handling: client name is extracted from text using patterns like 'Member Name:', 'Patient:', 'Beneficiary:'. The name is fuzzy-matched against the clients table in auth_tracker.db. If matched: file goes to ~/Documents/.../authorization/{LastName_FirstName}/. If not matched: file goes to _incoming/ staging folder for manual assignment.",
     2, ["auth documents", "authorization", "client matching", "staging"]),

    ("context", "fact",
     "File naming convention day abbreviations: Monday=M, Tuesday=T, Wednesday=W, Thursday=TH, Friday=F, Saturday=Sa. Shift numbers: S1=Shift 1 (AM), S2=Shift 2 (PM). Example full filename: GOJ_TH_S1_Thursday_signin.pdf",
     2, ["file naming", "day abbreviations", "shift", "conventions"]),

    # ── SCHEDULER JOBS ────────────────────────────────────────────────────────
    ("context", "fact",
     "GOJ Scheduler runs 6 automatic jobs via Rexxie Telegram: 7:30am = morning_report (auth expirations, today's clients, menu status). 10:30am = kitchen_sheets (kitchen prep PDF + distribution sheet PDF). 3:15pm = changes_routes (driver routes + pending schedule changes). 8:30pm Friday = missing_menus (alert for next week). 9:00pm = nightly_rundown (actual vs expected attendance, all pending changes). 9:00pm Friday = weekly_email_fri (full week summary).",
     3, ["scheduler", "jobs", "timing", "automatic", "reports"]),

    ("context", "fact",
     "Run any scheduler job manually: python3 goj_daily_scheduler.py --job morning_report. Replace morning_report with: kitchen_sheets, changes_routes, missing_menus_fri, nightly_rundown, weekly_email_fri, or status_check.",
     2, ["scheduler", "manual run", "command line"]),

    # ── DATABASE ──────────────────────────────────────────────────────────────
    ("context", "fact",
     "Main GOJ database is auth_tracker.db at ~/Documents/goj files/dashboard/auth_tracker.db. Key tables: clients (all GOJ clients with schedule), client_menus (weekly meal selections), attendance_log (who showed up each day), pending_schedule_changes (changes awaiting 9pm confirmation), client_route_assignments (which driver covers which client).",
     3, ["database", "auth_tracker.db", "tables", "sql"]),

    ("context", "fact",
     "Client schedule uses _actual vs _base fields: day_M_base = permanent Monday schedule, day_M_actual = what is actually happening this week. One-time change: only _actual changes, _base stays the same (auto-reverts next week). Recurring change: both _actual AND _base are updated. The 9pm nightly rundown always asks Kato: recurring or one-time?",
     3, ["schedule changes", "actual vs base", "one-time", "recurring", "database"]),

    ("context", "fact",
     "pending_schedule_changes table tracks all schedule modifications: client_name, change_type, day_key (which day changed), old_value, new_value, note, created_at, confirmed (0=pending, 1=recurring confirmed, 2=one-time confirmed). Always checked at 9pm nightly rundown.",
     2, ["pending changes", "schedule", "database", "confirmation"]),

    # ── STARTUP & TROUBLESHOOTING ─────────────────────────────────────────────
    ("context", "fact",
     "Main startup file: FIX_REXXIE.command — double-click to restart everything. It runs 5 steps: (1) Kill all old processes. (2) Start REX Backend port 8000. (3) Start GOJ Dashboard port 8080. (4) Start Rexxie Telegram bot. (5) Start REX Telegram bot (only if token differs from Rexxie).",
     3, ["startup", "FIX_REXXIE", "restart", "command files"]),

    ("context", "fact",
     "REX_HEALTH_CHECK.command — full A-Z diagnostic in 30 seconds. Checks 10 areas: Python env, core files, API keys, launchd agents, running processes, HTTP endpoints, database tables, recent log errors (last 30 min only), backup status, disk space. Run this before asking what's wrong.",
     3, ["health check", "diagnostic", "troubleshooting"]),

    ("context", "fact",
     "If Telegram bots get 409 Conflict errors: run fix_telegram_conflict.command — it kills all bot processes, checks for webhooks, deletes any found, waits 20 seconds for Telegram servers to release the session lock, then restarts both bots. The 20-second wait is critical — restarting immediately causes another 409.",
     3, ["409", "conflict", "telegram", "fix", "webhook", "20 seconds"]),

    ("context", "fact",
     "If OCR is not working: double-click install_ocr_deps.command. It installs: poppler (brew), tesseract + Russian language pack (brew), pdf2image, pytesseract, Pillow, anthropic, pdfplumber (pip). All OCR engines depend on these.",
     3, ["ocr", "fix", "install", "dependencies"]),

    ("context", "fact",
     "If Rexxie seems to not know who Kato is or forgets context: run seed_rexxie_memory.command to re-seed her long-term memory, then restart with FIX_REXXIE.command.",
     3, ["rexxie", "memory", "seed", "forget", "fix"]),

    ("context", "fact",
     "Log files location ~/Desktop/REX/logs/: rex_backend.log (backend errors), rexxie_telegram.log (Rexxie activity), rex_telegram.log (REX bot activity — 409s appear here), dashboard_startup.log (Flask errors), goj_scheduler.log (all 6 scheduled jobs), ocr_run.log (OCR engine results and confidence scores).",
     2, ["logs", "log files", "debugging"]),

    ("context", "fact",
     "Backups: REX system snapshots live ONLY on the external Cartoons drive at /Volumes/Cartoons/REX_Backups/REX_{YYYY-MM-DD}_{HH-MM}/ (the Mac also accepts the lowercase variant /Volumes/cartoons/). Nothing in the REX build tree is read from here — snapshots are write-once, read-for-recovery-only, and every snapshot carries a DO_NOT_USE_AS_SOURCE.txt marker. If the Cartoons drive is not mounted, rex-backup.command hard-fails rather than falling back to Desktop. GOJ config backup is separate and still in-tree: ~/Desktop/REX/GOJ_Backups/GOJ_{YYYY-MM-DD}_{HH-MM}/ — run rex-backup-goj.command at any time. Health check warns if no REX backup today or if Cartoons is unmounted.",
     2, ["backups", "backup files", "REX_Backups", "GOJ_Backups", "cartoons", "external drive"]),

    # ── PRIVACY & SECURITY ────────────────────────────────────────────────────
    ("context", "fact",
     "PHI rule: client sign-in sheets (which contain real client names) must NOT be sent to external APIs including Claude Vision. Only Tesseract (local) and Paperless-NGX (local Tailscale network) can process PHI documents. Menu forms and non-client-name documents CAN use Claude Vision.",
     3, ["phi", "privacy", "hipaa", "security", "client names"]),

    ("identity", "fact",
     "Rexxie's memory is completely separate from REX's memory. Nothing Kato says in Rexxie mode is accessible to REX mode or to GOJ staff. Rexxie's vault is triple-encrypted (AES-GCM + ChaCha20 + AES-GCM). Kato's confidentiality is absolute.",
     3, ["rexxie", "privacy", "memory", "encryption", "separation"]),
]

# ─────────────────────────────────────────────────────────────────────────────
#  1. TEACH REXXIE (direct DB write)
# ─────────────────────────────────────────────────────────────────────────────
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("  📖 Teaching Rexxie (rexxie_memory.db)...")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

conn = sqlite3.connect(REXXIE_DB)
conn.row_factory = sqlite3.Row
conn.execute("""
CREATE TABLE IF NOT EXISTS rex_user_model (
    id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL,
    category TEXT NOT NULL, content TEXT NOT NULL, tier INTEGER NOT NULL DEFAULT 2,
    confidence REAL NOT NULL DEFAULT 0.9, source TEXT DEFAULT 'manual',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    expires_at TEXT, access_count INTEGER DEFAULT 0, active INTEGER NOT NULL DEFAULT 1
)""")

r_added = 0; r_skipped = 0
for category, _, content, tier, _ in KNOWLEDGE:
    exists = conn.execute(
        "SELECT id FROM rex_user_model WHERE chat_id=? AND content=? AND active=1",
        (CHAT_ID, content)
    ).fetchone()
    if exists:
        r_skipped += 1
        continue
    conn.execute("""INSERT INTO rex_user_model
        (chat_id,category,content,tier,confidence,source,created_at,updated_at,active)
        VALUES (?,?,?,?,0.95,'handoff_doc',?,?,1)""",
        (CHAT_ID, category, content, tier, NOW, NOW))
    r_added += 1

conn.commit()
total = conn.execute("SELECT COUNT(*) FROM rex_user_model WHERE chat_id=? AND active=1",(CHAT_ID,)).fetchone()[0]
conn.close()
print(f"  ✅ Added {r_added} new facts, skipped {r_skipped} already known")
print(f"  ✅ Rexxie total knowledge: {total} entries")
print()

# ─────────────────────────────────────────────────────────────────────────────
#  2. TEACH REX (via REST API — backend must be running)
# ─────────────────────────────────────────────────────────────────────────────
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("  🦖 Teaching REX (http://localhost:8000/api/memory)...")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

# Check backend is alive
try:
    urllib.request.urlopen("http://localhost:8000/", timeout=4)
except Exception:
    print("  ❌ REX Backend not reachable at port 8000.")
    print("     Run FIX_REXXIE.command first, then re-run this script.")
    exit(0)

rex_added = 0; rex_fail = 0

# First: get existing memories to avoid duplicates
try:
    with urllib.request.urlopen("http://localhost:8000/api/memory", timeout=10) as r:
        existing_mems = json.loads(r.read())
        existing_contents = {m["content"].strip() for m in existing_mems.get("memories", [])}
except Exception:
    existing_contents = set()

for _, mem_type, content, _, tags in KNOWLEDGE:
    # Skip if content already in REX memory
    if content.strip() in existing_contents:
        continue
    payload = json.dumps({"content": content, "mem_type": mem_type, "tags": tags, "source": "handoff_doc"}).encode()
    req = urllib.request.Request(
        "http://localhost:8000/api/memory",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                rex_added += 1
            else:
                rex_fail += 1
    except Exception as e:
        rex_fail += 1

# Get updated count
try:
    with urllib.request.urlopen("http://localhost:8000/api/memory", timeout=10) as r:
        final = json.loads(r.read())
        rex_total = final.get("count", "?")
except Exception:
    rex_total = "?"

print(f"  ✅ Stored {rex_added} new memories in REX")
if rex_fail: print(f"  ⚠️  {rex_fail} entries failed (may already exist)")
print(f"  ✅ REX total memory: {rex_total} entries")
print()

print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("  ✅ DONE — both REX and Rexxie have been taught")
print("  Restart both with FIX_REXXIE.command for")
print("  Rexxie to load her new long-term memory.")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

PYTHON_EOF

echo ""
echo -e "${YELLOW}Restart both bots now so Rexxie loads her updated memory:${NC}"
echo -e "${CYAN}  → Double-click FIX_REXXIE.command${NC}"
echo ""
echo "Press Enter to close..."
read
