"""
CC_schedule_hub_standalone.py — TEMPORARY bridge service for Schedule Hub v3
============================================================================
Why this exists (2026-07-24): macOS TCC revoked overwrite access to
CC_schedule_hub.py mid-session (OBJ-004). The v3 router could be CREATED as
CC_schedule_hub_new.py but not swapped into place. This wrapper serves v3 on
:8002 until the file swap heals, at which point:
  1. mv CC_schedule_hub_new.py CC_schedule_hub.py
  2. launchctl bootout gui/$(id -u)/com.goj.schedule-hub
  3. delete this file + ~/Library/LaunchAgents/com.goj.schedule-hub.plist
  4. restart com.rex.backend (v3 then lives at :8000/schedule-hub)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn
from fastapi import FastAPI

from CC_schedule_hub_new import router

app = FastAPI(title="GHS Schedule Hub — v3 bridge")
app.include_router(router)


@app.get("/health")
async def root_health():
    return {"status": "ok", "service": "schedule-hub-v3-bridge", "port": 8002}


@app.get("/")
async def root_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/schedule-hub/", status_code=303)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8002, log_level="info")
