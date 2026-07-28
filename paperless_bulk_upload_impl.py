#!/usr/bin/env python3
"""
GOJ → Paperless Bulk Uploader
==============================
Uploads all auth docs and menu PDFs that have paperless_id = NULL
to Paperless-NGX, then stores the Paperless document ID back in the DB.

Run once to catch up on 567 existing auth docs.
After this, all new uploads auto-push via the dashboard.

Requires: Tailscale on, Paperless at 100.99.86.60:8000
"""

import sys
import json
import sqlite3
import time
import urllib.request
import urllib.error
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
SCRIPT_DIR     = Path(__file__).parent
DASHBOARD      = Path.home() / "Documents" / "goj files" / "dashboard"
DB_PATH        = DASHBOARD / "auth_tracker.db"
AUTH_DOCS_BASE = DASHBOARD / "documents" / "authorization"
MENUS_BASE     = DASHBOARD / "documents" / "menus"

PAPERLESS_URL   = "http://100.99.86.60:8000"
PAPERLESS_TOKEN = "583e819be1146b96b935007c6ad7f584a3a1b1b7"
HEADERS = {"Authorization": f"Token {PAPERLESS_TOKEN}"}

RATE_LIMIT_DELAY = 1.0   # seconds between uploads (be gentle on Paperless)
TIMEOUT_UPLOAD   = 60    # seconds per upload
TIMEOUT_SHORT    = 8     # seconds for quick API calls


# ── Paperless API helpers ─────────────────────────────────────────────────────

def pl_health() -> bool:
    try:
        req = urllib.request.Request(
            f"{PAPERLESS_URL}/api/documents/?page_size=1",
            headers=HEADERS
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_SHORT) as r:
            return r.status == 200
    except Exception:
        return False


def pl_get_or_create_tag(name: str, cache: dict) -> int | None:
    """Return Paperless tag ID for name, creating if needed. Cache avoids duplicate lookups."""
    if name in cache:
        return cache[name]
    import urllib.parse
    url = f"{PAPERLESS_URL}/api/tags/?name={urllib.parse.quote(name)}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SHORT) as r:
            data = json.loads(r.read())
            if data.get("results"):
                tag_id = data["results"][0]["id"]
                cache[name] = tag_id
                return tag_id
    except Exception:
        pass
    # Create tag
    body = json.dumps({"name": name}).encode()
    req = urllib.request.Request(
        f"{PAPERLESS_URL}/api/tags/",
        data=body,
        headers={**HEADERS, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SHORT) as r:
            data = json.loads(r.read())
            tag_id = data.get("id")
            if tag_id:
                cache[name] = tag_id
                return tag_id
    except Exception as e:
        print(f"     ⚠️  Could not create tag '{name}': {e}")
    return None


def pl_upload(file_path: Path, title: str, tag_ids: list) -> dict:
    """Upload a file to Paperless. Returns dict with 'task_id' or 'error'."""
    boundary = "----GOJBulkBoundary"
    pdf_bytes = file_path.read_bytes()

    body = b""
    body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"title\"\r\n\r\n{title}\r\n".encode()
    for tid in tag_ids:
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"tags\"\r\n\r\n{tid}\r\n".encode()
    body += (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"document\"; filename=\"{file_path.name}\"\r\n"
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode()
    body += pdf_bytes
    body += f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{PAPERLESS_URL}/api/documents/post_document/",
        data=body,
        headers={
            "Authorization": f"Token {PAPERLESS_TOKEN}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_UPLOAD) as r:
            resp_text = r.read().decode()
            return {"status": "ok", "task_id": resp_text.strip().strip('"')}
    except urllib.error.HTTPError as e:
        return {"status": "error", "detail": e.read().decode()[:300]}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def pl_find_by_title(title: str) -> int | None:
    """Check if a doc with this exact title already exists in Paperless."""
    import urllib.parse
    url = f"{PAPERLESS_URL}/api/documents/?title={urllib.parse.quote(title)}&page_size=5"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SHORT) as r:
            data = json.loads(r.read())
            for doc in data.get("results", []):
                if doc.get("title", "").lower() == title.lower():
                    return doc["id"]
    except Exception:
        pass
    return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("🔌 Checking Paperless connection...")
    if not pl_health():
        print("❌ Cannot reach Paperless at", PAPERLESS_URL)
        print()
        print("Make sure:")
        print("  1. Tailscale is ON")
        print("  2. The Paperless machine is running")
        print("  3. You can open http://100.99.86.60:8000 in your browser")
        return 1

    print("   ✓ Paperless is reachable\n")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get all auth docs that haven't been uploaded to Paperless
    cur.execute("""
        SELECT doc_id, client_name, doc_type, stored_path_relative, stored_filename,
               file_size_bytes, original_filename
        FROM auth_documents
        WHERE (paperless_id IS NULL OR paperless_id = '')
          AND client_name != 'UNMATCHED'
          AND stored_path_relative IS NOT NULL
        ORDER BY client_name, uploaded_at
    """)
    auth_docs = cur.fetchall()

    # Get all menu docs that haven't been uploaded
    cur.execute("""
        SELECT id, stored_filename, week_start, scan_date, stored_path_relative
        FROM menus
        WHERE (paperless_id IS NULL OR paperless_id = '')
          AND stored_filename IS NOT NULL
        ORDER BY week_start, stored_filename
    """)
    menu_docs = cur.fetchall()

    total_auth  = len(auth_docs)
    total_menus = len(menu_docs)
    total       = total_auth + total_menus

    print(f"📊 Auth docs to upload:  {total_auth}")
    print(f"   Menu PDFs to upload:  {total_menus}")
    print(f"   Total:                {total}")
    print()

    if total == 0:
        print("✅ Everything is already in Paperless!")
        conn.close()
        return 0

    tag_cache = {}

    # Pre-create the main tags
    print("🏷️  Setting up Paperless tags...")
    for tag_name in ["GOJ-AUTH", "GOJ-MENUS", "GOJ-OPERATIONS"]:
        tid = pl_get_or_create_tag(tag_name, tag_cache)
        if tid:
            print(f"   ✓ {tag_name} (id={tid})")
        else:
            print(f"   ⚠️  {tag_name} — could not create")
    print()

    uploaded = 0
    skipped  = 0
    failed   = 0

    # ── Upload auth docs ──────────────────────────────────────────────────────
    if auth_docs:
        print(f"═══ AUTH DOCUMENTS ({total_auth}) ═══════════════════")
        for i, doc in enumerate(auth_docs, 1):
            rel = doc['stored_path_relative']
            full_path = AUTH_DOCS_BASE / rel
            if not full_path.exists():
                print(f"  [{i:4}/{total_auth}] ✗ FILE MISSING: {rel}")
                failed += 1
                continue

            title = f"{doc['client_name']} — {doc['doc_type']}"
            print(f"  [{i:4}/{total_auth}] {doc['client_name']} ({doc['doc_type']})")

            # Check if already in Paperless by title
            existing_id = pl_find_by_title(title)
            if existing_id:
                print(f"           ↳ Already in Paperless (id={existing_id}) — updating DB")
                cur.execute(
                    "UPDATE auth_documents SET paperless_id=?, paperless_url=? WHERE doc_id=?",
                    (existing_id, f"{PAPERLESS_URL}/documents/{existing_id}", doc['doc_id'])
                )
                conn.commit()
                skipped += 1
                continue

            # Get tag IDs
            tag_ids = [tag_cache.get("GOJ-AUTH")] if "GOJ-AUTH" in tag_cache else []
            client_tag_id = pl_get_or_create_tag(doc['client_name'], tag_cache)
            if client_tag_id:
                tag_ids.append(client_tag_id)

            result = pl_upload(full_path, title, [t for t in tag_ids if t])
            if result.get("status") == "ok":
                print(f"           ↳ ✓ Uploaded (task: {result.get('task_id','?')[:16]}...)")
                # Note: Paperless processes async — task_id ≠ doc_id
                # Store task_id in notes for now; a later sync can resolve to doc_id
                cur.execute(
                    "UPDATE auth_documents SET notes = COALESCE(notes||' | ', '') || ? WHERE doc_id=?",
                    (f"paperless_task:{result.get('task_id','')[:36]}", doc['doc_id'])
                )
                conn.commit()
                uploaded += 1
            else:
                print(f"           ↳ ❌ Failed: {result.get('detail','?')[:80]}")
                failed += 1

            time.sleep(RATE_LIMIT_DELAY)

    # ── Upload menu PDFs ──────────────────────────────────────────────────────
    if menu_docs:
        print()
        print(f"═══ MENU PDFs ({total_menus}) ═══════════════════════")
        for i, menu in enumerate(menu_docs, 1):
            rel = menu['stored_path_relative'] or menu['stored_filename']
            full_path = MENUS_BASE / rel
            if not full_path.exists():
                # Try just filename in MENUS_BASE
                full_path = MENUS_BASE / menu['stored_filename']
                if not full_path.exists():
                    print(f"  [{i:3}/{total_menus}] ✗ FILE MISSING: {rel}")
                    failed += 1
                    continue

            week = menu['week_start'] or 'unknown'
            title = f"GOJ Menu — Week {week} — {menu['stored_filename']}"
            print(f"  [{i:3}/{total_menus}] {menu['stored_filename']} (week {week})")

            tag_ids = [t for t in [
                tag_cache.get("GOJ-MENUS"),
                tag_cache.get("GOJ-OPERATIONS"),
            ] if t]

            result = pl_upload(full_path, title, tag_ids)
            if result.get("status") == "ok":
                print(f"         ↳ ✓ Uploaded")
                cur.execute(
                    "UPDATE menus SET paperless_id=? WHERE id=?",
                    (result.get('task_id','')[:36], menu['id'])
                )
                conn.commit()
                uploaded += 1
            else:
                print(f"         ↳ ❌ Failed: {result.get('detail','?')[:80]}")
                failed += 1

            time.sleep(RATE_LIMIT_DELAY)

    conn.close()

    print()
    print("═" * 50)
    print(f"  Uploaded:  {uploaded}")
    print(f"  Skipped:   {skipped} (already in Paperless)")
    print(f"  Failed:    {failed}")
    print("═" * 50)
    print()
    print("Note: Paperless processes uploads asynchronously.")
    print("Documents will appear in Paperless within 1-2 minutes.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
