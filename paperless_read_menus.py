"""
paperless_read_menus.py
========================
Reads menu documents DIRECTLY from Paperless OCR text without
needing to re-OCR.  Works even on older Paperless-NGX versions.

What it does:
  1. Searches Paperless for all GOJ menu documents
  2. Downloads the OCR text for each (already stored in Paperless)
  3. Tries to match client names against auth_tracker.db
  4. Shows what it found and what needs manual review

Run:
    cd ~/Desktop/REX && source .venv/bin/activate
    python paperless_read_menus.py

Flags:
    --verbose    Show full OCR text for each document
    --limit N    Only process N documents (default: all)
"""

import difflib
import json
import sqlite3
import sys
import urllib.request
import urllib.error
from pathlib import Path

PAPERLESS_URL   = "http://localhost:8010"
PAPERLESS_TOKEN = "51420bd5c9d61208b331d09a528019d50a70520b"
HEADERS = {"Authorization": f"Token {PAPERLESS_TOKEN}"}

DB_PATH  = Path.home() / "Documents/goj files/dashboard/auth_tracker.db"
REX_DIR  = Path.home() / "Desktop/REX"

VERBOSE  = "--verbose" in sys.argv
LIMIT    = None
for i, arg in enumerate(sys.argv):
    if arg == "--limit" and i + 1 < len(sys.argv):
        try:
            LIMIT = int(sys.argv[i + 1])
        except ValueError:
            pass

# ── Noise words to skip (food items, day headers, etc.) ──
NOISE_WORDS = {
    "monday","tuesday","wednesday","thursday","friday","saturday","sunday",
    "breakfast","lunch","dinner","snack","menu","weekly","shift","center",
    "garden","joy","adult","day","care","total","name","date","week",
    "пн","вт","ср","чт","пт","сб","вс",
    "soup","salad","bread","milk","juice","tea","coffee","rice","chicken",
    "fish","beef","pork","vegetables","fruit","dessert","hot","cold",
    "yes","no","none","n/a","na","x",
}


def paperless_get(path):
    url = f"{PAPERLESS_URL}/api/{path.lstrip('/')}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()[:200]}, e.code
    except urllib.error.URLError as e:
        print(f"❌  Cannot reach Paperless: {e}")
        sys.exit(1)


def load_clients():
    """Load all active clients from auth_tracker.db."""
    if not DB_PATH.exists():
        print(f"❌  Database not found: {DB_PATH}")
        sys.exit(1)

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT client_id, name FROM clients WHERE active=1")
    clients = {}
    for row in cur.fetchall():
        cid  = row["client_id"]
        full = (row["name"] or "").strip()
        if not full:
            continue
        norm = full.lower()
        clients[norm] = {"id": cid, "full": full}
    con.close()
    print(f"   Loaded {len(clients)} active clients from database.")
    return clients


def find_menu_docs():
    """Find menu documents in Paperless."""
    found = []
    page = 1
    while True:
        data, status = paperless_get(
            f"documents/?page_size=50&page={page}&ordering=-created"
        )
        if status != 200:
            break
        results = data.get("results", [])
        if not results:
            break

        for doc in results:
            title   = (doc.get("title") or "").lower()
            orig    = (doc.get("original_file_name") or "").lower()
            content = (doc.get("content") or "")  # OCR text Paperless already has

            is_menu = (
                "menu" in title
                or "menu" in orig
                or ("doc00" in orig and len(content) > 100)  # large scanner batch
            )
            # Exclude sign-in sheets and driver sheets
            is_not_menu = any(w in title for w in ["sign", "driver", "signin", "sign-in"])

            if is_menu and not is_not_menu:
                found.append({
                    "id":      doc["id"],
                    "title":   doc.get("title", "(no title)"),
                    "date":    doc.get("created", ""),
                    "content": content,
                    "orig":    doc.get("original_file_name", ""),
                })

        if not data.get("next"):
            break
        page += 1

    return found


def match_client(line: str, clients: dict) -> tuple:
    """
    Try to match a line of text to a client name.
    Returns (client_full_name, client_id, score) or (None, None, 0).
    """
    line = line.strip()
    if not line or len(line) < 3:
        return None, None, 0

    words = line.lower().split()
    if not words:
        return None, None, 0

    # Skip if first word is a noise word
    if words[0] in NOISE_WORDS:
        return None, None, 0

    # Skip purely numeric lines
    if all(w.replace(".", "").replace(",", "").isdigit() for w in words):
        return None, None, 0

    # Skip very short tokens (< 2 words or < 4 chars total)
    if len(words) < 2 and len(line) < 5:
        return None, None, 0

    norm = line.lower()

    # Exact match
    if norm in clients:
        c = clients[norm]
        return c["full"], c["id"], 1.0

    # Fuzzy match against all client names
    names = list(clients.keys())
    matches = difflib.get_close_matches(norm, names, n=1, cutoff=0.55)
    if matches:
        c = clients[matches[0]]
        score = difflib.SequenceMatcher(None, norm, matches[0]).ratio()
        return c["full"], c["id"], score

    return None, None, 0


def extract_candidate_lines(ocr_text: str) -> list:
    """Pull out lines from OCR text that could be client names."""
    candidates = []
    for line in ocr_text.splitlines():
        line = line.strip()
        if not line or len(line) < 3:
            continue
        words = line.split()
        if len(words) < 2 or len(words) > 6:
            continue  # names are 2-5 words
        # Must start with a letter
        if not line[0].isalpha():
            continue
        candidates.append(line)
    return candidates


def main():
    print("=" * 60)
    print("  Paperless Menu Reader — Direct OCR Text Extraction")
    print("=" * 60)

    # ── Load clients ─────────────────────────────────────
    print("\n👥  Loading client roster...")
    clients = load_clients()

    # ── Connect to Paperless ──────────────────────────────
    print("\n🔌  Connecting to Paperless...")
    data, status = paperless_get("documents/?page_size=1")
    if status != 200:
        print(f"❌  Paperless not reachable. Is Tailscale on?")
        sys.exit(1)
    print(f"   ✅  Connected — {data.get('count', '?')} total documents.")

    # ── Find menu documents ───────────────────────────────
    print("\n🔍  Searching for menu documents...")
    menu_docs = find_menu_docs()
    if LIMIT:
        menu_docs = menu_docs[:LIMIT]
    print(f"   Found {len(menu_docs)} menu document(s).")

    if not menu_docs:
        print("\n   No menu documents found. Try running goj_ingest_all.py first.")
        return

    # ── Process each doc ──────────────────────────────────
    print(f"\n{'─'*60}")
    all_matched   = {}   # client_id → {name, count, docs}
    all_unmatched = []   # (doc_title, line)

    for i, doc in enumerate(menu_docs, 1):
        print(f"\n[{i}/{len(menu_docs)}] {doc['title']}")
        print(f"         ID: {doc['id']}  |  File: {doc['orig'][:50]}")
        print(f"         Date: {doc['date'][:10]}")

        ocr_text = doc["content"]
        if not ocr_text or len(ocr_text.strip()) < 20:
            print(f"         ⚠️  No OCR text available for this document.")
            print(f"            → Paperless may not have processed it yet.")
            continue

        if VERBOSE:
            print(f"\n--- OCR TEXT ({len(ocr_text)} chars) ---")
            print(ocr_text[:1000])
            print("---")

        candidates = extract_candidate_lines(ocr_text)
        doc_matches  = []
        doc_unmatched = []

        for line in candidates:
            name, cid, score = match_client(line, clients)
            if name and score >= 0.55:
                doc_matches.append((name, cid, score, line))
                if cid not in all_matched:
                    all_matched[cid] = {"name": name, "count": 0, "docs": []}
                all_matched[cid]["count"] += 1
                if doc["title"] not in all_matched[cid]["docs"]:
                    all_matched[cid]["docs"].append(doc["title"])
            else:
                doc_unmatched.append(line)
                all_unmatched.append((doc["title"], line))

        print(f"         ✅  Matched:   {len(doc_matches)} client lines")
        print(f"         ❓  Unmatched: {len(doc_unmatched)} lines")

        if doc_matches:
            for name, cid, score, raw in doc_matches[:10]:
                pct = int(score * 100)
                print(f"            {pct}%  {name}  (raw: '{raw[:30]}')")
            if len(doc_matches) > 10:
                print(f"            ... and {len(doc_matches)-10} more")

        if doc_unmatched and VERBOSE:
            print(f"         Unmatched lines:")
            for line in doc_unmatched[:8]:
                print(f"            ? '{line}'")

    # ── Summary ───────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"  SUMMARY")
    print("=" * 60)
    print(f"  Documents processed:    {len(menu_docs)}")
    print(f"  Unique clients matched: {len(all_matched)}")
    print(f"  Unmatched lines total:  {len(all_unmatched)}")

    if all_matched:
        print(f"\n  Clients found in menus:")
        for cid, info in sorted(all_matched.items(), key=lambda x: x[1]["name"]):
            print(f"    ✅  [{cid:>5}] {info['name']}")

    if all_unmatched:
        print(f"\n  Top unmatched lines (may be client names with OCR errors):")
        seen = set()
        count = 0
        for doc_title, line in all_unmatched:
            if line.lower() not in seen and count < 20:
                seen.add(line.lower())
                print(f"    ?  '{line}'  (from: {doc_title[:40]})")
                count += 1

    print()
    print("  Next steps:")
    if len(all_matched) > 0:
        print("  ✅  Run goj_menu_ocr_processor.py to formally process and store results.")
    print("  📋  For unmatched lines, improving OCR (eng+rus) will help.")
    print("  🔍  Use --verbose flag to see full OCR text per document.")
    print()


if __name__ == "__main__":
    main()
