#!/usr/bin/env python3
"""
GOJ ← Paperless Sync
======================
Checks Paperless for new documents tagged GOJ-AUTH or GOJ-MENUS
and registers them in the dashboard DB if they're not already there.

This handles the case where docs are scanned DIRECTLY into Paperless
(not via the dashboard upload form). Runs every 30 min via LaunchAgent.

Designed to be idempotent — safe to run repeatedly.
"""

import sys
import json
import sqlite3
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, date

# ── Config ────────────────────────────────────────────────────────────────────
SCRIPT_DIR     = Path(__file__).parent
DASHBOARD      = Path.home() / "Documents" / "goj files" / "dashboard"
DB_PATH        = DASHBOARD / "auth_tracker.db"
AUTH_DOCS_BASE = DASHBOARD / "documents" / "authorization"
MENUS_BASE     = DASHBOARD / "documents" / "menus"

PAPERLESS_URL   = "http://100.99.86.60:8000"
PAPERLESS_TOKEN = "583e819be1146b96b935007c6ad7f584a3a1b1b7"
HEADERS = {"Authorization": f"Token {PAPERLESS_TOKEN}"}
TIMEOUT = 15

STATE_FILE = SCRIPT_DIR / "logs" / "paperless_sync_state.json"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get(path: str) -> tuple:
    url = f"{PAPERLESS_URL}/api/{path.lstrip('/')}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read()), r.status
    except Exception as e:
        return {}, 0


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"last_sync": None, "seen_paperless_ids": []}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def get_tag_id(tag_name: str) -> int | None:
    data, status = _get(f"tags/?name={urllib.parse.quote(tag_name)}")
    if status == 200 and data.get("results"):
        return data["results"][0]["id"]
    return None


def download_doc_from_paperless(doc_id: int, dest_path: Path) -> bool:
    """Download a document's PDF from Paperless to dest_path."""
    url = f"{PAPERLESS_URL}/api/documents/{doc_id}/download/"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(r.read())
            return True
    except Exception as e:
        print(f"     ↳ Download failed: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Quick connectivity check
    _, status = _get("documents/?page_size=1")
    if status != 200:
        print("Paperless unreachable — skipping sync (Tailscale may be off)")
        return 0   # Not an error — Tailscale might just be off

    state = load_state()
    seen_ids = set(state.get("seen_paperless_ids", []))

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    new_auth = 0
    new_menus = 0

    # ── Sync GOJ-AUTH tagged docs ─────────────────────────────────────────────
    auth_tag_id = get_tag_id("GOJ-AUTH")
    if auth_tag_id:
        page = 1
        while True:
            data, status = _get(f"documents/?tags__id={auth_tag_id}&page_size=50&page={page}&ordering=-created")
            if status != 200 or not data.get("results"):
                break
            for doc in data["results"]:
                pl_id = doc["id"]
                if pl_id in seen_ids:
                    continue
                seen_ids.add(pl_id)

                # Check if already in auth_documents
                cur.execute("SELECT doc_id FROM auth_documents WHERE paperless_id=?", (pl_id,))
                if cur.fetchone():
                    continue

                # Try to extract client name from title
                title = doc.get("title", "")
                # Title format: "ClientName — DocType" or just "ClientName"
                if " — " in title:
                    client_name, doc_type = title.split(" — ", 1)
                else:
                    client_name = title
                    doc_type = "Authorization Letter"

                client_name = client_name.strip()
                doc_type = doc_type.strip()

                # Download PDF to the right folder
                folder = AUTH_DOCS_BASE / client_name.replace("/", "_")
                safe_title = title.replace(" — ", "_").replace("/", "_")[:80]
                filename = f"{safe_title}_pl{pl_id}.pdf"
                dest = folder / filename

                print(f"  NEW AUTH DOC: {title} (Paperless id={pl_id})")
                if download_doc_from_paperless(pl_id, dest):
                    rel_path = str(dest.relative_to(AUTH_DOCS_BASE))
                    cur.execute("""
                        INSERT INTO auth_documents
                            (client_name, doc_type, original_filename, stored_filename,
                             stored_path_relative, file_size_bytes, paperless_id, paperless_url,
                             uploaded_by, notes)
                        VALUES (?,?,?,?,?,?,?,?,?,?)
                    """, (
                        client_name, doc_type, filename, filename, rel_path,
                        dest.stat().st_size if dest.exists() else 0,
                        pl_id, f"{PAPERLESS_URL}/documents/{pl_id}",
                        "paperless_sync",
                        f"Auto-synced from Paperless on {datetime.now().date()}"
                    ))
                    conn.commit()
                    new_auth += 1
                    print(f"     ↳ ✓ Registered in dashboard")

            if not data.get("next"):
                break
            page += 1

    # ── Sync GOJ-MENUS tagged docs ────────────────────────────────────────────
    menus_tag_id = get_tag_id("GOJ-MENUS")
    if menus_tag_id:
        page = 1
        while True:
            data, status = _get(f"documents/?tags__id={menus_tag_id}&page_size=50&page={page}&ordering=-created")
            if status != 200 or not data.get("results"):
                break
            for doc in data["results"]:
                pl_id = doc["id"]
                if pl_id in seen_ids:
                    continue
                seen_ids.add(pl_id)

                # Check if already in menus table
                cur.execute("SELECT id FROM menus WHERE paperless_id=?", (str(pl_id),))
                if cur.fetchone():
                    continue

                title = doc.get("title", f"GOJ Menu pl{pl_id}")
                filename = f"paperless_{pl_id}.pdf"
                dest = MENUS_BASE / filename

                print(f"  NEW MENU: {title} (Paperless id={pl_id})")
                if download_doc_from_paperless(pl_id, dest):
                    cur.execute("""
                        INSERT INTO menus
                            (stored_filename, original_filename, stored_path_relative,
                             week_start, scan_date, file_size_bytes,
                             paperless_id, source, uploaded_by, notes)
                        VALUES (?,?,?,?,?,?,?,?,?,?)
                    """, (
                        filename, filename, filename,
                        date.today().isoformat(),
                        date.today().isoformat(),
                        dest.stat().st_size if dest.exists() else 0,
                        str(pl_id),
                        "paperless_sync",
                        "paperless_sync",
                        f"Auto-synced from Paperless: {title}"
                    ))
                    conn.commit()
                    new_menus += 1
                    print(f"     ↳ ✓ Registered in dashboard")

            if not data.get("next"):
                break
            page += 1

    conn.close()

    # Update state
    state["last_sync"] = datetime.now().isoformat()
    state["seen_paperless_ids"] = sorted(seen_ids)
    save_state(state)

    if new_auth + new_menus == 0:
        print("No new Paperless documents to sync.")
    else:
        print(f"\nSync complete: +{new_auth} auth docs, +{new_menus} menus")

    return 0


if __name__ == "__main__":
    sys.exit(main())
