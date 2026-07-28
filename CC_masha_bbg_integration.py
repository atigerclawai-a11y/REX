"""
CC_masha_bbg_integration.py
============================
Masha — BBG Voice Agent Integration (Retell AI)
Gold Health Systems · Boardwalk Beer Garden

⚠️  STATUS: DEAD — Retell API key expired.
    Activation requires: renew Retell subscription → new API key →
    update RETELL_API_KEY env var → confirm MASHA_AGENT_ID in Retell dashboard.
    See CC_VOICE_INTEGRATION_GUIDE.md for full reactivation checklist.

This is a STANDALONE FastAPI app (not mounted to the REX GOJ backend).
BBG is a separate business from GOJ — no shared DB, no PHI overlap.

Start independently:
    uvicorn CC_masha_bbg_integration:app --host 0.0.0.0 --port 8100 --reload

Or add a launchd plist:
    com.bbg.masha.plist → same pattern as com.rex.backend.plist

Reservations stored at: ~/Desktop/REX/CC_bbg_reservations.json

Capabilities:
    1. Inbound call handler        (hours, events, reservations, callback requests)
    2. Event promotion calls       (outbound to VIP list)
    3. Instagram DM bridge         (webhook from n8n / Meta webhooks)
    4. Reservation confirmation    (outbound confirmation after booking)
"""

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("masha")

# ── Configuration constants — fill after Retell reactivation ──────────────────
RETELL_API_KEY: str = os.getenv("RETELL_API_KEY", "")       # ← BLOCKED: key expired
MASHA_AGENT_ID: str = os.getenv("MASHA_AGENT_ID", "")      # ← from Retell dashboard
MASHA_PHONE_NUMBER: str = os.getenv("MASHA_FROM_PHONE", "+1XXXXXXXXXX")  # ← from Retell dashboard
RETELL_WEBHOOK_SECRET: str = os.getenv("RETELL_WEBHOOK_SECRET", "")

# Reservations file — plain JSON, no PHI concerns for BBG
RESERVATIONS_PATH = Path.home() / "Desktop" / "REX" / "CC_bbg_reservations.json"

# VIP list file — populated manually or by a future admin endpoint
VIP_LIST_PATH = Path.home() / "Desktop" / "REX" / "CC_bbg_vip_list.json"

# ── Masha's persona and scripts ───────────────────────────────────────────────
BBG_PERSONA = """
You are Masha, the friendly voice of Boardwalk Beer Garden in Brooklyn.
You're warm, knowledgeable about the beer selection, and excited about events.
Keep responses under 30 seconds. If you can't answer, offer to connect them to the team.
Instagram: @boardwalkbeergarden
"""

HOURS_SCRIPT = """
Thanks for calling Boardwalk Beer Garden! We're open
Monday through Thursday noon to eleven PM,
Friday and Saturday noon to midnight,
and Sunday noon to ten PM.
We're located in Brooklyn — find us on Instagram at boardwalk beer garden.
Is there anything else I can help you with?
"""

RESERVATION_CONFIRM_SCRIPT = """
Hi, this is Masha calling from Boardwalk Beer Garden to confirm your reservation
for {party_name}, party of {party_size}, on {reservation_date} at {reservation_time}.
We're looking forward to seeing you! If you need to make any changes,
please call us or reply to this message. See you soon!
"""

EVENT_PROMO_SCRIPT = """
Hi {contact_name}, this is Masha from Boardwalk Beer Garden!
We have an exciting event coming up — {event_name} on {event_date}.
{event_description}
We'd love to see you there. Visit our Instagram at boardwalk beer garden for details.
Hope to see you soon!
"""

CALLBACK_ACK_SCRIPT = """
Thanks for calling Boardwalk Beer Garden! I've noted your callback request.
Someone from our team will reach out to you shortly.
In the meantime, follow us on Instagram at boardwalk beer garden for the latest news.
Have a great day!
"""


# ── Pydantic models ────────────────────────────────────────────────────────────

class Reservation(BaseModel):
    party_name: str
    party_size: int
    reservation_date: str       # ISO date "YYYY-MM-DD"
    reservation_time: str       # "HH:MM" 24h
    phone: Optional[str] = None
    notes: Optional[str] = None
    source: str = "api"         # "call" | "dm" | "api" | "online"


class EventPromoRequest(BaseModel):
    event_name: str
    event_date: str             # ISO date or human-readable string
    event_description: str
    vip_phones: Optional[list[str]] = None  # override VIP list for this call


class InstagramDMWebhook(BaseModel):
    sender_id: str
    message_text: str
    timestamp: Optional[str] = None


# ── Reservations storage helpers ───────────────────────────────────────────────

def _load_reservations() -> list[dict[str, Any]]:
    """Load all reservations from CC_bbg_reservations.json."""
    if not RESERVATIONS_PATH.exists():
        return []
    try:
        return json.loads(RESERVATIONS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error(f"Failed to load reservations: {exc}")
        return []


def _save_reservations(reservations: list[dict[str, Any]]) -> None:
    """Write reservations list back to disk atomically-ish."""
    RESERVATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESERVATIONS_PATH.write_text(
        json.dumps(reservations, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _add_reservation(res: Reservation) -> dict[str, Any]:
    """Append a new reservation and return the saved record (with id)."""
    reservations = _load_reservations()
    record = res.model_dump()
    record["id"] = len(reservations) + 1
    record["created_at"] = datetime.utcnow().isoformat() + "Z"
    record["confirmed"] = False
    reservations.append(record)
    _save_reservations(reservations)
    logger.info(
        f"Reservation #{record['id']} saved: {res.party_name} × {res.party_size} "
        f"on {res.reservation_date} @ {res.reservation_time}"
    )
    return record


def _load_vip_list() -> list[dict[str, Any]]:
    """Load VIP list from CC_bbg_vip_list.json. Returns [] if not found."""
    if not VIP_LIST_PATH.exists():
        return []
    try:
        return json.loads(VIP_LIST_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error(f"Failed to load VIP list: {exc}")
        return []


# ── Retell SDK wrapper ─────────────────────────────────────────────────────────

def _retell_create_call(
    to_number: str,
    metadata: dict[str, Any],
    agent_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Create an outbound phone call via Retell REST API.
    Raises RuntimeError when RETELL_API_KEY is missing or expired.
    """
    if not RETELL_API_KEY:
        raise RuntimeError(
            "RETELL_API_KEY is not set — Masha is DEAD (key expired). "
            "Renew Retell subscription at retell.ai and update the key."
        )
    resolved_agent_id = agent_id or MASHA_AGENT_ID
    if not resolved_agent_id:
        raise RuntimeError(
            "MASHA_AGENT_ID is not set — check Retell dashboard after reactivation."
        )

    payload = json.dumps(
        {
            "from_number": MASHA_PHONE_NUMBER,
            "to_number": to_number,
            "agent_id": resolved_agent_id,
            "metadata": metadata,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        "https://api.retellai.com/v2/create-phone-call",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {RETELL_API_KEY}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Retell API error {exc.code}: {body}") from exc


# ── Background task helpers ────────────────────────────────────────────────────

def _do_reservation_confirmation_call(record: dict[str, Any]) -> None:
    """Outbound call to confirm a newly created reservation."""
    phone = record.get("phone")
    if not phone:
        logger.info(f"Reservation #{record.get('id')} has no phone — skipping confirmation call")
        return

    metadata = {
        "call_type": "reservation_confirmation",
        "reservation_id": record.get("id"),
        "party_name": record.get("party_name"),
        "party_size": record.get("party_size"),
        "reservation_date": record.get("reservation_date"),
        "reservation_time": record.get("reservation_time"),
        "script_hint": RESERVATION_CONFIRM_SCRIPT.format(
            party_name=record.get("party_name", "your party"),
            party_size=record.get("party_size", ""),
            reservation_date=record.get("reservation_date", ""),
            reservation_time=record.get("reservation_time", ""),
        ).strip(),
    }

    try:
        call = _retell_create_call(to_number=phone, metadata=metadata)
        call_id = call.get("call_id", "unknown")
        logger.info(
            f"📞 Masha confirmation call: reservation #{record.get('id')} call_id={call_id}"
        )
        # Mark confirmed in reservations file
        reservations = _load_reservations()
        for r in reservations:
            if r.get("id") == record.get("id"):
                r["confirmed"] = True
                r["confirmation_call_id"] = call_id
        _save_reservations(reservations)
    except RuntimeError as exc:
        logger.error(f"Masha confirmation call failed for reservation #{record.get('id')}: {exc}")


def _do_event_promo_call(phone: str, contact_name: str, event: EventPromoRequest) -> None:
    """Outbound promo call for a single VIP contact."""
    metadata = {
        "call_type": "event_promo",
        "contact_name": contact_name,
        "event_name": event.event_name,
        "event_date": event.event_date,
        "script_hint": EVENT_PROMO_SCRIPT.format(
            contact_name=contact_name,
            event_name=event.event_name,
            event_date=event.event_date,
            event_description=event.event_description,
        ).strip(),
    }
    try:
        call = _retell_create_call(to_number=phone, metadata=metadata)
        call_id = call.get("call_id", "unknown")
        logger.info(f"📞 Masha promo call: {contact_name} ({phone}) call_id={call_id}")
    except RuntimeError as exc:
        logger.error(f"Masha promo call failed for {contact_name} ({phone}): {exc}")


# ── FastAPI app ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Masha — BBG Voice Agent",
    version="1.0.0",
    description=(
        "Boardwalk Beer Garden voice agent integration. "
        "⚠️ DEAD — Retell API key expired. See CC_VOICE_INTEGRATION_GUIDE.md."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

masha_router = APIRouter(prefix="/masha", tags=["masha"])


# ── Endpoints ──────────────────────────────────────────────────────────────────

@masha_router.get("/status")
async def masha_status() -> dict[str, Any]:
    """Health + current reservation count + Retell connection status."""
    retell_live = bool(RETELL_API_KEY and MASHA_AGENT_ID)
    reservations = _load_reservations()
    today_str = date.today().isoformat()
    today_reservations = [r for r in reservations if r.get("reservation_date") == today_str]

    return {
        "agent": "masha",
        "retell_configured": retell_live,
        "retell_blocked": not bool(RETELL_API_KEY),
        "block_reason": (
            "RETELL_API_KEY missing or expired — renew at retell.ai"
            if not retell_live
            else None
        ),
        "masha_agent_id": MASHA_AGENT_ID or "NOT SET",
        "masha_phone": MASHA_PHONE_NUMBER,
        "total_reservations": len(reservations),
        "today_reservations": len(today_reservations),
        "vip_list_size": len(_load_vip_list()),
    }


@masha_router.get("/reservations")
async def list_reservations(
    date_filter: Optional[str] = None,
) -> dict[str, Any]:
    """
    Return reservations. Optional date_filter in ISO format "YYYY-MM-DD".
    Defaults to today if no filter provided.
    """
    reservations = _load_reservations()
    filter_date = date_filter or date.today().isoformat()
    filtered = [r for r in reservations if r.get("reservation_date") == filter_date]
    return {
        "date": filter_date,
        "count": len(filtered),
        "reservations": filtered,
    }


@masha_router.post("/reservations")
async def create_reservation(
    res: Reservation, background_tasks: BackgroundTasks
) -> dict[str, Any]:
    """
    Create a new reservation (from call, DM, or direct API).
    If a phone number is provided, queues a Masha confirmation call.
    """
    record = _add_reservation(res)

    if res.phone:
        background_tasks.add_task(_do_reservation_confirmation_call, record)

    return {
        "created": True,
        "reservation": record,
        "confirmation_call_queued": bool(res.phone),
    }


@masha_router.post("/call/event-promo")
async def trigger_event_promo(
    req: EventPromoRequest, background_tasks: BackgroundTasks
) -> dict[str, Any]:
    """
    Trigger promo calls to VIP list (or an override list) for an event.
    VIP list loaded from CC_bbg_vip_list.json unless req.vip_phones is set.
    """
    if req.vip_phones:
        targets = [
            {"phone": p, "name": "Valued Guest"} for p in req.vip_phones
        ]
    else:
        vip_list = _load_vip_list()
        if not vip_list:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"VIP list not found at {VIP_LIST_PATH}. "
                    "Create it as a JSON array: "
                    '[{"phone": "+1XXXXXXXXXX", "name": "Jane Doe"}, ...]'
                ),
            )
        targets = vip_list

    count = 0
    for contact in targets:
        phone = contact.get("phone")
        name = contact.get("name", "Valued Guest")
        if phone:
            background_tasks.add_task(_do_event_promo_call, phone, name, req)
            count += 1

    return {
        "queued": count,
        "event": req.event_name,
        "date": req.event_date,
        "note": f"{count} promo call(s) queued for '{req.event_name}'.",
    }


@masha_router.post("/webhook/inbound")
async def masha_inbound_webhook(request: Request) -> dict[str, Any]:
    """
    Retell webhook endpoint for inbound BBG call events.
    Handles: call_started, call_ended (with transcript), call_analyzed.

    Configure in Retell dashboard:
        Webhook URL: https://<your-domain>/masha/webhook/inbound

    RESERVATION FLOW:
        If Retell extracts a reservation intent from the call (via custom data),
        Masha will auto-create the reservation record here.

    CALLBACK FLOW:
        If caller requests a callback, logs the phone number for follow-up.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = body.get("event", "")
    call_data = body.get("call", {})
    call_id = call_data.get("call_id", "unknown")
    from_number = call_data.get("from_number", "unknown")
    custom_data = call_data.get("custom_data", {})

    logger.info(f"Masha inbound webhook: event={event} call_id={call_id}")

    if event == "call_started":
        logger.info(f"📞 BBG inbound call started: {from_number} call_id={call_id}")

    elif event == "call_ended":
        duration = call_data.get("duration_ms", 0)
        logger.info(
            f"📞 BBG inbound call ended: {from_number} duration={duration}ms call_id={call_id}"
        )

        # ── Auto-create reservation if Retell extracted one ───────────────────
        res_data = custom_data.get("reservation")
        if res_data and isinstance(res_data, dict):
            try:
                res = Reservation(
                    party_name=res_data.get("party_name", "Unknown"),
                    party_size=int(res_data.get("party_size", 1)),
                    reservation_date=res_data.get("reservation_date", date.today().isoformat()),
                    reservation_time=res_data.get("reservation_time", "19:00"),
                    phone=from_number,
                    notes=f"Auto-created from inbound call {call_id}",
                    source="call",
                )
                record = _add_reservation(res)
                logger.info(f"Auto-reservation created from call: #{record['id']}")
            except Exception as exc:
                logger.error(f"Failed to auto-create reservation from call: {exc}")

        # ── Log callback request ───────────────────────────────────────────────
        if custom_data.get("callback_requested"):
            _log_callback_request(from_number, call_id)

    elif event == "call_analyzed":
        summary = call_data.get("call_analysis", {}).get("call_summary", "")
        logger.info(f"BBG call analyzed: {summary[:200]}")

    return {"received": True, "event": event, "call_id": call_id}


@masha_router.post("/webhook/instagram-dm")
async def instagram_dm_webhook(
    payload: InstagramDMWebhook, background_tasks: BackgroundTasks
) -> dict[str, Any]:
    """
    Instagram DM bridge — receives DMs routed via n8n / Meta webhook.
    When someone DMs asking about reservations, logs the inquiry.
    If their DM contains a phone number, Masha can call them back.

    n8n setup: Instagram trigger → extract sender_id + message_text →
        POST http://localhost:8100/masha/webhook/instagram-dm

    TODO: When Masha is live, this endpoint can trigger an outbound call
    or SMS reply via Retell / Twilio.
    """
    logger.info(
        f"Instagram DM from {payload.sender_id}: {payload.message_text[:100]}"
    )

    inquiry_type = _classify_dm(payload.message_text)
    response_hint = _get_dm_response_hint(inquiry_type, payload.message_text)

    # Log inquiry to reservations file as a pending item if reservation intent
    if inquiry_type == "reservation":
        dm_record: dict[str, Any] = {
            "id": f"dm_{payload.sender_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "source": "instagram_dm",
            "sender_id": payload.sender_id,
            "message": payload.message_text,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "status": "pending_follow_up",
        }
        reservations = _load_reservations()
        reservations.append(dm_record)
        _save_reservations(reservations)
        logger.info(f"DM reservation inquiry logged: sender={payload.sender_id}")

    return {
        "received": True,
        "inquiry_type": inquiry_type,
        "response_hint": response_hint,
        "note": "Automated response or callback not yet wired — Retell key expired.",
    }


def _classify_dm(text: str) -> str:
    """Simple keyword classification for DM intent."""
    lower = text.lower()
    if any(w in lower for w in ["book", "reserve", "reservation", "table", "seat"]):
        return "reservation"
    if any(w in lower for w in ["hours", "open", "close", "time"]):
        return "hours"
    if any(w in lower for w in ["event", "show", "live", "music", "tonight"]):
        return "event"
    if any(w in lower for w in ["call", "phone", "reach", "contact"]):
        return "callback"
    return "general"


def _get_dm_response_hint(inquiry_type: str, text: str) -> str:
    """Return a suggested response string based on inquiry type."""
    hints = {
        "reservation": (
            "Thanks for reaching out! We'd love to have you. "
            "Please share your preferred date, time, and party size."
        ),
        "hours": (
            "We're open Mon–Thu noon–11pm, Fri–Sat noon–midnight, Sun noon–10pm!"
        ),
        "event": (
            "Check our latest events on @boardwalkbeergarden. "
            "DM us for details or call to confirm!"
        ),
        "callback": (
            "Happy to call you back! Share your number and best time to reach you."
        ),
        "general": (
            "Thanks for reaching out to Boardwalk Beer Garden! "
            "How can we help you today?"
        ),
    }
    return hints.get(inquiry_type, hints["general"])


def _log_callback_request(phone: str, call_id: str) -> None:
    """Append a callback request entry to the reservations file for follow-up."""
    entry: dict[str, Any] = {
        "id": f"cb_{call_id}",
        "source": "callback_request",
        "phone": phone,
        "retell_call_id": call_id,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "status": "pending_callback",
    }
    reservations = _load_reservations()
    reservations.append(entry)
    _save_reservations(reservations)
    logger.info(f"Callback request logged: phone={phone} call_id={call_id}")


@masha_router.post("/webhook/owner-com")
async def owner_com_webhook(request: Request) -> dict[str, Any]:
    """
    Owner.com webhook endpoint for reservation events.
    
    Configure in owner.com dashboard:
        Webhook URL: https://<your-domain>/masha/webhook/owner-com
        Events: reservation.created, reservation.updated, reservation.cancelled
    
    Accepts owner.com's expected payload format and normalizes to BBG
    reservation schema. Falls back to raw-body parsing if the format differs.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = body.get("event") or body.get("type", "unknown")
    res_data = body.get("reservation") or body.get("data") or body

    try:
        record = _add_reservation(Reservation(
            party_name=(
                res_data.get("guest_name")
                or res_data.get("name")
                or res_data.get("customer", {}).get("name", "Unknown Guest")
            ),
            party_size=int(
                res_data.get("party_size")
                or res_data.get("guests")
                or res_data.get("size", 2)
            ),
            reservation_date=(
                res_data.get("date")
                or res_data.get("reservation_date")
                or (res_data.get("start", "")[:10] if res_data.get("start") else date.today().isoformat())
            ),
            reservation_time=(
                res_data.get("time")
                or res_data.get("reservation_time")
                or (res_data.get("start", "")[11:16] if res_data.get("start") else "19:00")
            ),
            phone=(
                res_data.get("phone")
                or res_data.get("customer", {}).get("phone")
            ),
            notes=f"Owner.com {event_type}: {json.dumps(res_data)[:200]}",
            source="owner_com",
        ))

        logger.info(
            f"Owner.com reservation #{record['id']}: {record['party_name']} "
            f"x{record['party_size']} on {record['reservation_date']} "
            f"@ {record['reservation_time']}"
        )
        return {
            "created": True,
            "reservation_id": record["id"],
            "event": event_type,
        }

    except Exception as exc:
        logger.error(f"Owner.com webhook failed: {exc}")
        raise HTTPException(status_code=422, detail=str(exc))


@masha_router.get("/reservations/dashboard")
async def reservations_dashboard() -> dict[str, Any]:
    """
    Simple reservation dashboard — all reservations grouped by date.
    For Masha to reference when callers ask "what's booked tonight?"
    """
    reservations = _load_reservations()
    today = date.today().isoformat()
    upcoming = [r for r in reservations if r.get("reservation_date", "") >= today]

    by_date: dict[str, list] = {}
    for r in upcoming:
        d = r.get("reservation_date", "unknown")
        by_date.setdefault(d, []).append(r)

    return {
        "total_reservations": len(reservations),
        "upcoming": len(upcoming),
        "today_count": len(by_date.get(today, [])),
        "by_date": dict(sorted(by_date.items())),
    }


# ── Mount router and start ─────────────────────────────────────────────────────

app.include_router(masha_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "agent": "masha",
        "retell_active": str(bool(RETELL_API_KEY)),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "CC_masha_bbg_integration:app",
        host="0.0.0.0",
        port=8100,
        reload=True,
        log_level="info",
    )
