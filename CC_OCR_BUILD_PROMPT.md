# GOJ OCR System — Optimal Build Prompt
# Use this prompt verbatim to instruct Claude to build the full OCR system.
# Last updated: May 2026 | System: Garden of Joy Adult Day Care, Brooklyn NY

---

## YOUR TASK

Build the complete two-stack OCR system for Garden of Joy (GOJ) adult day care. Everything you need is described below. Do not ask clarifying questions — all decisions have already been made. Build in the exact order specified. All new files you create must start with `CC`.

---

## SYSTEM CONTEXT

**Organization:** Garden of Joy (GOJ), adult day care, Brooklyn NY. ~425 active clients.

**What OCR does:** Clients submit 2-page weekly Russian-language menu forms (checkboxes for meals Mon–Sat). Allen scans these at the office scanner and emails them to `atigerclawai@gmail.com`. REX detects the emails via Gmail API, downloads the PDFs, and runs OCR to extract each client's meal selections for the upcoming service week, storing results in `client_menus` in SQLite.

**Key paths:**
- REX root: `~/Desktop/REX/`
- REX venv Python: `~/Desktop/REX/.venv/bin/python3`
- Database: `~/Documents/goj files/dashboard/auth_tracker.db`
- Menus folder (PDFs land here): `~/Documents/goj files/dashboard/documents/menus/`
- Locks folder: `~/Desktop/REX/locks/` (create if missing)
- Paperless-NGX: `http://100.99.86.60:8000` | Token: `583e819be1146b96b935007c6ad7f584a3a1b1b7`
- Telegram config: `~/Desktop/REX/rex_rexxie_telegram_config.json`

**Existing OCR files (do NOT rename):**
- `~/Desktop/REX/goj_menu_ocr.py` → **HYBRID stack** (Claude Vision primary, Tesseract secondary, Paperless archival)
- `~/Desktop/REX/goj_menu_consensus_ocr.py` → **LOCAL ONLY stack** (Tesseract + Paperless only, no cloud calls)

**Dashboard:** Flask app at `~/Documents/goj files/dashboard/app.py`, port 8080.
**Watcher:** `~/Desktop/REX/backend/rex_menu_scan_watcher.py` — polls Gmail every 5 min.
**Rexxie OCR trigger:** `~/Desktop/REX/backend/rex_rexxie.py` around line 433 — MENU BLAST command.

---

## LOCKED RULES (never change these without operator approval)

1. **Week start rule:** Any menu PDF scanned during the current week is ALWAYS assigned to NEXT WEEK's service period (next Monday). The `Неделя:` field on the form is stored in notes but never used to determine `week_start`. The only override is `force_week_start='YYYY-MM-DD'` (operator use only, must be a Monday ISO string). This rule is already implemented in `goj_menu_ocr.py::infer_week_start()` — replicate it exactly in `CC_ocr_worker.py`.

2. **CC naming:** All new files must start with `CC`.

3. **Larry route exclusion:** Never include client named Larry in any transport/driver route lists. (Unrelated to OCR but never cross-contaminate.)

4. **No duplicate DB writes:** Before any INSERT into `client_menus`, check for existing row with same `(client_id, week_start, day)`. Skip if exists.

5. **PHI stays local:** LOCAL ONLY mode must never call any external API. No Anthropic, no Google Drive, no cloud anything. Paperless-NGX at 100.99.86.60 is on the local Tailscale network and is allowed.

---

## WHAT TO BUILD — IN ORDER

### STEP 1: `CC_menu_constants.py`
Single source of truth for all menu items. Both engine stacks import from here. Place at `~/Desktop/REX/CC_menu_constants.py`.

Use EXACTLY these items (confirmed from real scanned forms — do not alter):

```python
SALADS = [
    "Салат из баклажан", "Салат весенний", "Винегрет", "Салат Днестр",
    "Квашеная капуста", "Оливье", "Свекла", "Селедка", "Сало"
]

SOUPS = [
    "Борщ зеленый", "Борщ красный", "Грибной суп", "Куриный суп",
    "Овощной суп", "Харчо", "Гороховый суп"
]

# Page 1 mains (top half of form)
MAINS_P1 = [
    "Баса с помидорами под сыром", "Блины с мясом", "Блины с творогом",
    "Вареники с картошкой", "Голубцы", "Гуляш",
]

# Page 2 mains (bottom half / continuation)
MAINS_P2 = [
    "Дорадо запеченая", "Жульен", "Котлеты куриные", "Курица в терияки соусе",
    "Куриные крылышки", "Пельмени", "Поперечка", "Салмон",
    "Свиная отбивная", "Цыпленок табака", "Чалахач", "Чебуреки",
    "Шницель куриный",
]

ALL_MAINS = MAINS_P1 + MAINS_P2

SIDES = [
    "Тушеная капуста", "Картошка по деревенски", "Пюре", "Гречка",
    "Паста", "Жареная картошка", "Стручковая фасоль",
]

# Day column abbreviations (form uses Russian, we store as English codes)
DAYS = ["M", "T", "W", "TH", "F", "SA"]

DAY_MAP = {
    "ПН": "M",  "Пн": "M",  "Пон": "M",
    "ВТ": "T",  "Вт": "T",  "Втор": "T",
    "СР": "W",  "Ср": "W",
    "ЧТ": "TH", "Чт": "TH", "Четв": "TH",
    "ПТ": "F",  "Пт": "F",  "Пят": "F",
    "СБ": "SA", "Сб": "SA", "Суб": "SA",
}

# Checkmark characters recognized as "checked"
CHECKMARKS = {'✓', 'x', 'X', 'v', 'V', '+', '√', '☑', 'L', 'л', '*'}
```

Then update `goj_menu_ocr.py` and `goj_menu_consensus_ocr.py` to import from `CC_menu_constants` instead of defining their own lists.

---

### STEP 2: `CC_ocr_queue.py`
Job queue manager. Place at `~/Desktop/REX/CC_ocr_queue.py`.

**Creates this table in `auth_tracker.db` if it doesn't exist:**
```sql
CREATE TABLE IF NOT EXISTS ocr_jobs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path    TEXT NOT NULL,
    file_hash    TEXT NOT NULL,
    mode         TEXT NOT NULL DEFAULT 'hybrid',  -- 'local' or 'hybrid'
    status       TEXT NOT NULL DEFAULT 'pending', -- pending/running/done/error
    created_at   TEXT DEFAULT (datetime('now')),
    started_at   TEXT,
    completed_at TEXT,
    error        TEXT,
    inserted     INTEGER DEFAULT 0,
    skipped      INTEGER DEFAULT 0,
    UNIQUE(file_hash, mode)  -- prevent duplicate jobs for same file+mode
);
```

**Public functions:**
- `enqueue_scan(file_path: str, mode: str = "hybrid") -> int | None` — computes SHA-256 of file, inserts row, returns job id. Returns None if already queued/done.
- `get_next_pending() -> dict | None` — returns oldest pending job as dict, marks it `running`, sets `started_at`
- `mark_done(job_id, inserted, skipped)` — sets status=done, completed_at, counts
- `mark_error(job_id, error_msg)` — sets status=error, error field
- `get_queue_status() -> dict` — returns counts by status for dashboard display
- `reset_stuck_jobs()` — any job in `running` state for >30 min gets reset to `pending` (handles crashes)

---

### STEP 3: `CC_ocr_worker.py`
The worker. Place at `~/Desktop/REX/CC_ocr_worker.py`.

**Behavior:**
1. Call `reset_stuck_jobs()` first
2. Check `~/Desktop/REX/locks/system.lock` — if exists and is less than 10 min old, print "system locked — another agent running, exiting" and exit(0). Do not error. Do not wait.
3. Create `~/Desktop/REX/locks/ocr_worker.lock` (write current PID). If lock exists and process is still running (check PID), exit(0).
4. Pull next pending job from queue
5. If no pending job, remove own lock and exit(0)
6. Lazy-import the engine module ONLY at this point (inside the job loop, not at module level)
7. Run the appropriate engine based on `job['mode']`:
   - `'local'` → call `process_pdf_local(pdf_path)` from `goj_menu_consensus_ocr`
   - `'hybrid'` → call `process_menu_pdf(pdf_path)` from `goj_menu_ocr`
8. Apply `infer_week_start()` — the locked rule lives here (copy from `goj_menu_ocr.py` exactly)
9. Mark job done/error with counts
10. Send Telegram notification (success or failure) using `_notify_telegram()`
11. Loop back to step 4 — continue until queue empty
12. Remove `~/Desktop/REX/locks/ocr_worker.lock` and exit(0)

**`_notify_telegram(msg)`** — reads `rex_rexxie_telegram_config.json`, sends to `owner_chat_id`. Silent fail if config missing.

**CLI interface:**
```
python3 CC_ocr_worker.py              # process all pending (default mode from queue)
python3 CC_ocr_worker.py --mode local # enqueue+process specific mode
python3 CC_ocr_worker.py --file path/to/scan.pdf --mode hybrid
python3 CC_ocr_worker.py --status    # print queue status and exit
```

---

### STEP 4: Fix `goj_menu_consensus_ocr.py` (LOCAL ONLY — 4-line change only)

In `process_pdf()`, remove the Claude Vision call. Change lines ~913–919 from:
```python
# Engine 4: Claude Vision...
_claude_results = run_claude_vision_ocr(pdf_path)
ocr_claude = _claude_results[0] if _claude_results and _claude_results[0] else None
if ocr_claude:
    engines_used.append('claude_vision')
print("OK" if ocr_claude else "FAIL")
```
To:
```python
# Engine 4: Claude Vision — DISABLED in LOCAL ONLY mode (PHI stays on-machine)
ocr_claude = None
```

Also update the function docstring to say: "LOCAL ONLY mode. Active engines: Tesseract (on-machine), Paperless-NGX (Tailscale LAN). No external API calls."

Add `from CC_menu_constants import SALADS, SOUPS, ALL_MAINS, SIDES, DAYS, DAY_MAP, CHECKMARKS` at top and remove the inline list definitions.

Also rename the main entry function to `process_pdf_local()` (keep `process_pdf()` as an alias for backward compatibility so existing callers don't break).

---

### STEP 5: Fix `goj_menu_ocr.py` (HYBRID — constants only)

Add `from CC_menu_constants import SALADS, SOUPS, MAINS_P1, MAINS_P2, ALL_MAINS, SIDES, DAYS, DAY_MAP, CHECKMARKS` and remove the inline list definitions. No other changes — this file is otherwise correct.

---

### STEP 6: Fix `backend/rex_menu_scan_watcher.py`

Replace `_trigger_ocr_on_files()` — instead of calling the OCR script directly, call:
```python
from CC_ocr_queue import enqueue_scan
for pdf_path in pdf_paths:
    enqueue_scan(str(pdf_path), mode="hybrid")
```

Then after enqueuing, launch the worker in a subprocess (non-blocking):
```python
subprocess.Popen(
    [str(REX_DIR / ".venv" / "bin" / "python3"), str(REX_DIR / "CC_ocr_worker.py")],
    close_fds=True
)
```

Remove `OCR_SCRIPT` constant. Update the Telegram message from "running all 4 OCR engines" to "queued for OCR processing."

---

### STEP 7: Fix `backend/rex_rexxie.py` (MENU BLAST)

Around line 433, replace the direct subprocess call to `goj_menu_consensus_ocr.py` with:
```python
from CC_ocr_queue import enqueue_scan
for pdf in pdf_files:
    enqueue_scan(str(pdf), mode="hybrid")
subprocess.Popen([
    str(Path.home() / "Desktop" / "REX" / ".venv" / "bin" / "python3"),
    str(Path.home() / "Desktop" / "REX" / "CC_ocr_worker.py"),
], close_fds=True)
```

Update `ack_msg` to remove the "4 OCR engines" language — say "MENU BLAST queued — worker running in background."

---

### STEP 8: Fix `dashboard/app.py` — THREE changes

**Change A — `/api/ocr/run-folder` (line ~8435):** Fix Python interpreter path.
Change `~/debate-chamber/.venv/bin/python3` to `~/Desktop/REX/.venv/bin/python3`.

Also replace the direct `subprocess.run` to `goj_menu_ocr.py` with:
```python
from CC_ocr_queue import enqueue_scan
mode = (request.get_json() or {}).get('mode', 'hybrid')
for pdf in sorted(OCR_MENUS_DIR.glob('*.pdf')):
    enqueue_scan(str(pdf), mode=mode)
subprocess.Popen([str(venv_py), str(Path.home() / 'Desktop' / 'REX' / 'CC_ocr_worker.py')],
                 close_fds=True)
return json.dumps({'ok': True, 'message': f'OCR queued ({mode} mode)'})
```

**Change B — `/api/ocr/run` (line ~4013):** This route calls `process_menu_batch.py` which doesn't exist. Remove this entire route. The `/api/ocr/run-folder` route is the correct one.

**Change C — Add mode param to OCR Command Center template call:** The `/api/ocr/run-folder` POST from `ocr_command.html` should pass `{"mode": selectedMode}` where `selectedMode` is from the new toggle (see UI change below). If no toggle exists yet, default to `"hybrid"`.

---

### STEP 9: Archive `core/`

Move `~/Desktop/REX/core/` to `~/Desktop/REX/_archive/lucy_core_ghs_hardening/`. This is the LUCY CORE directory (ocr_schema.py, ocr_mirror.py, ocr_policy_bridge.py, goj_ocr_wrapper.py, alert_bus.py, etc.). It is not wired to anything that runs. Leaving it in the active codebase risks accidental import that would quarantine all OCR results containing `client_name`.

```bash
mkdir -p ~/Desktop/REX/_archive/
mv ~/Desktop/REX/core/ ~/Desktop/REX/_archive/lucy_core_ghs_hardening/
```

---

### STEP 10: Add mode toggle to OCR dashboard UI (optional, do last)

In `ocr_command.html`, add a toggle near the "Run OCR" button:
```html
<div class="ocr-mode-toggle">
  <label>OCR Mode:</label>
  <button class="mode-btn active" data-mode="hybrid" onclick="setMode('hybrid')">Hybrid</button>
  <button class="mode-btn" data-mode="local" onclick="setMode('local')">Local Only</button>
</div>
```

Pass `mode` in the fetch body when calling `/api/ocr/run-folder`.

---

## WHAT YOU MUST NOT CHANGE

- `infer_week_start()` logic in `goj_menu_ocr.py` — the locked rule is correct, do not alter
- `match_client_name()` fuzzy matching (cutoff 0.55, last-name boost +0.15) — correct as-is
- `insert_menu_row()` duplicate check — correct as-is
- `submit_to_paperless()` — skip integer tag PKs (already handles Paperless API correctly)
- `PROCESSED_LOG` deduplication in `goj_menu_ocr.py` — keep this, the queue adds a second layer of dedup on top
- Telegram config path `rex_rexxie_telegram_config.json` — do not change
- All existing dashboard routes except the two specified above
- DB table `client_menus` schema — do not alter

---

## DB SCHEMA REFERENCE

`client_menus` table (existing, do not alter):
```sql
id, client_id, client_name, week_start, day, salad, soup, main, side,
confidence, source_pdf, page_num, source, notes, created_at
```

`clients` table (read-only for matching):
```sql
client_id, name, active (1=active)
```

---

## ENGINE BEHAVIOR REFERENCE

**HYBRID (`goj_menu_ocr.py::process_menu_pdf`):**
- Page classification: pdfplumber → PyMuPDF fallback
- Engine 1 (primary): Claude Vision via `api.anthropic.com/v1/messages`, model `claude-opus-4-6`
  - Sends base64 JPEG of each page with structured extraction prompt
  - Returns JSON with `client_name`, `week_indicator`, `checks` per day
  - If confidence ≥ 0.90: skip Tesseract entirely (fast path)
- Engine 2 (validator): Tesseract — header region crop only (top 22% of page 1)
  - Used only for name/week cross-check when Vision confidence < 0.90
- Engine 3 (archival): Paperless-NGX upload — result not used in consensus
- Name matching: `difflib.SequenceMatcher` against active clients, cutoff 0.55, last-name boost +0.15
- Unmatched names: Telegram alert via `_notify_unmatched()`

**LOCAL ONLY (`goj_menu_consensus_ocr.py::process_pdf_local`):**
- Engine 1: Tesseract with `rus+eng`, PSM 6, DPI 300, contrast/sharpen preprocessing
  - Custom tessdata at `~/.tesseract_data/tessdata`
- Engine 2: Paperless-NGX text extraction (Tailscale LAN only)
- Google Drive: permanently disabled
- Claude Vision: permanently disabled (after your fix in Step 4)
- Voting: `consensus_vote()` — if Claude Vision absent, Tesseract vs Paperless vote
- Learning corrections: `goj_doc_patterns.json` (known OCR error mappings)

---

## WHAT'S MISSING (gaps you need to fill)

These items are NOT yet built and are required for the system to work end-to-end:

1. `CC_menu_constants.py` — doesn't exist yet
2. `CC_ocr_queue.py` — doesn't exist yet, `ocr_jobs` table doesn't exist yet
3. `CC_ocr_worker.py` — doesn't exist yet
4. The `~/Desktop/REX/locks/` directory — may not exist, create it
5. `goj_menu_consensus_ocr.py` still calls Claude Vision (must be removed)
6. Watcher still calls OCR directly instead of enqueuing
7. Rexxie still calls the wrong script directly
8. Dashboard `/api/ocr/run-folder` uses wrong venv path
9. Dashboard dead route `/api/ocr/run` still exists
10. `core/` directory is not archived — risk of accidental import
11. Both engine files still define their own menu item lists (should import from CC_menu_constants)

---

## VERIFICATION AFTER BUILD

Run these checks after completing all steps:

```bash
# 1. Queue table exists
sqlite3 ~/Documents/goj\ files/dashboard/auth_tracker.db ".schema ocr_jobs"

# 2. Worker exits cleanly on empty queue
python3 ~/Desktop/REX/CC_ocr_worker.py --status

# 3. Enqueue a test file
python3 -c "from CC_ocr_queue import enqueue_scan; print(enqueue_scan('/tmp/test.pdf', 'local'))"

# 4. Constants import correctly from both engine files
python3 -c "from goj_menu_ocr import SALADS; print(len(SALADS))"
python3 -c "from goj_menu_consensus_ocr import SALADS; print(len(SALADS))"

# 5. Claude Vision NOT in consensus_ocr process_pdf_local
grep -n "claude" ~/Desktop/REX/goj_menu_consensus_ocr.py | grep -v "DISABLED\|#\|disabled"

# 6. No imports of core/ in active files
grep -r "from core\." ~/Desktop/REX/*.py ~/Desktop/REX/backend/*.py

# 7. Watcher no longer calls OCR script directly
grep -n "OCR_SCRIPT\|goj_menu_consensus_ocr\|subprocess.*ocr" ~/Desktop/REX/backend/rex_menu_scan_watcher.py
```

All 7 checks should pass cleanly. If any fail, fix before moving on.
