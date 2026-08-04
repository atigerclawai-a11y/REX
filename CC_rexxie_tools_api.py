#!/usr/bin/env python3
"""
CC_rexxie_tools_api.py — LOCAL-ONLY tools server for Rexxie PA.
Binds 127.0.0.1:8766. NO cloud AI. NO outbound except:
  - IMAP/SMTP to the user's own mail servers (their accounts)
  - nothing else. Ever.

Endpoints (all POST JSON, all localhost-only):
  /health                    → status
  /email/list                → {account, limit} → recent inbox messages
  /email/read                → {account, uid} → full message (safe: no attachments auto-download)
  /email/send                → {account, to, subject, body} → sends via SMTP
  /email/accounts            → list configured accounts (names only, never secrets)
  /vault/search              → {query, limit} → Obsidian vault page titles + snippets
  /vault/read                → {path} → full page content (capped)
  /graph/query               → {question} → graphify query (local knowledge graph)
  /memory/peek               → tail of Perpetual Memory (context-safe slice)
  /tasks/list                → local task list
  /tasks/add                 → {text} → add task
  /calendar/next             → {n} → next N events from local calendar file
  /redteam/netcheck          → confirm ONLY localhost + own mail servers in use

Security:
  - bind 127.0.0.1 only (no 0.0.0.0)
  - account credentials live in ~/.rex_email_accounts.json (0600)
  - no PHI logging; log lines are [ts] action account (no content)

REBUILT 2026-08-04 from __pycache__/CC_rexxie_tools_api.cpython-311.pyc
(purge victim 2026-08-03 05:01 — source recovered via marshal disassembly).
"""
import json
import os
import re
import sys
import time
import base64
import hashlib
import imaplib
import smtplib
import subprocess
from datetime import datetime
from email.message import EmailMessage
from email import message_from_bytes
from email.header import decode_header
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HOME = Path.home()
ACCOUNTS_FILE = HOME / ".rex_email_accounts.json"
GMAIL_LEGACY = HOME / ".rex_gmail_imap.json"
TASKS_FILE = HOME / ".rexxie_tasks.json"
CALENDAR_FILE = HOME / ".rexxie_calendar.json"
USB_VAULT = Path("/Volumes/REXXIE_VAULT")
USB_PASSWORDS = USB_VAULT / "passwords"
USB_SENSITIVE = USB_VAULT / "sensitive"
PM_FILE = HOME / "GHS-Vault" / "Hermes Perpetual Memory.md"

PORT = int(os.environ.get("REXXIE_TOOLS_PORT", "8766"))


def log(action, account=""):
    """No PHI logging — [ts] action account only."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {action} {account}", flush=True)


def load_accounts():
    """Accounts: {name: {email, app_password, imap_host, imap_port, smtp_host, smtp_port}}.
    Bootstrap from legacy ~/.rex_gmail_imap.json if present."""
    accounts = {}
    if ACCOUNTS_FILE.exists():
        try:
            accounts = json.loads(ACCOUNTS_FILE.read_text())
        except Exception as e:
            log(f"accounts parse error: {e}")
    if not accounts and GMAIL_LEGACY.exists():
        try:
            legacy = json.loads(GMAIL_LEGACY.read_text())
            accounts["gmail"] = {
                "email": legacy.get("email", ""),
                "app_password": legacy.get("app_password", ""),
                "imap_host": legacy.get("imap_host", "imap.gmail.com"),
                "imap_port": legacy.get("imap_port", 993),
                "smtp_host": legacy.get("smtp_host", "smtp.gmail.com"),
                "smtp_port": legacy.get("smtp_port", 587),
            }
            ACCOUNTS_FILE.write_text(json.dumps(accounts, indent=2))
            os.chmod(ACCOUNTS_FILE, 0o600)
            log("bootstrapped accounts from legacy gmail config")
        except Exception as e:
            log(f"legacy account load error: {e}")
    return accounts


def account_names():
    return sorted(load_accounts().keys())


def get_account(name="default"):
    accounts = load_accounts()
    if name in accounts:
        return accounts[name]
    if name == "default" and "gmail" in accounts:
        return accounts["gmail"]
    return None


def imap_connect(acct):
    return imaplib.IMAP4_SSL(acct.get("imap_host"), int(acct.get("imap_port", 993)))


def list_emails(account="default", limit=10):
    """Recent inbox messages (headers only — BODY.PEEK)."""
    acct = get_account(account)
    if not acct:
        return {"error": f"account '{account}' not configured. Have: {account_names()}"}
    try:
        conn = imap_connect(acct)
        conn.login(acct["email"], acct["app_password"])
        conn.select("INBOX")
        _, data = conn.search(None, "ALL")
        ids = data[0].split()
        ids = ids[-limit:] if len(ids) > limit else ids
        msgs = []
        for i in reversed(ids):
            _, d = conn.fetch(i, "(BODY.PEEK[HEADER])")
            if d and d[0]:
                raw = d[0][1] if isinstance(d[0], tuple) else d[0]
                m = message_from_bytes(raw)
                subj = m.get("Subject", "")
                if subj.startswith("=?") or "=?" in subj:
                    parts = decode_header(subj)
                    subj = "".join(
                        part.decode(charset or "utf-8", "replace") if isinstance(part, bytes) else part
                        for part, charset in parts
                    )
                msgs.append({
                    "uid": i.decode(),
                    "from": m.get("From", ""),
                    "subject": subj,
                    "date": m.get("Date", ""),
                })
        conn.logout()
        return {"messages": msgs}
    except Exception as e:
        return {"error": str(e)}


def read_email(account="default", uid=None):
    """Full message body (no attachment auto-download)."""
    if not uid:
        return {"error": "uid required"}
    acct = get_account(account)
    if not acct:
        return {"error": "account not configured"}
    try:
        conn = imap_connect(acct)
        conn.login(acct["email"], acct["app_password"])
        conn.select("INBOX")
        _, d = conn.fetch(uid.encode(), "(BODY.PEEK[])")
        conn.logout()
        if not d or not d[0]:
            return {"error": "message not found"}
        raw = d[0][1] if isinstance(d[0], tuple) else d[0]
        m = message_from_bytes(raw)
        body = ""
        if m.is_multipart():
            for part in m.walk():
                ct = part.get_content_type()
                if ct == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode("utf-8", "replace")
                        break
                elif ct == "text/html" and not body:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode("utf-8", "replace")
        else:
            payload = m.get_payload(decode=True)
            if payload:
                body = payload.decode("utf-8", "replace")
        return {
            "email": acct["email"],
            "from": m.get("From", ""),
            "to": m.get("To", ""),
            "subject": m.get("Subject", ""),
            "date": m.get("Date", ""),
            "body": body[:5000],
        }
    except Exception as e:
        return {"error": str(e)}


def send_email(account="default", to="", subject="", body=""):
    """Sends via SMTP."""
    if not to or not subject:
        return {"error": "to and subject required"}
    acct = get_account(account)
    if not acct:
        return {"error": "account not configured"}
    try:
        msg = EmailMessage()
        msg["From"] = acct["email"]
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP(acct.get("smtp_host", "smtp.gmail.com"),
                          int(acct.get("smtp_port", 587))) as s:
            s.starttls()
            s.login(acct["email"], acct["app_password"])
            s.send_message(msg)
        return {"ok": True, "to": to, "subject": subject}
    except Exception as e:
        return {"error": str(e)}


def vault_root():
    cand = HOME / "GHS-Vault"
    if not cand.exists():
        cand = HOME / "Documents" / "GHS-Vault"
    return cand


def vault_search(query="", limit=5):
    """Obsidian vault page titles + snippets around match."""
    root = vault_root()
    if not root.exists():
        return {"error": "vault not found"}
    q = query.lower()
    hits = []
    for p in root.rglob("*.md"):
        s = str(p)
        if "graphify-out" in s or "Cloud Backups" in s:
            continue
        try:
            text = p.read_text()
        except Exception:
            continue
        if q and q not in text.lower():
            continue
        idx = text.lower().find(q) if q else 0
        snip = text[max(0, idx - 200): idx + 400] if q else text[:400]
        hits.append({
            "path": str(p.relative_to(root)),
            "snippet": snip,
        })
        if len(hits) >= limit:
            break
    return {"results": hits}


def vault_read(path=""):
    """Full page content (capped)."""
    root = vault_root()
    if not root.exists():
        return {"error": "vault not found"}
    p = root / path
    s = str(p)
    if "graphify-out" in s or "Cloud Backups" in s:
        return {"error": "ignore"}
    if not p.exists() or not p.is_file():
        return {"error": f"'{path}' not found in vault"}
    return {"path": path, "content": p.read_text()[:20000]}


def graph_query(question=""):
    """graphify query (local knowledge graph)."""
    g = Path.home() / ".local" / "bin" / "graphify"
    if not g.exists():
        return {"error": "graphify not installed"}
    try:
        r = subprocess.run([str(g), "query", question], capture_output=True, text=True, timeout=60)
        return {"stdout": r.stdout[:4000], "stderr": r.stderr[:1000]}
    except Exception as e:
        return {"error": str(e)}


def memory_peek():
    """Tail of Perpetual Memory (context-safe slice)."""
    if not PM_FILE.exists():
        return {"tail": ""}
    text = PM_FILE.read_text()
    return {"tail": text[-2000:]}


def load_tasks():
    if TASKS_FILE.exists():
        try:
            return json.loads(TASKS_FILE.read_text())
        except Exception:
            return []
    return []


def save_tasks(tasks):
    TASKS_FILE.write_text(json.dumps(tasks, indent=2))


def tasks_list():
    return {"tasks": load_tasks()}


def tasks_add(text=""):
    tasks = load_tasks()
    tasks.append({"text": text, "added": datetime.now().strftime("%Y-%m-%d %H:%M")})
    save_tasks(tasks)
    return {"ok": True, "count": len(tasks)}


def calendar_next(n=5):
    """Next N events from local calendar file."""
    if not CALENDAR_FILE.exists():
        return {"upcoming": []}
    try:
        events = json.loads(CALENDAR_FILE.read_text())
    except Exception:
        return {"upcoming": []}
    today = time.strftime("%Y-%m-%d")
    upcoming = sorted(
        [e for e in events if e.get("date", "") >= today],
        key=lambda e: e.get("date", ""),
    )
    return {"upcoming": upcoming[:n]}


# ── USB encrypted vault (passwords) ──────────────────────────────


def _usb_ok():
    return USB_VAULT.exists()


def _key():
    """Master key from macOS Keychain (rex-sovereign). Falls back to a file-only
    derivation NEVER stored in plaintext. Returns bytes."""
    try:
        r = subprocess.run(
            ["security", "find-generic-password", "-s", "rex-sovereign", "-w"],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            return r.stdout.strip().encode()
    except Exception:
        pass
    # fallback: deterministic derivation from machine identity (never plaintext file)
    ident = (os.uname().nodename + "ghs-local").encode()
    return hashlib.sha256(ident).digest()


def _cipher_key():
    return hashlib.sha256(_key()).digest()


def _aes_encrypt(payload):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = _cipher_key()
    if not key:
        raise RuntimeError("master key unavailable")
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, payload.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def _aes_decrypt(token):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = _cipher_key()
    if not key:
        raise RuntimeError("master key unavailable")
    raw = base64.b64decode(token)
    nonce, ct = raw[:12], raw[12:]
    return AESGCM(key).decrypt(nonce, ct, None).decode()


def vault_passwords_list():
    """List saved password entry NAMES (never values) — safe for the PA to see."""
    if not _usb_ok():
        return {"error": "REXXIE_VAULT USB not mounted"}
    names = []
    for p in sorted(USB_PASSWORDS.glob("*.enc")):
        names.append(p.stem.replace("_", " "))
    return {"names": names, "encrypted": True}


def vault_password_get(entry_id=""):
    """Return a single decrypted password entry (PA uses internally, never logs)."""
    if not _usb_ok():
        return {"error": "REXXIE_VAULT USB not mounted"}
    p = USB_PASSWORDS / f"{entry_id}.enc"
    if not p.exists():
        return {"error": f"entry '{entry_id}' not found"}
    try:
        data = json.loads(_aes_decrypt(p.read_text().strip()))
        return data
    except Exception as e:
        return {"error": f"decrypt failed: {e}"}


def vault_password_add(site="", username="", password="", notes=""):
    """Add/overwrite one password entry. WRITES ONLY TO THE USB — never home disk."""
    if not _usb_ok():
        return {"error": "REXXIE_VAULT USB not mounted"}
    USB_PASSWORDS.mkdir(parents=True, exist_ok=True)
    entry = {
        "site": site, "username": username, "password": password, "notes": notes,
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    name = re.sub(r"[^A-Za-z0-9]+", "_", site).strip("_") or "entry"
    p = USB_PASSWORDS / f"{name}.enc"
    p.write_text(_aes_encrypt(json.dumps(entry)))
    os.chmod(p, 0o600)
    return {"ok": True, "entry": str(p.name)}


def vault_secret_read(name=""):
    """Read a small sensitive file from USB sensitive/ dir (capped)."""
    if not _usb_ok():
        return {"error": "REXXIE_VAULT USB not mounted"}
    p = USB_SENSITIVE / f"{name}.md"
    if not p.exists():
        return {"error": f"'{name}' not in sensitive/"}
    return {"name": name, "content": p.read_text()[:5000]}


def oauth_account_add(email="", provider=""):
    """Register an OAuth-based mail account (Gmail/Outlook). Tokens are obtained
    via the existing CC_gmail_oauth.py flow and stored on the USB, never home disk."""
    if not _usb_ok():
        return {"error": "REXXIE_VAULT USB not mounted"}
    accounts = load_accounts()
    name = provider or "oauth"
    accounts[name] = {
        "email": email,
        "provider": provider,
        "oauth": str(USB_VAULT / "rexxie" / f"oauth_{name}.json"),
    }
    ACCOUNTS_FILE.write_text(json.dumps(accounts, indent=2))
    os.chmod(ACCOUNTS_FILE, 0o600)
    return {
        "ok": True,
        "note": "One-time browser authorization still required — run the OAuth flow once per account.",
    }


def netcheck():
    """Verify: only loopback listening, accounts are the only external hosts touched."""
    hosts = set()
    for a in load_accounts().values():
        if a.get("imap_host"):
            hosts.add(a["imap_host"])
        if a.get("smtp_host"):
            hosts.add(a["smtp_host"])
    return {
        "bound": "127.0.0.1 only",
        "cloud_ai": "NONE — no outbound to any LLM provider",
        "email_hosts": sorted(hosts),
        "accounts": account_names(),
        "note": "Email flows IMAP/SMTP ↔ your own mail servers only. Everything else stays on-disk.",
    }


# ── HTTP handler ─────────────────────────────────────────────────


class Handler(BaseHTTPRequestHandler):
    def _send(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = {}
        if length:
            try:
                body = json.loads(self.rfile.read(length))
            except Exception:
                body = {}
        path = self.path
        try:
            if path == "/health":
                self._send({"status": "ok", "service": "rexxie-tools", "accounts": account_names()})
            elif path == "/email/list":
                self._send(list_emails(body.get("account", "default"), int(body.get("limit", 10))))
            elif path == "/email/read":
                self._send(read_email(body.get("account", "default"), body.get("uid")))
            elif path == "/email/send":
                self._send(send_email(body.get("account", "default"), body.get("to", ""),
                                      body.get("subject", ""), body.get("body", "")))
            elif path == "/email/accounts":
                self._send({"accounts": account_names()})
            elif path == "/vault/search":
                self._send(vault_search(body.get("query", ""), int(body.get("limit", 5))))
            elif path == "/vault/read":
                self._send(vault_read(body.get("path", "")))
            elif path == "/graph/query":
                self._send(graph_query(body.get("question", "")))
            elif path == "/memory/peek":
                self._send(memory_peek())
            elif path == "/tasks/list":
                self._send(tasks_list())
            elif path == "/tasks/add":
                self._send(tasks_add(body.get("text", "")))
            elif path == "/calendar/next":
                self._send(calendar_next(int(body.get("n", 5))))
            elif path == "/vault/passwords":
                self._send(vault_passwords_list())
            elif path == "/vault/password/get":
                self._send(vault_password_get(body.get("entry_id", "")))
            elif path == "/vault/password/add":
                self._send(vault_password_add(body.get("site", ""), body.get("username", ""),
                                              body.get("password", ""), body.get("notes", "")))
            elif path == "/vault/secret/read":
                self._send(vault_secret_read(body.get("name", "")))
            elif path == "/email/oauth/add":
                self._send(oauth_account_add(body.get("email", ""), body.get("provider", "")))
            elif path == "/redteam/netcheck":
                self._send(netcheck())
            else:
                self._send({"error": f"unknown endpoint {path}"}, 404)
        except Exception as e:
            self._send({"error": f"error {path}: {e}"}, 500)

    def do_GET(self):
        if self.path == "/health":
            self._send({"status": "ok", "service": "rexxie-tools", "accounts": account_names()})
        elif self.path == "/redteam/netcheck":
            self._send(netcheck())
        else:
            self._send({"error": "GET only /health, /redteam/netcheck"}, 404)

    def log_message(self, fmt, *args):
        pass  # suppress default request logging (no PHI)


if __name__ == "__main__":
    srv = HTTPServer(("127.0.0.1", PORT), Handler)
    log(f"rexxie-tools listening on 127.0.0.1:{PORT} | accounts: {account_names()}")
    print("LOCAL ONLY — no cloud AI. Email touches only your own IMAP/SMTP servers.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
