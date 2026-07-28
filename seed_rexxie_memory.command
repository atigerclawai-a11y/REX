#!/bin/bash
# ====================================================================
#  SEED REXXIE MEMORY — Proper one-time seeding
#  Populates rexxie_ideas in auth_tracker.db with Kato's real profile,
#  GOJ context, and Rexxie's behavioral ground rules.
#  Safe to re-run — uses content-based deduplication.
# ====================================================================
set -uo pipefail
REX="$HOME/Desktop/REX"
DB="$HOME/Documents/goj files/dashboard/auth_tracker.db"
LOG_DIR="$REX/logs"
mkdir -p "$LOG_DIR"
exec > >(tee "$LOG_DIR/seed_rexxie_$(date +%Y%m%d_%H%M%S).log") 2>&1

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Seeding Rexxie Memory — GOJ Profile                ║"
echo "║  $(date +%Y-%m-%d\ %H:%M)                                ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

[ ! -f "$DB" ] && echo "❌ auth_tracker.db not found at: $DB" && read -n 1 && exit 1

PY=""
for C in "$REX/.venv/bin/python3" "$(command -v python3 2>/dev/null)"; do
    [ -f "$C" ] && PY="$C" && break
done
[ -z "$PY" ] && echo "❌ No Python found." && read -n 1 && exit 1

_SEED_PY="$LOG_DIR/_seed_$$.py"
cat > "$_SEED_PY" << 'PYEOF'
import sqlite3, json
from pathlib import Path
from datetime import datetime

DB   = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
NOW  = datetime.now().isoformat()

conn = sqlite3.connect(str(DB))
conn.execute("""
    CREATE TABLE IF NOT EXISTS rexxie_ideas (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        idea_type      TEXT NOT NULL DEFAULT 'idea',
        content        TEXT NOT NULL,
        source         TEXT DEFAULT 'seed',
        component_link TEXT,
        status         TEXT DEFAULT 'open',
        created_at     TEXT DEFAULT (datetime('now')),
        access_count   INTEGER DEFAULT 0,
        importance     REAL DEFAULT 0.5
    )
""")
for col, defval in [("access_count","INTEGER DEFAULT 0"), ("importance","REAL DEFAULT 0.5")]:
    try:
        conn.execute(f"ALTER TABLE rexxie_ideas ADD COLUMN {col} {defval}")
    except Exception:
        pass
conn.commit()

SEEDS = [
    ("preference", "My name is Kato. I am the Chairman of Garden of Joy Adult Day Care Center in Brooklyn, New York. Address me as Kato.", "identity", 1.0),
    ("preference", "I built Rex and Rexxie to reduce my administrative workload. I want things automated and proactive — Rexxie should deliver information before I have to ask for it.", "working_style", 1.0),
    ("preference", "I communicate primarily in English. Sometimes I use Russian or Ukrainian. Respond in whatever language I write in.", "language", 1.0),
    ("preference", "I use Telegram as my primary interface. I am on mobile most of the time. Keep responses concise unless I ask for detail.", "interface", 1.0),
    ("preference", "Privacy and data sovereignty are non-negotiable. Rex is local-only. Nothing about GOJ clients, staff, or operations goes to any cloud service. Ever.", "privacy_rule", 1.0),
    ("state", "Garden of Joy Adult Day Care serves approximately 426 active clients. Most are elderly Russian-speaking immigrants from Brooklyn. Forms and menus are in Russian.", "goj_operations", 1.0),
    ("state", "GOJ has two shifts: Shift 1 (morning) and Shift 2 (afternoon). Facility operates Monday through Saturday. Some clients attend Sundays.", "goj_schedule", 1.0),
    ("state", "Core staff: Vladimir Khiger (Director), Natalie Altman (Social Worker), Svitlana Rozmetanyuk (Supervisor), Olena Sturovska (Activity), Ravil Aleev, Vadim Kononenko, Oleg Tikhonov, Valerian Ormotsadze, Alisher Imomberdiev, Andriy Sheremet (Drivers), Inna Klimova (Maintenance), Liudmila Zhuk (Activity), Gennadiy Gugilov (Driver), Allen Khiger (Administrator).", "goj_staff", 1.0),
    ("state", "Payer plans: CPHL (~208 clients), Eld Serve (~87), Anthem (~47), VCM (~29), SWH (~24), VNS (~20), Aetna, Metro Plus, Private Pay, Empire.", "goj_plans", 1.0),
    ("state", "Primary database: auth_tracker.db at ~/Documents/goj files/dashboard/auth_tracker.db. All client records, attendance, menus, staff data live here.", "goj_database", 1.0),
    ("decision", "Rexxie is my personal confidant AND business assistant. She handles my personal thinking AND GOJ operations. She is not just a bot.", "rexxie_role", 1.0),
    ("decision", "Rexxie proactively alerts me to overdue staff medicals, missing client menus, low-confidence OCR, upcoming authorization renewals, schedule gaps. She does not wait to be asked.", "rexxie_proactive", 1.0),
    ("decision", "Rexxie should NEVER redesign Rex, suggest cloud services, introduce frameworks, or make architectural changes without my explicit request.", "rexxie_boundaries", 1.0),
    ("state", "Rex has a full FastAPI backend at localhost:8000 with 40+ routes including attendance, roster, staff compliance, Chairman Command Center. Rexonasence v4.", "rex_backend", 0.9),
    ("state", "OCR pipeline: 4 engines — pdfplumber, Tesseract, Paperless-NGX, Claude Vision (primary, 3x vote weight). Menu forms Apr 20-27 are pre-printed personalized. Flag queue: 28 unresolved stale-path items.", "ocr_state", 0.9),
    ("state", "Lucy Core hardening complete (Phases 0-4): Alert Bus, OCR Schema, Memory Steward (L0-L5), Alert Router, Gauntlet (32 tests passing).", "lucy_core", 0.8),
    ("state", "Calendar 2026 attendance (8,122 records Jan-Apr) imported April 13, 2026. Staff medical PDFs downloaded but not yet OCR extracted — run EXTRACT_STAFF_MEDICALS.command.", "recent_work", 0.8),
    ("decision", "Architecture going forward: Next.js (Railway) frontend → FastAPI backend on Mac via Tailscale → SQLite auth_tracker.db. Railway hosts only the UI. All data stays local. This fixes the Railway/local database disconnect.", "architecture_decision", 1.0),
    ("state", "Known issue: Railway dashboard shows Railway database (separate from local). Fix: configure Next.js app to call FastAPI at Tailscale IP instead of Railway DB. Not yet implemented.", "known_issue_railway", 0.9),
    ("state", "Two Rexxie bots exist: rex_rexxie_telegram_bot.py (REX folder, GOJ operations v2.2, started by FIX_REXXIE) and private_confidant_gold.py (Gold_Health_Systems, growth loop v3.0, Ollama). These need to be merged into one.", "known_issue_two_bots", 0.9),
]

inserted = 0
for idea_type, content, component_link, importance in SEEDS:
    existing = conn.execute("SELECT id FROM rexxie_ideas WHERE content=?", (content,)).fetchone()
    if existing:
        continue
    conn.execute(
        "INSERT INTO rexxie_ideas (idea_type, content, source, component_link, status, created_at, access_count, importance) VALUES (?,?,?,?,?,?,?,?)",
        (idea_type, content, "seed_2026_04_14", component_link, "open", NOW, 0, importance)
    )
    inserted += 1

conn.commit()
total = conn.execute("SELECT COUNT(*) FROM rexxie_ideas WHERE status='open'").fetchone()[0]
conn.close()

print(f"\n  ✅  {inserted} new seed entries written")
print(f"  ✅  {total} total entries now in rexxie_ideas")
print(f"  Rexxie now knows who Kato is, what GOJ is, and current system state.")
print(f"  She will recall these on every relevant conversation.\n")
PYEOF

"$PY" "$_SEED_PY"
rm -f "$_SEED_PY"

echo ""
read -n 1 -p "Press any key to close..."
