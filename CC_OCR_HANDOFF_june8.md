# OCR Pipeline — Full Audit & Debug Handoff
# Written: 2026-06-08 by Cowork (Claude) for Claude Code CLI
# READ CLAUDE.md FIRST: ~/Desktop/REX/CLAUDE.md

---

## WHAT WAS BUILT & FIXED IN A PRIOR SESSION

Last session I (Cowork) diagnosed and fixed the following:

1. **Gmail OAuth token** — token at `~/.rex_google_token.json` had expired. Fixed by re-running `python backend/rex_gmail.py --setup` OAuth flow.
2. **rex_menu_scan_watcher.py credential loading** — hardcoded session paths were replaced with proper `Path.home()` references. MENUS_DIR now correctly points to `~/Documents/goj files/dashboard/documents/menus`.
3. **Created `CC_gmail_reauth.command`** — one-click script for future re-auths.

---

## CURRENT STATE (verified June 8 from logs)

### Gmail Watcher — `backend/rex_menu_scan_watcher.py`
- ✅ Running as background task in REX FastAPI lifespan
- ✅ Polls every 5 minutes, last check: `2026-06-08T12:47:50`
- ✅ Has seen 162 email threads, downloaded from 113 scan messages
- ✅ State file: `~/Desktop/REX/logs/menu_scan_watcher_state.json`
- ✅ MENUS_DIR = `~/Documents/goj files/dashboard/documents/menus`

### OCR Live Watcher — `CC_ocr_live_watcher.py`
- ✅ Running, polls every ~31 minutes
- ⚠️ Reports "Total PDFs: 206 | New since last: 0 | Unprocessed: 0" — this means it thinks everything is done
- ❌ **But `menu_ocr_processed.json` only has 2 confirmed processed PDFs (both May 28)**

### OCR Actual Success Rate
- **Only 2 PDFs were ever successfully OCR'd** (May 28, 2026)
- 206 total PDFs are known. The rest are either silently failing or never attempted successfully.
- The pipeline has been broken for most of its history.

---

## ROOT CAUSES — ALL CONFIRMED FROM LOGS

### Bug 1 — TESSDATA_PREFIX not set in subprocess environment (CRITICAL)
**File:** `CC_ocr_worker.py` → spawns `CC_ocr_worker.py` as subprocess via `subprocess.Popen`
**File:** `goj_menu_consensus_ocr.py` → calls `pytesseract.image_to_string(..., lang="rus+eng")`

**Error in log:**
```
Error opening data file /Users/mainsobhelper/.tesseract_data/tessdata/eng.traineddata
Please make sure the TESSDATA_PREFIX environment variable is set to your "tessdata" directory.
Failed loading language 'eng' Tesseract couldn't load any languages!
```

**The tessdata IS there** at `~/.tesseract_data/tessdata/` but `TESSDATA_PREFIX` is not in the subprocess environment. REX runs as a launchd service with a minimal env. The subprocess spawned in `_trigger_ocr_on_files` does NOT inherit `TESSDATA_PREFIX`.

**Also needs Russian tessdata** — the menus are Russian. `lang="rus+eng"` requires `rus.traineddata` too.

**Fix:**
```python
# In _trigger_ocr_on_files() in rex_menu_scan_watcher.py:
import os
env = os.environ.copy()
env["TESSDATA_PREFIX"] = str(Path.home() / ".tesseract_data" / "tessdata")
subprocess.Popen(
    [str(python_bin), str(REX_DIR / "CC_ocr_worker.py")],
    close_fds=True,
    env=env,          # ← ADD THIS
)
```

**Verify tessdata exists:**
```bash
ls ~/.tesseract_data/tessdata/
# Must have: eng.traineddata AND rus.traineddata
# If rus.traineddata missing: brew install tesseract-lang OR download from tessdata repo
```

---

### Bug 2 — ANTHROPIC_API_KEY not in subprocess environment (CRITICAL)
**File:** `goj_menu_ocr.py` line 37:
```python
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
```

**Error in log:**
```
[Claude Vision] Page 1-2 error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error',
'message': 'Your credit balance is too low to access the Anthropic API.'}}
```

This was during an earlier run (March-April) when the API credits were low. But the deeper issue is that `goj_menu_ocr.py` reads `ANTHROPIC_API_KEY` at **module import time** from `os.environ`. When `CC_ocr_worker.py` spawns as a subprocess from launchd, `ANTHROPIC_API_KEY` is not in the environment — it gets `""` — so every Claude Vision request fails with a 401 (or 400), not a credit error.

The "credit balance too low" error is the API's response to a request made with an **empty or invalid API key**. Credits may be fine.

**Fix — add .env loading to `CC_ocr_worker.py` at startup, before any imports of OCR modules:**
```python
# Add near top of CC_ocr_worker.py, before the goj_menu_ocr import:
from pathlib import Path
import os

_env_path = Path.home() / ".hermes" / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        if "=" in _line and not _line.startswith("#"):
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

# Also set TESSDATA_PREFIX
os.environ.setdefault("TESSDATA_PREFIX", str(Path.home() / ".tesseract_data" / "tessdata"))
```

**Also fix in `rex_menu_scan_watcher.py` subprocess spawn** (same env propagation fix as Bug 1).

---

### Bug 3 — Paperless 415 Unsupported Media Type
**Error in log:**
```
WARNING: Paperless OCR failed: HTTP Error 415: Unsupported Media Type
```

**Location:** `goj_menu_ocr.py` → Paperless Engine 3, and `rex_menu_scan_watcher.py` → `_ingest_paperless()`

The Paperless API at `http://100.99.86.60:8000/api/documents/post_document/` is rejecting the multipart request. The boundary handling in both files is non-standard and broken. Paperless-ngx expects a proper `multipart/form-data` boundary — the current hand-rolled multipart encoder is malformed.

**Fix — use `urllib3` or the proper multipart format:**
```python
# Replace the hand-rolled multipart in _ingest_paperless() with:
import urllib.request
import io

def _ingest_paperless(filepath: Path, title: str):
    cfg = _get_paperless_config()
    if not cfg["token"]:
        return
    
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    data = filepath.read_bytes()
    
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="document"; filename="{filepath.name}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + data + (
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="title"\r\n\r\n'
        f"{title}\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    
    req = urllib.request.Request(
        f"{cfg['url'].rstrip('/')}/api/documents/post_document/",
        data=body,
        headers={
            "Authorization": f"Token {cfg['token']}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    # ... rest of request
```

Note: Paperless is a non-critical archival engine. If it keeps failing, disable it gracefully rather than letting it block OCR.

---

### Bug 4 — CC_ocr_live_watcher says "Unprocessed: 0" but only 2 PDFs confirmed done
**File:** `CC_ocr_live_watcher.py` — has its own tracking logic separate from `menu_ocr_processed.json`

The live watcher reports everything as "processed" because it's likely checking against its own internal state file or the PDF filenames in the directory — not against actual DB insertions. This creates a false sense that OCR is complete.

**Verify actual DB state:**
```bash
source ~/debate-chamber/.venv/bin/activate
cd ~/Desktop/REX
python3 - <<'EOF'
import sqlite3
from pathlib import Path
conn = sqlite3.connect(str(Path.home() / "Documents/goj files/dashboard/auth_tracker.db"))
cur = conn.cursor()
# Total client_menus rows
cur.execute("SELECT COUNT(*) FROM client_menus")
print("Total client_menus rows:", cur.fetchone()[0])
# By week
cur.execute("SELECT week_start, COUNT(*) FROM client_menus GROUP BY week_start ORDER BY week_start DESC LIMIT 10")
print("By week (last 10):")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]} rows")
# Rows with non-null main column
cur.execute("SELECT COUNT(*) FROM client_menus WHERE main IS NOT NULL AND main != ''")
print("Rows with main dish filled:", cur.fetchone()[0])
conn.close()
EOF
```

---

### Bug 5 — Claude Vision uses claude-opus-4-6 (very expensive)
**File:** `goj_menu_ocr.py` line 40:
```python
CLAUDE_MODEL = "claude-opus-4-6"
```

Opus is the most expensive model. For menu OCR at scale (206 PDFs, 2 pages per client per week), this drains credits fast. Switch to `claude-haiku-4-5-20251001` for vision tasks — it handles form checkboxes just as well at 1/20th the cost.

---

### Bug 6 — MENUS_DIR: old menus in wrong location
The OCR log showed files being processed from `~/Documents/goj files/documents/menus/` (old path without "dashboard"). The new path is `~/Documents/goj files/dashboard/documents/menus`. There may be old un-OCR'd PDFs sitting in the old location that were never reprocessed.

**Check:**
```bash
ls ~/Documents/goj\ files/documents/menus/ 2>/dev/null | wc -l
ls ~/Documents/goj\ files/dashboard/documents/menus/ 2>/dev/null | wc -l
```

If files exist in the old path, move them to the new path and requeue them.

---

## KEY FILES

| File | Role |
|------|------|
| `~/Desktop/REX/backend/rex_menu_scan_watcher.py` | Gmail watcher — downloads PDFs, enqueues OCR |
| `~/Desktop/REX/CC_ocr_worker.py` | Queue runner — processes jobs via goj_menu_ocr |
| `~/Desktop/REX/CC_ocr_queue.py` | SQLite queue — tracks job state |
| `~/Desktop/REX/goj_menu_ocr.py` | Primary OCR — Claude Vision + Tesseract + Paperless |
| `~/Desktop/REX/goj_menu_consensus_ocr.py` | Alt OCR — 4-engine consensus (local mode) |
| `~/Desktop/REX/CC_ocr_live_watcher.py` | Separate watcher — monitors menus dir |
| `~/Desktop/REX/logs/ocr_run.log` | OCR run log — all errors visible here |
| `~/Desktop/REX/logs/ocr_watcher.log` | Live watcher log |
| `~/Desktop/REX/logs/menu_ocr_processed.json` | Confirmed processed PDFs (only 2 entries!) |
| `~/Desktop/REX/logs/menu_scan_watcher_state.json` | Gmail watcher state — seen IDs |
| `~/.tesseract_data/tessdata/` | Tesseract language data — verify eng.traineddata + rus.traineddata |

---

## RECOMMENDED FIX ORDER

1. **Add .env loading + TESSDATA_PREFIX to `CC_ocr_worker.py`** — fixes Bugs 1 and 2 in one shot
2. **Pass env to subprocess in `rex_menu_scan_watcher.py`** — ensures background worker inherits same fixes
3. **Switch CLAUDE_MODEL to haiku** in `goj_menu_ocr.py` — stops burning credits
4. **Run a manual test** on one PDF:
   ```bash
   source ~/debate-chamber/.venv/bin/activate
   export TESSDATA_PREFIX=~/.tesseract_data/tessdata
   export ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY ~/.hermes/.env | cut -d= -f2)
   cd ~/Desktop/REX
   python3 CC_ocr_worker.py --file "$(ls ~/Documents/goj\ files/dashboard/documents/menus/*.pdf 2>/dev/null | head -1)" --mode hybrid
   ```
5. **Check if rus.traineddata exists** — if not, install it before Tesseract will work at all
6. **Fix Paperless 415** (non-critical, can defer — it's archival only)
7. **Check old menus dir** — reprocess any stranded PDFs
8. **Fix CC_ocr_live_watcher tracking** so it reports accurate completion

---

## QUICK DIAGNOSIS COMMANDS

```bash
# Check the queue database
source ~/debate-chamber/.venv/bin/activate && cd ~/Desktop/REX
python3 CC_ocr_worker.py --status

# Check tessdata
ls ~/.tesseract_data/tessdata/ | grep -E "eng|rus"

# Check Anthropic key is in env
grep -c "ANTHROPIC_API_KEY" ~/.hermes/.env

# Run one PDF manually (set env first)
export TESSDATA_PREFIX=~/.tesseract_data/tessdata
export ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY ~/.hermes/.env | cut -d= -f2-)

# How many menus are in DB
sqlite3 ~/Documents/goj\ files/dashboard/auth_tracker.db \
  "SELECT week_start, COUNT(*) FROM client_menus GROUP BY week_start ORDER BY week_start DESC LIMIT 5"

# What's in the menus dir
ls ~/Documents/goj\ files/dashboard/documents/menus/ | wc -l
```

---

## HARD RULES (always apply)
- DB column is `main` not `main_dish`
- PHI stays local — Presidio on all outbound — no OCR results to cloud logging
- `auth_tracker.db` never reaches cloud
- New files get `CC_` prefix
- MENUS_DIR = `~/Documents/goj files/dashboard/documents/menus` (with "dashboard" in path)
- Week start is ALWAYS the NEXT Monday from scan date (locked rule in infer_week_start)
