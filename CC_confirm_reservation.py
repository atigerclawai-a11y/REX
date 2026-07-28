#!/usr/bin/env python3
"""
CC_confirm_reservation.py
==========================
Marks a BBG reservation as confirmed and sends SMS confirmation via Twilio.

Usage:
    python3 CC_confirm_reservation.py <reservation_id>
    python3 CC_confirm_reservation.py --all-unconfirmed
    python3 CC_confirm_reservation.py --list

Configuration (in ~/Desktop/REX/.env):
    TWILIO_ACCOUNT_SID       — Twilio Account SID
    TWILIO_AUTH_TOKEN        — Twilio Auth Token
    BBG_TWILIO_FROM_NUMBER   — E.164 Twilio number to send from (toll-free: +18777682887)

SMS integration:
    Uses Twilio REST API (Messages.json) for outbound SMS.
    Working immediately — toll-free number (877) 768-2887, verification pending but SMS functional.
"""

from __future__ import annotations

import base64
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REX_DIR = Path.home() / "Desktop" / "REX"
RESERVATIONS_PATH = REX_DIR / "CC_bbg_reservations.json"
ENV_PATH = REX_DIR / ".env"

# ── Configuration ────────────────────────────────────────────────────────────────
TWILIO_SID: str = ""
TWILIO_TOKEN: str = ""
BBG_TWILIO_FROM: str = ""


def _load_env() -> None:
    """Load credentials from ~/Desktop/REX/.env into module globals."""
    global TWILIO_SID, TWILIO_TOKEN, BBG_TWILIO_FROM
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip().strip('"').strip("'")
        if key == "TWILIO_ACCOUNT_SID":
            TWILIO_SID = val
        elif key == "TWILIO_AUTH_TOKEN":
            TWILIO_TOKEN = val
        elif key == "BBG_TWILIO_FROM_NUMBER":
            BBG_TWILIO_FROM = val


_load_env()

# ── SMS Template ─────────────────────────────────────────────────────────────────

SMS_CONFIRMATION = (
    "Boardwalk Beer Garden 🍻: Reservation confirmed! "
    "{party_name}, party of {party_size}, {reservation_date} at {reservation_time}. "
    "3152 Brighton 6th St, Brooklyn. Reply or call (929) 205-6408 for changes."
)


# ── JSON helpers ─────────────────────────────────────────────────────────────────


def _load_reservations() -> list[dict]:
    if not RESERVATIONS_PATH.exists():
        return []
    return json.loads(RESERVATIONS_PATH.read_text(encoding="utf-8"))


def _save_reservations(data: list[dict]) -> None:
    RESERVATIONS_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ── Twilio SMS ───────────────────────────────────────────────────────────────────


def send_sms_confirmation(
    to_phone: str,
    party_name: str,
    party_size: int,
    reservation_date: str,
    reservation_time: str,
) -> dict:
    """Send an SMS confirmation via Twilio. Returns {'ok': bool, 'detail': str, 'sid': ...}."""
    if not TWILIO_SID or not TWILIO_TOKEN:
        return {"ok": False, "detail": "Twilio creds not configured"}
    if not BBG_TWILIO_FROM:
        return {"ok": False, "detail": "BBG_TWILIO_FROM_NUMBER not configured"}
    if not to_phone or len(to_phone.replace("*", "").replace("+", "")) < 7:
        return {"ok": False, "detail": f"Phone too short or masked: {to_phone}"}

    message = SMS_CONFIRMATION.format(
        party_name=party_name,
        party_size=party_size,
        reservation_date=reservation_date,
        reservation_time=reservation_time,
    )

    try:
        auth = base64.b64encode(f"{TWILIO_SID}:{TWILIO_TOKEN}".encode()).decode()
        body = urlencode(
            {
                "From": BBG_TWILIO_FROM,
                "To": to_phone,
                "Body": message,
            }
        ).encode()

        req = Request(
            f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json",
            data=body,
            headers={"Authorization": f"Basic {auth}"},
        )
        resp = urlopen(req, timeout=15)
        data = json.loads(resp.read())

        sid = data.get("sid", "unknown")
        status = data.get("status", "unknown")
        error = data.get("error_message")

        if error:
            return {"ok": False, "detail": f"Twilio: {error}", "sid": sid}

        return {
            "ok": True,
            "detail": f"SMS {status} (sid: {sid})",
            "sid": sid,
            "status": status,
        }

    except HTTPError as e:
        err_body = e.read().decode()[:500]
        return {"ok": False, "detail": f"Twilio HTTP {e.code}: {err_body}"}

    except Exception as exc:
        return {"ok": False, "detail": f"Twilio error: {exc}"}


# ── Confirmation ─────────────────────────────────────────────────────────────────


def confirm(reservation_id: int, dry_run: bool = False) -> dict | None:
    """Confirm a reservation and send SMS if phone available."""
    reservations = _load_reservations()
    target = None
    for r in reservations:
        if r.get("id") == reservation_id:
            target = r
            break

    if not target:
        print(f"Reservation #{reservation_id} not found")
        return None

    if target.get("confirmed"):
        print(f"Reservation #{reservation_id} is already confirmed")
        return target

    phone = target.get("phone", "")
    party_name = target.get("party_name", "Guest")
    party_size = target.get("party_size", 1)
    res_date = target.get("reservation_date", "")
    res_time = target.get("reservation_time", "")

    if dry_run:
        print(
            f"[DRY RUN] Would confirm #{reservation_id}: {party_name} "
            f"on {res_date} @ {res_time}"
        )
        if phone:
            print(f"  Would SMS {phone} from {BBG_TWILIO_FROM}")
        return target

    # Mark as confirmed
    target["confirmed"] = True
    target["confirmed_at"] = datetime.now(timezone.utc).isoformat()
    target["sms_status"] = None

    # Attempt SMS
    if phone:
        sms_result = send_sms_confirmation(
            to_phone=phone,
            party_name=party_name,
            party_size=party_size,
            reservation_date=res_date,
            reservation_time=res_time,
        )
        target["sms_status"] = sms_result
        icon = "✓" if sms_result["ok"] else "✗"
        print(f"  SMS {icon} {sms_result['detail']}")
    else:
        print(f"  No guest phone — SMS skipped")

    _save_reservations(reservations)

    print(
        f"✓ Confirmed #{reservation_id}: {party_name} "
        f"on {res_date} @ {res_time}"
    )
    return target


def confirm_all_unconfirmed(dry_run: bool = False) -> list[dict]:
    """Confirm all unconfirmed, non-declined reservations."""
    reservations = _load_reservations()
    unconfirmed = [
        r
        for r in reservations
        if not r.get("confirmed")
        and r.get("party_name")
        and r.get("status") != "declined"
    ]
    confirmed = []
    for r in unconfirmed:
        result = confirm(r["id"], dry_run=dry_run)
        if result:
            confirmed.append(result)
    return confirmed


def list_unconfirmed() -> list[dict]:
    """List all unconfirmed, non-declined reservations."""
    reservations = _load_reservations()
    return [
        r
        for r in reservations
        if not r.get("confirmed") and r.get("status") != "declined"
    ]


# ── CLI ──────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--all-unconfirmed" in sys.argv:
        dry = "--dry-run" in sys.argv
        confirm_all_unconfirmed(dry_run=dry)
    elif len(sys.argv) > 1 and sys.argv[1].isdigit():
        rid = int(sys.argv[1])
        dry = "--dry-run" in sys.argv
        confirm(rid, dry_run=dry)
    elif "--list" in sys.argv:
        unconfirmed = list_unconfirmed()
        if not unconfirmed:
            print("All reservations confirmed ✓")
        for r in unconfirmed:
            print(
                f"  #{r['id']} | {r.get('reservation_date')} @ {r.get('reservation_time')} | "
                f"{r['party_name']:25} | x{r['party_size']} | {r.get('phone', '?')}"
            )
    else:
        print(
            "Usage: python3 CC_confirm_reservation.py <id> | --all-unconfirmed | --list"
        )
