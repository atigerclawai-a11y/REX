# GOJ — LOCKED EXTRACTION PASS: Prior Claude Work Only
**Generated:** April 22, 2026  
**Type:** Forensic inventory — no new design, no new architecture  
**Scope:** All Claude work on GOJ / Rexxie / OCR / Sheets from prior sessions  

---

## SECTION A — PRIOR CLAUDE IMPLEMENTATIONS

### A1. Flask Dashboard (`app.py`)
- **Purpose:** Web dashboard for GOJ operations (clients, auth, attendance, menus, billing)
- **Type:** Code + routes
- **Path:** `~/Documents/goj files/dashboard/app.py`
- **Status:** Fully built, running on port 8080
- **Confidence:** HIGH
- **Notes:**
  - v1.2 April 2026 — version string locked in code
  - DB_PATH: `Path.home() / 'Documents' / 'goj files' / 'auth_tracker.db'` (root level, NOT `/dashboard/`)
  - MENUS_BASE: `Path(__file__).parent / 'documents' / 'menus'`
  - Claude added CORS headers via `@app.after_request` for all `/api/*` routes
  - Vault context error fixed: `_ensure_vault_table()` wrapped in `with app.app_context()`
  - Monthly attendance route built: queries `att_map`, `change_map`, `month_days`, `color_cfg`
  - `/api/ocr/run` and `/api/ocr/flags` endpoints added
  - `/attendance/colors` POST route (chairman-only) writes to `~/Desktop/REX/attendance_colors.json`
  - pdfplumber guarded with try/except so dashboard doesn't crash if absent
  - Billing + locks added via `add_billing_and_locks.py`

### A2. `attendance_log.html`
- **Purpose:** Monthly attendance view with color-coded cells, schedule trail, chairman color editor
- **Type:** Code (Jinja2 template)
- **Path:** `~/Documents/goj files/dashboard/templates/attendance_log.html`
- **Status:** Fully built (syntax-checked), installed
- **Confidence:** HIGH
- **Features:**
  - Monthly tabs Jan–Dec + year navigation
  - Legend bar with color-coded dots + chairman edit button
  - CSS variables: `--c-present`, `--c-absent`, `--c-changed-from`, `--c-changed-to`, `--c-scheduled`, `--c-not-sched`
  - Schedule Trail slide-out panel (`#trail-panel`) with search input
  - Color editor modal (chairman-only) with live preview + AJAX save

### A3. `goj_daily_scheduler.py`
- **Purpose:** All scheduled GOJ operations (morning report, kitchen sheets, changes/routes, nightly rundown, weekly email)
- **Type:** Code
- **Path:** `~/Desktop/REX/goj_daily_scheduler.py`
- **Status:** Fully built, syntax-checked, launchd plists installed
- **Confidence:** HIGH
- **6 jobs:**
  - `morning_report` → 7:30am daily (Mon–Sat)
  - `kitchen_sheets` → 10:30am daily
  - `changes_routes` → 3:15pm daily (Mon–Sat)
  - `missing_menus_fri` → 8:30pm Fridays
  - `nightly_rundown` → 9:00pm daily (Mon–Sat)
  - `weekly_email_fri` → 9:00pm Fridays
- **DB path used:** `~/Documents/goj files/dashboard/auth_tracker.db` (CHECK — may differ from locked params)
- **Delivery:** All via Rexxie Telegram bot (reads `rex_rexxie_telegram_config.json`)

### A4. launchd Plists (6 scheduler + support)
- **Path:** `~/Desktop/REX/launchd/`
- **Installed via:** `install_scheduler.command`
- **Status:** Built and installed
- **Confidence:** HIGH
- **Plists created by Claude:**
  - `com.goj.scheduler.morning_report.plist` — 7:30am
  - `com.goj.scheduler.kitchen_sheets.plist` — 10:30am
  - `com.goj.scheduler.changes_routes.plist` — 3:15pm Mon–Sat
  - `com.goj.scheduler.missing_menus_fri.plist` — 8:30pm Fri
  - `com.goj.scheduler.nightly_rundown.plist` — 9:00pm Mon–Sat
  - `com.goj.scheduler.weekly_email_fri.plist` — 9:00pm Fri
  - `com.rex.backend.plist` — REX FastAPI always-on
- **venv path used in all plists:** `/Users/mainsobhelper/debate-chamber/.venv/bin/python3`
- **Username assumed:** `mainsobhelper`

### A5. `goj_menu_consensus_ocr.py`
- **Purpose:** 4-engine OCR pipeline for Russian Olimp menu PDFs → `client_menus` table + flags queue
- **Type:** Code
- **Path:** `~/Desktop/REX/goj_menu_consensus_ocr.py`
- **Status:** Fully built; **Google Drive (Engine 2) currently DISABLED in code** due to PHI concern; Claude Vision (Engine 4) IS active
- **Confidence:** HIGH
- **Active engines in current code state:**
  1. Tesseract (local)
  2. Google Drive — **DISABLED** (`print("Engine 2: Google Drive — DISABLED")`)
  3. Paperless-ngx (Tailscale: `http://100.99.86.60:8000`)
  4. Claude Vision (Anthropic API)
- **Output targets:** `client_menus` table in `auth_tracker.db` (high confidence) + `goj_menu_flags_queue.json` (low confidence)
- **Claude Vision fast-path:** if Claude Vision confidence ≥ 0.90, it bypasses voting and is trusted directly
- **Confidence thresholds:** auto_accept=0.75, flag=0.50
- **Learning file:** `~/Desktop/REX/goj_menu_learning.json`

### A6. `download_menu_pdfs_impl.py`
- **Purpose:** Downloads menu PDFs from Gmail to `~/Documents/goj files/documents/menus/`
- **Type:** Code
- **Path:** `~/Desktop/REX/download_menu_pdfs_impl.py`
- **Status:** Built; **uses hardcoded Gmail message IDs — only downloads specific March 30 + April 3, 2026 files**
- **Confidence:** HIGH
- **Token search path order:**
  1. `~/Desktop/REX/gmail_token.json`
  2. `~/Desktop/REX/gmail_token.json` (same)
  3. `~/.config/google-gmail-mcp/credentials.json`
  4. `~/Library/Application Support/google-gmail-mcp/token.json`
  5. `~/Library/Application Support/Claude/gmail_token.json`
  6. `~/.gmail_token.json`
- **Hardcoded Gmail message IDs:**
  - March 30 scans: `19d5720c403b2736`, `19d56572c638493f`, `19d5610067936f9f`
  - April 3 scans: `19d5604f33622807`, `19d560489c99e9e9` + more
- **Does NOT dynamically search Gmail for new emails** — must be manually updated for new weeks

### A7. `generate_kitchen_sheet.py`
- **Purpose:** Daily kitchen prep PDF (SALADS + SOUPS / MAIN+SIDE combos)
- **Type:** Code
- **Path:** `~/Desktop/REX/generate_kitchen_sheet.py`
- **Status:** Built, syntax-checked
- **Confidence:** HIGH
- **KEY RULE (locked):** Main and side are ALWAYS combined as one pair in "MAIN DISH + SIDE COMBOS" — never counted separately
- **Source:** Queries `client_menus` in `auth_tracker.db`

### A8. `generate_distribution_sheet.py`
- **Purpose:** Per-shift daily distribution PDF (alphabetical by name, NO MENU clients in red)
- **Type:** Code
- **Path:** `~/Desktop/REX/generate_distribution_sheet.py`
- **Status:** Built, syntax-checked
- **Confidence:** HIGH
- **Columns:** No | Client Name | Salad | Soup | Main + Side | ✓ checkbox
- **Output filename:** `distribution_shift{N}_{YYYY-MM-DD}.pdf`

### A9. `rex_rexxie_telegram_bot.py` (GOJ additions)
- **Purpose:** Rexxie personal Telegram bot — GOJ absence handler + MENU BLAST + MENU OCR added at v1.2
- **Type:** Code patches added to Rexxie personal bot
- **Path:** `~/Desktop/REX/rex_rexxie_telegram_bot.py`
- **Status:** Built + syntax-checked; **NOTE: MENU BLAST has been partially migrated to `rex_telegram_bot.py`**
- **Confidence:** HIGH
- **GOJ features added (v1.2):**
  - `_detect_absence()` — keyword-based attendance change detection
  - `_extract_client_name()` — heuristic name extraction from message
  - `_log_absence_to_db()` — writes to `attendance_log` + `pending_schedule_changes`
  - Inline keyboard: [1-Time Change] [Recurring Change] [❓ Not Sure] [↩️ UNDO]
  - `_menu_blast()` — builds full MENU BLAST report from `auth_tracker.db`
  - `MENU OCR` command — triggers `goj_menu_consensus_ocr.py`
  - `MENU FLAGS` command — reads `goj_menu_flags_queue.json`
  - `_check_friday_menu_blast()` — **NOTE: comments at lines 2529 + 3435 say this was MOVED to rex_telegram_bot.py**
- **VLAD_CHAT_ID and MISHA_CHAT_ID:** Both are `None` (placeholder — not yet set)

### A10. `goj_menu_flag_reporter.py` + `goj_menu_confirm_handler.py`
- **Purpose:** OCR flag Telegram review loop (send flags → Kato replies → corrections applied)
- **Type:** Code
- **Paths:** `~/Desktop/REX/goj_menu_flag_reporter.py`, `~/Desktop/REX/goj_menu_confirm_handler.py`
- **Status:** Built
- **Confidence:** HIGH
- **Reply format:** `menu fix: flag_id=42 confirm` / `menu fix: flag_id=42 name=John Smith` / `menu fix: flag_id=42 skip`
- **Polling offset tracking:** `.goj_menu_tg_offset` file

### A11. `goj_signin_ocr_processor.py`
- **Purpose:** OCR sign-in sheet PDFs → populate `attendance_log` table
- **Type:** Code
- **Path:** `~/Desktop/REX/goj_signin_ocr_processor.py`
- **Status:** Built
- **Confidence:** HIGH
- **Identification:** Detects sign-in sheets by keywords "SIGN-IN SHEET", "Total present", "GARDEN OF JOY ADULT DAY CARE CENTER"
- **Rejects:** Russian food words, kitchen/driver sheets
- **Matching:** `difflib` fuzzy at cutoff 0.55; 70% threshold for confirmed DB insert

### A12. `goj_attendance_report.py`
- **Purpose:** Professional PDF attendance report for Molina SWH audit
- **Type:** Code
- **Path:** `~/Desktop/REX/goj_attendance_report.py`
- **Status:** Built
- **Confidence:** HIGH

### A13. GOJ Logo + GHS Logo
- **GOJ Logo (flower PNG):** `~/Documents/goj files/dashboard/static/img/goj_logo.png` — top-right all pages, 44px in nav, 160px on login
- **GHS Logo (black triangle PNG):** `~/Documents/goj files/dashboard/static/ghs_logo.png` — top-left all pages
- **HOT-SWAP:** Replace files in place to update everywhere instantly (no code change)
- **Status:** Implemented in all 13 dashboard templates
- **Confidence:** HIGH

### A14. `SWH_Client_Binder.pdf`
- **Purpose:** 136-page compiled PDF binder for Molina SWH audit (22 of 24 clients documented)
- **Path:** `~/Desktop/REX/SWH_Client_Binder.pdf`
- **Status:** Fully built
- **Confidence:** HIGH
- **Missing clients:** Halas Teresa + Krupnik Raisa (divider-only, flagged MISSING)

### A15. `goj_daily_scheduler.py` — OCR auto-trigger
- **Purpose:** On Fridays, if menu PDFs are present and `client_menus` is empty for that week → auto-triggers OCR
- **Type:** Logic within `job_missing_menus_fri` → `_maybe_trigger_ocr()`
- **Status:** Built
- **Confidence:** HIGH

### A16. Daily Sheet Templates (locked PDFs)
- `TEMPLATE_distribution.pdf` — `~/Desktop/REX/`
- `TEMPLATE_kitchen.pdf` — `~/Desktop/REX/`
- `TEMPLATE_signin.pdf` — `~/Desktop/REX/`
- `TEMPLATE_driver.pdf` — `~/Desktop/REX/`
- **Status:** Present on disk, used as reference/blank templates
- **Confidence:** HIGH (templates exist); **population logic for distribution+kitchen was built in separate Python generators**

### A17. Rexxie Personal Profile (rexxie.db)
- **Purpose:** Injected personal operating profile into Rexxie's memory DB
- **Content:** Blunt feedback, work/org first, never surface emotions, good day = operational smoothness
- **Path:** `~/Desktop/REX/rexxie.db`
- **Status:** Injected April 2026
- **Confidence:** HIGH

### A18. Gold Health Systems Rexxie (`private_confidant_gold.py`)
- **Purpose:** New Rexxie v3.3.0 — personal confidant, 3-lane, fully local Ollama, separate from GOJ operations
- **Path:** `~/Desktop/Gold_Health_Systems/private_confidant_gold.py`
- **Status:** Built v1.3.1, RTF encoding issue fixed
- **Confidence:** HIGH
- **Architecture:** Ollama (local), SQLite `rexxie_memory.db`, token from `.rexxie_config.json` or env var
- **Completely separate bot token** from REX business bot and old Rexxie bot

---

## SECTION B — PRIOR CLAUDE KNOWLEDGE / ASSUMPTIONS

### B1. Database location
- **Assumption:** `auth_tracker.db` is at `~/Documents/goj files/auth_tracker.db` (root level, NOT in `dashboard/`)
- **Affects:** `app.py` (correct), `goj_daily_scheduler.py` (may use different path), `rex_rexxie_telegram_bot.py` (was fixed from wrong path)
- **Required for correct operation:** YES
- **Current confusion risk:** HIGH — the working doc references `goj files/dashboard/auth_tracker.db` as the actual location in some places, and `goj files/auth_tracker.db` in locked parameters. A second DB (`goj.db`) also exists in the dashboard folder.

### B2. `client_menus` column is `main`, not `main_dish`
- **Assumption:** Column name is `main`
- **Affects:** All scripts that read/write client_menus (OCR, kitchen, distribution, dashboard, bot)
- **Required:** YES
- **Confusion risk:** HIGH — this was a recurring bug and was patched multiple times. If any new script or migration recreates the table with `main_dish`, everything breaks again.

### B3. `ocr_engines` column in `client_menus`
- **Assumption:** `goj_menu_consensus_ocr.py` creates `client_menus` with an `ocr_engines TEXT` column
- **Affects:** OCR writes
- **Required for correct operation:** Only if the DB was created by this script's `init_database()`
- **Confusion risk:** MEDIUM — LOCKED_PARAMETERS lists `client_menus` columns without `ocr_engines`. If the live DB doesn't have this column, every OCR write fails.

### B4. Days stored as short codes
- **Assumption:** `client_menus.day` stores `M`, `T`, `W`, `TH`, `F`, `SA` — NOT full names
- **Affects:** MENU BLAST, kitchen/distribution generators, attendance bot
- **Required:** YES
- **This was a known bug** — was fixed in the April 6 session

### B5. Menu forms are Olimp 2-page format
- **Assumption:** Each client gets a 2-page Russian menu form. Page 1: name + salads + soups + start of mains. Page 2: mains continued + sides.
- **Affects:** OCR page-pair processing logic
- **Required:** YES
- **Risk:** If forms change (different supplier, different layout), OCR anchors fail

### B6. Gmail account is `atigerclawai@gmail.com`
- **Assumption:** Allen Khiger scans menus and emails to this address
- **Affects:** Gmail OAuth token, download script
- **Required:** YES

### B7. venv is at `~/debate-chamber/.venv`
- **Assumption:** All Python work uses this venv, not `/usr/local/bin/python3` or system Python
- **Affects:** ALL launchd plists (all use `/Users/mainsobhelper/debate-chamber/.venv/bin/python3`)
- **Required:** YES — if venv path changes, ALL scheduler jobs stop working

### B8. Username is `mainsobhelper`
- **Assumption:** All hardcoded paths in launchd plists use this home directory
- **Required:** YES
- **Risk:** If user changes or machine migrates, all plists break

### B9. Paperless-ngx Tailscale IP
- **Assumption:** `http://100.99.86.60:8000` is the Paperless server address on Tailscale
- **Token:** `583e819be1146b96b935007c6ad7f584a3a1b1b7` (hardcoded in OCR script)
- **Risk:** This token was returning 401 as of last check. If IP changes (Tailscale rekey), OCR Engine 3 fails silently.

### B10. Download script does NOT dynamically poll Gmail
- **Assumption:** `download_menu_pdfs_impl.py` downloads a fixed set of hardcoded Gmail message IDs
- **Risk:** HIGH — each new week of menus requires manually adding new message IDs to the script. This is not automatic.

### B11. MISHA_CHAT_ID and VLAD_CHAT_ID are None
- **Assumption:** MENU BLAST is only fully functional to Kato. Vlad and Misha receive nothing until these are populated.
- **Affects:** `rex_rexxie_telegram_bot.py` MENU_BLAST_RECIPIENTS list

### B12. Rexxie uses getUpdates long-polling (not webhook)
- **Assumption:** Rexxie polls via `getUpdates` every 30s
- **Risk:** Running two bot instances with the same token causes 409 Conflict — each instance gets only half the updates

---

## SECTION C — TEMPLATES ALREADY CREATED OR IMPLIED

### C1. Olimp Russian Menu Form (source-of-truth item list)
- **Structure:** 2-page per client, handwritten checkmarks
- **Section anchors:** САЛАТЫ, СУПЫ, ГЛАВНОЕ БЛЮДО, ГАРНИР + day columns ПН/ВТ/СР/ЧТ/ПТ/СБ
- **Exact item lists hardcoded in `goj_menu_consensus_ocr.py`:**

| Category | Items |
|----------|-------|
| САЛАТЫ (9) | Салат из баклажан, Салат весенний, Винегрет, Салат Днестр, Квашеная капуста, Оливье, Свекла, Селедка, Сало |
| СУПЫ (7) | Борщ зеленый, Борщ красный, Грибной суп, Куриный суп, Овощной суп, Харчо, Гороховый суп |
| ГЛАВНОЕ (19) | Баса с помидорами под сыром, Блины с мясом, Блины с творогом, Вареники с картошкой, Голубцы, Гуляш, Дорадо запеченая, Жульен, Котлеты куриные, Куриные крылышки, Курица в терияки соусе, Пельмени, Поперечка, Салмон, Свиная отбивная, Цыпленок табака, Чалахач, Чебуреки, Шницель куриный |
| ГАРНИР (8) | Тушеная капуста, Картошка по деревенски, Пюре, Гречка, Паста, Рис, Жареная картошка, Без гарнира |

- **Day mappings:** Пон/Пн→M, Втор/Вт→T, Ср→W, Четв/Чт→TH, Пят/Пт→F, Суб/Сб→SA
- **Implemented in code:** YES (`goj_menu_consensus_ocr.py` lines 53–82)
- **Mismatch risk:** HIGH — abbreviated forms on real forms (e.g., "Борщ" vs "Борщ красный", "Свкл" vs "Свекла") may not fuzzy-match the stored full names

### C2. Kitchen Sheet Template (`TEMPLATE_kitchen.pdf`)
- **Format:** 2-page
  - Page 1 (COLD): SALADS section (6 rows) + SOUPS section (6 rows)
  - Page 2 (HOT): MAIN DISH + SIDE COMBOS (10 rows)
- **Columns:** # | Dish/Description | QTY | ✓ Prepped | ✓ Served | Section Total
- **KEY RULE:** Main + side always combined as a pair — never count separately
- **Population logic:** `generate_kitchen_sheet.py`
- **Implemented:** Template PDF exists; Python generator exists

### C3. Distribution Sheet Template (`TEMPLATE_distribution.pdf`)
- **Format:** 2-page, 32 clients (16 per page), large legible font
- **Columns:** No | Client Name | Salad | Soup | Main + Side | ✓ checkbox
- **Footer (page 2):** TOTAL | All dishes delivered | Staff signature
- **Source:** OCR-confirmed `client_menus` records for that day
- **Population logic:** `generate_distribution_sheet.py`
- **Implemented:** Template PDF exists; Python generator exists

### C4. Sign-in Sheet Template (`TEMPLATE_signin.pdf`)
- **Format:** Landscape, large font, signature space per row
- **Columns:** No | Name | Plan | TR | Time In | Signature
- **15 rows per page**
- **Dark navy header + blue column headers**
- **Footer on last page:** Total present + Staff signature + address
- **Population logic:** `build_signin_pdf.py` (built this session for Wednesday routes)

---

## SECTION D — OCR CONFIGURATION HISTORY

### D1. Engine Status (current as of code review)
| Engine | Method | Status in Code | Notes |
|--------|--------|---------------|-------|
| 1 — Tesseract | Local | ✅ Active | pytesseract + pdf2image |
| 2 — Google Drive | Cloud | ❌ Disabled | PHI risk — explicitly disabled in code |
| 3 — Paperless-ngx | Tailscale LAN | ✅ Active (if token valid) | Token was returning 401; may be stale |
| 4 — Claude Vision | Anthropic API | ✅ Active + trusted first | Fast-path if confidence ≥ 0.90 |

**NOTE: The script header at line 4-5 says "Google Drive OCR and Claude Vision OCR are DISABLED" — this is INCORRECT/stale.** Claude Vision IS called in `process_pdf()`. The header was not updated after Claude Vision was re-enabled.

### D2. Language Support
- Tesseract: English only (as of install; Russian language pack noted as needing install in Priority 3)
- Google Drive: Disabled (would have supported Russian)
- Paperless: Server-side OCR language depends on server config
- Claude Vision: Fully handles Russian (no configuration needed)

### D3. Handwriting Handling
- Tesseract: Poor (not configured for handwriting)
- Claude Vision: Designed to handle checkmarks + handwritten names on Olimp forms
- Checkmarks detected: `{'✓', 'x', 'X', 'v', 'V', '+', '√', '☑', 'L', 'л'}` (hardcoded in CHECKMARKS set)

### D4. Output Targets
- **High confidence (≥0.75):** Written to `client_menus` table in `auth_tracker.db`
- **Low confidence (<0.75 or needs_review):** Written to `goj_menu_flags_queue.json`
- **`GOJ_Menu_Orders.json`:** Currently empty (`{}`). This file exists but has no records. It was previously the primary JSON output but has been superseded by DB writes.

### D5. Was Russian menu OCR supposed to be operational?
**Yes, partially.** Claude Vision was the intended reliable engine for Russian. Tesseract was configured as a backup but only has English lang pack. Paperless was the third vote. The pipeline was declared operational in the working doc as of April 6 with 27 PDFs processed. However, the hardcoded item list uses full Russian names while real forms use abbreviations — this is a known accuracy gap.

---

## SECTION E — GMAIL / FILE INTAKE / SHEET GENERATION

### E1. Gmail Intake
- **Trigger:** Manual — operator runs `download_menu_pdfs_impl.py` directly OR double-clicks `RUN_MENU_VISION_INBOX.command`
- **Script:** `~/Desktop/REX/download_menu_pdfs_impl.py`
- **Token:** `~/Desktop/REX/gmail_token.json` (OAuth2 refresh token)
- **Account:** `atigerclawai@gmail.com`
- **Output:** PDFs to `~/Documents/goj files/documents/menus/`
- **DB registration:** Also inserts into `menus` table in `auth_tracker.db`
- **CRITICAL LIMITATION:** Downloads specific hardcoded Gmail message IDs only — does NOT search for new messages dynamically
- **Was intended to be automatic:** The launchd plist `com.rex.email-pdf-watcher.plist` exists, suggesting a watcher was planned, but the download script itself is hardcoded

### E2. OCR Trigger
- **Manual:** `RUN_MENU_VISION_INBOX.command` or `RUN_VISION_OCR.command`
- **Automatic:** `job_missing_menus_fri` in `goj_daily_scheduler.py` triggers OCR if PDFs present + `client_menus` empty for week
- **Output:** `client_menus` table + `goj_menu_flags_queue.json`

### E3. Kitchen + Distribution Sheet Generation
- **Trigger:** `job_kitchen_sheets` in `goj_daily_scheduler.py` at 10:30am
- **Script:** `generate_daily_sheets.py` → calls `generate_kitchen_sheet.py` + `generate_distribution_sheet.py`
- **Source data:** `client_menus` table for that service date
- **Output:** PDF sent via Rexxie Telegram to Kato
- **Requires:** OCR to have already run and populated `client_menus` for that date

### E4. Driver/Transport Sheets
- **Trigger:** `job_changes_routes` at 3:15pm OR `job_signin_driver_sheets` (separate plist at 3:00pm)
- **Note:** Two separate plists both run around 3pm with transport-related content (see Section F)

### E5. Attendance Sheets
- **Trigger:** `goj_signin_ocr_processor.py` — manual or via Rexxie
- **Source:** Scanned sign-in PDFs from Paperless/Gmail
- **Output:** `attendance_log` table in `auth_tracker.db`

---

## SECTION F — DUPLICATION RISK REPORT

### F1. ⚠️ CRITICAL: Duplicate 9pm Nightly Send
**What exists:**
- `com.goj.scheduler.nightly_rundown.plist` → `goj_daily_scheduler.py --job nightly_rundown` at **9:00pm Mon–Sat**
- `com.rex.evening-report.plist` → `goj_evening_report.py` at **9:00pm every day (7 days)**

**Risk:** Both fire at exactly 9:00pm. Kato receives two 9pm reports from different scripts. `goj_evening_report.py` is a separate script (not the scheduler) that may produce a different or conflicting rundown.

**Check before changing:** Does `com.rex.evening-report.plist` have `RunAtLoad=false` and is it actually loaded in launchctl? Are both producing output in logs?

### F2. ⚠️ HIGH: Duplicate 3pm Transport Alert
**What exists:**
- `com.goj.scheduler.changes_routes.plist` → `--job changes_routes` at **3:15pm Mon–Sat**
- `com.goj.scheduler.signin_driver_sheets.plist` → `--job signin_driver_sheets` at **3:00pm Mon–Fri**

**Risk:** Two jobs 15 minutes apart both relate to driver/transport. May send redundant messages to Kato or conflict on DB reads.

**Check:** What does `job_signin_driver_sheets` produce vs `job_changes_routes`?

### F3. ⚠️ HIGH: Duplicate Rexxie Instances
**What exists:**
- Old Rexxie: `rex_rexxie_telegram_bot.py` — `com.rex.rexxie-bot.plist` (KeepAlive=true, but uses PLACEHOLDER paths)
- New Rexxie Gold Health: `~/Desktop/Gold_Health_Systems/private_confidant_gold.py` — different bot token, local Ollama

**Memory says:** Gold Health Rexxie v3.3.0 REPLACES the old REX Rexxie entirely. But the old `com.rex.rexxie-bot.plist` still has `KeepAlive=true` with PLACEHOLDER paths. If this plist was ever loaded with real paths, two bots may be running on the same token → 409 Conflict.

**Check:** Run `launchctl list | grep rexxie`. Verify which token each uses. Confirm only one is active.

### F4. ⚠️ MEDIUM: MENU BLAST in Two Bot Files
**What exists:**
- `_menu_blast()` function still fully defined in `rex_rexxie_telegram_bot.py` (line 683)
- Comments at lines 2529 + 3435 say "MENU BLAST → moved to rex_telegram_bot.py (REX business bot)"
- `rex_telegram_bot.py` was not found to have `menu_blast` in grep output

**Risk:** MENU BLAST may exist in neither bot correctly, or in both. If it was "moved" but not deleted from Rexxie, it could fire from both bots.

**Check:** Search `rex_telegram_bot.py` for `menu_blast` or `MENU BLAST`.

### F5. ⚠️ MEDIUM: Duplicate DB Paths
**Two paths referenced in different places:**
- `~/Documents/goj files/auth_tracker.db` (LOCKED_PARAMETERS — root level)
- `~/Documents/goj files/dashboard/auth_tracker.db` (some scripts + working doc)
- A second DB `goj.db` also exists in the dashboard folder

**Risk:** Different scripts may be reading/writing different databases. Scheduler may read from one, dashboard from another.

**Check:** `ls -la "~/Documents/goj files/"auth_tracker.db "~/Documents/goj files/dashboard/"auth_tracker.db`

### F6. ⚠️ MEDIUM: `ocr_engines` Column
**What exists:**
- `goj_menu_consensus_ocr.py` `init_database()` creates `client_menus` with `ocr_engines TEXT`
- `LOCKED_PARAMETERS.md` lists `client_menus` columns WITHOUT `ocr_engines`
- The OCR script INSERT includes `ocr_engines`

**Risk:** If the live `auth_tracker.db` was created before the `ocr_engines` column was added (or by a different init), every OCR INSERT fails with "table has no column named ocr_engines".

**Check:** `SELECT * FROM client_menus LIMIT 1;` and verify column count + names.

### F7. ⚠️ MEDIUM: Hardcoded Gmail Message IDs
**What exists:** `download_menu_pdfs_impl.py` has ~8 hardcoded message IDs from March 30 + April 3, 2026.

**Risk:** An operator might add a dynamic Gmail search and not realize this script exists. Or they might run this script expecting it to download new menus, and nothing new appears.

**Check:** New weeks require manual message ID additions. There is no auto-discovery.

### F8. ⚠️ LOW: Launchd Plists Outside Claude-Managed Set
**Additional plists in `/launchd/` that Claude may not have built:**
- `com.goj.menuaudit.plist`
- `com.goj.rexcurriculum.plist`
- `com.goj.saturdayreview.plist`
- `com.goj.scanprocessor.plist`
- `com.rex.daily-backup.plist`
- `com.rex.email-pdf-watcher.plist`
- `com.rex.encrypted-backup.plist`
- `com.rex.nextday-preview.plist` (9:30pm — close to 9pm jobs)
- `com.rex.queue-processor.plist`
- `com.rex.reminders.plist`

**Risk:** Unknown overlap with Claude-built jobs. `com.rex.nextday-preview.plist` fires at 9:30pm running `generate_tomorrow.py` — this is a third nightly report.

---

## SECTION G — CURRENT ISSUE RELEVANCE

### G1. Operations Bot Instability
- **Prior Claude involvement:** HIGH — GOJ operations were patched into Rexxie personal bot (v1.2 additions)
- **What may matter:** The GOJ additions (`_detect_absence`, `_menu_blast`, absence keyboard) added significant complexity to a bot designed as a personal confidant. Session restoration was also fixed (REST session fix).
- **Evidence to check:** `~/Desktop/REX/logs/rexxie_bot_stdout.log` for crash patterns

### G2. Rexxie Duplicate Instance / 409
- **Prior Claude involvement:** HIGH — both old plist (`com.rex.rexxie-bot.plist` with KeepAlive=true) and new Gold Health bot were created by Claude
- **What may matter:** If old plist was ever installed with real paths AND new Gold Health bot is running → same token → 409 Conflict
- **Evidence to check:** `launchctl list | grep -i rexxie` on Mac. Compare bot tokens in `rex_rexxie_telegram_config.json` vs `.rexxie_config.json`.

### G3. OCR Menu Pipeline Failure
- **Prior Claude involvement:** HIGH
- **What may matter:**
  1. Script header says Vision disabled but Vision IS active → stale documentation causing confusion
  2. Hardcoded full Russian item names vs abbreviated form text (e.g. "Свкл" ≠ "Свекла")
  3. `ocr_engines` column may not exist in live DB
  4. Paperless token returning 401 → Engine 3 fails silently, votes skewed
- **Evidence to check:** Run OCR on a test PDF with verbose output. Check `client_menus` schema in live DB.

### G4. Russian Menu Extraction Accuracy
- **Prior Claude involvement:** HIGH
- **What may matter:** CHECKMARKS set handles common marks. But abbreviated Russian (Свкл, Вин, Борщ vs full names) won't match SALADS/SOUPS/MAINS/SIDES lists. Only Claude Vision handles this robustly because it reads context, not just keyword matching.
- **Implication:** With Google Drive disabled and Paperless possibly broken, only Tesseract + Claude Vision remain. Tesseract with English-only has near-zero accuracy on Russian. This means effectively ALL reliable OCR is Claude Vision alone.

### G5. `client_menus` / `ocr_engines` Mismatch
- **Prior Claude involvement:** HIGH (column added by Claude in OCR script init)
- **What may matter:** If live DB schema doesn't have `ocr_engines`, every OCR INSERT fails with a column error
- **Evidence to check:** `PRAGMA table_info(client_menus);` in SQLite on live DB

### G6. Duplicate 9pm Send
- **Prior Claude involvement:** HIGH (both `nightly_rundown` plist and `com.rex.evening-report.plist` were created by Claude)
- **What may matter:** `goj_daily_scheduler.py --job nightly_rundown` runs Mon–Sat. `com.rex.evening-report.plist` runs `goj_evening_report.py` 7 days. Both at 9:00pm.
- **Evidence to check:** `launchctl list | grep evening` and `grep nightly`. Check which are loaded.

### G7. Duplicate 3pm Transport Alert
- **Prior Claude involvement:** HIGH (both plists created by Claude)
- **What may matter:** `changes_routes` at 3:15pm and `signin_driver_sheets` at 3:00pm both involve transport. They are different jobs but close in time and could produce overlapping Telegram messages.
- **Evidence to check:** What does `job_signin_driver_sheets` produce? Is it still relevant or superseded by `changes_routes`?

---

## SECTION H — EXACT OUTPUT FORMAT

### 1. WHAT CLAUDE DEFINITELY ALREADY DID
- Built `app.py` Flask dashboard (v1.2) with CORS fix, vault fix, pdfplumber guard, OCR API endpoints, monthly attendance route
- Built `goj_daily_scheduler.py` with 6 jobs and all launchd plists
- Built `goj_menu_consensus_ocr.py` (4-engine pipeline) with Claude Vision fast-path, flags queue, DB writes
- Built `generate_kitchen_sheet.py` + `generate_distribution_sheet.py` + `generate_daily_sheets.py`
- Patched `rex_rexxie_telegram_bot.py` with absence detection, MENU BLAST, MENU OCR, MENU FLAGS
- Built `download_menu_pdfs_impl.py` (hardcoded Gmail IDs)
- Built `goj_menu_flag_reporter.py` + `goj_menu_confirm_handler.py`
- Built `goj_signin_ocr_processor.py` + `goj_attendance_report.py`
- Built `SWH_Client_Binder.pdf` (136 pages)
- Built `attendance_log.html` (full rewrite, monthly tabs, color editor)
- Created GOJ + GHS logos in all templates
- Injected Rexxie personal profile into `rexxie.db`
- Built Gold Health Rexxie `private_confidant_gold.py` v1.3.1
- Built all locked reference documents (`GOJ_LOCKED_PARAMETERS.md`, `GOJ_WORKING_DOC.md`, `GOJ_LOCKED_PARAMETERS.md`)
- Built sign-in PDFs matching GOJ template (this session: Wednesday April 22 W1/W2)
- Built route Excel files (Tuesday Apr 21, Wednesday Apr 22)
- Built Thursday April 23 kitchen + distribution sheets (this session)

### 2. WHAT CLAUDE PROBABLY DID OR INFLUENCED
- `rex_telegram_bot.py` (REX business bot) — Claude likely touched this but MENU BLAST migration is unclear
- `goj_evening_report.py` — referenced in plist; unclear if Claude built it or it's separate
- `generate_tomorrow.py` — referenced in `com.rex.nextday-preview.plist`; unknown authorship
- `goj_tba_alert.py`, `goj_tba_assign.py`, `goj_write_renders.py` — in dashboard folder; likely Claude
- Additional plists in `/launchd/` beyond the 6 scheduler jobs — unclear which Claude built

### 3. WHAT CLAUDE CANNOT CONFIDENTLY CLAIM
- Whether the live `auth_tracker.db` has the `ocr_engines` column (was it actually migrated?)
- Whether `com.rex.evening-report.plist` and `com.rex.nextday-preview.plist` are loaded in launchctl on the Mac
- Whether MENU BLAST was successfully moved to `rex_telegram_bot.py` and removed from Rexxie
- Which Rexxie bot token is currently active (old vs Gold Health)
- Whether `goj_daily_scheduler.py` uses the root-level or dashboard-subfolder `auth_tracker.db`
- Current state of `goj.db` vs `auth_tracker.db` (two separate DBs in dashboard folder)

### 4. WHAT SHOULD BE PROTECTED FROM DUPLICATE REWORK
- **`goj_menu_consensus_ocr.py`** — do not rebuild OCR pipeline; check schema compatibility first
- **`goj_daily_scheduler.py` + all launchd plists** — do not create new schedulers; audit what's loaded first
- **`client_menus` schema** — do not alter without checking `ocr_engines` presence and `main` vs `main_dish`
- **Rexxie personal bot patching** — GOJ operations are already patched in; verify MENU BLAST location before adding again
- **Logo placements** — hot-swappable; do not hardcode in templates
- **Kitchen/distribution template format** — main+side always combined; do not separate them

### 5. WHAT SHOULD BE HANDED TO THE CURRENT OPERATOR FIRST
1. **DB schema verification:** `PRAGMA table_info(client_menus);` on live DB → confirm `main` column exists (not `main_dish`) and `ocr_engines` column present
2. **DB path resolution:** Confirm which `auth_tracker.db` is authoritative — root-level or dashboard subfolder
3. **Launchd audit:** `launchctl list | grep -E "goj|rex"` — identify which plists are loaded and which conflict
4. **Rexxie token audit:** Compare `rex_rexxie_telegram_config.json` vs `~/Desktop/Gold_Health_Systems/.rexxie_config.json` — are they the same token?
5. **OCR script header correction:** Line 4-5 says Vision disabled but it's not — fix comment to avoid confusion
6. **MENU BLAST location:** Grep `rex_telegram_bot.py` for `menu_blast` — verify it was actually moved before removing from Rexxie

---
*End of Extraction Report — forensic only, no redesign*
