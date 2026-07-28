#!/bin/bash
# ====================================================================
#  GOJ Menu Vision OCR — Inbox Runner
#  Runs Claude Vision on all menu PDFs in REX/Scanned docs/
#  and logs food choices to client_menus in auth_tracker.db
#
#  Handles multi-page PDFs (each 2-page spread = 1 client form)
#  Double-click to run. Requires internet + ANTHROPIC_API_KEY in .env
# ====================================================================

set -uo pipefail

REX="$HOME/Desktop/REX"
DB="$HOME/Documents/goj files/dashboard/auth_tracker.db"
LOG_DIR="$REX/logs"
TS=$(date +%Y%m%d_%H%M%S)
LOG="$LOG_DIR/menu_vision_${TS}.log"
mkdir -p "$LOG_DIR"
exec > >(tee "$LOG") 2>&1

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  GOJ Menu Vision OCR — Inbox Runner                 ║"
echo "║  $(date +%Y-%m-%d\ %H:%M)                                ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# Python
PY=""
for C in "$HOME/debate-chamber/.venv/bin/python3" "$REX/.venv/bin/python3" "$(command -v python3 2>/dev/null)"; do
    [ -f "$C" ] && PY="$C" && break
done
[ -z "$PY" ] && echo "❌ No Python found." && read -n 1 && exit 1

# Dep check
for MOD in anthropic pdf2image pdfplumber; do
    "$PY" -c "import $MOD" 2>/dev/null || {
        echo "❌ $MOD not installed. Run install_ocr_deps.command first."
        read -n 1; exit 1
    }
done
echo "✅  Dependencies OK"

# API key
grep -q "^ANTHROPIC_API_KEY=sk-ant-" "$REX/.env" 2>/dev/null || {
    echo "❌ ANTHROPIC_API_KEY missing from $REX/.env"
    read -n 1; exit 1
}
echo "✅  API key OK"
echo ""

"$PY" - <<PYEOF
import os, sys, json, sqlite3, base64, io, time, re
from pathlib import Path
from datetime import datetime
import difflib

REX = Path("$REX")
DB  = Path("$DB")

# Load API key
with open(REX / '.env') as f:
    for line in f:
        if line.startswith('ANTHROPIC_API_KEY='):
            os.environ['ANTHROPIC_API_KEY'] = line.split('=',1)[1].strip()

import anthropic

# Client list from DB for matching
def load_clients():
    if not DB.exists():
        return []
    conn = sqlite3.connect(str(DB))
    rows = conn.execute("SELECT client_id, name FROM clients WHERE active=1").fetchall()
    conn.close()
    return rows

def match_client(name, clients):
    if not name or not clients:
        return None, None, 0.0
    best_score = 0.0
    best = None
    for cid, cname in clients:
        score = difflib.SequenceMatcher(None, name.lower(), cname.lower()).ratio()
        if score > best_score:
            best_score = score
            best = (cid, cname)
    if best and best_score >= 0.55:
        return best[0], best[1], best_score
    return None, None, best_score

def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS client_menus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            client_name TEXT,
            week_start TEXT,
            day TEXT,
            salad TEXT,
            soup TEXT,
            main TEXT,
            side TEXT,
            confidence REAL,
            source_pdf TEXT,
            ocr_engines TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

# Find pending menu PDFs
SCAN_DIR = REX / 'Scanned docs'
SCAN_DIR.mkdir(exist_ok=True)
# Fallback to legacy signins/ if Scanned docs/ is empty
SIGNINS = SCAN_DIR if any(SCAN_DIR.glob('*.pdf')) else (REX / 'signins')
done_log = SCAN_DIR / '.menu_vision_done.json'
done = set(json.loads(done_log.read_text())) if done_log.exists() else set()

all_pdfs = sorted([f for f in SCAN_DIR.iterdir()
                   if not f.name.startswith('.') and f.suffix == '.pdf'])

# Classify quickly: skip obvious non-menu files
menu_pdfs = []
import pdfplumber, pytesseract
from pdf2image import convert_from_path

print("Scanning signins/ for menu PDFs...")
for pdf in all_pdfs:
    if str(pdf) in done:
        print(f"  SKIP (already done): {pdf.name}")
        continue
    # Quick first-page text check
    try:
        pages = convert_from_path(str(pdf), dpi=100, first_page=1, last_page=1)
        text = pytesseract.image_to_string(pages[0], lang='eng+rus')
        has_menu = any(w in text for w in ['ADULT DAYCARE','GARDEN OF JOY','САЛАТ','СУПЫ','СУП','МН ВТ','ПН ВТ','ГЛАВНОЕ'])
        has_signin = any(w in text.upper() for w in ['SIGN-IN','SIGN IN','TOTAL PRESENT','ATTENDANCE REPORT'])
        if has_menu and not has_signin:
            menu_pdfs.append(pdf)
            print(f"  MENU: {pdf.name} ({pdf.stat().st_size//1024}KB, {len(convert_from_path(str(pdf), dpi=72))} pages)")
        else:
            print(f"  SKIP ({('SIGN-IN' if has_signin else 'UNKNOWN')}): {pdf.name}")
    except Exception as e:
        print(f"  ERR:  {pdf.name}: {e}")

print(f"\nMenu PDFs to process: {len(menu_pdfs)}")
if not menu_pdfs:
    print("Nothing to do.")
    sys.exit(0)

client = anthropic.Anthropic()
clients = load_clients()
print(f"Client list: {len(clients)} active clients in DB\n")

PROMPT = """This is a Russian-language weekly menu form from Garden of Joy Adult Day Care in Brooklyn.

Extract and return ONLY valid JSON (no other text):

{
  "client_name": "full name as written on the form",
  "week_start": "YYYY-MM-DD (Monday of the week)",
  "days": {
    "M":  {"salad": "item or null", "soup": "item or null", "main": "item or null", "side": "item or null"},
    "T":  {"salad": null, "soup": null, "main": null, "side": null},
    "W":  {"salad": null, "soup": null, "main": null, "side": null},
    "TH": {"salad": null, "soup": null, "main": null, "side": null},
    "F":  {"salad": null, "soup": null, "main": null, "side": null},
    "SA": {"salad": null, "soup": null, "main": null, "side": null}
  }
}

САЛАТЫ: Салат из баклажан, Салат весенний, Винегрет, Салат Днестр, Квашеная капуста, Оливье, Свекла, Селедка, Сало
СУПЫ: Борщ зеленый, Борщ красный, Грибной суп, Куриный суп, Овощной суп, Харчо, Гороховый суп
ГЛАВНОЕ БЛЮДО: Баса с помидорами под сыром, Блины с мясом, Блины с творогом, Вареники с картошкой, Голубцы, Гуляш, Дорадо запеченая, Жульен, Котлеты куриные, Куриные крылышки, Курица в терияки соусе, Пельмени, Поперечка, Салмон, Свиная отбивная, Цыпленок табака, Чалахач, Чебуреки, Шницель куриный
ГАРНИР: Тушеная капуста, Картошка по деревенски, Пюре, Гречка, Паста, Рис, Жареная картошка, Без гарнира

Columns: Пон/ПН/МН=Monday(M), Вт/ВТ=Tuesday(T), Ср/СР=Wednesday(W), Чт/ЧТ=Thursday(TH), Пт/ПТ=Friday(F), Сб/СБ=Saturday(SA)
A checkmark (✓,V,v,√,+,x,■,●, or filled box) = item selected for that day. Return null if nothing marked.
Return ONLY the JSON object."""

stats = {'pdfs':0, 'forms':0, 'saved':0, 'no_match':0, 'errors':0}
newly_done = set()

conn = sqlite3.connect(str(DB)) if DB.exists() else None
if conn:
    ensure_table(conn)

for pdf_idx, pdf in enumerate(menu_pdfs, 1):
    print(f"\n[{pdf_idx}/{len(menu_pdfs)}] {pdf.name}")
    stats['pdfs'] += 1

    try:
        pages = convert_from_path(str(pdf), dpi=200)
        total_pages = len(pages)
        print(f"  {total_pages} pages → {(total_pages+1)//2} client form(s)")

        for i in range(0, total_pages, 2):
            batch = pages[i:i+2]
            form_num = i//2 + 1
            print(f"  Form {form_num} (pages {i+1}-{min(i+2,total_pages)})...", end=' ', flush=True)

            content = []
            for img in batch:
                buf = io.BytesIO()
                img.save(buf, format='JPEG', quality=85)
                enc = base64.standard_b64encode(buf.getvalue()).decode()
                content.append({"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":enc}})
            content.append({"type":"text","text":PROMPT})

            try:
                resp = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=1200,
                    messages=[{"role":"user","content":content}]
                )
                text = resp.content[0].text.strip()
                if '```' in text:
                    text = text.split('```')[1]
                    if text.startswith('json'): text = text[4:]
                parsed = json.loads(text)
            except Exception as e:
                print(f"FAIL ({e})")
                stats['errors'] += 1
                continue

            name_raw = parsed.get('client_name') or ''
            week     = parsed.get('week_start', '')
            print(f"name={name_raw!r}  week={week}")
            stats['forms'] += 1

            cid, cname, score = match_client(name_raw, clients)
            if not cid:
                print(f"    ⚠️  No client match (score={score:.2f}) — skipping DB write")
                stats['no_match'] += 1
                continue

            print(f"    → {cname} (score={score:.2f})")

            # Show what was parsed
            for day, meals in parsed.get('days',{}).items():
                non_null = {k:v for k,v in meals.items() if v}
                if non_null:
                    print(f"       {day}: {non_null}")

            # Save to DB
            if conn:
                rows = 0
                for day in ['M','T','W','TH','F','SA']:
                    meals = parsed.get('days',{}).get(day,{})
                    if any(v for v in meals.values()):
                        conn.execute("""
                            INSERT OR REPLACE INTO client_menus
                            (client_id, client_name, week_start, day,
                             salad, soup, main, side,
                             confidence, source_pdf, ocr_engines)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?)
                        """, (cid, cname, week, day,
                              meals.get('salad'), meals.get('soup'),
                              meals.get('main'),  meals.get('side'),
                              0.95, pdf.name, 'claude_vision'))
                        rows += 1
                conn.commit()
                print(f"    ✅  Saved {rows} day row(s)")
                stats['saved'] += rows

            time.sleep(0.8)  # rate limit

    except Exception as e:
        print(f"  ERROR: {e}")
        stats['errors'] += 1
        continue

    newly_done.add(str(pdf))

if conn:
    conn.close()

# Update done log
done.update(newly_done)
done_log.write_text(json.dumps(sorted(done), indent=2))

print(f"""
╔══════════════════════════════════════════════════════╗
║  Summary                                            ║
╚══════════════════════════════════════════════════════╝
  PDFs processed:     {stats['pdfs']}
  Client forms read:  {stats['forms']}
  DB rows saved:      {stats['saved']}
  No client match:    {stats['no_match']}
  Errors:             {stats['errors']}
""")
PYEOF

echo ""
read -n 1 -p "Press any key to close..."
