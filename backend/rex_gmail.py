"""
rex_gmail.py — Gmail Integration for REX

Provides:
  • Daily inbox digest (summary of important emails)
  • Auto-labeling rules (GOJ, authorizations, urgent, etc.)
  • On-demand search from REX/Rexxie chat
  • Unread count + sender watch

OAuth2 tokens stored in ~/.rex_google_token.json
Credentials (from Google Cloud) go in REX root as google_credentials.json

Setup:
  1. Go to console.cloud.google.com → New project
  2. Enable Gmail API + Google Drive API
  3. OAuth consent screen → Desktop app
  4. Download credentials.json → ~/Desktop/REX/google_credentials.json
  5. Run: python backend/rex_gmail.py --setup
"""

import os
import json
import re
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from email.mime.text import MIMEText
import base64

logger = logging.getLogger("rex.gmail")

# ── Paths ──────────────────────────────────────────────────────────────
REX_DIR   = Path(__file__).resolve().parent.parent
CREDS_PATH = REX_DIR / "google_credentials.json"
TOKEN_PATH = Path.home() / ".rex_google_token.json"

# ── Auto-label rules ───────────────────────────────────────────────────
# Each rule: { "label": str, "senders": [...], "keywords": [...], "subject_patterns": [...] }
DEFAULT_LABEL_RULES = [
    {
        "label":            "REX/GOJ",
        "senders":          ["@gov.jm", "@moh.gov.jm", "@mlss.gov.jm", "@mof.gov.jm"],
        "keywords":         ["GOJ", "government of jamaica", "ministry", "authorization"],
        "subject_patterns": ["authorization", "approval", "schedule", "directive"],
    },
    {
        "label":            "REX/Authorizations",
        "senders":          [],
        "keywords":         [],
        "subject_patterns": ["authorization", "auth request", "approved", "denied", "pending approval"],
    },
    {
        "label":            "REX/Urgent",
        "senders":          [],
        "keywords":         ["urgent", "asap", "immediately", "critical", "emergency"],
        "subject_patterns": ["urgent", "action required", "immediate", "asap"],
    },
    {
        "label":            "REX/Schedules",
        "senders":          [],
        "keywords":         ["schedule", "roster", "timetable", "shift"],
        "subject_patterns": ["schedule", "roster", "weekly", "monthly plan"],
    },
]


def _get_service():
    """Return authenticated Gmail API service, triggering OAuth if needed."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError(
            "Google API packages not installed. Run: "
            "pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client --break-system-packages"
        )

    # IMPORTANT: keep Drive scopes alongside Gmail so this auto-refresh
    # path doesn't strip Drive access on every token refresh. Several other
    # consumers (Drive watcher, ingest agent, gdrive_mirror) read the same
    # ~/.rex_google_token.json and break when Drive scopes are missing.
    SCOPES = [
        "https://www.googleapis.com/auth/gmail.modify",         # read + label
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/drive.file",           # upload + read OCR files (Engine 2)
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive.metadata.readonly",
        "https://www.googleapis.com/auth/documents",            # Google Docs OCR conversion
    ]

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS_PATH.exists():
                raise FileNotFoundError(
                    f"Google credentials not found at {CREDS_PATH}. "
                    "Run setup: python backend/rex_gmail.py --setup"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
            creds = flow.run_local_server(port=0, access_type='offline', prompt='consent')
        _tok = json.loads(creds.to_json())
        if not _tok.get("scopes"):
            _tok["scopes"] = SCOPES
        TOKEN_PATH.write_text(json.dumps(_tok))

    return build("gmail", "v1", credentials=creds)


def is_configured() -> bool:
    """True if Gmail is set up and token exists."""
    return TOKEN_PATH.exists() and CREDS_PATH.exists()


def get_profile() -> Dict[str, Any]:
    """Return Gmail profile info."""
    try:
        svc = _get_service()
        profile = svc.users().getProfile(userId="me").execute()
        return {"ok": True, "email": profile.get("emailAddress"), "total": profile.get("messagesTotal")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_unread_count() -> int:
    """Return number of unread messages in inbox."""
    try:
        svc = _get_service()
        result = svc.users().messages().list(
            userId="me", labelIds=["INBOX", "UNREAD"], maxResults=1
        ).execute()
        return result.get("resultSizeEstimate", 0)
    except Exception:
        return -1


def _decode_body(payload: dict) -> str:
    """Extract plain-text body from a Gmail message payload."""
    body = ""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            body = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    elif "parts" in payload:
        for part in payload["parts"]:
            body += _decode_body(part)
    return body


def _parse_headers(headers: list) -> dict:
    """Convert list of {name, value} headers to a dict (lowercase keys)."""
    return {h["name"].lower(): h["value"] for h in headers}


def get_inbox_summary(max_messages: int = 20) -> Dict[str, Any]:
    """
    Fetch up to `max_messages` recent unread messages and return a structured summary.
    Used for daily digest.
    """
    try:
        svc = _get_service()
        # Get unread messages from inbox
        result = svc.users().messages().list(
            userId="me",
            labelIds=["INBOX", "UNREAD"],
            maxResults=max_messages
        ).execute()
        messages = result.get("messages", [])
        if not messages:
            return {"ok": True, "count": 0, "emails": [], "summary": "No unread messages. Inbox is clear. ✓"}

        emails = []
        for msg_ref in messages:
            try:
                msg = svc.users().messages().get(
                    userId="me", id=msg_ref["id"], format="metadata",
                    metadataHeaders=["From", "Subject", "Date"]
                ).execute()
                headers  = _parse_headers(msg.get("payload", {}).get("headers", []))
                snippet  = msg.get("snippet", "")
                emails.append({
                    "id":      msg_ref["id"],
                    "from":    headers.get("from", "Unknown"),
                    "subject": headers.get("subject", "(no subject)"),
                    "date":    headers.get("date", ""),
                    "snippet": snippet[:200],
                    "labels":  msg.get("labelIds", []),
                })
            except Exception as e:
                logger.warning(f"Skipping message {msg_ref['id']}: {e}")

        # Build plain-text summary
        lines = [f"📬 **{len(emails)} unread emails** in your inbox:\n"]
        for i, e in enumerate(emails, 1):
            lines.append(f"{i}. **From:** {e['from']}")
            lines.append(f"   **Subject:** {e['subject']}")
            lines.append(f"   {e['snippet'][:150]}…\n")

        return {"ok": True, "count": len(emails), "emails": emails, "summary": "\n".join(lines)}
    except Exception as e:
        logger.error(f"Gmail summary failed: {e}")
        return {"ok": False, "error": str(e), "count": 0, "emails": []}


def search_emails(query: str, max_results: int = 10) -> Dict[str, Any]:
    """
    Search Gmail with a query string (supports Gmail search syntax).
    e.g. "from:boss@company.com subject:authorization"
    """
    try:
        svc = _get_service()
        result = svc.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()
        messages = result.get("messages", [])
        if not messages:
            return {"ok": True, "count": 0, "emails": [], "summary": f"No emails found for: '{query}'"}

        emails = []
        for msg_ref in messages:
            try:
                msg = svc.users().messages().get(
                    userId="me", id=msg_ref["id"], format="metadata",
                    metadataHeaders=["From", "To", "Subject", "Date"]
                ).execute()
                headers = _parse_headers(msg.get("payload", {}).get("headers", []))
                emails.append({
                    "id":      msg_ref["id"],
                    "from":    headers.get("from", "Unknown"),
                    "to":      headers.get("to", ""),
                    "subject": headers.get("subject", "(no subject)"),
                    "date":    headers.get("date", ""),
                    "snippet": msg.get("snippet", "")[:250],
                    "labels":  msg.get("labelIds", []),
                })
            except Exception as e:
                logger.warning(f"Skipping message: {e}")

        lines = [f"🔍 Found **{len(emails)} email(s)** for `{query}`:\n"]
        for i, e in enumerate(emails, 1):
            lines.append(f"{i}. **{e['subject']}**")
            lines.append(f"   From: {e['from']}  |  {e['date'][:16]}")
            lines.append(f"   {e['snippet'][:150]}…\n")

        return {"ok": True, "count": len(emails), "emails": emails, "summary": "\n".join(lines)}
    except Exception as e:
        return {"ok": False, "error": str(e), "count": 0, "emails": []}


def _ensure_label(svc, label_name: str) -> Optional[str]:
    """Get or create a Gmail label by name. Returns label ID."""
    try:
        labels_result = svc.users().labels().list(userId="me").execute()
        for lbl in labels_result.get("labels", []):
            if lbl["name"].lower() == label_name.lower():
                return lbl["id"]
        # Create it
        created = svc.users().labels().create(
            userId="me",
            body={
                "name":                  label_name,
                "labelListVisibility":   "labelShow",
                "messageListVisibility": "show",
            }
        ).execute()
        logger.info(f"Created Gmail label: {label_name}")
        return created["id"]
    except Exception as e:
        logger.warning(f"Label ensure failed for '{label_name}': {e}")
        return None


def _email_matches_rule(email: dict, rule: dict) -> bool:
    """Check if an email matches an auto-label rule."""
    sender   = email.get("from", "").lower()
    subject  = email.get("subject", "").lower()
    snippet  = email.get("snippet", "").lower()
    combined = f"{subject} {snippet}"

    for domain in rule.get("senders", []):
        if domain.lower() in sender:
            return True
    for kw in rule.get("keywords", []):
        if kw.lower() in combined:
            return True
    for pat in rule.get("subject_patterns", []):
        if pat.lower() in subject:
            return True
    return False


def run_auto_label(max_messages: int = 50) -> Dict[str, Any]:
    """
    Scan recent inbox messages and apply auto-labels based on DEFAULT_LABEL_RULES.
    Returns a summary of what was labeled.
    """
    try:
        svc = _get_service()

        # Pre-create/fetch all label IDs
        label_ids_cache: Dict[str, str] = {}
        for rule in DEFAULT_LABEL_RULES:
            lbl_name = rule["label"]
            lid = _ensure_label(svc, lbl_name)
            if lid:
                label_ids_cache[lbl_name] = lid

        # Fetch recent inbox messages (read + unread)
        result = svc.users().messages().list(
            userId="me", labelIds=["INBOX"], maxResults=max_messages
        ).execute()
        messages = result.get("messages", [])

        labeled_count = 0
        actions = []

        for msg_ref in messages:
            try:
                msg = svc.users().messages().get(
                    userId="me", id=msg_ref["id"], format="metadata",
                    metadataHeaders=["From", "Subject"]
                ).execute()
                headers = _parse_headers(msg.get("payload", {}).get("headers", []))
                email_data = {
                    "from":    headers.get("from", ""),
                    "subject": headers.get("subject", ""),
                    "snippet": msg.get("snippet", ""),
                    "labels":  msg.get("labelIds", []),
                }

                add_labels = []
                for rule in DEFAULT_LABEL_RULES:
                    lbl_name = rule["label"]
                    lid = label_ids_cache.get(lbl_name)
                    if lid and lid not in email_data["labels"] and _email_matches_rule(email_data, rule):
                        add_labels.append(lid)

                if add_labels:
                    svc.users().messages().modify(
                        userId="me", id=msg_ref["id"],
                        body={"addLabelIds": add_labels}
                    ).execute()
                    labeled_count += 1
                    label_names = [k for k, v in label_ids_cache.items() if v in add_labels]
                    actions.append({
                        "subject": email_data["subject"][:60],
                        "from":    email_data["from"][:40],
                        "applied": label_names,
                    })
            except Exception as e:
                logger.warning(f"Auto-label error for {msg_ref['id']}: {e}")

        summary = f"✅ Auto-labeled **{labeled_count}** email(s) across {len(DEFAULT_LABEL_RULES)} rules."
        return {"ok": True, "labeled": labeled_count, "actions": actions, "summary": summary}
    except Exception as e:
        logger.error(f"Auto-label run failed: {e}")
        return {"ok": False, "error": str(e), "labeled": 0, "actions": []}


def get_label_rules() -> List[dict]:
    return DEFAULT_LABEL_RULES


def save_label_rules(rules: List[dict]) -> None:
    """Persist custom label rules to rex_gmail_rules.json in REX root."""
    path = REX_DIR / "rex_gmail_rules.json"
    path.write_text(json.dumps(rules, indent=2))
    DEFAULT_LABEL_RULES.clear()
    DEFAULT_LABEL_RULES.extend(rules)


def load_label_rules() -> None:
    """Load custom rules from file if present."""
    path = REX_DIR / "rex_gmail_rules.json"
    if path.exists():
        try:
            rules = json.loads(path.read_text())
            DEFAULT_LABEL_RULES.clear()
            DEFAULT_LABEL_RULES.extend(rules)
        except Exception as e:
            logger.warning(f"Could not load custom label rules: {e}")


def send_email(to: str, subject: str, body: str) -> Dict[str, Any]:
    """
    Send an email from the configured Gmail account via the Gmail API.
    Returns {"ok": True} on success or {"ok": False, "error": "..."} on failure.
    """
    svc = _get_service()
    if not svc:
        return {"ok": False, "error": "Gmail not configured — run Gmail setup first."}
    try:
        message = MIMEText(body, "plain")
        message["to"]      = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        svc.users().messages().send(userId="me", body={"raw": raw}).execute()
        logger.info(f"📧 Email sent to {to}: {subject}")
        return {"ok": True}
    except Exception as e:
        logger.error(f"send_email failed: {e}")
        return {"ok": False, "error": str(e)}


# ── CLI ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    load_label_rules()

    if "--setup" in sys.argv:
        print("🔑 Starting Gmail OAuth2 setup...")
        print(f"   Looking for credentials at: {CREDS_PATH}")
        if not CREDS_PATH.exists():
            print(f"\n❌  credentials.json not found at {CREDS_PATH}")
            print("   Steps:")
            print("   1. Go to https://console.cloud.google.com")
            print("   2. Create/select a project")
            print("   3. Enable 'Gmail API' and 'Google Drive API'")
            print("   4. OAuth consent screen → External → Add your email as test user")
            print("   5. Credentials → Create → OAuth client ID → Desktop app")
            print("   6. Download JSON → save as ~/Desktop/REX/google_credentials.json")
            sys.exit(1)
        try:
            svc = _get_service()
            p   = svc.users().getProfile(userId="me").execute()
            print(f"\n✅ Connected to Gmail as: {p['emailAddress']}")
            print(f"   Total messages: {p.get('messagesTotal', '?')}")
            print(f"   Token saved to: {TOKEN_PATH}")
        except Exception as e:
            print(f"\n❌ Setup failed: {e}")
        sys.exit(0)

    elif "--summary" in sys.argv:
        load_label_rules()
        result = get_inbox_summary()
        if result["ok"]:
            print(result["summary"])
        else:
            print(f"Error: {result['error']}")

    elif "--autolabel" in sys.argv:
        result = run_auto_label()
        if result["ok"]:
            print(result["summary"])
            for a in result["actions"]:
                print(f"  → [{', '.join(a['applied'])}] {a['subject']}")
        else:
            print(f"Error: {result['error']}")

    elif "--search" in sys.argv:
        idx = sys.argv.index("--search")
        if idx + 1 < len(sys.argv):
            q = sys.argv[idx + 1]
            result = search_emails(q)
            print(result["summary"])
        else:
            print("Usage: python backend/rex_gmail.py --search 'your query'")

    else:
        print("Usage:")
        print("  --setup       Run OAuth2 setup (one-time)")
        print("  --summary     Show inbox summary")
        print("  --autolabel   Run auto-labeling on inbox")
        print("  --search Q    Search emails")
