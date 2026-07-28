#!/usr/bin/env python3
"""
serve_goj_dashboard.py — Standalone GOJ Dashboard Server
=========================================================
Serves the comprehensive GOJ operations dashboard at goj.goldhealthsys.com.
Runs on port 8095. Wired through Cloudflare tunnel.

Usage:
    python3 serve_goj_dashboard.py              # Run directly
    launchctl load com.goj.dashboard.plist       # Run as service
"""

import sys
from pathlib import Path

# Add REX directory to path for the dashboard router
sys.path.insert(0, str(Path(__file__).resolve().parent))

from goj_dashboard_router import router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="GOJ Operations Dashboard", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8095, log_level="info")
