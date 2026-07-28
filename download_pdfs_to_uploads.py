#!/usr/bin/env python3
"""
Download 6 PDF attachments from Gmail to ~/Desktop/REX/uploads/
Uses the existing ~/.rex_google_token.json credentials.
Run from: ~/Desktop/REX/
"""
import sys
import base64
from pathlib import Path

TOKEN_PATH  = Path.home() / ".rex_google_token.json"
UPLOADS_DIR = Path.home() / "Desktop/REX/uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

TARGETS = [
    ("19d5610067936f9f", "doc00167820260330143352.pdf"),
    ("19d5604f33622807", "doc00189720260403100057.pdf"),
    ("19d560489c99e9e9", "doc00189920260403100157.pdf"),
    ("19d56036b11ce00a", "doc00190420260403121359.pdf"),
    ("19d5603007ff6a08", "doc00198320260403154200.pdf"),
    ("19d560244978fd0e", "doc00198520260403162451.pdf"),
]

if not TOKEN_PATH.exists():
    print(f"❌  Gmail token not found at {TOKEN_PATH}")
    sys.exit(1)

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
except ImportError:
    print("❌  google-api-python-client not installed.")
    print("    Run: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client --break-system-packages")
    sys.exit(1)

print("🔐  Loading Gmail credentials...")
creds = Credentials.from_authorized_user_file(
    str(TOKEN_PATH),
    ["https://www.googleapis.com/auth/gmail.readonly"],
)
if creds and creds.expired and creds.refresh_token:
    creds.refresh(Request())
if not creds or not creds.valid:
    print("❌  Gmail credentials invalid or expired.")
    sys.exit(1)

svc = build("gmail", "v1", credentials=creds)
print("✅  Gmail authenticated.\n")

def get_parts(payload):
    """Recursively collect all MIME parts."""
    parts = []
    if payload.get("body", {}).get("attachmentId"):
        parts.append(payload)
    for sub in payload.get("parts", []):
        parts.extend(get_parts(sub))
    return parts

results = []
for msg_id, filename in TARGETS:
    out_path = UPLOADS_DIR / filename
    if out_path.exists():
        size = out_path.stat().st_size
        print(f"✅  Already exists: {filename} ({size:,} bytes) — skipping")
        results.append((filename, "exists", size))
        continue

    print(f"📥  Downloading {filename} from message {msg_id} ...")
    try:
        msg     = svc.users().messages().get(userId="me", id=msg_id, format="full").execute()
        payload = msg.get("payload", {})
        all_parts = get_parts(payload)

        saved = False
        for part in all_parts:
            fname = part.get("filename", "")
            mime  = part.get("mimeType", "")
            att_id = part.get("body", {}).get("attachmentId", "")
            if att_id and (fname == filename or "pdf" in mime.lower() or fname.endswith(".pdf")):
                att  = svc.users().messages().attachments().get(
                    userId="me", messageId=msg_id, id=att_id
                ).execute()
                data = base64.urlsafe_b64decode(att["data"] + "==")
                out_path.write_bytes(data)
                print(f"   ✅  Saved → {out_path}  ({len(data):,} bytes)")
                results.append((filename, "downloaded", len(data)))
                saved = True
                break

        if not saved:
            print(f"   ⚠️   No matching PDF part found in message {msg_id}")
            results.append((filename, "not_found", 0))

    except Exception as e:
        print(f"   ❌  Error: {e}")
        results.append((filename, "error", 0))

print("\n" + "="*60)
print("SUMMARY — ~/Desktop/REX/uploads/")
print("="*60)
for fname, status, size in results:
    icon = "✅" if status in ("exists","downloaded") else "❌"
    print(f"  {icon}  {fname:<45} {size:>12,} bytes  [{status}]")

ok = sum(1 for _,s,_ in results if s in ("exists","downloaded"))
print(f"\n{ok}/{len(TARGETS)} files ready in uploads/")
