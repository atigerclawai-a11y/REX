#!/usr/bin/env python3
"""
Download 9 missing menu PDFs from Gmail and upload to Paperless-NGX.
Run from ~/Desktop/REX/ (venv active).
"""
import sys, base64, json, time, warnings, urllib.request, urllib.error, mimetypes
warnings.filterwarnings("ignore")
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
TOKEN_PATH      = Path.home() / ".rex_google_token.json"
REX_TOKEN_PATH  = Path.home() / "Desktop" / "REX" / ".rex_google_token.json"
DOWNLOADS_DIR   = Path.home() / "Desktop" / "REX" / "menu_pdfs_missing"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

PAPERLESS_URL   = "http://100.99.86.60:8000"
PAPERLESS_TOKEN = "583e819be1146b96b935007c6ad7f584a3a1b1b7"

# Missing Gmail messages — NOT yet in Paperless
MISSING = [
    ("19d56572c638493f", "doc00167720260330143248.pdf"),   # 19 MB Mar 30 — LARGE
    ("19d4d19f94f51332", "doc00168020260330143546.pdf"),   # 1.8 MB
    ("19d4d179fa4987e1", "doc00170220260330163909.pdf"),   # 3.0 MB
    ("19d4d173eb8333ef", "doc00170320260330163951.pdf"),   # 2.7 MB
    ("19d4d104bedb7b21", "doc00170420260330164037.pdf"),   # 2.3 MB
    ("19d4d0ff4722f74f", "doc00170520260330164100.pdf"),   # 1.9 MB
    ("19d4d0f713c89b33", "doc00172320260331104256.pdf"),   # 2.2 MB
    ("19d4d0ed2dd3ad7c", "doc00172420260331104322.pdf"),   # 1.8 MB
    ("19d4d0d8abb30752", "doc00178320260401094217.pdf"),   # 2.3 MB
]

# ── Gmail auth ────────────────────────────────────────────────────────────────
tok_path = REX_TOKEN_PATH if REX_TOKEN_PATH.exists() else TOKEN_PATH
if not tok_path.exists():
    print(f"❌  Token not found at {tok_path}"); sys.exit(1)

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
except ImportError:
    print("❌  google-api-python-client not installed.")
    print("    pip install google-auth google-api-python-client --break-system-packages")
    sys.exit(1)

print("🔐  Loading Gmail credentials...")
creds = Credentials.from_authorized_user_file(str(tok_path), ["https://www.googleapis.com/auth/gmail.readonly"])
if creds and creds.expired and creds.refresh_token:
    print("   Refreshing token...")
    creds.refresh(Request())
if not creds or not creds.valid:
    print("❌  Gmail credentials invalid."); sys.exit(1)
print("✅  Gmail authenticated.\n")

svc = build("gmail", "v1", credentials=creds)

def get_parts(payload):
    parts = []
    if payload.get("body", {}).get("attachmentId"):
        parts.append(payload)
    for sub in payload.get("parts", []):
        parts.extend(get_parts(sub))
    return parts

# ── Paperless upload ─────────────────────────────────────────────────────────
def upload_to_paperless(pdf_path, title="GOJ Menu — Menu Shift 1 — Week 2026-03-30", created="2026-03-30"):
    """Upload a PDF file to Paperless-NGX via the post_document API."""
    pdf_bytes = pdf_path.read_bytes()
    boundary = b"----PaperlessBoundary7a8b9c"

    def field(name, value):
        return (b"--" + boundary + b"\r\n"
                + f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
                + value.encode() + b"\r\n")

    def file_field(name, filename, data):
        return (b"--" + boundary + b"\r\n"
                + f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
                + b"Content-Type: application/pdf\r\n\r\n"
                + data + b"\r\n")

    body = (field("title", title)
            + field("created", created)
            + file_field("document", pdf_path.name, pdf_bytes)
            + b"--" + boundary + b"--\r\n")

    req = urllib.request.Request(
        f"{PAPERLESS_URL}/api/documents/post_document/",
        data=body,
        headers={
            "Authorization": f"Token {PAPERLESS_TOKEN}",
            "Content-Type": f"multipart/form-data; boundary={boundary.decode()}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = r.read()
            return True, resp.decode()
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read()[:300].decode()}"
    except Exception as e:
        return False, str(e)

# ── Main loop ─────────────────────────────────────────────────────────────────
downloaded = []
uploaded   = []
errors     = []

for msg_id, hint_filename in MISSING:
    dest = DOWNLOADS_DIR / hint_filename
    # ── Download ──
    if dest.exists():
        print(f"  [{msg_id}] {hint_filename} already downloaded ({dest.stat().st_size/1e6:.1f} MB)")
        downloaded.append(dest)
    else:
        try:
            msg     = svc.users().messages().get(userId="me", messageId=msg_id, format="full").execute()
            parts   = get_parts(msg.get("payload", {}))
            if not parts:
                print(f"  [{msg_id}] ⚠️  No attachment found — skipping")
                errors.append(msg_id)
                continue
            part    = parts[0]
            att_id  = part["body"]["attachmentId"]
            print(f"  [{msg_id}] Downloading {hint_filename}...", end="", flush=True)
            att  = svc.users().messages().attachments().get(userId="me", messageId=msg_id, id=att_id).execute()
            data = base64.urlsafe_b64decode(att["data"])
            dest.write_bytes(data)
            print(f" {len(data)/1e6:.1f} MB ✅")
            downloaded.append(dest)
        except Exception as e:
            print(f"  [{msg_id}] ❌  Download failed: {e}")
            errors.append(msg_id)
            continue

    # ── Upload to Paperless ──
    print(f"  → Uploading {dest.name} to Paperless...", end="", flush=True)
    ok, resp = upload_to_paperless(dest)
    if ok:
        print(f" ✅  (task_id: {resp[:60]})")
        uploaded.append(dest.name)
    else:
        print(f" ❌  {resp[:100]}")
        errors.append(dest.name)

# ── Summary ────────────────────────────────────────────────────────────────────
print(f"\n{'='*55}")
print(f"Downloaded: {len(downloaded)}/{len(MISSING)} PDFs")
print(f"Uploaded:   {len(uploaded)}/{len(MISSING)} to Paperless")
print(f"Errors:     {len(errors)}")

if uploaded:
    print(f"\n⏳  Paperless is now OCR-ing {len(uploaded)} new document(s).")
    print(f"    This typically takes 2–5 minutes per document.")
    print(f"\n    When done, run:  python3 paperless_menu_extract.py")
    print(f"    to re-extract all menus and rebuild GOJ_Menu_Orders.json.")
print(f"\n✅  Done.")
