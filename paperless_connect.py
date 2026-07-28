"""
Paperless-NGX Connection Test + Info
=====================================
Run this to confirm Tailscale is working and Paperless is reachable.
Shows document count, recent docs, and OCR language setting.

Run:
    cd ~/Desktop/REX && source .venv/bin/activate
    python paperless_connect.py
"""

import json
import urllib.request
import urllib.error
import sys
from datetime import datetime

PAPERLESS_URL   = "http://localhost:8010"
PAPERLESS_TOKEN = "51420bd5c9d61208b331d09a528019d50a70520b"
HEADERS         = {"Authorization": f"Token {PAPERLESS_TOKEN}"}


def get(path: str, params: dict = None) -> dict:
    url = f"{PAPERLESS_URL}/api/{path.lstrip('/')}"
    if params:
        qs  = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read())
    except urllib.error.URLError as e:
        print(f"\n❌ Cannot reach Paperless: {e}")
        print("   → Is Tailscale running? Check the Tailscale icon in your menu bar.")
        print("   → Is Paperless running on the work computer?")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)


def main():
    print("=" * 52)
    print("  Paperless-NGX Connection Check")
    print(f"  {PAPERLESS_URL}")
    print("=" * 52)

    # ── Basic connectivity ───────────────────────────────
    print("\n🔌 Connecting...", end="", flush=True)
    docs = get("documents/", {"page_size": 5, "ordering": "-created"})
    total = docs.get("count", 0)
    print(f" ✅ Connected!\n")

    print(f"📄 Total documents in Paperless: {total}")

    # ── Recent documents ─────────────────────────────────
    results = docs.get("results", [])
    if results:
        print(f"\n📋 5 Most Recent Documents:")
        for doc in results:
            title   = doc.get("title", "(no title)")[:55]
            created = doc.get("created", "")[:10]
            doc_id  = doc.get("id")
            print(f"   [{doc_id}] {created}  {title}")

    # ── Scanner docs (menu/signin forms) ─────────────────
    scanner_docs = get("documents/", {
        "page_size": 5,
        "ordering": "-created",
        "title__icontains": "GOJ",
    })
    goj_count = scanner_docs.get("count", 0)
    print(f"\n📁 GOJ-tagged documents: {goj_count}")

    # ── Check OCR language ────────────────────────────────
    print("\n🌐 Checking OCR language setting...")
    try:
        ui_settings = get("ui_settings/")
        ocr_lang = ui_settings.get("ocr_language") or "(not set)"
        print(f"   OCR Language: {ocr_lang}")
        if "rus" not in str(ocr_lang).lower():
            print("   ⚠️  Russian (rus) is NOT enabled.")
            print("   → To fix: Settings → General Settings → OCR Language → add 'Russian'")
            print("   → This will improve name recognition on Russian menu forms.")
        else:
            print("   ✅ Russian OCR is enabled — name recognition will be accurate.")
    except Exception:
        print("   (Could not read OCR language — check manually in Settings)")

    print("\n" + "=" * 52)
    print("✅ Paperless is connected and ready.")
    print("   Run: python goj_menu_ocr_processor.py")
    print("=" * 52)


if __name__ == "__main__":
    main()
