"""
GOJ Ingest All — Gmail → Paperless
====================================
Downloads every unprocessed PDF from GOJ scanner emails and uploads
them to Paperless-NGX with correct tags.

Sources scanned:
  • goj3152.scans@gmail.com  (Olympus scanner batches — menus + sign-in)
  • allen@gardenofjoybrooklyn.com (Allen manual attachments)
  • olympusbbg@gmail.com      (Allen's personal scanner — manual sign-in sheets)

Since: March 1 2026 (edit START_DATE below to change)

Run:
    cd ~/Desktop/REX && source .venv/bin/activate
    python goj_ingest_all.py

Flags:
    --dry-run     Show what would be uploaded, don't actually upload
    --since YYYY/MM/DD  Override start date (e.g. --since 2026/03/01)
    --reocr       After upload, trigger re-OCR on all GOJ docs in Paperless
"""

import base64
import json
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

START_DATE      = "2026/03/01"
UPLOADS_DIR     = Path.home() / "Desktop" / "REX" / "uploads"
REX_DIR         = Path.home() / "Desktop" / "REX"
TOKEN_PATH      = Path.home() / ".rex_google_token.json"
CREDS_PATH      = REX_DIR / "google_credentials.json"
INGEST_LOG_FILE = REX_DIR / "goj_ingest_log.json"

PAPERLESS_URL   = "http://100.99.86.60:8000"
PAPERLESS_TOKEN = "583e819be1146b96b935007c6ad7f584a3a1b1b7"

SCANNER_SENDERS = [
    "goj3152.scans@gmail.com",
    "allen@gardenofjoybrooklyn.com",
    "olympusbbg@gmail.com",
]

DRY_RUN = "--dry-run" in sys.argv
REOCR   = "--reocr" in sys.argv

# Override start date from CLI: --since 2026/01/01
if "--since" in sys.argv:
    idx = sys.argv.index("--since")
    if idx + 1 < len(sys.argv):
        START_DATE = sys.argv[idx + 1]


# ─── Paperless helpers ────────────────────────────────────────────────────────

def paperless_req(method: str, path: str, body: dict = None):
    """Simple JSON request to Paperless API."""
    url  = f"{PAPERLESS_URL}/api/{path.lstrip('/')}"
    data = json.dumps(body).encode() if body else None
    headers = {
        "Authorization": f"Token {PAPERLESS_TOKEN}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return {"error": str(e), "detail": e.read().decode()[:200]}, e.code
    except urllib.error.URLError as e:
        print(f"\n❌  Cannot reach Paperless at {PAPERLESS_URL}: {e}")
        print("    → Is Tailscale connected?")
        sys.exit(1)


def paperless_search_by_filename(filename: str) -> list:
    """Search Paperless for a document by its original filename."""
    # Try title search first
    base = Path(filename).stem  # remove .pdf
    data, status = paperless_req("GET", f"documents/?title__icontains={urllib.parse.quote(base)}&page_size=5")
    if status == 200:
        return data.get("results", [])
    return []


def paperless_upload(pdf_bytes: bytes, filename: str, tags: list[str], title: str = None) -> tuple[bool, str]:
    """
    Upload a PDF to Paperless via multipart/form-data POST /api/documents/post_document/
    Returns (success: bool, message: str)
    """
    url = f"{PAPERLESS_URL}/api/documents/post_document/"

    # Resolve tag IDs
    tag_ids = []
    for tag_name in tags:
        existing, status = paperless_req("GET", f"tags/?name={urllib.parse.quote(tag_name)}")
        if status == 200 and existing.get("results"):
            tag_ids.append(existing["results"][0]["id"])
        else:
            # Create tag
            created, cs = paperless_req("POST", "tags/", {"name": tag_name, "color": "#4a7c59"})
            if cs in (200, 201) and "id" in created:
                tag_ids.append(created["id"])

    # Build multipart/form-data
    boundary = "----GOJIngestBoundary"

    def field(name, value):
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode()

    body = b""
    if title:
        body += field("title", title)
    for tid in tag_ids:
        body += field("tags", str(tid))

    # File part
    body += (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode()
    body += pdf_bytes
    body += f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Token {PAPERLESS_TOKEN}",
            "Content-Type":  f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = r.read().decode()
            return True, f"status {r.status}: {resp[:100]}"
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:200]
        return False, f"HTTP {e.code}: {detail}"
    except Exception as e:
        return False, str(e)


def trigger_reocr_all_goj():
    """Trigger re-OCR on all GOJ scanner docs in Paperless."""
    print("\n🔄  Triggering re-OCR on GOJ docs in Paperless...")
    data, status = paperless_req("GET", "documents/?page_size=100&ordering=-created")
    if status != 200:
        print(f"   ❌  Could not list docs: {status}")
        return

    docs = data.get("results", [])
    goj_docs = [
        d for d in docs
        if "doc00" in (d.get("original_file_name") or "").lower()
        or "goj" in (d.get("title") or "").lower()
        or "signin" in (d.get("title") or "").replace(" ", "").lower()
        or "menu" in (d.get("title") or "").lower()
    ]

    triggered = 0
    for doc in goj_docs:
        _, s = paperless_req("POST", "documents/bulk_edit/", {
            "documents": [doc["id"]],
            "method":    "redo_ocr",
        })
        if s in (200, 204):
            triggered += 1
        time.sleep(0.15)

    print(f"   ✅  Re-OCR queued for {triggered} documents.")


# ─── Gmail helpers ────────────────────────────────────────────────────────────

import urllib.parse

def build_gmail_service():
    """Authenticate and return Gmail API service."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        print("❌  google-api-python-client not installed.")
        print("    Run: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client --break-system-packages")
        sys.exit(1)

    if not TOKEN_PATH.exists():
        print(f"❌  Gmail token not found at {TOKEN_PATH}")
        print("    Run: python rex_gmail_auth.py  (or re-authenticate via OAuth)")
        sys.exit(1)

    creds = Credentials.from_authorized_user_file(
        str(TOKEN_PATH),
        ["https://www.googleapis.com/auth/gmail.readonly"],
    )
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        print("❌  Gmail credentials invalid. Re-run OAuth flow.")
        sys.exit(1)

    return build("gmail", "v1", credentials=creds)


def get_all_parts(payload):
    """Recursively extract all MIME parts."""
    parts = []
    mime = payload.get("mimeType", "")
    att_id = payload.get("body", {}).get("attachmentId")
    filename = payload.get("filename", "")
    if att_id and filename:
        parts.append(payload)
    for sub in payload.get("parts", []):
        parts.extend(get_all_parts(sub))
    return parts


def classify_pdf(filename: str, subject: str, sender: str) -> tuple[list[str], str]:
    """
    Decide which Paperless tags to apply and build a clean title.
    Returns (tags: list[str], title: str)
    """
    fn_lower = filename.lower()
    sub_lower = subject.lower()

    tags = ["GOJ"]

    # Detect scanner batch date from filename pattern doc00XXXXYYYYMMDDHHMMSS.pdf
    date_str = ""
    m = re.match(r"doc\d{5}(\d{8})", fn_lower)
    if m:
        raw = m.group(1)  # YYYYMMDD
        try:
            d = datetime.strptime(raw, "%Y%m%d")
            date_str = d.strftime("%Y-%m-%d")
        except Exception:
            date_str = raw

    # Sign-in sheet detection
    if any(w in fn_lower for w in ["signin", "sign_in", "sign-in", "sign in", "s1", "s2"]) \
    or any(w in sub_lower for w in ["signin", "sign in", "attendance"]) \
    or any(w in fn_lower for w in ["mon", "tue", "wed", "thu", "fri", "sat"]):
        tags.append("SignIn")
        # Extract day from filename if present
        day_map = {"mon": "Mon", "tue": "Tue", "wed": "Wed", "thu": "Thu", "fri": "Fri", "sat": "Sat"}
        day = next((day_map[k] for k in day_map if k in fn_lower), "")
        shift = "S2" if "s2" in fn_lower else "S1" if "s1" in fn_lower else ""
        parts = ["GOJ SignIn"]
        if day:
            parts.append(day)
        if shift:
            parts.append(shift)
        if date_str:
            parts.append(date_str)
        title = " ".join(parts)

    # Menu detection
    elif any(w in fn_lower for w in ["menu", "order", "form"]) \
    or any(w in sub_lower for w in ["menu", "food order"]):
        tags.append("Menu")
        title = f"GOJ Menu {date_str}" if date_str else f"GOJ Menu {filename}"

    # Large scanner batch (likely mixed or menu week)
    elif fn_lower.startswith("doc00"):
        tags.append("Scanner")
        title = f"GOJ Scan {date_str}" if date_str else f"GOJ Scan {filename}"

    else:
        tags.append("Document")
        title = f"GOJ Doc {filename}"

    return tags, title


# ─── Ingest log ───────────────────────────────────────────────────────────────

def load_log() -> dict:
    if INGEST_LOG_FILE.exists():
        try:
            return json.loads(INGEST_LOG_FILE.read_text())
        except Exception:
            pass
    return {"uploaded": {}, "skipped": {}, "failed": {}}


def save_log(log: dict):
    INGEST_LOG_FILE.write_text(json.dumps(log, indent=2, ensure_ascii=False))


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  GOJ Ingest All — Gmail → Paperless")
    print(f"  Since: {START_DATE}   Dry-run: {DRY_RUN}")
    print("=" * 60)

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    log = load_log()

    # ── Authenticate Gmail ────────────────────────────────────
    print("\n🔐  Authenticating Gmail...")
    svc = build_gmail_service()
    print("   ✅  Gmail connected.")

    # ── Verify Paperless ──────────────────────────────────────
    print("\n🔌  Checking Paperless connection...")
    data, status = paperless_req("GET", "documents/?page_size=1")
    if status != 200:
        print(f"   ❌  Paperless not reachable (status {status}). Is Tailscale on?")
        sys.exit(1)
    total = data.get("count", 0)
    print(f"   ✅  Paperless connected — {total} documents currently stored.")

    # ── Search Gmail for scanner emails ──────────────────────
    all_attachments = []  # list of (msg_id, msg_subject, sender, filename, attachment_id)

    sender_query = " OR ".join(f"from:{s}" for s in SCANNER_SENDERS)
    query = f"({sender_query}) after:{START_DATE} has:attachment"

    print(f"\n🔍  Searching Gmail for scanner emails since {START_DATE}...")
    page_token = None
    page_count  = 0
    while True:
        params = {"userId": "me", "q": query, "maxResults": 50}
        if page_token:
            params["pageToken"] = page_token
        result = svc.users().messages().list(**params).execute()
        messages = result.get("messages", [])
        page_count += 1

        for msg_meta in messages:
            msg_id = msg_meta["id"]
            msg = svc.users().messages().get(userId="me", id=msg_id, format="full").execute()
            payload = msg.get("payload", {})

            # Extract subject + sender from headers
            headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
            subject = headers.get("subject", "")
            sender  = headers.get("from", "")

            # Find all PDF parts
            pdf_parts = [
                p for p in get_all_parts(payload)
                if p.get("filename", "").lower().endswith(".pdf")
                and p.get("body", {}).get("attachmentId")
            ]

            for part in pdf_parts:
                fname  = part["filename"]
                att_id = part["body"]["attachmentId"]
                all_attachments.append((msg_id, subject, sender, fname, att_id))

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    print(f"   Found {len(all_attachments)} PDF attachments across {page_count} page(s).")

    if not all_attachments:
        print("\n   No PDF attachments found. Check that Gmail OAuth has access to this account.")
        return

    # ── Process each attachment ───────────────────────────────
    stats = {"uploaded": 0, "skipped_cached": 0, "skipped_paperless": 0, "failed": 0}

    print(f"\n{'─'*60}")
    print(f"  Processing {len(all_attachments)} attachments...")
    print(f"{'─'*60}\n")

    for i, (msg_id, subject, sender, filename, att_id) in enumerate(all_attachments, 1):
        print(f"[{i:>3}/{len(all_attachments)}] {filename}")
        print(f"        From: {sender[:50]}")
        print(f"        Subject: {subject[:60]}")

        # ── Skip if already uploaded (by our log) ────────────
        log_key = f"{msg_id}_{filename}"
        if log_key in log["uploaded"]:
            print(f"        ✅ Already uploaded — skipping.\n")
            stats["skipped_cached"] += 1
            continue
        if log_key in log["failed"] and not DRY_RUN:
            print(f"        ♻️  Previously failed — retrying...\n")

        # ── Check if already in Paperless ────────────────────
        existing = paperless_search_by_filename(filename)
        if existing:
            print(f"        📁 Already in Paperless (doc id={existing[0]['id']}) — skipping.\n")
            log["skipped"][log_key] = {
                "filename": filename, "paperless_id": existing[0]["id"],
                "at": datetime.now().isoformat()
            }
            stats["skipped_paperless"] += 1
            save_log(log)
            continue

        # ── Classify ──────────────────────────────────────────
        tags, title = classify_pdf(filename, subject, sender)
        print(f"        🏷️  Tags: {tags}  |  Title: {title}")

        if DRY_RUN:
            print(f"        🔵 DRY-RUN — would upload as: {title}\n")
            stats["uploaded"] += 1
            continue

        # ── Download from Gmail ───────────────────────────────
        local_path = UPLOADS_DIR / filename
        if not local_path.exists():
            print(f"        📥 Downloading from Gmail...")
            try:
                att = svc.users().messages().attachments().get(
                    userId="me", messageId=msg_id, id=att_id
                ).execute()
                pdf_bytes = base64.urlsafe_b64decode(att["data"] + "==")
                local_path.write_bytes(pdf_bytes)
                print(f"        ✅ Downloaded: {len(pdf_bytes):,} bytes")
            except Exception as e:
                print(f"        ❌ Download failed: {e}\n")
                log["failed"][log_key] = {"filename": filename, "error": str(e), "at": datetime.now().isoformat()}
                stats["failed"] += 1
                save_log(log)
                continue
        else:
            pdf_bytes = local_path.read_bytes()
            print(f"        📂 Using cached: {len(pdf_bytes):,} bytes")

        # ── Upload to Paperless ───────────────────────────────
        print(f"        🚀 Uploading to Paperless...")
        ok, msg_out = paperless_upload(pdf_bytes, filename, tags, title)
        if ok:
            print(f"        ✅ Uploaded! {msg_out[:80]}\n")
            log["uploaded"][log_key] = {
                "filename": filename, "title": title, "tags": tags,
                "sender": sender[:60], "at": datetime.now().isoformat()
            }
            log["failed"].pop(log_key, None)
            stats["uploaded"] += 1
        else:
            print(f"        ❌ Upload failed: {msg_out[:120]}\n")
            log["failed"][log_key] = {"filename": filename, "error": msg_out[:120], "at": datetime.now().isoformat()}
            stats["failed"] += 1

        save_log(log)
        time.sleep(0.5)  # be kind to Paperless

    # ── Summary ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  INGEST SUMMARY")
    print("=" * 60)
    print(f"  ✅ Uploaded:              {stats['uploaded']}")
    print(f"  📁 Already in Paperless: {stats['skipped_paperless']}")
    print(f"  ⚡ Already uploaded:     {stats['skipped_cached']}")
    print(f"  ❌ Failed:               {stats['failed']}")
    print(f"\n  Log saved → {INGEST_LOG_FILE}")

    # ── Optional: trigger re-OCR ──────────────────────────────
    if REOCR or stats["uploaded"] > 0:
        if not DRY_RUN:
            trigger_reocr_all_goj()
            print("\n⏳  Paperless will OCR new docs in the background (1–5 min).")
            print("   Then run:")
            print("   python goj_menu_ocr_processor.py")
            print("   python goj_signin_ocr_processor.py")

    print("\n✅  Done.\n")


if __name__ == "__main__":
    main()
