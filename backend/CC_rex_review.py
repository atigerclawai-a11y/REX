"""CC_rex_review.py — REX Review App
Unified CRM + Reservations + Billing + SMS + Firecrawl proxy.
Mounts to REX on :8000 at /rex-review.
"""
import json
import logging
import os
import smtplib
import sqlite3
import urllib.request
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("rex_review")
router = APIRouter(prefix="/rex-review", tags=["REX Review"])

REX_DIR = Path.home() / "Desktop/REX"
DB_PATH = REX_DIR / "CC_rex_review.db"


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ── Pydantic models ──
class ContactCreate(BaseModel):
    first_name: str = ""
    last_name: str = ""
    phone: str = ""
    email: str = ""
    tags: str = "[]"
    source: str = "manual"
    business: str = "BBG"
    notes: str = ""


class BillCreate(BaseModel):
    contact_id: int
    amount: float
    items: str = "[]"
    due_date: str = ""
    notes: str = ""


class SMSSend(BaseModel):
    contact_id: int
    message: str
    dry_run: bool = True  # Safe by default


class ReservationCreate(BaseModel):
    contact_id: int = 0
    reservation_date: str
    party_size: int = 2
    guest_name: str = ""
    source: str = "owner.com"


class DealCreate(BaseModel):
    contact_id: int
    pipeline_id: int = 0
    title: str = ""
    value: float = 0
    notes: str = ""


# ── CONTACTS ──
@router.get("/contacts")
def list_contacts(status: str = "", search: str = "", limit: int = 100, offset: int = 0,
                  business: str = ""):
    db = get_db()
    query = "SELECT * FROM contacts WHERE deleted_at IS NULL"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if business:
        query += " AND business = ?"
        params.append(business)
    if search:
        query += " AND (name LIKE ? OR phone LIKE ? OR email LIKE ?)"
        s = f"%{search}%"
        params.extend([s, s, s])
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = db.execute(query, params).fetchall()
    count = db.execute("SELECT COUNT(*) FROM contacts WHERE deleted_at IS NULL").fetchone()[0]
    db.close()
    return {"contacts": [dict(r) for r in rows], "total": count}


@router.post("/contacts")
def create_contact(body: ContactCreate):
    db = get_db()
    name = f"{body.first_name} {body.last_name}".strip()
    cur = db.execute("""
        INSERT INTO contacts (first_name, last_name, name, phone, email, tags, source,
                             business, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (body.first_name, body.last_name, name, body.phone, body.email,
          body.tags, body.source, body.business, body.notes))
    db.commit()
    contact_id = cur.lastrowid
    db.close()
    return {"ok": True, "id": contact_id}


@router.get("/contacts/{contact_id}")
def get_contact(contact_id: int):
    db = get_db()
    row = db.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if not row:
        db.close()
        raise HTTPException(404, "Contact not found")
    conversations = [dict(r) for r in db.execute(
        "SELECT * FROM conversations WHERE contact_id = ? ORDER BY created_at DESC LIMIT 20",
        (contact_id,)).fetchall()]
    bills = [dict(r) for r in db.execute(
        "SELECT * FROM bills WHERE contact_id = ? ORDER BY created_at DESC LIMIT 20",
        (contact_id,)).fetchall()]
    reservations = [dict(r) for r in db.execute(
        "SELECT * FROM reservations WHERE contact_id = ? ORDER BY reservation_date DESC LIMIT 20",
        (contact_id,)).fetchall()]
    deals = [dict(r) for r in db.execute(
        "SELECT * FROM deals WHERE contact_id = ? ORDER BY created_at DESC LIMIT 20",
        (contact_id,)).fetchall()]
    activities = [dict(r) for r in db.execute(
        "SELECT * FROM activities WHERE contact_id = ? ORDER BY created_at DESC LIMIT 50",
        (contact_id,)).fetchall()]
    db.close()
    return {"contact": dict(row), "conversations": conversations, "bills": bills,
            "reservations": reservations, "deals": deals, "activities": activities}


@router.put("/contacts/{contact_id}")
def update_contact(contact_id: int, body: ContactCreate):
    db = get_db()
    name = f"{body.first_name} {body.last_name}".strip()
    db.execute("""
        UPDATE contacts SET first_name=?, last_name=?, name=?, phone=?, email=?,
                            tags=?, source=?, business=?, notes=?, updated_at=datetime('now')
        WHERE id=?
    """, (body.first_name, body.last_name, name, body.phone, body.email,
          body.tags, body.source, body.business, body.notes, contact_id))
    db.commit()
    db.close()
    return {"ok": True}


# ── PIPELINES & DEALS ──
@router.get("/pipelines")
def list_pipelines():
    db = get_db()
    rows = db.execute("SELECT * FROM pipelines ORDER BY created_at DESC").fetchall()
    db.close()
    return {"pipelines": [dict(r) for r in rows]}


@router.get("/deals")
def list_deals(pipeline_id: int = 0, status: str = "", contact_id: int = 0, limit: int = 50):
    db = get_db()
    query = """SELECT d.*, c.name as contact_name, p.name as pipeline_name
               FROM deals d
               LEFT JOIN contacts c ON d.contact_id = c.id
               LEFT JOIN pipelines p ON d.pipeline_id = p.id
               WHERE 1=1"""
    params = []
    if pipeline_id:
        query += " AND d.pipeline_id = ?"
        params.append(pipeline_id)
    if status:
        query += " AND d.status = ?"
        params.append(status)
    if contact_id:
        query += " AND d.contact_id = ?"
        params.append(contact_id)
    query += " ORDER BY d.created_at DESC LIMIT ?"
    params.append(limit)
    rows = db.execute(query, params).fetchall()
    db.close()
    return {"deals": [dict(r) for r in rows]}


@router.post("/deals")
def create_deal(body: DealCreate):
    db = get_db()
    cur = db.execute("""
        INSERT INTO deals (contact_id, pipeline_id, title, value, notes)
        VALUES (?, ?, ?, ?, ?)
    """, (body.contact_id, body.pipeline_id, body.title, body.value, body.notes))
    db.commit()
    db.execute("""INSERT INTO activities (contact_id, deal_id, type, content)
                  VALUES (?, ?, 'deal_created', ?)""",
               (body.contact_id, cur.lastrowid, f"Deal: {body.title} (${body.value})"))
    db.commit()
    db.close()
    return {"ok": True, "id": cur.lastrowid}


# ── RESERVATIONS ──
@router.get("/reservations")
def list_reservations(date_from: str = "", date_to: str = "", limit: int = 50,
                      contact_id: int = 0):
    db = get_db()
    query = """SELECT r.*, c.name as contact_name
               FROM reservations r
               LEFT JOIN contacts c ON r.contact_id = c.id
               WHERE 1=1"""
    params = []
    if date_from:
        query += " AND r.reservation_date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND r.reservation_date <= ?"
        params.append(date_to)
    if contact_id:
        query += " AND r.contact_id = ?"
        params.append(contact_id)
    query += " ORDER BY r.reservation_date DESC LIMIT ?"
    params.append(limit)
    rows = db.execute(query, params).fetchall()
    db.close()
    return {"reservations": [dict(r) for r in rows]}


@router.post("/reservations")
def create_reservation(body: ReservationCreate):
    db = get_db()
    cur = db.execute("""
        INSERT INTO reservations (contact_id, reservation_date, party_size, guest_name, source)
        VALUES (?, ?, ?, ?, ?)
    """, (body.contact_id, body.reservation_date, body.party_size,
          body.guest_name, body.source))
    db.commit()
    rid = cur.lastrowid
    if body.contact_id:
        db.execute("""INSERT INTO activities (contact_id, type, content)
                      VALUES (?, 'reservation', ?)""",
                   (body.contact_id, f"Reservation: {body.reservation_date} party of {body.party_size}"))
        db.commit()
    db.close()
    return {"ok": True, "id": rid}


# ── BILLS / STRIPE ──
@router.get("/bills")
def list_bills(status: str = "", contact_id: int = 0, limit: int = 50):
    db = get_db()
    query = """SELECT b.*, c.name as contact_name
               FROM bills b LEFT JOIN contacts c ON b.contact_id = c.id WHERE 1=1"""
    params = []
    if status:
        query += " AND b.status = ?"
        params.append(status)
    if contact_id:
        query += " AND b.contact_id = ?"
        params.append(contact_id)
    query += " ORDER BY b.created_at DESC LIMIT ?"
    params.append(limit)
    rows = db.execute(query, params).fetchall()
    db.close()
    return {"bills": [dict(r) for r in rows]}


@router.post("/bills")
def create_bill(body: BillCreate):
    db = get_db()
    cur = db.execute("""
        INSERT INTO bills (contact_id, amount, items, due_date, notes)
        VALUES (?, ?, ?, ?, ?)
    """, (body.contact_id, body.amount, body.items, body.due_date, body.notes))
    bill_id = cur.lastrowid

    # Try Stripe checkout if key present
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    checkout_url = ""
    if stripe_key:
        try:
            payload = json.dumps({
                "payment_method_types": ["card"],
                "line_items": [{"price_data": {"currency": "usd",
                                                  "product_data": {"name": "BBG Bill"},
                                                  "unit_amount": int(body.amount * 100)},
                                  "quantity": 1}],
                "mode": "payment",
                "success_url": "https://goldhealthsys.com/rex-review/payment-success",
                "cancel_url": "https://goldhealthsys.com/rex-review/payment-cancel",
            }).encode()
            req = urllib.request.Request(
                "https://api.stripe.com/v1/checkout/sessions", data=payload,
                headers={"Authorization": f"Bearer {stripe_key}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                resp = json.loads(r.read())
                checkout_url = resp.get("url", "")
                db.execute("UPDATE bills SET stripe_checkout_url=?, stripe_payment_id=? WHERE id=?",
                           (checkout_url, resp.get("id", ""), bill_id))
        except Exception as e:
            logger.warning(f"Stripe error: {e}")

    db.execute("""INSERT INTO activities (contact_id, bill_id, type, content)
                  VALUES (?, ?, 'bill_created', ?)""",
               (body.contact_id, bill_id, f"Bill: ${body.amount}"))
    db.commit()
    db.close()
    return {"ok": True, "id": bill_id, "checkout_url": checkout_url}


# ── CAMPAIGNS ──
@router.get("/campaigns")
def list_campaigns(limit: int = 50):
    db = get_db()
    rows = db.execute("SELECT * FROM campaigns ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    db.close()
    return {"campaigns": [dict(r) for r in rows]}


@router.post("/campaigns")
def create_campaign(name: str, channel: str, body: str, subject: str = "", filter_tags: str = ""):
    db = get_db()
    cur = db.execute("""
        INSERT INTO campaigns (name, channel, subject, body, filter_tags)
        VALUES (?, ?, ?, ?, ?)
    """, (name, channel, subject, body, filter_tags))
    db.commit()
    db.close()
    return {"ok": True, "id": cur.lastrowid}


# ── SMS (with dry-run guard) ──
CARRIER_GATEWAYS = {
    "att": "txt.att.net", "verizon": "vtext.com", "tmobile": "tmomail.net",
    "sprint": "messaging.sprintpcs.com", "googlefi": "msg.fi.google.com",
    "cricket": "mms.cricketwireless.net", "metropcs": "mymetropcs.com",
    "boost": "smsmyboostmobile.com",
}


@router.post("/sms/send")
def send_sms(body: SMSSend):
    db = get_db()
    contact = db.execute("SELECT * FROM contacts WHERE id = ?", (body.contact_id,)).fetchone()
    if not contact:
        db.close()
        raise HTTPException(404, "Contact not found")
    phone = contact["phone"] or ""
    if not phone:
        db.close()
        raise HTTPException(400, "Contact has no phone number")

    clean = ''.join(c for c in str(phone) if c.isdigit())
    if clean.startswith("1") and len(clean) == 11:
        clean = clean[1:]

    # Always log the conversation (dry-run OR sent)
    db.execute("""
        INSERT INTO conversations (contact_id, channel, direction, body, metadata)
        VALUES (?, 'sms', 'outbound', ?, ?)
    """, (body.contact_id, body.message,
          json.dumps({"dry_run": body.dry_run, "phone": phone})))
    db.execute("""INSERT INTO activities (contact_id, type, content)
                  VALUES (?, 'sms', ?)""", (body.contact_id, body.message[:200]))
    db.commit()

    if body.dry_run:
        db.close()
        return {"ok": True, "dry_run": True, "phone": phone, "message": "Logged only, no SMS sent"}

    sent = False
    carrier_used = None
    for carrier, domain in CARRIER_GATEWAYS.items():
        try:
            to_addr = f"{clean}@{domain}"
            msg = MIMEText(body.message)
            msg["From"] = os.environ.get("BBG_EMAIL", "noreply@hermestigerclaw.com")
            msg["To"] = to_addr
            msg["Subject"] = "BBG"
            with smtplib.SMTP("localhost", 25, timeout=5) as smtp:
                smtp.sendmail(msg["From"], [to_addr], msg.as_string())
            sent = True
            carrier_used = carrier
            break
        except Exception:
            continue

    db.close()
    if not sent:
        raise HTTPException(500, "SMS failed for all carriers (logged for review)")
    return {"ok": True, "carrier": carrier_used}


# ── ACTIVITIES ──
@router.get("/activities")
def list_activities(contact_id: int = 0, limit: int = 100):
    db = get_db()
    if contact_id:
        rows = db.execute(
            "SELECT * FROM activities WHERE contact_id = ? ORDER BY created_at DESC LIMIT ?",
            (contact_id, limit)).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM activities ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    db.close()
    return {"activities": [dict(r) for r in rows]}


# ── STATS / DASHBOARD ──
@router.get("/stats")
def get_stats():
    db = get_db()
    stats = {
        "contacts": db.execute("SELECT COUNT(*) FROM contacts WHERE deleted_at IS NULL").fetchone()[0],
        "contacts_bbg": db.execute("SELECT COUNT(*) FROM contacts WHERE business='BBG' AND deleted_at IS NULL").fetchone()[0],
        "deals_open": db.execute("SELECT COUNT(*) FROM deals WHERE status='open'").fetchone()[0],
        "deals_won": db.execute("SELECT COUNT(*) FROM deals WHERE status='won'").fetchone()[0],
        "reservations": db.execute("SELECT COUNT(*) FROM reservations").fetchone()[0],
        "bills_pending": db.execute("SELECT COUNT(*) FROM bills WHERE status='pending'").fetchone()[0],
        "bills_paid": db.execute("SELECT COUNT(*) FROM bills WHERE status='paid'").fetchone()[0],
        "conversations": db.execute("SELECT COUNT(*) FROM conversations").fetchone()[0],
    }
    db.close()
    return stats


# ── Health ──
@router.get("/health")
def health():
    db = get_db()
    contacts = db.execute("SELECT COUNT(*) FROM contacts WHERE deleted_at IS NULL").fetchone()[0]
    reservations = db.execute("SELECT COUNT(*) FROM reservations").fetchone()[0]
    deals = db.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
    db.close()
    return {"status": "ok", "contacts": contacts, "reservations": reservations, "deals": deals}

# ── Frontend ──
@router.get("/", response_class=HTMLResponse)
def serve_review_app():
    html_path = REX_DIR / "CC_rex_review.html"
    if html_path.exists():
        return html_path.read_text()
    return "<h1>REX Review App — Frontend not built yet</h1><p>Run CP3 to create CC_rex_review.html</p>"