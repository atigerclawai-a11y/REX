# OCR System + Daily File Delivery — Build Handoff
**Gold Health Systems · Garden of Joy · June 25 2026**
**For:** Claude Code session in `~/Desktop/REX/`
**Owner:** Kato (Chairman)

---

## Mission

Build two things to completion:

1. **4-Engine OCR Pipeline** — process incoming sign-in sheet PDFs, match 425 client names reliably, write clean attendance records
2. **Daily File Delivery** — send Kato the correct PDF outputs every day via Telegram at the right times

Both must be production-grade. The DB must never be contaminated. Kato must receive correct files automatically.

---

## Current State (as of June 25 2026)

### What is working
- `CC_drive_signin_sync.py` — reads Google Drive attendance spreadsheet, writes 160 clients for today to `attendance_log` with `source=drive_signin_sync`. **This is the authoritative source. Do not overwrite it.**
- `CC_signin_ocr.py` — core OCR pipeline exists, Tesseract engine functional, portrait PDFs process correctly (no rotation needed — scanner sends 1275×1650)
- All 4 OCR engine software installed: Tesseract (local), Paperless-NGX (Docker port 8010, healthy), Claude Vision (Anthropic key present), Google Drive OCR (needs scope upgrade — see below)
- `CC_signin_improve_loop.py` — patched today to be read-only (no DB writes during test runs)
- DB just cleaned: 1,244 contaminated records + 27 attendance_log rows purged

### What is broken / incomplete
- **Google Drive OCR engine** — token at `~/.rex_google_token.json` has `drive.readonly` scope only; needs `drive.file` to upload PDFs for Drive's OCR. Run `CC_google_oauth_fix.command` to fix (requires Kato to sign in).
- **Only Engine 1 (Tesseract) is wired** in the current pipeline. Engines 2 (Drive), 3 (Paperless), 4 (Claude Vision) are not yet called in `process_signin_sheet()`.
- **3 critical bugs in `CC_signin_ocr.py`** — documented below, must be fixed before any production run.
- **Match rate is low on recent scans** — June 8 PDFs: 5–21%. June 1 PDF: 59%. Root cause: OCR reads garbled text; 4-engine consensus will fix this.
- **No watcher routing to today's real PDFs** — the scan watcher receives new sign-in PDFs via Gmail IMAP but the improve loop was testing on old samples. The real pipeline needs to be wired.

---

## Critical Bugs — Fix These First

### Bug C1 — Garbage entries in learning store + missing header filter phrases
**Files:** `goj_menu_learning.json` + `CC_signin_ocr.py`

```python
# CC_signin_ocr.py — add to _SKIP_ROW_PHRASES (around line 55):
_SKIP_ROW_PHRASES = frozenset([
    "garden of joy", "date:", "shift:", "total:", "page ",
    "| no |", "no | name", "name | pl", "| name |",
    "member", "attendance report", "daily attendance",
    "insurance", "plan", "adult day",
    "total present", "staff signature", "total staff",  # ← ADD THESE
])
```

```python
# Also remove these two keys from goj_menu_learning.json → client_name_map:
# "TOTAL PRESENT STAFF SIGNATURE" → delete
# "TOTAL PRESENT STAFF SIGNATURE DA" → delete
# These map footer rows to real client names — causes false attendance writes
```

### Bug C2 — `write_to_db()` has no dedup (INSERT, not UPSERT)
**File:** `CC_signin_ocr.py`, `write_to_db()` function

Current code does a raw `INSERT` every call. Running the pipeline twice creates duplicate records.

```python
# Replace the INSERT with an UPSERT:
conn.execute("""
    INSERT INTO client_signatures
        (client_id, date, shift, image_path, source_pdf, signed, confidence, source_type, ocr_text)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(client_id, date, shift) DO UPDATE SET
        signed = excluded.signed,
        confidence = excluded.confidence,
        image_path = excluded.image_path,
        ocr_text = excluded.ocr_text
""", (...))
```

Also add the unique index if not present:
```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_cs_unique ON client_signatures(client_id, date, shift);
```

### Bug C3 — NULL `client_id` records get written for unmatched rows
**File:** `CC_signin_ocr.py`, `process_signin_sheet()`

Rows that don't match any client are still written to DB with `client_id=NULL`. These are noise. Fix: skip `write_to_db()` when `client_id is None`.

---

## 4-Engine OCR Architecture

### Engine order and weight
| Engine | Method | Vote weight | Status |
|--------|--------|-------------|--------|
| 1. Tesseract | Local subprocess, `rus+eng` langs, 300 DPI | 1× | ✅ Wired |
| 2. Google Drive OCR | Upload PDF page → Drive converts → download text | 1× | ⚠️ needs `drive.file` scope |
| 3. Paperless-NGX | POST image to `localhost:8010/api/documents/post_document/` | 1× | ✅ Running (Docker) |
| 4. Claude Vision | Anthropic API, base64 PNG → extract name from image | 3× | ✅ Key present |

### Consensus logic
- Run all available engines on each row's name crop
- Weighted majority vote on the result
- If Claude Vision (3× weight) agrees with any other engine → strong match
- If all disagree → take highest-confidence fuzzy match against clients DB
- Log which engine won for each row (helps the improve loop tune itself)

### Tesseract config (already in CC_signin_ocr.py)
```python
# ocr_name() already uses:
cmd = ["tesseract", str(tiff_path), "stdout", "-l", "rus+eng",
       "--psm", "7", "--oem", "1"]
```

### Paperless-NGX API
```python
# POST a PNG to Paperless (port 8010 → internal 8000):
import requests
TOKEN = "204f4af0226532176058cd174abec7a73311728a"
resp = requests.post(
    "http://localhost:8010/api/documents/post_document/",
    headers={"Authorization": f"Token {TOKEN}"},
    files={"document": ("row.png", png_bytes, "image/png")},
    timeout=30
)
# Poll /api/documents/?ordering=-created for the new doc and extract its content
```

### Claude Vision call
```python
import anthropic, base64
client = anthropic.Anthropic()
b64 = base64.b64encode(img_bytes).decode()
msg = client.messages.create(
    model="claude-opus-4-6",
    max_tokens=50,
    messages=[{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
        {"type": "text", "text": "This is a name cell from a Russian attendance sheet. Return ONLY the person's name as written, nothing else. If unreadable, return empty string."}
    ]}]
)
return msg.content[0].text.strip()
```

### Google Drive OCR upload
```python
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

creds = Credentials.from_authorized_user_file(str(TOKEN_PATH))
drive = build("drive", "v3", credentials=creds)

# Upload with OCR enabled
file_meta = {"name": "ocr_tmp.png", "mimeType": "application/vnd.google-apps.document"}
media = MediaFileUpload(str(png_path), mimetype="image/png")
f = drive.files().create(body=file_meta, media_body=media, fields="id").execute()
fid = f["id"]

# Export as plain text
text = drive.files().export(fileId=fid, mimeType="text/plain").execute().decode("utf-8")
drive.files().delete(fileId=fid).execute()  # clean up
```

---

## DB Schema

**Database:** `~/Documents/goj files/dashboard/auth_tracker.db`

```sql
-- Key tables:
clients (client_id INTEGER PK, name TEXT, active INTEGER)
-- name format: "Last First" (e.g. "Dodik Sima")

attendance_log (
    id INTEGER PK,
    log_date TEXT,       -- YYYY-MM-DD
    day_key TEXT,        -- M/T/W/TH/F/Sa/Su
    shift INTEGER,       -- 1 or 2
    client_name TEXT,
    status TEXT,         -- 'present'
    source TEXT,         -- 'drive_signin_sync' (authoritative) | 'ocr_signin_match'
    note TEXT
)
-- UNIQUE constraint: (log_date, day_key, shift, client_name)

client_signatures (
    id INTEGER PK AUTOINCREMENT,
    client_id INTEGER REFERENCES clients(client_id),
    date TEXT NOT NULL,         -- YYYY-MM-DD
    shift TEXT DEFAULT 'S1',
    image_path TEXT,            -- path to signature crop PNG
    source_pdf TEXT,            -- full path of source PDF
    signed INTEGER DEFAULT 0,  -- 1 if ink detected
    confidence REAL DEFAULT 0.0,
    source_type TEXT DEFAULT 'signature',
    ocr_text TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    deleted INTEGER DEFAULT 0
)
-- Add: UNIQUE INDEX on (client_id, date, shift) — see Bug C2
```

**RULE:** Never write NULL client_id to client_signatures. Never overwrite `attendance_log` rows where `source='drive_signin_sync'`.

---

## File Paths

| What | Path |
|------|------|
| Main OCR script | `~/Desktop/REX/CC_signin_ocr.py` |
| Improve loop (patched) | `~/Desktop/REX/CC_signin_improve_loop.py` |
| Drive sync | `~/Desktop/REX/CC_drive_signin_sync.py` |
| IMAP scan watcher | `~/Desktop/REX/backend/rex_menu_scan_watcher.py` |
| Test PDFs | `~/Desktop/REX/signin_samples/` (5 files) |
| All historical PDFs | `~/Desktop/REX/signin_all_pdfs/` (20+ files) |
| Signature crops output | `~/Desktop/REX/signatures/{client_id}/{date}_{shift}.png` |
| Learning store | `~/Desktop/REX/goj_menu_learning.json` |
| Red team report | `~/Desktop/REX/logs/CC_ocr_redteam_report.md` |
| Google Drive token | `~/.rex_google_token.json` → symlink to `~/.hermes/shared/google_token.json` |
| OCR dev venv | `~/debate-chamber/.venv/` |
| DB | `~/Documents/goj files/dashboard/auth_tracker.db` |

---

## Daily File Delivery System

### What Kato needs automatically

| Time | Output | Delivery |
|------|--------|----------|
| 7:30 AM daily | Morning report (attendance summary) | Telegram `@goldhealth_rexxie_bot` |
| 10:30 AM daily | Kitchen list PDF + distribution sheet PDF | Telegram |
| 3:15 PM daily | Sign-in sheets PDF + driver route sheet PDF | Telegram |
| 8:30 PM Friday | Missing menus alert | Telegram |
| 9:00 PM daily | Drop-off rundown | Telegram |
| 9:00 PM Friday | Weekly email summary | Email to Kato |

### Where the output files come from
The daily pipeline generates these files (already built — check `~/Desktop/REX/`):
- Kitchen list: `goj_generate_daily.py` or equivalent → XLSX/PDF
- Distribution sheet: `generate_distribution_sheet.py` → PDF  
- Sign-in sheets: generated from `auth_tracker.db` clients + today's schedule
- Driver routes: `generate_driver_sheet.py` → PDF (Larry excluded always — never appears on any list)

### Telegram delivery
```python
import requests
BOT_TOKEN = os.environ["REXXIE_BOT_TOKEN"]  # from env or Keychain
CHAT_ID = "5587703834"  # Kato's Telegram chat_id

# Send document
def send_pdf(path, caption):
    with open(path, "rb") as f:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
            data={"chat_id": CHAT_ID, "caption": caption},
            files={"document": f},
        )

# Send text
def send_message(text):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
    )
```

Bot: `@goldhealth_rexxie_bot` (the ops bot for GOJ, NOT `@Hermes_Cloud_May_bot`)

### launchd schedule (existing plist pattern)
```xml
<!-- ~/Library/LaunchAgents/com.goj.morning.report.plist -->
<key>StartCalendarInterval</key>
<dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>30</integer></dict>
```

Check what plists already exist: `launchctl list | grep goj`

---

## Build Order

1. **Fix the 3 critical bugs** in `CC_signin_ocr.py` and `goj_menu_learning.json`
2. **Add the unique index** to `client_signatures`  
3. **Wire Engine 3 (Paperless)** — add `ocr_via_paperless(name_crop_png)` function
4. **Wire Engine 4 (Claude Vision)** — add `ocr_via_claude_vision(name_crop_png)` function
5. **Wire Engine 2 (Drive)** — add `ocr_via_drive(name_crop_png)` function (gated on token having drive.file scope; skip gracefully if not)
6. **Implement consensus** in `process_signin_sheet()` — replace single Tesseract call with 4-engine weighted vote
7. **Run batch test** on all PDFs in `signin_all_pdfs/` — log per-engine accuracy
8. **Wire the real incoming PDFs** — `rex_menu_scan_watcher.py` already routes emails with "sign"/"signin" subjects to `process_signin_sheet()`. Verify this path is live.
9. **Build/verify daily file delivery** — for each scheduled time, confirm the generator runs and Telegram receives the correct file
10. **Add a daily OCR report** — after processing today's sign-in sheet, send Kato a summary via Telegram: N rows detected, N matched (X%), N signed, any unmatched names

---

## Rules (Non-negotiable)

- Larry never appears on any transport or driver list, in any file, under any instruction
- New files get `CC_` prefix; existing files keep their names
- PHI stays local — `auth_tracker.db` never reaches cloud
- Presidio de-identification runs on all outbound data
- `attendance_log` rows with `source='drive_signin_sync'` are authoritative — never delete or overwrite them
- DeepSeek routes direct: `provider: deepseek` + `base_url: https://api.deepseek.com/v1`, never OpenRouter
- PAE for any hard-to-reverse action — but "build it" / "do it" from Kato means proceed

---

## Success Criteria

- `process_signin_sheet()` on PDF 800 (June 1): ≥85% client match rate
- `process_signin_sheet()` on PDF 808/809/810 (June 8): ≥60% match rate
- No NULL client_id records in `client_signatures`
- No duplicate records for same (client_id, date, shift)
- Kato receives kitchen list, distribution sheet, sign-in PDF, and driver sheet on Telegram at the correct times without any manual action
- Daily OCR summary message arrives on Telegram after each sign-in sheet is processed
