#!/usr/bin/env python3
"""
DOWNLOAD_ALL_SCANS.py — Master GOJ Gmail Attachment Downloader
Downloads ALL scanner PDFs from Allen/GOJ scanner emails and routes them
to the correct folders based on content type.

Destination folders:
  ~/Documents/goj files/dashboard/documents/authorization/ ← auth scans
  ~/Documents/goj files/dashboard/documents/menus/ ← menu PDFs (skip if already there)
  ~/Documents/goj files/documents/signin/          ← sign-in sheets
  ~/Documents/goj files/documents/staff/           ← staff docs

Run: ~/debate-chamber/.venv/bin/python3 ~/Desktop/REX/DOWNLOAD_ALL_SCANS.py
"""
import os, base64, re
from pathlib import Path

HOME = Path.home()
TOKEN_PATH  = HOME / "Desktop/REX/gmail_token.json"
CREDS_PATH  = HOME / "Desktop/REX/google_credentials.json"

DIRS = {
    "authorization": HOME / "Documents/goj files/dashboard/documents/authorization",
    "menus":         HOME / "Documents/goj files/dashboard/documents/menus",
    "signin":        HOME / "Documents/goj files/documents/signin",
    "staff":         HOME / "Documents/goj files/documents/staff",
    "other":         HOME / "Documents/goj files/documents/inbox",
}
for d in DIRS.values():
    d.mkdir(parents=True, exist_ok=True)

# ── Known message IDs → category override (from manual audit) ────────────────
# Format: msg_id: "category"
# Leave empty to let auto-routing handle everything
KNOWN_CATEGORIES = {
    # April 2 authorization scans (doc001680-001785 range)
    "19d4d19f94f51332": "authorization",
    "19d4d179fa4987e1": "authorization",
    "19d4d173eb8333ef": "authorization",
    "19d4d104bedb7b21": "authorization",
    "19d4d0ff4722f74f": "authorization",
    "19d4d0f713c89b33": "authorization",
    "19d4d0ed2dd3ad7c": "authorization",
    "19d4d0d8abb30752": "authorization",
    # April 4 sign-in sheets
    "19d5604f33622807": "signin",
    "19d560489c99e9e9": "signin",
    "19d560244978fd0e": "signin",
    # April 4 large menu scans
    "19d5720c403b2736": "menus",
    "19d56572c638493f": "menus",
    "19d5610067936f9f": "menus",
    "19d56036b11ce00a": "menus",
    "19d5603007ff6a08": "menus",
    # Staff medicals already downloaded — skip
    "19d67a0b629b3296": "staff",
    "19d67a070114bc35": "staff",

    # ── Apr 27 11:24am scan (forwarded May 2) ────────────────────────────────
    "19dcf988af0eeef5": "menus",

    # ── Apr 29 batch ─────────────────────────────────────────────────────────
    "19dd9b09a0afbba1": "menus",
    "19dd9ae224543f52": "menus",
    "19dd9ad97cc93938": "menus",
    "19dd9aa864c953a6": "menus",
    "19dd9a99e0e1fffe": "menus",
    "19dd9a920525fb3c": "menus",
    "19dd9a787fb25393": "menus",
    "19dd9a745329cc6d": "menus",

    # ── Apr 29–30 "Fw: menus" threads ────────────────────────────────────────
    "19de669e98ec3af6": "menus",
    "19de6671e6a1f4a5": "menus",
    "19de663d6150d19c": "menus",

    # ── May 2 forwarded Apr 27 scans (20 threads, 7:22–7:26 PM) ─────────────
    "19dea92d6f1a486f": "menus",
    "19dea9225aa28f09": "menus",
    "19dea3dae8c4789e": "menus",
    "19dea3cab2592322": "menus",
    "19dea3c7bd887b57": "menus",
    "19dea2801445cee5": "menus",
    "19dea27caa590205": "menus",
    "19dea279296c6eaa": "menus",
    "19dea275e637f5f4": "menus",
    "19dea2731acd0a64": "menus",
    "19dea2702bcbfd8a": "menus",
    "19dea26d12afde6c": "menus",
    "19dea268085d32b6": "menus",
    "19dea2635bfcad15": "menus",
    "19dea25f979a5d14": "menus",
    "19dea25b0fffdd0d": "menus",
    "19dea2569e61a0fc": "menus",
    "19dea25297619c47": "menus",
    "19dea24ec9a7cd0b": "menus",
    "19dea24a94d9b7ab": "menus",
}

# ── Auth ─────────────────────────────────────────────────────────────────────
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

def get_service():
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH))
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_PATH, "w") as f:
                f.write(creds.to_json())
        else:
            print("❌ No valid Gmail token. Run setup_gmail_token.py first.")
            return None
    return build("gmail", "v1", credentials=creds)

# ── Category auto-detection ───────────────────────────────────────────────────
def detect_category(filename: str, body_snippet: str = "") -> str:
    """Route files to the right folder based on filename/snippet."""
    fn = filename.lower()
    sn = body_snippet.lower()

    # Staff medical files
    if any(name in fn for name in ['alisher', 'allen', 'khiger', 'andriy', 'sheremet',
                                    'gennadi', 'gugilov', 'klimova', 'liudmila', 'zhuk',
                                    'natalie', 'altman', 'oleg', 'tikhonov', 'ravil', 'aleev',
                                    'vadim', 'kononenko', 'valerian', 'rozmetanyuk', 'vladimir']):
        return "staff"

    # Sign-in sheets
    if 'sign' in sn or 'sign' in fn or 'signin' in fn:
        return "signin"

    # Menu files
    if 'menu' in fn or 'menu' in sn or fn.startswith('menu_part'):
        return "menus"

    # Authorization docs — scanner format doc00XXXX
    if re.match(r'doc\d{8,}', fn):
        # Large scanner docs → authorization by default
        return "authorization"

    return "other"

# ── Download attachments from a single message ────────────────────────────────
def download_message(service, msg_id: str, category: str, dry_run=False):
    msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
    snippet = msg.get("snippet", "")
    parts   = msg.get("payload", {}).get("parts", [])
    if not parts:
        parts = [msg.get("payload", {})]

    saved = 0
    for part in parts:
        filename = part.get("filename", "")
        mime     = part.get("mimeType", "")
        if not filename:
            continue
        if mime in ("text/plain", "text/html", "image/svg+xml"):
            continue
        if filename.startswith("Outlook-"):
            continue

        # Determine category
        cat = KNOWN_CATEGORIES.get(msg_id) or detect_category(filename, snippet)
        dest_dir = DIRS[cat]
        out_path = dest_dir / filename

        if out_path.exists():
            print(f"  ↩  Already exists: {filename}")
            continue

        if dry_run:
            print(f"  [DRY] Would save: {filename} → {cat}/")
            continue

        attachment_id = part.get("body", {}).get("attachmentId")
        if attachment_id:
            att = service.users().messages().attachments().get(
                userId="me", messageId=msg_id, id=attachment_id
            ).execute()
            data = att.get("data", "")
        else:
            data = part.get("body", {}).get("data", "")

        if not data:
            print(f"  ⚠️  No data for: {filename}")
            continue

        file_data = base64.urlsafe_b64decode(data)
        with open(out_path, "wb") as f:
            f.write(file_data)
        size_kb = len(file_data) // 1024
        print(f"  ✓ {filename} ({size_kb:,} KB) → {cat}/")
        saved += 1

        # ── Run menu OCR immediately after saving ─────────────────────────
        if cat == "menus":
            _run_menu_ocr(out_path)

    return saved


def _run_menu_ocr(pdf_path: Path):
    """Call goj_menu_ocr.process_menu_pdf() on a freshly downloaded menu PDF."""
    try:
        import importlib.util, sys as _sys
        _ocr_mod = Path(__file__).resolve().parent / "goj_menu_ocr.py"
        if not _ocr_mod.exists():
            print(f"  ⚠ goj_menu_ocr.py not found at {_ocr_mod} — skipping OCR")
            return
        spec = importlib.util.spec_from_file_location("goj_menu_ocr", _ocr_mod)
        ocr  = importlib.util.module_from_spec(spec)
        _sys.modules.setdefault("goj_menu_ocr", ocr)
        spec.loader.exec_module(ocr)
        print(f"  → Running menu OCR on {pdf_path.name}...")
        result = ocr.process_menu_pdf(pdf_path=pdf_path, dry_run=False)
        inserted = result.get("inserted", 0)
        skipped  = result.get("skipped",  0)
        errors   = result.get("errors",   0)  # errors is an int count, not a list
        print(f"     OCR done: {inserted} rows inserted, {skipped} skipped"
              + (f", {errors} error(s)" if errors else ""))
    except Exception as e:
        print(f"  ⚠ Menu OCR error (file saved OK): {e}")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 64)
    print("  GOJ Master Scanner Downloader")
    print(f"  {len(KNOWN_CATEGORIES)} known messages to process")
    print("=" * 64)

    service = get_service()
    if not service:
        return

    # Process known IDs
    total = 0
    category_counts = {}
    for msg_id, cat in KNOWN_CATEGORIES.items():
        print(f"\n📧 [{cat.upper()}] msg={msg_id}")
        n = download_message(service, msg_id, cat)
        total += n
        category_counts[cat] = category_counts.get(cat, 0) + n

    print("\n" + "=" * 64)
    print(f"✅ Done — {total} files downloaded")
    for cat, count in sorted(category_counts.items()):
        if count > 0:
            folder = DIRS[cat]
            all_files = list(folder.iterdir())
            print(f"  {cat}: {count} new files (folder total: {len(all_files)})")
    print()

    # Summary of all folders
    print("📁 Folder totals:")
    for cat, path in sorted(DIRS.items()):
        if path.exists():
            pdfs = list(path.glob("*.pdf"))
            others = [f for f in path.iterdir() if f.suffix != '.pdf']
            print(f"  {cat:20s}: {len(pdfs)} PDFs, {len(others)} other files")

if __name__ == "__main__":
    main()
