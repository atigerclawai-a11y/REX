"""
Paperless-NGX OCR Language — Verify & Re-OCR Trigger
======================================================
Paperless stores its OCR language in server-side config, not via a
public API field.  This script:

  1. Pings Paperless to confirm it's reachable
  2. Tells you exactly where to check / set the language in the UI
  3. Triggers re-OCR on all GOJ scanner documents

Run:
    cd ~/Desktop/REX && source .venv/bin/activate
    python paperless_set_ocr_language.py

Flags:
    --reocr-only   Skip instructions, just trigger re-OCR immediately
"""

import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

PAPERLESS_URL   = "http://localhost:8010"
PAPERLESS_TOKEN = "51420bd5c9d61208b331d09a528019d50a70520b"
HEADERS = {
    "Authorization": f"Token {PAPERLESS_TOKEN}",
    "Content-Type":  "application/json",
}

REOCR_ONLY = "--reocr-only" in sys.argv


def api(method: str, path: str, body: dict = None):
    url  = f"{PAPERLESS_URL}/api/{path.lstrip('/')}"
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return {"error": str(e), "detail": e.read().decode()[:300]}, e.code
    except urllib.error.URLError as e:
        print(f"\n❌  Cannot reach Paperless at {PAPERLESS_URL}: {e}")
        print("    → Make sure Tailscale is connected first.")
        sys.exit(1)


def check_connection():
    print(f"🔌  Connecting to Paperless at {PAPERLESS_URL}...")
    data, status = api("GET", "documents/?page_size=1")
    if status != 200:
        print(f"   ❌  Connection failed (HTTP {status})")
        sys.exit(1)
    total = data.get("count", 0)
    print(f"   ✅  Connected — {total} documents in Paperless.\n")
    return total


def trigger_reocr():
    """Trigger re-OCR on all GOJ scanner documents."""
    print("🔄  Fetching GOJ scanner documents...")
    data, status = api("GET", "documents/?page_size=100&ordering=-created")
    if status != 200:
        print(f"   ❌  Could not list documents (HTTP {status})")
        return

    docs = data.get("results", [])
    # Match scanner batches and any GOJ-tagged docs
    target = [
        d for d in docs
        if "doc00" in (d.get("original_file_name") or "").lower()
        or "goj" in (d.get("title") or "").lower()
        or "signin" in (d.get("title") or "").replace(" ","").lower()
        or "sign in" in (d.get("title") or "").lower()
        or "menu" in (d.get("title") or "").lower()
    ]

    if not target:
        print("   No GOJ scanner docs found in the last 100 documents.")
        print("   Retrying with broader search...")
        data2, s2 = api("GET", "documents/?page_size=100&ordering=-created&page=2")
        if s2 == 200:
            target += [
                d for d in data2.get("results", [])
                if "doc00" in (d.get("original_file_name") or "").lower()
            ]

    if not target:
        print("   ⚠️  No scanner documents found to re-OCR.")
        return

    print(f"   Found {len(target)} GOJ documents to re-OCR:")
    for d in target[:10]:
        print(f"      • [{d['id']:>4}] {d.get('title','(no title)')}")
    if len(target) > 10:
        print(f"      ... and {len(target)-10} more")

    print(f"\n   Triggering re-OCR on all {len(target)} documents...")

    # Batch all IDs in one call — much faster and more reliable
    all_ids = [doc["id"] for doc in target]
    result, status = api("POST", "documents/bulk_edit/", {
        "documents":  all_ids,
        "method":     "redo_ocr",
        "parameters": {},
    })

    if status in (200, 204):
        print(f"\n   ✅  Re-OCR queued for {len(all_ids)} documents (batch call succeeded).")
        print("   ⏳  Paperless will re-process docs in the background (2–10 min).")
        print("   Then run: python goj_menu_ocr_processor.py")
    else:
        err_detail = result.get("detail", str(result))[:150]
        is_invalid_method = "not a valid choice" in err_detail or "redo_ocr" in err_detail

        print(f"\n   ⚠️  Batch re-OCR failed (HTTP {status}): {err_detail}")

        if is_invalid_method:
            print("""
   ─────────────────────────────────────────────────────────
   This version of Paperless-NGX does not support re-OCR
   via the API.  'redo_ocr' was added in Paperless-NGX v2.x.

   YOU HAVE TWO OPTIONS:

   OPTION A — Manual via browser (quickest):
     1. Open http://localhost:8010
     2. Click Documents in the left sidebar
     3. Click filter icon → filter Tag = GOJ (or search "doc00")
     4. Check the top checkbox to select ALL matching docs
     5. Click Actions → Redo OCR

   OPTION B — Read menus NOW without re-OCR:
     Your documents already have English OCR text stored.
     This script reads the existing text directly:
       python paperless_read_menus.py

   OPTION C — Check your Paperless version first:
       python paperless_version_check.py
   ─────────────────────────────────────────────────────────
""")
        else:
            print()
            print("   ── Manual fallback ───────────────────────────────────")
            print("   Open http://localhost:8010 in your browser")
            print("   Select all GOJ documents → Actions → Redo OCR")
            print("   ─────────────────────────────────────────────────────")

        print("   Meanwhile, run the menu processor with existing OCR text:")
        print("   python paperless_read_menus.py")


def show_ocr_instructions():
    print("=" * 60)
    print("  Paperless OCR Language — How to Verify & Set")
    print("=" * 60)
    print("""
NOTE: Paperless keeps its OCR language in server config, not
an API field you can read directly. The API check will always
say "not found" — that's normal.

HOW TO CHECK / SET IT IN THE BROWSER
─────────────────────────────────────
1. Open:  http://localhost:8010
2. Click the gear icon (⚙) → Settings
3. Look for: "OCR" or "Default Language"
4. It should show:   English + Russian  (or "eng+rus")
5. If Russian is missing, add it and click Save.

HOW TO SET IT IN docker-compose (more permanent)
──────────────────────────────────────────────────
Open your docker-compose.yml and make sure this line is set:

  environment:
    PAPERLESS_OCR_LANGUAGE: "eng+rus"

Then restart Paperless:
  docker-compose down && docker-compose up -d

─────────────────────────────────────────────────────────────
Once you've confirmed Russian is set, re-run this script with:

  python paperless_set_ocr_language.py --reocr-only

This will trigger Paperless to re-OCR all GOJ documents.
─────────────────────────────────────────────────────────────
""")


def main():
    check_connection()

    if REOCR_ONLY:
        print("📋  --reocr-only mode: skipping instructions.\n")
        trigger_reocr()
    else:
        show_ocr_instructions()

        answer = input("Has Russian been added to Paperless OCR settings? (y/n): ").strip().lower()
        if answer in ("y", "yes"):
            trigger_reocr()
        else:
            print("\n⏸  OK — add Russian to Paperless first, then re-run with:")
            print("   python paperless_set_ocr_language.py --reocr-only")
            print("\n   The GOJ pipeline will work much better with Russian OCR enabled.")


if __name__ == "__main__":
    main()
