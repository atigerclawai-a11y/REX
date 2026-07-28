"""
CC_voice_integration.py
========================
TigerClaw Voice Integration Service — Gold Health Systems
Standalone FastAPI service on port 8003.

Features:
    1. GET  /voice/read/{filename}   — reads a GHS Live/ Obsidian .md file aloud
    2. POST /voice/speak             — speaks arbitrary text via macOS TTS
    3. POST /voice/hermes            — sends a message to Hermes (localhost:3002), speaks response
    4. POST /voice/retell/start      — pre-wired Retell bridge (blocked until API key renewed)
    5. GET  /voice/health            — TTS engine status + Retell connection status

Usage:
    # Start the service (stays running, port 8003):
    python CC_voice_integration.py

    # Speak immediately and exit:
    python CC_voice_integration.py --speak "Good morning, Kato."

    # Read an Obsidian GHS Live/ file aloud and exit:
    python CC_voice_integration.py --read BUILD_STATUS

Environment variables (all optional):
    RETELL_API_KEY      — when set, activates Retell bridge (currently blocked)
    VICTORIA_AGENT_ID   — Retell agent ID for Victoria (GOJ)
    MASHA_AGENT_ID      — Retell agent ID for Masha (BBG)
    TTS_VOICE           — macOS voice to use (default: Samantha)

Retell status:
    ⚠️  BLOCKED — Retell API key expired. Renew at https://retell.ai
        Set RETELL_API_KEY env var to activate.

Dependencies:
    fastapi, uvicorn, requests (pip install fastapi uvicorn requests)
    macOS `say` command — built-in, no install needed
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────────────────────
GHS_LIVE_DIR = Path.home() / "Desktop" / "Gold_Health_Systems" / "BRAIN" / "GHS Live"
HERMES_URL = "http://localhost:3002"
REX_URL = "http://localhost:8000"
RETELL_API_URL = "https://api.retell.ai/v2/create-phone-call"

# ── Config ─────────────────────────────────────────────────────────────────────
TTS_VOICE = os.getenv("TTS_VOICE", "Samantha")
RETELL_API_KEY = os.getenv("RETELL_API_KEY", "")
VICTORIA_AGENT_ID = os.getenv("VICTORIA_AGENT_ID", "")
MASHA_AGENT_ID = os.getenv("MASHA_AGENT_ID", "")
PORT = 8003


# ── TTS helpers ────────────────────────────────────────────────────────────────

def strip_markdown(text: str) -> str:
    """Remove markdown syntax and return plain readable text."""
    # Remove code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]+`", "", text)
    # Remove headings markers, bold, italic
    text = re.sub(r"[#*_~>]+", "", text)
    # Remove links: [text](url) → text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Remove horizontal rules
    text = re.sub(r"^[-=]{3,}$", "", text, flags=re.MULTILINE)
    # Collapse excess whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def speak(text: str, voice: str = TTS_VOICE) -> None:
    """Speak text using macOS `say` command. Blocks until done."""
    subprocess.run(["say", "-v", voice, text], check=False)


def speak_background(text: str, voice: str = TTS_VOICE) -> None:
    """Speak text without blocking the HTTP response."""
    subprocess.Popen(["say", "-v", voice, text])


# ── FastAPI app ────────────────────────────────────────────────────────────────

def build_app():
    """Build and return the FastAPI app. Imported lazily so CLI --speak/--read
    work without fastapi installed."""
    try:
        from fastapi import FastAPI, HTTPException
        from pydantic import BaseModel
        import requests
    except ImportError as e:
        print(f"Missing dependency: {e}\nRun: pip install fastapi uvicorn requests")
        sys.exit(1)

    app = FastAPI(
        title="TigerClaw Voice Integration",
        description="GHS voice layer — TTS, Hermes, Retell bridge",
        version="1.0.0",
    )

    # ── Request models ─────────────────────────────────────────────────────────

    class SpeakRequest(BaseModel):
        text: str
        voice: str = TTS_VOICE

    class HermesVoiceRequest(BaseModel):
        message: str
        voice: str = TTS_VOICE

    class RetellStartRequest(BaseModel):
        agent: str = "victoria"          # "victoria" or "masha"
        to_phone: Optional[str] = None   # required when Retell is active
        from_phone: Optional[str] = None

    # ── Endpoints ──────────────────────────────────────────────────────────────

    @app.get("/voice/health")
    def health():
        """Return TTS engine status and Retell connection status."""
        # Quick check: does `say` exist?
        say_ok = subprocess.run(["which", "say"], capture_output=True).returncode == 0

        retell_status = "blocked — API key expired. Renew at https://retell.ai"
        retell_active = False
        if RETELL_API_KEY:
            retell_status = "configured"
            retell_active = True

        return {
            "status": "ok",
            "tts_engine": "macOS say",
            "tts_voice": TTS_VOICE,
            "tts_available": say_ok,
            "hermes_url": HERMES_URL,
            "retell_active": retell_active,
            "retell_status": retell_status,
            "victoria_agent_configured": bool(VICTORIA_AGENT_ID),
            "masha_agent_configured": bool(MASHA_AGENT_ID),
        }

    @app.get("/voice/read/{filename}")
    def read_file(filename: str):
        """Read a GHS Live/ Obsidian .md file aloud via macOS TTS.

        filename — bare name without .md extension, e.g. BUILD_STATUS
        """
        # Try exact match, then .md variant
        candidates = [
            GHS_LIVE_DIR / filename,
            GHS_LIVE_DIR / f"{filename}.md",
        ]
        found = None
        for c in candidates:
            if c.exists():
                found = c
                break

        if not found:
            raise HTTPException(
                status_code=404,
                detail=f"File not found in GHS Live/: {filename} (also tried {filename}.md)",
            )

        raw = found.read_text(encoding="utf-8", errors="replace")
        plain = strip_markdown(raw)

        if not plain:
            raise HTTPException(status_code=400, detail="File has no readable text after markdown stripping.")

        speak_background(plain)
        return {
            "status": "speaking",
            "file": str(found),
            "characters": len(plain),
            "preview": plain[:200],
        }

    @app.post("/voice/speak")
    def speak_text(req: SpeakRequest):
        """Speak arbitrary text using macOS TTS."""
        if not req.text.strip():
            raise HTTPException(status_code=400, detail="text is empty")
        speak_background(req.text, voice=req.voice)
        return {"status": "speaking", "voice": req.voice, "characters": len(req.text)}

    @app.post("/voice/hermes")
    def hermes_voice(req: HermesVoiceRequest):
        """Send a message to the Hermes gateway, get response, speak it aloud."""
        if not req.message.strip():
            raise HTTPException(status_code=400, detail="message is empty")

        # Send to Hermes gateway. Hermes expects POST /chat with {"message": "..."}
        # (falls back to /api/chat if the root route 404s)
        hermes_response_text = None
        tried_urls = []

        for endpoint in ["/chat", "/api/chat"]:
            url = f"{HERMES_URL}{endpoint}"
            tried_urls.append(url)
            try:
                resp = requests.post(
                    url,
                    json={"message": req.message, "stream": False},
                    timeout=30,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    # Common response shapes: {"response": "..."}, {"reply": "..."}, {"message": "..."}
                    hermes_response_text = (
                        data.get("response")
                        or data.get("reply")
                        or data.get("message")
                        or data.get("content")
                        or str(data)
                    )
                    break
            except requests.exceptions.RequestException:
                continue

        if not hermes_response_text:
            raise HTTPException(
                status_code=502,
                detail=f"Could not reach Hermes at {HERMES_URL} (tried {tried_urls}). Is the gateway running?",
            )

        plain = strip_markdown(hermes_response_text)
        speak_background(plain, voice=req.voice)
        return {
            "status": "speaking",
            "voice": req.voice,
            "hermes_response": hermes_response_text,
        }

    @app.post("/voice/retell/start")
    def retell_start(req: RetellStartRequest):
        """Initiate a Retell voice call via Victoria or Masha.

        Currently blocked — RETELL_API_KEY not set (subscription expired).
        Set RETELL_API_KEY env var to activate.
        """
        if not RETELL_API_KEY:
            return {
                "status": "blocked",
                "reason": "Retell API key expired — renew at https://retell.ai and set RETELL_API_KEY env var",
            }

        agent = req.agent.lower()
        if agent == "victoria":
            agent_id = VICTORIA_AGENT_ID
            label = "Victoria (GOJ)"
        elif agent == "masha":
            agent_id = MASHA_AGENT_ID
            label = "Masha (BBG)"
        else:
            raise HTTPException(status_code=400, detail="agent must be 'victoria' or 'masha'")

        if not agent_id:
            raise HTTPException(
                status_code=400,
                detail=f"{label} agent ID not configured. Set VICTORIA_AGENT_ID or MASHA_AGENT_ID env var.",
            )

        if not req.to_phone:
            raise HTTPException(status_code=400, detail="to_phone is required when Retell is active")

        payload = {
            "agent_id": agent_id,
            "from_number": req.from_phone or "",
            "to_number": req.to_phone,
        }

        try:
            resp = requests.post(
                RETELL_API_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {RETELL_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
            if resp.status_code in (200, 201):
                return {"status": "call_initiated", "agent": label, "data": resp.json()}
            else:
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"Retell API error: {resp.text}",
                )
        except requests.exceptions.RequestException as e:
            raise HTTPException(status_code=502, detail=f"Could not reach Retell API: {e}")

    return app


# ── CLI entry point ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="TigerClaw Voice Integration Service (port 8003)"
    )
    parser.add_argument(
        "--speak",
        metavar="TEXT",
        help="Speak the given text immediately and exit",
    )
    parser.add_argument(
        "--read",
        metavar="FILENAME",
        help="Read a GHS Live/ Obsidian .md file aloud and exit (bare name, no .md)",
    )
    parser.add_argument(
        "--voice",
        default=TTS_VOICE,
        help=f"macOS voice to use (default: {TTS_VOICE})",
    )
    args = parser.parse_args()

    if args.speak:
        speak(args.speak, voice=args.voice)
        sys.exit(0)

    if args.read:
        candidates = [
            GHS_LIVE_DIR / args.read,
            GHS_LIVE_DIR / f"{args.read}.md",
        ]
        found = None
        for c in candidates:
            if c.exists():
                found = c
                break
        if not found:
            print(f"File not found in {GHS_LIVE_DIR}: {args.read}")
            sys.exit(1)
        raw = found.read_text(encoding="utf-8", errors="replace")
        plain = strip_markdown(raw)
        if not plain:
            print("No readable text after markdown stripping.")
            sys.exit(1)
        print(f"Reading: {found}")
        speak(plain, voice=args.voice)
        sys.exit(0)

    # No CLI flags — start the FastAPI server
    try:
        import uvicorn
    except ImportError:
        print("uvicorn not installed. Run: pip install fastapi uvicorn requests")
        sys.exit(1)

    app = build_app()
    print(f"TigerClaw Voice Integration starting on port {PORT}")
    print(f"  TTS voice  : {TTS_VOICE}")
    print(f"  GHS Live/  : {GHS_LIVE_DIR}")
    print(f"  Hermes     : {HERMES_URL}")
    print(f"  Retell     : {'ACTIVE' if RETELL_API_KEY else 'BLOCKED (key expired)'}")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")


if __name__ == "__main__":
    main()
