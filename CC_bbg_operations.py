#!/usr/bin/env python3
"""
CC_bbg_operations.py
====================
Unified BBG Operations System — replaces Lead Connector / GHL.

Capabilities:
  - Contact DB (SQLite) with full conversation history
  - SMS sending via carrier email gateways (free, no Twilio needed)
  - Email campaigns via himalaya SMTP
  - Call logging + transcripts (manual + Retell webhook)
  - Reservation sync from CC_bbg_reservations.json
  - REST API + simple dashboard HTML

Start:
    uvicorn CC_bbg_operations:app --host 0.0.0.0 --port 8100 --reload

DB:   ~/Desktop/REX/CC_bbg_contacts.db
"""

import json
import logging
import os
import smtplib
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Any, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("bbg_ops")

REX_DIR = Path.home() / "Desktop" / "REX"
DB_PATH = REX_DIR / "CC_bbg_contacts.db"
RESERVATIONS_PATH = REX_DIR / "CC_bbg_reservations.json"

# ── Carrier email-to-SMS gateways ──────────────────────────────────────────
CARRIER_GATEWAYS = {
    "att": "txt.att.net",
    "verizon": "vtext.com",
    "tmobile": "tmomail.net",
    "sprint": "messaging.sprintpcs.com",
    "google_fi": "msg.fi.google.com",
    "boost": "sms.myboostmobile.com",
    "cricket": "mms.cricketwireless.net",
    "metro": "mymetropcs.com",
    "us_cellular": "email.uscc.net",
    "virgin": "vmobl.com",
}

BBG_PHONE = "9292056408"  # for SMS sender ID tagging
BBG_EMAIL = "olympusbbg@gmail.com"
BBG_NAME = "Boardwalk Beer Garden"

# ── Database ────────────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            notes TEXT,
            tags TEXT DEFAULT '',
            source TEXT DEFAULT 'manual',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER REFERENCES contacts(id),
            channel TEXT NOT NULL,  -- 'call', 'sms', 'email', 'instagram', 'walk_in'
            direction TEXT NOT NULL, -- 'inbound', 'outbound'
            body TEXT,
            duration_sec INTEGER,
            recording_url TEXT,
            transcript TEXT,
            metadata TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            channel TEXT NOT NULL, -- 'sms', 'email'
            subject TEXT,
            body TEXT NOT NULL,
            filter_tags TEXT DEFAULT '',
            sent_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            sent_at TEXT
        );

        CREATE TABLE IF NOT EXISTS campaign_recipients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER REFERENCES campaigns(id),
            contact_id INTEGER REFERENCES contacts(id),
            status TEXT DEFAULT 'pending', -- 'pending', 'sent', 'failed'
            sent_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_contacts_phone ON contacts(phone);
        CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
        CREATE INDEX IF NOT EXISTS idx_conversations_contact ON conversations(contact_id);
        CREATE INDEX IF NOT EXISTS idx_conversations_created ON conversations(created_at);
    """)
    conn.commit()
    conn.close()


init_db()

# ── Pydantic models ─────────────────────────────────────────────────────────

class ContactCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None
    tags: str = ""
    source: str = "manual"


class ConversationLog(BaseModel):
    contact_id: Optional[int] = None
    contact_phone: Optional[str] = None
    contact_name: Optional[str] = None
    channel: str  # call, sms, email, instagram, walk_in
    direction: str = "inbound"
    body: Optional[str] = None
    duration_sec: Optional[int] = None
    recording_url: Optional[str] = None
    transcript: Optional[str] = None


class SMSMessage(BaseModel):
    phone: str
    message: str
    carrier: Optional[str] = None  # if known, otherwise guess from number


class EmailCampaign(BaseModel):
    name: str
    subject: str
    body: str
    filter_tags: str = ""  # comma-separated tags to filter contacts
    contact_ids: Optional[list[int]] = None


# ── SMS via carrier gateway ─────────────────────────────────────────────────

def send_sms(phone: str, message: str, carrier: Optional[str] = None) -> dict:
    """Send SMS via carrier email-to-SMS gateway. Returns status dict."""
    phone = "".join(c for c in phone if c.isdigit())
    if len(phone) == 11 and phone.startswith("1"):
        phone = phone[1:]
    if len(phone) != 10:
        return {"success": False, "error": f"Invalid phone: {phone}"}

    # Determine gateway
    gateway = None
    if carrier and carrier in CARRIER_GATEWAYS:
        gateway = CARRIER_GATEWAYS[carrier]

    if not gateway:
        return {
            "success": False,
            "error": f"No carrier specified. Known carriers: {list(CARRIER_GATEWAYS.keys())}",
            "hint": "Use format: carrier=verizon|att|tmobile|sprint|google_fi"
        }

    to_addr = f"{phone}@{gateway}"
    msg = MIMEMultipart()
    msg["From"] = BBG_EMAIL
    msg["To"] = to_addr
    msg["Subject"] = "BBG"
    msg.attach(MIMEText(f"[Boardwalk Beer Garden]\n{message}\n\nReply STOP to opt out.", "plain"))

    try:
        # Use himalaya SMTP via subprocess
        # Determine himalaya path
        himalaya_paths = ["/opt/homebrew/bin/himalaya", "/usr/local/bin/himalaya", "himalaya"]
        himalaya_cmd = None
        for p in himalaya_paths:
            if os.path.exists(p) or p == "himalaya":
                himalaya_cmd = p
                break
        
        pipe = subprocess.Popen(
            [himalaya_cmd or "himalaya", "template", "send"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        template = f"From: {BBG_NAME} <{BBG_EMAIL}>\nTo: {to_addr}\nSubject: BBG\n\n[Boardwalk Beer Garden]\n{message}\n\nReply STOP to opt out."
        stdout, stderr = pipe.communicate(input=template, timeout=15)
        if pipe.returncode != 0:
            # Fallback: direct SMTP
            logger.warning(f"himalaya SMS send failed: {stderr}, trying direct SMTP")
            _send_direct_smtp(to_addr, message)
        logger.info(f"SMS sent to {phone} via {carrier}")
        return {"success": True, "to": phone, "carrier": carrier}
    except Exception as e:
        logger.error(f"SMS failed for {phone}: {e}")
        return {"success": False, "error": str(e)}


def _send_direct_smtp(to_addr: str, message: str):
    """Fallback direct SMTP for SMS sending."""
    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login("olympusbbg@gmail.com", "Olympus12345!")
    msg = MIMEText(f"[Boardwalk Beer Garden]\n{message}", "plain")
    msg["From"] = BBG_EMAIL
    msg["To"] = to_addr
    msg["Subject"] = "BBG"
    server.send_message(msg)
    server.quit()


# ── Contact helpers ─────────────────────────────────────────────────────────

def find_or_create_contact(phone: str = None, email: str = None, name: str = None) -> int:
    """Find contact by phone/email or create new. Returns contact_id."""
    conn = get_db()
    contact_id = None

    if phone:
        phone_clean = "".join(c for c in phone if c.isdigit())
        row = conn.execute(
            "SELECT id FROM contacts WHERE phone LIKE ?", (f"%{phone_clean[-10:]}%",)
        ).fetchone()
        if row:
            contact_id = row["id"]

    if not contact_id and email:
        row = conn.execute("SELECT id FROM contacts WHERE email = ?", (email,)).fetchone()
        if row:
            contact_id = row["id"]

    if not contact_id:
        cursor = conn.execute(
            "INSERT INTO contacts (name, phone, email, source) VALUES (?, ?, ?, 'auto')",
            (name or "Unknown Guest", phone, email),
        )
        contact_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return contact_id


# ── FastAPI app ─────────────────────────────────────────────────────────────

app = FastAPI(title="BBG Operations", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Contacts ────────────────────────────────────────────────────────────────

@app.get("/contacts")
def list_contacts(q: str = Query(None), limit: int = 50):
    conn = get_db()
    if q:
        rows = conn.execute(
            "SELECT * FROM contacts WHERE name LIKE ? OR phone LIKE ? OR email LIKE ? ORDER BY updated_at DESC LIMIT ?",
            (f"%{q}%", f"%{q}%", f"%{q}%", limit),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM contacts ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return {"contacts": [dict(r) for r in rows], "count": len(rows)}


@app.post("/contacts")
def create_contact(contact: ContactCreate):
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO contacts (name, phone, email, notes, tags, source) VALUES (?, ?, ?, ?, ?, ?)",
        (contact.name, contact.phone, contact.email, contact.notes, contact.tags, contact.source),
    )
    contact_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"created": True, "id": contact_id}


@app.put("/contacts/{contact_id}")
def update_contact(contact_id: int, contact: ContactCreate):
    conn = get_db()
    conn.execute(
        "UPDATE contacts SET name=?, phone=?, email=?, notes=?, tags=?, updated_at=datetime('now') WHERE id=?",
        (contact.name, contact.phone, contact.email, contact.notes, contact.tags, contact_id),
    )
    conn.commit()
    conn.close()
    return {"updated": True, "id": contact_id}


@app.get("/contacts/{contact_id}")
def get_contact(contact_id: int):
    conn = get_db()
    contact = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if not contact:
        conn.close()
        raise HTTPException(404, "Contact not found")
    conversations = conn.execute(
        "SELECT * FROM conversations WHERE contact_id = ? ORDER BY created_at DESC LIMIT 100",
        (contact_id,),
    ).fetchall()
    conn.close()
    return {"contact": dict(contact), "conversations": [dict(c) for c in conversations]}


# ── Conversations ───────────────────────────────────────────────────────────

@app.post("/conversations")
def log_conversation(conv: ConversationLog):
    contact_id = conv.contact_id
    if not contact_id:
        contact_id = find_or_create_contact(
            phone=conv.contact_phone, name=conv.contact_name
        )
    conn = get_db()
    cursor = conn.execute(
        """INSERT INTO conversations (contact_id, channel, direction, body, duration_sec, recording_url, transcript)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (contact_id, conv.channel, conv.direction, conv.body,
         conv.duration_sec, conv.recording_url, conv.transcript),
    )
    conn.execute("UPDATE contacts SET updated_at = datetime('now') WHERE id = ?", (contact_id,))
    conn.commit()
    conv_id = cursor.lastrowid
    conn.close()
    return {"logged": True, "id": conv_id, "contact_id": contact_id}


@app.get("/conversations")
def list_conversations(contact_id: int = None, channel: str = None, limit: int = 50):
    conn = get_db()
    query = "SELECT c.*, co.name as contact_name FROM conversations c LEFT JOIN contacts co ON c.contact_id = co.id WHERE 1=1"
    params = []
    if contact_id:
        query += " AND c.contact_id = ?"
        params.append(contact_id)
    if channel:
        query += " AND c.channel = ?"
        params.append(channel)
    query += " ORDER BY c.created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return {"conversations": [dict(r) for r in rows], "count": len(rows)}


# ── SMS ─────────────────────────────────────────────────────────────────────

@app.post("/sms/send")
def api_send_sms(sms: SMSMessage, background_tasks: BackgroundTasks):
    """Send SMS via carrier gateway."""
    result = send_sms(sms.phone, sms.message, sms.carrier)

    # Find contact and log conversation
    contact_id = find_or_create_contact(phone=sms.phone)
    conn = get_db()
    conn.execute(
        "INSERT INTO conversations (contact_id, channel, direction, body) VALUES (?, 'sms', 'outbound', ?)",
        (contact_id, sms.message),
    )
    conn.execute("UPDATE contacts SET updated_at = datetime('now') WHERE id = ?", (contact_id,))
    conn.commit()
    conn.close()

    if result["success"]:
        return {"sent": True, "to": sms.phone, "carrier": sms.carrier or "unknown"}
    return {"sent": False, "error": result.get("error")}


@app.get("/sms/carriers")
def list_carriers():
    return {"carriers": list(CARRIER_GATEWAYS.keys())}


# ── Email Campaigns ─────────────────────────────────────────────────────────

@app.post("/campaigns/email")
def create_email_campaign(campaign: EmailCampaign, background_tasks: BackgroundTasks):
    """Create and queue an email campaign."""
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO campaigns (name, channel, subject, body, filter_tags) VALUES (?, 'email', ?, ?, ?)",
        (campaign.name, campaign.subject, campaign.body, campaign.filter_tags),
    )
    campaign_id = cursor.lastrowid

    # Find target contacts
    if campaign.contact_ids:
        contacts = conn.execute(
            f"SELECT id, email FROM contacts WHERE id IN ({','.join('?'*len(campaign.contact_ids))}) AND email IS NOT NULL",
            campaign.contact_ids,
        ).fetchall()
    elif campaign.filter_tags:
        tags = [t.strip() for t in campaign.filter_tags.split(",")]
        conditions = " OR ".join(["tags LIKE ?"] * len(tags))
        contacts = conn.execute(
            f"SELECT id, email FROM contacts WHERE ({conditions}) AND email IS NOT NULL",
            [f"%{t}%" for t in tags],
        ).fetchall()
    else:
        contacts = conn.execute("SELECT id, email FROM contacts WHERE email IS NOT NULL").fetchall()

    # Queue recipients
    for c in contacts:
        conn.execute(
            "INSERT INTO campaign_recipients (campaign_id, contact_id) VALUES (?, ?)",
            (campaign_id, c["id"]),
        )

    conn.commit()
    conn.close()

    background_tasks.add_task(_send_email_campaign, campaign_id)
    return {"created": True, "campaign_id": campaign_id, "recipient_count": len(contacts)}


def _send_email_campaign(campaign_id: int):
    """Background task: send campaign emails one by one."""
    conn = get_db()
    campaign = conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
    if not campaign:
        conn.close()
        return

    recipients = conn.execute(
        """SELECT cr.id, c.email, c.name FROM campaign_recipients cr
           JOIN contacts c ON cr.contact_id = c.id
           WHERE cr.campaign_id = ? AND cr.status = 'pending'""",
        (campaign_id,),
    ).fetchall()

    sent = 0
    for r in recipients:
        try:
            body = campaign["body"].replace("{{name}}", r["name"] or "Guest")
            pipe = subprocess.Popen(
                ["himalaya", "template", "send"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            template = f"From: {BBG_NAME} <{BBG_EMAIL}>\nTo: {r['name']} <{r['email']}>\nSubject: {campaign['subject']}\n\n{body}"
            stdout, stderr = pipe.communicate(input=template, timeout=30)
            status = "sent" if pipe.returncode == 0 else "failed"
            conn.execute(
                "UPDATE campaign_recipients SET status=?, sent_at=datetime('now') WHERE id=?",
                (status, r["id"]),
            )
            conn.execute(
                "INSERT INTO conversations (contact_id, channel, direction, body) VALUES ((SELECT contact_id FROM campaign_recipients WHERE id=?), 'email', 'outbound', ?)",
                (r["id"], body[:500]),
            )
            if status == "sent":
                sent += 1
            time.sleep(0.5)  # rate limit
        except Exception as e:
            logger.error(f"Campaign email failed for {r['email']}: {e}")
            conn.execute(
                "UPDATE campaign_recipients SET status='failed' WHERE id=?", (r["id"],),
            )

    conn.execute("UPDATE campaigns SET sent_count=?, sent_at=datetime('now') WHERE id=?", (sent, campaign_id))
    conn.commit()
    conn.close()
    logger.info(f"Campaign {campaign_id} sent: {sent}/{len(recipients)}")


@app.get("/campaigns")
def list_campaigns():
    conn = get_db()
    campaigns = conn.execute("SELECT * FROM campaigns ORDER BY created_at DESC LIMIT 20").fetchall()
    conn.close()
    return {"campaigns": [dict(c) for c in campaigns]}


@app.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: int):
    conn = get_db()
    campaign = conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
    if not campaign:
        conn.close()
        raise HTTPException(404)
    recipients = conn.execute(
        """SELECT cr.*, c.name, c.email FROM campaign_recipients cr
           JOIN contacts c ON cr.contact_id = c.id WHERE cr.campaign_id = ?""",
        (campaign_id,),
    ).fetchall()
    conn.close()
    return {"campaign": dict(campaign), "recipients": [dict(r) for r in recipients]}


# ── Call Recording ──────────────────────────────────────────────────────────

@app.post("/calls/record")
def log_call(conv: ConversationLog):
    """Log a call conversation (manual or from Retell webhook)."""
    conv.channel = "call"
    return log_conversation(conv)


@app.get("/calls")
def list_calls(limit: int = 50):
    return list_conversations(channel="call", limit=limit)


# ── Retell webhook (when Masha is reactivated) ─────────────────────────────

@app.post("/webhook/retell")
async def retell_webhook(request: Request):
    """Receive call events from Retell AI — auto-log conversations."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    call = body.get("call", {})
    event = body.get("event", "")
    call_id = call.get("call_id", "unknown")
    from_number = call.get("from_number", "")
    transcript = call.get("transcript", "")
    recording_url = call.get("recording_url", "")
    duration = call.get("duration_ms", 0)

    contact_id = find_or_create_contact(phone=from_number)
    conn = get_db()
    conn.execute(
        """INSERT INTO conversations (contact_id, channel, direction, body, duration_sec, recording_url, transcript, metadata)
           VALUES (?, 'call', 'inbound', ?, ?, ?, ?, ?)""",
        (contact_id, transcript[:500] if transcript else f"Call {call_id}",
         duration // 1000 if duration else None, recording_url, transcript,
         json.dumps({"call_id": call_id, "event": event})),
    )
    conn.execute("UPDATE contacts SET updated_at = datetime('now') WHERE id = ?", (contact_id,))
    conn.commit()
    conn.close()

    return {"received": True, "call_id": call_id, "contact_id": contact_id}


# ── Reservation Sync ────────────────────────────────────────────────────────

@app.post("/sync/reservations")
def sync_reservations_to_contacts():
    """Pull reservations from CC_bbg_reservations.json into contacts DB."""
    if not RESERVATIONS_PATH.exists():
        return {"synced": 0, "message": "No reservations file found"}

    reservations = json.loads(RESERVATIONS_PATH.read_text())
    synced = 0
    for r in reservations:
        name = r.get("party_name", "Unknown")
        phone = r.get("phone", "")
        date = r.get("reservation_date", "")
        time = r.get("reservation_time", "")
        size = r.get("party_size", "")

        contact_id = find_or_create_contact(phone=phone, name=name)
        conn = get_db()
        # Add reservation note if not already present
        existing = conn.execute(
            "SELECT id FROM conversations WHERE contact_id = ? AND body LIKE ?",
            (contact_id, f"%Reservation: {date}%"),
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO conversations (contact_id, channel, direction, body) VALUES (?, 'walk_in', 'inbound', ?)",
                (contact_id, f"Reservation: {date} @ {time}, party of {size}"),
            )
            synced += 1
        conn.commit()
        conn.close()

    return {"synced": synced, "total_reservations": len(reservations)}


# ── Dashboard ───────────────────────────────────────────────────────────────

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    conn = get_db()
    contact_count = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
    conv_count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    today_conv = conn.execute(
        "SELECT COUNT(*) FROM conversations WHERE date(created_at) = date('now')"
    ).fetchone()[0]
    recent_conv = conn.execute(
        """SELECT c.*, co.name as contact_name FROM conversations c
           LEFT JOIN contacts co ON c.contact_id = co.id
           ORDER BY c.created_at DESC LIMIT 20"""
    ).fetchall()

    # Campaign stats
    campaign_count = conn.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0]
    total_sent = conn.execute("SELECT COALESCE(SUM(sent_count),0) FROM campaigns").fetchone()[0]

    # Reservation count
    res_count = 0
    if RESERVATIONS_PATH.exists():
        res_count = len(json.loads(RESERVATIONS_PATH.read_text()))

    conn.close()

    return f"""<!DOCTYPE html>
<html><head><title>BBG Operations</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, sans-serif; background: #0d1117; color: #c9d1d9; padding:20px; }}
h1 {{ color: #58a6ff; margin-bottom:20px; }}
.stats {{ display:flex; gap:15px; flex-wrap:wrap; margin-bottom:25px; }}
.stat {{ background:#161b22; border:1px solid #30363d; border-radius:8px; padding:16px; min-width:140px; }}
.stat .value {{ font-size:32px; font-weight:bold; color:#58a6ff; }}
.stat .label {{ font-size:13px; color:#8b949e; margin-top:4px; }}
table {{ width:100%; border-collapse:collapse; background:#161b22; border:1px solid #30363d; border-radius:8px; overflow:hidden; }}
th {{ background:#21262d; padding:10px; text-align:left; font-size:13px; color:#8b949e; }}
td {{ padding:10px; border-top:1px solid #30363d; font-size:14px; }}
.channel {{ display:inline-block; padding:2px 8px; border-radius:10px; font-size:12px; }}
.channel.call {{ background:#1a3a1a; color:#3fb950; }}
.channel.sms {{ background:#1a2a3a; color:#58a6ff; }}
.channel.email {{ background:#3a1a2a; color:#f778ba; }}
.channel.walk_in {{ background:#3a2a1a; color:#d2991d; }}
.channel.instagram {{ background:#2a1a3a; color:#a371f7; }}
</style></head><body>
<h1>🍺 BBG Operations</h1>
<div class="stats">
  <div class="stat"><div class="value">{contact_count}</div><div class="label">Contacts</div></div>
  <div class="stat"><div class="value">{conv_count}</div><div class="label">Conversations</div></div>
  <div class="stat"><div class="value">{today_conv}</div><div class="label">Today</div></div>
  <div class="stat"><div class="value">{res_count}</div><div class="label">Reservations</div></div>
  <div class="stat"><div class="value">{campaign_count}</div><div class="label">Campaigns</div></div>
  <div class="stat"><div class="value">{total_sent}</div><div class="label">Total Sent</div></div>
</div>
<h2 style="color:#8b949e;font-size:16px;margin-bottom:10px;">Recent Activity</h2>
<table>
<tr><th>Time</th><th>Contact</th><th>Channel</th><th>Details</th></tr>
{"".join(f'<tr><td>{r["created_at"][:19]}</td><td>{r["contact_name"] or "?"}</td><td><span class="channel {r["channel"]}">{r["channel"]}</span></td><td>{(r["body"] or "")[:100]}</td></tr>' for r in recent_conv)}
</table>
<p style="margin-top:20px;font-size:12px;color:#484f58;">API: /contacts /conversations /sms/send /campaigns/email /calls/record /sync/reservations</p>
</body></html>"""


# ── Health ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    conn = get_db()
    contact_count = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
    conv_count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    conn.close()
    return {
        "status": "ok",
        "system": "bbg_operations",
        "contacts": contact_count,
        "conversations": conv_count,
        "db": str(DB_PATH),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("CC_bbg_operations:app", host="127.0.0.1", port=8100, reload=True)
