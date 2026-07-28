#!/usr/bin/env python3
"""
CC_comms_router.py — Hybrid Twilio + Telnyx communication router
Routes SMS, voice, and fax to the right provider based on service type.

Twilio: BBG reservations, Chairman alerts, Retell SIP trunk (KEEP)
Telnyx: GOJ bulk SMS, Victoria Voice AI, Medicaid fax (ADD)

Credentials from ~/.hermes/.env:
  TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_NUMBER
  TELNYX_API_KEY, TELNYX_NUMBER
"""

import os, sys, json, base64, urllib.request, urllib.error
from pathlib import Path
from typing import Optional, Literal

# ── Config ──────────────────────────────────────────────
HERMES_ENV = Path.home() / ".hermes" / ".env"
TELNYX_JSON = Path(__file__).parent / "telnyx_config.json"

Provider = Literal["twilio", "telnyx"]
Service = Literal["bbg_sms", "chairman_sms", "goj_sms", "victoria_voice", "medicaid_fax"]

SERVICE_ROUTING: dict[Service, Provider] = {
    "bbg_sms":          "twilio",
    "chairman_sms":     "twilio",
    "goj_sms":          "telnyx",
    "victoria_voice":   "telnyx",
    "medicaid_fax":     "telnyx",
}

# ── Env loading ─────────────────────────────────────────
def _load_env() -> dict:
    env = {}
    if HERMES_ENV.exists():
        for line in HERMES_ENV.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env

ENV = _load_env()

# ── Twilio client ───────────────────────────────────────
class TwilioClient:
    def __init__(self):
        self.sid = ENV.get("TWILIO_ACCOUNT_SID", "")
        self.token = ENV.get("TWILIO_AUTH_TOKEN", "")
        self.from_number = ENV.get("TWILIO_NUMBER", "+18776882887")

    def send_sms(self, to: str, body: str) -> dict:
        if not self.sid or not self.token:
            return {"ok": False, "error": "Twilio creds missing"}
        try:
            auth = base64.b64encode(f"{self.sid}:{self.token}".encode()).decode()
            data = urllib.parse.urlencode({
                "From": self.from_number, "To": to, "Body": body
            }).encode()
            req = urllib.request.Request(
                f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json",
                data=data,
                headers={"Authorization": f"Basic {auth}"}
            )
            resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
            return {"ok": True, "sid": resp.get("sid"), "provider": "twilio"}
        except Exception as e:
            return {"ok": False, "error": str(e), "provider": "twilio"}

# ── Telnyx client ──────────────────────────────────────
class TelnyxClient:
    def __init__(self):
        self.api_key = ENV.get("TELNYX_API_KEY", "")
        self.from_number = ENV.get("TELNYX_NUMBER", "")
        # Fallback to JSON config if env vars missing (TCC-safe path)
        if (not self.api_key or not self.from_number) and TELNYX_JSON.exists():
            try:
                data = json.loads(TELNYX_JSON.read_text())
                self.api_key = self.api_key or data.get("telnyx_api_key", "")
                self.from_number = self.from_number or data.get("telnyx_number", "")
            except Exception:
                pass

    def send_sms(self, to: str, body: str) -> dict:
        if not self.api_key or not self.from_number:
            return {"ok": False, "error": "Telnyx creds missing"}
        try:
            data = json.dumps({
                "from": self.from_number,
                "to": to,
                "text": body,
            }).encode()
            req = urllib.request.Request(
                "https://api.telnyx.com/v2/messages",
                data=data,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
            )
            resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
            msg_id = resp.get("data", {}).get("id", "")
            return {"ok": True, "id": msg_id, "provider": "telnyx"}
        except Exception as e:
            return {"ok": False, "error": str(e), "provider": "telnyx"}

    def send_fax(self, to: str, media_url: str) -> dict:
        if not self.api_key:
            return {"ok": False, "error": "Telnyx creds missing"}
        try:
            data = json.dumps({
                "from": self.from_number,
                "to": to,
                "media_url": media_url,
            }).encode()
            req = urllib.request.Request(
                "https://api.telnyx.com/v2/faxes",
                data=data,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
            )
            resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
            return {"ok": True, "id": resp.get("data", {}).get("id", ""), "provider": "telnyx"}
        except Exception as e:
            return {"ok": False, "error": str(e), "provider": "telnyx"}

# ── Router ──────────────────────────────────────────────
class CommsRouter:
    def __init__(self):
        self.twilio = TwilioClient()
        self.telnyx = TelnyxClient()

    def route(self, service: Service, to: str, body: str) -> dict:
        """Route a message to the correct provider. Falls back to the other if primary fails."""
        primary = SERVICE_ROUTING.get(service, "twilio")

        # Try primary
        if primary == "twilio":
            result = self.twilio.send_sms(to, body)
        else:
            result = self.telnyx.send_sms(to, body)

        if result["ok"]:
            return result

        # Fallback to secondary
        fallback = "telnyx" if primary == "twilio" else "twilio"
        result["fallback_from"] = primary
        if fallback == "twilio":
            result_fb = self.twilio.send_sms(to, body)
        else:
            result_fb = self.telnyx.send_sms(to, body)

        if result_fb["ok"]:
            result_fb["fallback_from"] = primary
            return result_fb

        return {"ok": False, "error": "Both providers failed", "primary_error": result.get("error"), "fallback_error": result_fb.get("error")}

    def send_fax(self, to: str, media_url: str) -> dict:
        return self.telnyx.send_fax(to, media_url)

# ── CLI ─────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Comms Router — Twilio + Telnyx")
    sub = parser.add_subparsers(dest="cmd")

    sms = sub.add_parser("sms", help="Send SMS")
    sms.add_argument("service", choices=list(SERVICE_ROUTING.keys()))
    sms.add_argument("to", help="Phone number (E.164)")
    sms.add_argument("body", help="Message body")

    fax = sub.add_parser("fax", help="Send fax")
    fax.add_argument("to", help="Fax number")
    fax.add_argument("media_url", help="URL of document to fax")

    status = sub.add_parser("status", help="Show config status")

    args = parser.parse_args()
    router = CommsRouter()

    if args.cmd == "status":
        tw_ok = bool(ENV.get("TWILIO_ACCOUNT_SID"))
        tl_ok = bool(ENV.get("TELNYX_API_KEY"))
        # Fallback to JSON config for Telnyx
        if not tl_ok and TELNYX_JSON.exists():
            try:
                data = json.loads(TELNYX_JSON.read_text())
                tl_ok = bool(data.get("telnyx_api_key"))
            except Exception:
                pass
        print(f"Twilio: {'✅ configured' if tw_ok else '❌ missing creds'}")
        print(f"Telnyx: {'✅ configured' if tl_ok else '❌ missing creds'}")
        print(f"Routing: {json.dumps(SERVICE_ROUTING, indent=2)}")

    elif args.cmd == "sms":
        result = router.route(args.service, args.to, args.body)
        print(json.dumps(result, indent=2))

    elif args.cmd == "fax":
        result = router.send_fax(args.to, args.media_url)
        print(json.dumps(result, indent=2))
