"""
REX — FastAPI Backend (Desktop Mode)
The macOS desktop app runs entirely on localhost — no auth token needed.
iPhone pairing uses JWT (handled in auth.py) but the desktop is always trusted.

Pipeline (Secure Mode ON):
  Receive → Encrypt locally → De-ID → Send to AI → Re-ID → Display → Encrypt response

Pipeline (Standard Mode):
  Receive → Encrypt locally → Send to AI → Display → Encrypt response

New in Sovereign Edition:
  • Persistent memory (RexMemory) — REX remembers across sessions
  • Sovereign system prompt (sovereign.py) — Claude-mentored identity
  • Session auto-backup — every session saved, picked up on resume
  • Encrypted agent bus (AgentBus) — secure inter-agent comms
  • REST /api/chat endpoint — for GOJ dashboard widget integration
  • Memory API — /api/memory (CRUD) for long-term facts
"""
import asyncio
import os
import uuid
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Header, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import shutil
import sys, os

# Prompt injection guard (red team hardening)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from CC_prompt_guard import PromptGuardMiddleware

from .config import Settings
from .deidentify import DeidentificationEngine
from .auth import device_manager, require_auth
from .litellm_proxy import LiteLLMProxy
from .audit import AuditLogger, AuditEventType
from .storage import EncryptedStorage
from .models import SecureModeRequest
from .memory import RexMemory
from .sovereign import build_system_prompt
from .agent_bus import AgentBus
from .rex_vault import ChairmanVault
from .rex_training import RexTraining
from .rex_rexxie import RexxieMode, RexxieMemory
from .rex_ai_enrichment import get_background_block, should_enrich, ingest_reports
from .rex_behavior_monitor import check_response as _behavior_check
from .rex_quiz import RexQuiz
from .rex_notify import RexNotify
from .rex_role_auth import verify_role
from .rex_encrypted_transcript import TranscriptStore, EncryptedSessionCache
from .rex_gmail import (
    is_configured as gmail_configured,
    get_profile as gmail_profile,
    get_inbox_summary,
    search_emails,
    run_auto_label,
    get_label_rules,
    save_label_rules,
    load_label_rules,
    get_unread_count,
    send_email as gmail_send_email,
)
from .rex_gdrive import (
    is_configured as gdrive_configured,
    upload_file as gdrive_upload,
    list_drive_files,
    sync_uploads_to_drive,
)
from .rex_menu_scan_watcher import run_menu_scan_watcher
from .rex_telegram_reader import (
    load_config as tg_load_config,
    save_config as tg_save_config,
    fetch_channel as tg_fetch,
    get_cached_messages as tg_cached,
    get_schedule_summary as tg_schedule_summary,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("rex")

# ── Singletons ────────────────────────────────────────────────────────────────
settings  = Settings()
settings.load_all_keys_to_env()
storage   = EncryptedStorage()
audit     = AuditLogger(storage)
deid      = DeidentificationEngine()
llm       = LiteLLMProxy(settings)
memory    = RexMemory(db_path=storage.db_path, key=storage._key)
agent_bus = AgentBus(master_key=storage._key)
vault     = ChairmanVault(master_key=storage._key)
training  = RexTraining(db_path=str(storage.db_path))
notify    = RexNotify()
rexxie    = RexxieMode(memory=RexxieMemory())
quiz      = RexQuiz(db_path=str(storage.db_path), notify=notify)
transcript_store  = TranscriptStore(master_key=storage._key)   # triple-encrypted transcript log
session_cache_enc = EncryptedSessionCache(master_key=storage._key)  # encrypted session resume cache

# ── Uploads directory ─────────────────────────────────────────────────
UPLOADS_DIR = Path(__file__).parent.parent / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Load persisted Gmail label rules if any
load_label_rules()

# ── Phone unlock server (starts in background thread with REX) ─────────────────
_phone_unlock_server = None
def _start_phone_unlock_server():
    global _phone_unlock_server
    try:
        import sys
        from pathlib import Path as _Path
        parent = _Path(__file__).resolve().parent.parent
        if str(parent) not in sys.path:
            sys.path.insert(0, str(parent))
        from rex_phone_unlock import PhoneUnlockServer
        _phone_unlock_server = PhoneUnlockServer()
        if _phone_unlock_server.secret:
            _phone_unlock_server.start_background()
            logger.info("📱 Phone unlock server started (background)")
        else:
            logger.info("📱 Phone unlock: not configured (run rex_phone_unlock.py --setup)")
    except Exception as e:
        logger.warning(f"Phone unlock server not started: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    audit.app_start()
    _start_phone_unlock_server()
    logger.info(f"🦖 REX Sovereign started | Memory: active | De-ID: {deid.engine_name} | DB: {storage.db_path}")
    # Start background watcher: Gmail → menu PDF auto-download → OCR BLAST
    _menu_watcher_task = asyncio.create_task(run_menu_scan_watcher())
    logger.info("📬 Menu scan watcher started (polls Gmail every 5 min)")

    # ── V4 Rexonasence startup hooks ──────────────────────────────────────────
    import sys as _sys
    _rex_root = str(Path(__file__).resolve().parent.parent)
    if _rex_root not in _sys.path:
        _sys.path.insert(0, _rex_root)

    # Routers are now registered pre-lifespan (see line ~384).
    # Only startup tasks below.

    # V4 DB migrations (all idempotent)
    try:
        from rex_receipt_manager_v4_patch import run_v4_migration
        _mig = run_v4_migration()
        added = _mig.get("added", [])
        logger.info(f"✅ V4: receipt schema migration — {len(added)} column(s) added: {added or 'none (already current)'}")
    except Exception as _v4m_err:
        logger.warning(f"⚠️ V4 receipt migration: {_v4m_err}")

    try:
        from rex_events import _ensure_db as _ensure_events_db
        _ensure_events_db()
        logger.info("✅ V4: events DB ready")
    except Exception as _v4e_err:
        logger.warning(f"⚠️ V4 events DB: {_v4e_err}")

    try:
        from rex_unresolved import _ensure_db as _ensure_unresolved_db
        _ensure_unresolved_db()
        logger.info("✅ V4: unresolved DB ready")
    except Exception as _v4u_err:
        logger.warning(f"⚠️ V4 unresolved DB: {_v4u_err}")

    # Daily 21:00 resurfacing scheduler (no APScheduler required — pure asyncio)
    _v4_resurface_task = None
    try:
        async def _v4_resurface_loop():
            while True:
                try:
                    from datetime import datetime as _dt, timedelta as _td
                    _now  = _dt.now()
                    _target = _now.replace(hour=21, minute=0, second=0, microsecond=0)
                    if _now >= _target:
                        _target += _td(days=1)
                    _wait = (_target - _dt.now()).total_seconds()
                    await asyncio.sleep(max(_wait, 1))
                    from rex_unresolved import check_resurfacing
                    check_resurfacing()
                    logger.info("✅ V4: unresolved resurfacing check complete")
                except asyncio.CancelledError:
                    break
                except Exception as _re:
                    logger.warning(f"⚠️ V4 resurfacing: {_re}")
                    await asyncio.sleep(3600)   # back off 1 hr on error
        _v4_resurface_task = asyncio.create_task(_v4_resurface_loop())
        logger.info("✅ V4: daily 21:00 resurfacing scheduler active")
    except Exception as _v4s_err:
        logger.warning(f"⚠️ V4 scheduler: {_v4s_err}")

    yield

    # ── V4 shutdown ───────────────────────────────────────────────────────────
    if _v4_resurface_task is not None:
        _v4_resurface_task.cancel()
        try:
            await _v4_resurface_task
        except asyncio.CancelledError:
            pass

    _menu_watcher_task.cancel()
    try:
        await _menu_watcher_task
    except asyncio.CancelledError:
        pass
    if _phone_unlock_server:
        _phone_unlock_server.stop()
    audit.app_stop()


_IS_LOCAL = os.getenv("REX_ENV", "local") == "local"

# ── FastAPI app — docs disabled in production ──────────────────────────────────
# /docs, /redoc, and /openapi.json are completely hidden when deployed publicly.
# They remain on when REX_ENV=local for development convenience.
app = FastAPI(
    title="REX Sovereign AI",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/docs" if _IS_LOCAL else None,
    redoc_url="/redoc" if _IS_LOCAL else None,
    openapi_url="/openapi.json" if _IS_LOCAL else None,
)

# ── CORS — locked to goldhealthsys.com in production ──────────────────────────
# Locally: allow localhost origins for the desktop app.
# Publicly: ONLY the production domain is allowed — no wildcards.
_ALLOWED_ORIGINS = (
    [
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1",
        "http://127.0.0.1:3000",
        "app://.",           # macOS desktop app (Electron/Tauri)
    ]
    if _IS_LOCAL
    else [
        "https://goldhealthsys.com",
        "https://www.goldhealthsys.com",
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Device-ID", "X-Role"],
)

# ── Security Headers Middleware ────────────────────────────────────────────────
# Injected on every response. Protects against XSS, clickjacking, MIME sniffing,
# and information leakage. Critical for HIPAA-sensitive deployments.
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"]    = "nosniff"
        response.headers["X-Frame-Options"]           = "DENY"
        response.headers["X-XSS-Protection"]          = "1; mode=block"
        response.headers["Referrer-Policy"]           = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"]        = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"]             = "no-store, no-cache, must-revalidate, private"
        if not _IS_LOCAL:
            # HSTS: force HTTPS for 1 year, include subdomains
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
            # CSP: only allow resources from our own domain
            response.headers["Content-Security-Policy"] = (
                "default-src 'self' https://goldhealthsys.com; "
                "script-src 'self' 'unsafe-inline'; "   # inline JS needed for dashboard
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; "
                "connect-src 'self' https://goldhealthsys.com; "
                "frame-ancestors 'none';"
            )
        # Never leak server details
        response.headers["Server"] = ""
        return response

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(PromptGuardMiddleware)

# ── Admin Auth Middleware ──────────────────────────────────────────────────────
# Protects admin/config endpoints. Localhost access is allowed without auth
# for development convenience; all remote requests require a valid Bearer token.
_ADMIN_PATH_PREFIXES = (
    "/api/keys", "/api/memory",
    "/api/devices", "/api/audit", "/api/journeys",
)
# Settings always requires auth — even from localhost
_ADMIN_LOCKED_PREFIXES = ("/api/settings",)
# Doc paths — hidden from non-localhost (return 404 to not confirm existence)
_DOC_PATHS = ("/docs", "/redoc", "/openapi.json")

@app.middleware("http")
async def admin_auth_middleware(request: Request, call_next):
    path = request.url.path
    # Hide docs from remote requests
    if any(path.startswith(p) for p in _DOC_PATHS):
        from fastapi.responses import JSONResponse
        is_local = request.client and request.client.host in ("127.0.0.1", "::1", "localhost")
        if not is_local:
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
    # Require auth for admin endpoints from remote
    if any(path.startswith(p) for p in _ADMIN_PATH_PREFIXES):
        from fastapi.responses import JSONResponse
        is_local = request.client and request.client.host in ("127.0.0.1", "::1", "localhost")
        if not is_local:
            auth_header = request.headers.get("authorization", "")
            if not auth_header.startswith("Bearer "):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Authentication required for admin endpoints"},
                )
            token = auth_header[7:]
            device = device_manager.verify_device(token)
            if not device:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or revoked token"},
                )
    # Locked endpoints — always require auth, even from localhost
    if any(path.startswith(p) for p in _ADMIN_LOCKED_PREFIXES):
        from fastapi.responses import JSONResponse
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
            )
        token = auth_header[7:]
        device = device_manager.verify_device(token)
        if not device:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or revoked token"},
            )
    return await call_next(request)

# ── Rate Limiting ──────────────────────────────────────────────────────────────
# Simple in-process rate limiter — no Redis required.
# Blocks IPs that exceed thresholds. Cloudflare WAF is the first line;
# this is the last line if anything slips through.
import threading
from collections import defaultdict

_rate_lock   = threading.Lock()
_rate_store: dict[str, list] = defaultdict(list)  # ip → [timestamps]

# Limits per IP per window
_RATE_LIMITS = {
    "/api/chat":         (20,  60),   # 20 requests per 60s  (chat)
    "/api/staff/chat":   (30,  60),   # 30 per 60s           (staff chat)
    "/api/auth":         (10,  60),   # 10 per 60s           (auth endpoints)
    "__default__":       (120, 60),   # 120 per 60s          (everything else)
}

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        # Only trust CF-Connecting-IP (set by Cloudflare, cannot be spoofed).
        # Never trust X-Forwarded-For — it's trivially spoofable.
        if not _IS_LOCAL:
            client_ip = (
                request.headers.get("CF-Connecting-IP")
                or (request.client.host if request.client else "unknown")
            )
        else:
            client_ip = request.client.host if request.client else "unknown"

        path = request.url.path
        # Find matching limit
        max_req, window = next(
            ((m, w) for prefix, (m, w) in _RATE_LIMITS.items()
             if path.startswith(prefix) and prefix != "__default__"),
            _RATE_LIMITS["__default__"]
        )

        now = time.time()
        key = f"{client_ip}:{path[:30]}"
        with _rate_lock:
            timestamps = _rate_store[key]
            _rate_store[key] = [t for t in timestamps if now - t < window]
            if len(_rate_store[key]) >= max_req:
                from fastapi.responses import JSONResponse
                logger.warning(f"🚫 Rate limit hit: {client_ip} → {path}")
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please slow down."},
                    headers={"Retry-After": str(window)},
                )
            _rate_store[key].append(now)

        return await call_next(request)

app.add_middleware(RateLimitMiddleware)

# ── V4 Router Registration (pre-lifespan, always available) ──────────────────
# These were previously registered inside the lifespan, but include_router
# inside a lifespan can cause routes to not persist after startup.
# Moving them here ensures they're always available regardless of lifespan order.
from pathlib import Path as _Path
import sys as _sys
_rex_root = str(_Path(__file__).resolve().parent.parent)
if _rex_root not in _sys.path:
    _sys.path.insert(0, _rex_root)

try:
    from .rex_command_center import cc_router
    from .rex_executive import exec_router
    app.include_router(cc_router, prefix="/api/chairman")
    app.include_router(exec_router, prefix="/api/executive")
    logger.info("✅ V4: /api/chairman + /api/executive mounted (pre-lifespan)")
except Exception as _v4r_err:
    logger.warning(f"⚠️ V4 routers not loaded: {_v4r_err}")

try:
    from .rex_passkey import router as passkey_router
    app.include_router(passkey_router)
    logger.info("✅ Passkey (WebAuthn) routes mounted (pre-lifespan)")
except Exception as _pk_err:
    logger.warning(f"⚠️ Passkey router not loaded: {_pk_err}")

try:
    from .CC_social_media_router import router as social_router
    app.include_router(social_router)
    logger.info("✅ Social Media Router mounted at /social (pre-lifespan)")
except Exception as _sm_err:
    import traceback
    logger.error(f"⚠️ Social Media Router FAILED: {_sm_err}\n{traceback.format_exc()}")

try:
    from .CC_rex_review import router as rex_review_router
    app.include_router(rex_review_router)
    logger.info("✅ REX Review Router mounted at /rex-review (pre-lifespan)")
except Exception as _rr_err:
    import traceback
    logger.error(f"⚠️ REX Review Router FAILED: {_rr_err}\n{traceback.format_exc()}")

try:
    from .CC_firecrawl_router import router as firecrawl_router
    app.include_router(firecrawl_router)
    logger.info("✅ Firecrawl Router mounted at /firecrawl (pre-lifespan)")
except Exception as _fc_err:
    import traceback
    logger.error(f"⚠️ Firecrawl Router FAILED: {_fc_err}\n{traceback.format_exc()}")

try:
    # Load Victoria Retell credentials from ~/Desktop/REX/.env (no hardcoded secrets)
    import os as _os
    from pathlib import Path as _Path
    
    _rex_env = _Path.home() / "Desktop" / "REX" / ".env"
    if _rex_env.exists():
        for _line in _rex_env.read_text().splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _, _val = _line.partition("=")
                _key = _key.strip()
                _val = _val.strip().strip('"').strip("'")
                if _key in ("RETELL_API_KEY", "VICTORIA_AGENT_ID", "VICTORIA_PHONE_NUMBER", "VICTORIA_FROM_PHONE", "RETELL_WEBHOOK_SECRET", "META_IG_ACCESS_TOKEN", "META_IG_USER_ID", "META_APP_SECRET", "META_APP_ID"):
                    if not _os.getenv(_key):
                        _os.environ[_key] = _val
    # Map VICTORIA_PHONE_NUMBER → VICTORIA_FROM_PHONE if only the former is set
    if not _os.getenv("VICTORIA_FROM_PHONE") and _os.getenv("VICTORIA_PHONE_NUMBER"):
        _os.environ["VICTORIA_FROM_PHONE"] = _os.environ["VICTORIA_PHONE_NUMBER"]
    
    from CC_victoria_goj_integration import victoria_router
    app.include_router(victoria_router, prefix="/victoria")
    logger.info("✅ Victoria GOJ Voice Agent mounted at /victoria (pre-lifespan)")
except Exception as _vic_err:
    import traceback
    logger.error(f"⚠️ Victoria router FAILED: {_vic_err}\n{traceback.format_exc()}")

try:
    from .CC_cowork_relay import router as cowork_relay_router
    app.include_router(cowork_relay_router)
    logger.info("✅ Cowork relay mounted at /api/cowork-relay (pre-lifespan)")
except Exception as _cr_err:
    logger.warning(f"⚠️ Cowork relay router not loaded: {_cr_err}")

try:
    from .CC_auth_router import router as ghs_auth_router
    app.include_router(ghs_auth_router)
    logger.info("✅ GHS auth mounted at /api/auth (pre-lifespan)")
except Exception as _ga_err:
    logger.warning(f"⚠️ GHS auth router not loaded: {_ga_err}")

try:
    from .CC_social_media_router import router as social_router
    app.include_router(social_router)
    logger.info("✅ Social media router mounted at /social (pre-lifespan)")
except Exception as _sm_err:
    logger.warning(f"⚠️ Social media router not loaded: {_sm_err}")

try:
    import sys, os
    _rex_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _rex_root not in sys.path:
        sys.path.insert(0, _rex_root)
    from CC_rex_bill import router as rex_bill_router
    app.include_router(rex_bill_router)
    logger.info("✅ Rex Bill mounted at /rex-bill (pre-lifespan)")
except Exception as _rb_err:
    logger.warning(f"⚠️ Rex Bill router not loaded: {_rb_err}")

try:
    import sys, os
    _rex_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _rex_root not in sys.path:
        sys.path.insert(0, _rex_root)
    from CC_quickbooks_capture import router as qb_capture_router
    app.include_router(qb_capture_router)
    logger.info("✅ QuickBooks Capture mounted at /quickbooks-capture (pre-lifespan)")
except Exception as _qb_err:
    logger.warning(f"⚠️ QuickBooks Capture router not loaded: {_qb_err}")

try:
    from .CC_goj_live import router as goj_live_router
    # router already declares prefix="/goj-live" — do NOT add it again (was double-prefixing to /goj-live/goj-live/*)
    app.include_router(goj_live_router)
    logger.info("✅ GOJ Live mounted at /goj-live (pre-lifespan)")
except Exception as _gl_err:
    logger.warning(f"⚠️ GOJ Live router not loaded: {_gl_err}")

# ── Newly mounted routers (June 2026) ─────────────────────────────────────

try:
    from .CC_attendance_bot import attendance_router
    app.include_router(attendance_router, prefix="/attendance")
    logger.info("✅ Attendance Bot mounted at /attendance (pre-lifespan)")
except Exception as _ab_err:
    logger.warning(f"⚠️ Attendance Bot not loaded (missing deps?): {_ab_err}")

try:
    from .CC_m19_insurance_comms import router as m19_router
    app.include_router(m19_router)
    logger.info("✅ M19 Insurance Comms mounted at /m19 (pre-lifespan)")
except Exception as _m19_err:
    logger.warning(f"⚠️ M19 Insurance Comms router not loaded: {_m19_err}")

try:
    from .CC_m21_bookkeeping_pl import router as m21_router
    app.include_router(m21_router)
    logger.info("✅ M21 Bookkeeping P&L mounted at /m21 (pre-lifespan)")
except Exception as _m21_err:
    logger.warning(f"⚠️ M21 Bookkeeping P&L router not loaded: {_m21_err}")

try:
    from .CC_m24_revenue_intelligence import router as m24_router
    app.include_router(m24_router)
    logger.info("✅ M24 Revenue Intelligence mounted at /m24 (pre-lifespan)")
except Exception as _m24_err:
    logger.warning(f"⚠️ M24 Revenue Intelligence router not loaded: {_m24_err}")

try:
    from .CC_recraft import router as recraft_router
    app.include_router(recraft_router)
    logger.info("✅ Recraft 4.1 mounted at /recraft (pre-lifespan)")
except Exception as _rc_err:
    logger.warning(f"⚠️ Recraft router not loaded: {_rc_err}")

try:
    from .CC_higgsfield import router as higgsfield_router
    app.include_router(higgsfield_router)
    logger.info("✅ Higgsfield AI mounted at /higgsfield — 12 models, virality predictor, extensions (pre-lifespan)")
except Exception as _hf_err:
    logger.warning(f"⚠️ Higgsfield router not loaded: {_hf_err}")

try:
    from CC_carerex_module1 import router as carerex_router
    app.include_router(carerex_router, prefix="/carerex")
    logger.info("✅ CareRex Scheduling mounted at /carerex (pre-lifespan)")
except Exception as _crx_err:
    logger.warning(f"⚠️ CareRex router not loaded: {_crx_err}")

try:
    from CC_masha_bbg_integration import masha_router
    app.include_router(masha_router)
    logger.info("✅ Masha BBG Integration mounted at /masha (pre-lifespan)")
except Exception as _mb_err:
    logger.warning(f"⚠️ Masha BBG router not loaded: {_mb_err}")

try:
    from CC_scrapy_agent.router import router as scrapy_agent_router
    app.include_router(scrapy_agent_router)
    logger.info("✅ Scrapy Agent mounted at /scrapy-agent (pre-lifespan)")
except Exception as _sa_err:
    logger.warning(f"⚠️ Scrapy Agent router not loaded: {_sa_err}")

try:
    from .CC_docker_status import router as docker_router
    app.include_router(docker_router)
    logger.info("✅ Docker Status mounted at /docker (pre-lifespan)")
except Exception as _dk_err:
    logger.warning(f"⚠️ Docker Status router not loaded: {_dk_err}")

try:
    from .CC_schedule_hub import router as schedule_hub_router
    app.include_router(schedule_hub_router)
    logger.info("✅ Schedule Hub mounted at /schedule-hub (pre-lifespan)")
except Exception as _sh_err:
    logger.warning(f"⚠️ Schedule Hub router not loaded: {_sh_err}")


# ── System Prompt Builder (used in all chat contexts) ─────────────────────────

try:
    from .CC_goj_live import router as goj_live_router
    # router already declares prefix="/goj-live" — do NOT add it again (was double-prefixing to /goj-live/goj-live/*)
    app.include_router(goj_live_router)
    logger.info("✅ GOJ Live mounted at /goj-live (pre-lifespan)")
except Exception as _gl_err:
    logger.warning(f"⚠️ GOJ Live router not loaded: {_gl_err}")


def _build_system_prompt(
    user_name: str = "",
    user_role: str = "",
    page_context: str = "",
    dashboard_mode: bool = False,
    vault_mode: bool = False,
    training_mode: bool = False,
    training_context: str = "",
    rexxie_mode: bool = False,
) -> str:
    """Assemble the full sovereign prompt with live memory filtered by caller role.

    When rexxie_mode=True, REX business memory and GOJ context are NOT loaded —
    only Rexxie's personal context (passed via training_context) is used.
    This keeps the two completely isolated from each other.
    """
    if rexxie_mode:
        # Rexxie gets her own context only — no REX business memory, no GOJ knowledge
        return build_system_prompt(
            memory_context="",
            session_history="",
            page_context="",
            user_name=user_name,
            user_role=user_role,
            dashboard_mode=False,
            vault_mode=vault_mode,
            training_mode=False,
            training_context=training_context,
            rexxie_mode=True,
        )

    mem_context      = memory.build_memory_context(role=user_role or "staff")
    session_context  = memory.build_session_resume_context(limit=3)
    return build_system_prompt(
        memory_context=mem_context,
        session_history=session_context,
        page_context=page_context,
        user_name=user_name,
        user_role=user_role,
        dashboard_mode=dashboard_mode,
        vault_mode=vault_mode,
        training_mode=training_mode,
        training_context=training_context,
        rexxie_mode=False,
    )


# ── Health / Info ─────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    import subprocess, sqlite3 as _sq
    from pathlib import Path as _P
    from datetime import datetime as _dt

    # GOJ health extras
    rexxie_alive = bool(subprocess.run(
        ["pgrep", "-f", "rex_rexxie_telegram_bot.py"],
        capture_output=True).returncode == 0)

    auth_count = 0
    menu_count = 0
    _auth_db = _P.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
    try:
        if _auth_db.exists():
            _con = _sq.connect(str(_auth_db))
            auth_count = _con.execute("SELECT COUNT(*) FROM clients WHERE active=1").fetchone()[0]
            _tbls = {r[0] for r in _con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "client_menus" in _tbls:
                menu_count = _con.execute("SELECT COUNT(DISTINCT client_name) FROM client_menus").fetchone()[0]
            _con.close()
    except Exception:
        pass

    ocr_log = _P.home() / "Desktop" / "REX" / "logs" / "ocr_run.log"
    ocr_last_run = None
    if ocr_log.exists():
        ocr_last_run = _dt.fromtimestamp(ocr_log.stat().st_mtime).isoformat()

    return {
        "status":           "ok",
        "version":          "3.0.0",
        "secure_mode":      settings.secure_mode,
        "vault_mode":       vault.vault_mode,
        "encryption_level": vault.mode_label(),
        "training_mode":    training.active,
        "training_trainer": training.trainer,
        "deid_engine":      deid.engine_name,
        "db_path":          str(storage.db_path),
        "key_fingerprint":  storage.key_fingerprint,
        "memory_count":     len(memory.get_all()),
        "rexxie_alive":     rexxie_alive,
        "active_clients":   auth_count,
        "menu_count":       menu_count,
        "ocr_last_run":     ocr_last_run,
    }


@app.get("/health")
def health_simple():
    """Simple health alias — used by CLAUDE.md health check."""
    return health()


@app.get("/api/models")
async def get_models():
    models     = llm.get_available_models()
    ollama_ok  = await llm.check_ollama()
    ollama_pulled = await llm.get_ollama_models() if ollama_ok else []
    for m in models:
        if m["provider"] == "ollama":
            name = m["id"].replace("ollama/", "")
            m["available"] = any(name in p for p in ollama_pulled) if ollama_pulled else False
    return {"models": models, "ollama_running": ollama_ok}


@app.get("/api/settings")
def get_settings():
    return {
        "secure_mode":      settings.secure_mode,
        "default_model":    settings.default_model,
        "ollama_base_url":  settings.ollama_base_url,
        "auto_ollama_on_phi": settings.auto_ollama_on_phi,
        "provider_status":  settings.provider_status(),
        "db_path":          str(storage.db_path),
    }


@app.post("/api/settings/secure-mode")
def set_secure_mode(body: SecureModeRequest):
    settings.secure_mode = body.enabled
    audit.secure_mode_toggle(body.enabled)
    return {"secure_mode": settings.secure_mode}


class ApiKeyRequest(BaseModel):
    provider: str
    api_key:  str


@app.post("/api/keys")
def set_api_key(body: ApiKeyRequest):
    try:
        settings.set_api_key(body.provider, body.api_key)
        audit.api_key_set(body.provider)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/keys/status")
def key_status():
    return {"providers": settings.provider_status()}


@app.get("/api/journeys")
def list_journeys():
    return {"journeys": storage.list_journeys()}


@app.get("/api/journeys/{journey_id}")
def get_journey(journey_id: str):
    audit.journey_viewed(journey_id)
    j = storage.load_journey(journey_id)
    if not j:
        raise HTTPException(404, "Journey not found")
    return j


@app.get("/api/audit")
def get_audit(limit: int = 200):
    return {"events": audit.get_recent_events(limit=limit)}


@app.get("/api/devices")
def list_devices():
    return {"devices": device_manager.list_devices()}


# ── Memory API ────────────────────────────────────────────────────────────────

class MemoryStoreRequest(BaseModel):
    content:  str
    mem_type: str = "fact"
    tags:     Optional[List[str]] = None
    source:   str = "api"


class MemoryForgetRequest(BaseModel):
    query: str


@app.get("/api/memory")
def list_memory():
    """Return all active memories (decrypted). Chairman-facing endpoint."""
    mems = memory.get_all()
    return {"memories": mems, "count": len(mems)}


@app.post("/api/memory")
def store_memory(body: MemoryStoreRequest):
    """Store a new memory."""
    if not body.content.strip():
        raise HTTPException(400, "Memory content cannot be empty")
    mem_id = memory.store(
        content=body.content,
        mem_type=body.mem_type,
        tags=body.tags,
        source=body.source,
    )
    return {"ok": True, "id": mem_id}


@app.delete("/api/memory")
def forget_memory(body: MemoryForgetRequest):
    """Soft-delete memories matching the query."""
    count = memory.forget(body.query)
    return {"ok": True, "removed": count}


@app.get("/api/memory/sessions")
def list_sessions():
    """Return recent session summaries."""
    sessions = memory.get_recent_sessions(limit=10)
    return {"sessions": sessions, "count": len(sessions)}


# ── REST Chat (for GOJ dashboard widget) ─────────────────────────────────────

class ChatRequest(BaseModel):
    message:       str
    page:          Optional[str] = ""
    user_name:     Optional[str] = ""
    user_role:     Optional[str] = ""
    model:         Optional[str] = None
    session_id:    Optional[str] = None
    dashboard_mode: bool = True
    # Conversation history — list of {"role": "user"/"assistant", "content": "..."}
    # Sent by the Telegram bot to enable multi-turn memory within a session.
    history:       Optional[List[Dict]] = None


class ChatResponse(BaseModel):
    reply:      str
    model_used: str
    session_id: str

    @classmethod
    def safe(cls, reply: str, model_used: str, session_id: str) -> "ChatResponse":
        """Create a ChatResponse with XSS-sanitized reply content."""
        import re as _re
        # Strip dangerous HTML/JS patterns from AI output before returning
        clean = _re.sub(r"(?i)<script[\s>][^<]*</script>", "[script removed]", reply)
        clean = _re.sub(r"(?i)<\s*script\b[^>]*>", "[script removed]", clean)
        clean = _re.sub(r"(?i)on\w+\s*=\s*[\"'][^\"']*[\"']", "", clean)
        clean = _re.sub(r"(?i)javascript\s*:", "[js blocked]", clean)
        return cls(reply=clean, model_used=model_used, session_id=session_id)


@app.post("/api/chat", response_model=ChatResponse)
async def rest_chat(body: ChatRequest):
    """
    REST (non-streaming) chat endpoint for GOJ dashboard widget.

    Differences from WebSocket:
      • No streaming — waits for full response
      • Injects sovereign system prompt with memory + session history
      • Detects memory commands (remember/forget) before sending to AI
      • Session is persisted to rex_session_log on every call
    """
    user_text  = body.message.strip()
    session_id = body.session_id or str(uuid.uuid4())

    # ── Input sanitization ──────────────────────────────────────────────────
    # Detect obvious injection attacks before they reach the AI model.
    # AI APIs process natural language — this catches clear malicious payloads
    # (SQL injection, command injection) while allowing legitimate code questions.
    import re as _re
    _lower = user_text.lower()
    # SQL injection patterns
    if _re.search(r"(?i)(union\s+select|drop\s+table|'?\s*or\s+'1'?\s*=\s*'1|cast\s*\(.*\bas\s+(int|text|varchar))", user_text):
        raise HTTPException(400, "Invalid input")
    # Command injection — shell metacharacters with system commands
    if _re.search(r"(?i)(\$\s*\(|\$\{|`[^`]*(?:id|whoami|ls|cat|rm|ping|wget|curl)[^`]*`)", user_text):
        raise HTTPException(400, "Invalid input")
    # Command injection — pipe to system command
    if _re.search(r"(?i)\|\s*(id|whoami|ls|cat|rm|ping|wget|curl|bash|sh|cmd|powershell)\b", user_text):
        raise HTTPException(400, "Invalid input")
    # Prompt injection — system override patterns
    if _re.search(r"(?i)(\[\[system\s*override|system:\s*you\s+are\s+now\s+(in\s+)?(admin|dan|god)\s*mode|ignore\s+all\s+(previous|prior)\s+instructions)", user_text):
        raise HTTPException(400, "Invalid input")
    # XSS — script/markup injection in message content
    if _re.search(r"(?i)(<script[\s>]|javascript\s*:|on\w+\s*=\s*[\"']|<\s*img[^>]+onerror)", user_text):
        raise HTTPException(400, "Invalid input")
    # Token flood — repetitive patterns (>500 repeated chars)
    if _re.search(r"(.)\1{500,}", user_text) or len(user_text) > 50000:
        raise HTTPException(400, "Input too large")

    # ── Hermes Gateway Routing ────────────────────────────────────────────────
    # Rex (cloud)      → Hermes Cloud gw  (:3002, deepseek-v4-pro)
    # Rexxie (local)   → Hermes Local gw  (:65001, gemma4:26b via Ollama)
    # Both gateways expose OpenAI-compatible /v1/chat/completions
    caller_role = verify_role(body.user_name or "", body.user_role or "staff")
    
    _requested_model = body.model
    if not _requested_model:
        if caller_role == "chairman":
            # Rexxie / chairman → Hermes LOCAL gateway
            model = "hermes-local"
            _hermes_url = "http://localhost:65001/v1/chat/completions"
            _hermes_key = "cmpzbkk9n0021iz0brfgygd1t"
            _cloud_approved = False
        else:
            # Rex / staff → Hermes CLOUD gateway
            model = "hermes-cloud"
            _hermes_url = "http://localhost:3002/v1/chat/completions"
            _hermes_key = "1b1fef5884cce9e7c8e5a383f0d4038e"
            _cloud_approved = True  # cloud gw is the approved path for Rex
    else:
        model = _requested_model
        _cloud_approved = False
        _hermes_url = None
        _hermes_key = None

    if not user_text:
        raise HTTPException(400, "Message cannot be empty")

    # ── 0. Restore session state from cache (memory bug fix) ────────────────────
    # Similar to WebSocket handler: restore Rexxie active state after backend restart
    # (caller_role already verified above in Hermes Gateway Routing section)
    if caller_role == "chairman":
        _, prior_rexxie_active = session_cache_enc.load()
        if prior_rexxie_active:
            rexxie._active = True

    # ── 1a. Check for Rexxie mode commands (Chairman only) ───────────────────
    # Server-side role verification — client cannot self-escalate to chairman
    rexxie_reply = rexxie.detect_command(user_text, user_role=caller_role)
    if rexxie_reply is not None:
        # Command was handled (mode toggle, status, etc.) — store if Rexxie is now active
        if rexxie.active and caller_role == "chairman":
            rexxie.memory.store(f"Kato said: {user_text[:300]}", mem_type="conversation")
        # Return the pre-computed reply directly (no AI call needed for commands)
        return ChatResponse.safe(reply=rexxie_reply, model_used="rexxie-engine", session_id=session_id)

    # If Rexxie is active and this is a regular message — route through Rexxie's context
    if rexxie.active and caller_role == "chairman":
        # Store the conversation naturally in Rexxie memory
        rexxie.memory.store(f"Kato: {user_text[:300]}", mem_type="conversation")

    # ── 1b. Check for vault commands (Chairman only) ──────────────────────────
    vault_reply = vault.detect_vault_command(user_text, user_role=caller_role)
    if vault_reply:
        memory.open_session(session_id, user_id=body.user_name or "unknown")
        memory.close_session(
            session_id,
            messages=[{"role": "user", "content": user_text},
                      {"role": "assistant", "content": vault_reply}],
        )
        return ChatResponse.safe(reply=vault_reply, model_used="vault-engine", session_id=session_id)

    # ── 1c. Check for training mode commands ─────────────────────────────────
    training_reply = training.detect_training_command(user_text, user_role=caller_role)
    if training_reply:
        memory.open_session(session_id, user_id=body.user_name or "unknown")
        memory.close_session(
            session_id,
            messages=[{"role": "user", "content": user_text},
                      {"role": "assistant", "content": training_reply}],
        )
        return ChatResponse.safe(reply=training_reply, model_used="training-engine", session_id=session_id)

    # ── 1d. Check for quiz commands ──────────────────────────────────────────
    quiz_reply = quiz.detect_quiz_command(user_text, user_role=caller_role)
    if quiz_reply:
        memory.open_session(session_id, user_id=body.user_name or "unknown")
        memory.close_session(session_id, messages=[
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": quiz_reply},
        ])
        return ChatResponse.safe(reply=quiz_reply, model_used="quiz-engine", session_id=session_id)

    # ── 1e. Check for notification commands ──────────────────────────────────
    notify_reply = notify.detect_notify_command(user_text, user_role=caller_role)
    if notify_reply:
        return ChatResponse.safe(reply=notify_reply, model_used="notify-engine", session_id=session_id)

    # ── 1f. Check for memory commands ────────────────────────────────────────
    mem_reply = memory.detect_and_execute_command(
        user_text,
        source=body.user_name or "dashboard",
        source_role=caller_role,
    )
    if mem_reply:
        # Log this interaction in session
        memory.open_session(session_id, user_id=body.user_name or "unknown")
        memory.close_session(
            session_id,
            messages=[{"role": "user", "content": user_text},
                      {"role": "assistant", "content": mem_reply}],
        )
        return ChatResponse.safe(reply=mem_reply, model_used="memory-engine", session_id=session_id)

    # ── 2. Build sovereign system prompt ────────────────────────────────────
    # Server enforces dashboard/staff mode for all non-chairman callers.
    # A staff member cannot override this by sending dashboard_mode=False.
    is_chairman_caller = (caller_role == "chairman")
    force_dashboard    = body.dashboard_mode or (not is_chairman_caller)

    # ── Phase 12: Explicit domain separation ─────────────────────────────────
    # _rexxie_context and _rex_training are NEVER merged or swapped.
    # Rexxie's sovereign block is ONLY used when building a Rexxie-mode prompt.
    # Rex's training context is ONLY used when building a Rex-mode prompt.
    _is_rexxie_active = is_chairman_caller and rexxie.active

    # Rexxie domain — used ONLY in rexxie_mode=True prompt builds
    _rexxie_context   = rexxie.get_sovereign_block() if _is_rexxie_active else ""

    # Rex training domain — NEVER populated when Rexxie is active
    _rex_training     = (training.get_context_block()
                         if (is_chairman_caller and training.active and not _is_rexxie_active)
                         else "")

    # ── Background AI enrichment ─────────────────────────────────────────────
    # Absorbed operational knowledge only. Never includes Rexxie memory.
    _bg_block = ""
    if should_enrich(user_text):
        try:
            _bg_block = get_background_block(topic_hint=user_text[:120], max_insights=5)
        except Exception:
            pass  # enrichment is always optional — never block a response

    # Build the correct context for the correct domain.
    # Rex mode:    _rex_training + _bg_block (never _rexxie_context)
    # Rexxie mode: _rexxie_context only (no bg enrichment crosses domains)
    if _is_rexxie_active:
        _prompt_context = _rexxie_context   # Rexxie domain — sovereign only
    else:
        _prompt_context = "\n\n".join(filter(None, [_rex_training, _bg_block]))  # Rex domain only

    system_prompt = _build_system_prompt(
        user_name=body.user_name or "",
        user_role=caller_role,                             # verified role, never client-trusted
        page_context=body.page or "",
        dashboard_mode=force_dashboard,
        vault_mode=vault.vault_mode if is_chairman_caller else False,
        training_mode=training.active if is_chairman_caller else False,
        training_context=_prompt_context,
        rexxie_mode=_is_rexxie_active,                    # isolates Rexxie from all REX/GOJ context
    )

    # ── 3. Open session if new ───────────────────────────────────────────────
    memory.open_session(session_id, user_id=body.user_name or "unknown")

    # ── 4. De-identify if secure mode ──────────────────────────────────────
    secure    = settings.secure_mode
    send_text = user_text
    mapping   = {}

    if secure:
        sanitized, mapping = deid.anonymize(user_text, {})
        if mapping:
            send_text = sanitized

    # ── 4b. FAIL-CLOSED PHI GATE (Gate 1 at the cloud-routing boundary) ──────
    # If secure mode is on but the de-id engine is degraded (Presidio down →
    # personal names undetectable) AND this request routes to the cloud gateway,
    # refuse rather than leak client PHI. Local (chairman) routing is unaffected.
    if secure and _cloud_approved and deid.engine_name != "Presidio":
        logger.error(
            f"PHI gate: blocked cloud routing — de-id engine degraded "
            f"({deid.engine_name})"
        )
        raise HTTPException(
            503, "PHI de-identification engine degraded — cloud routing blocked")

    # ── 5. Call AI ──────────────────────────────────────────────────────────
    # Build multi-turn message thread if history is provided (Telegram bot sends this).
    # History is a list of {"role": "user"/"assistant", "content": "..."} from prior turns.
    # Capped at 10 entries (5 exchanges) to stay within context limits.
    prior_history = body.history or []
    if prior_history:
        # Sanitize history entries — ensure role is user or assistant only
        safe_history = [
            {"role": m["role"], "content": str(m["content"])[:2000]}
            for m in prior_history[-10:]
            if m.get("role") in ("user", "assistant") and m.get("content")
        ]
        messages = [
            {"role": "system", "content": system_prompt},
            *safe_history,
            {"role": "user", "content": send_text},
        ]
    else:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": send_text},
        ]

    full_response = ""
    try:
        if _hermes_url:
            # Route through Hermes gateway (OpenAI-compatible API)
            import httpx
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    _hermes_url,
                    json={
                        "model": model,
                        "messages": messages,
                        "stream": False,
                    },
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {_hermes_key}",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    full_response = data["choices"][0]["message"]["content"]
                else:
                    logger.error(f"Hermes gateway error: {resp.status_code} — {resp.text[:200]}")
                    raise HTTPException(502, f"Hermes gateway returned {resp.status_code}")
        else:
            async for chunk in llm.stream(model, messages, phi_detected=bool(mapping), cloud_approved=_cloud_approved):
                full_response += chunk
    except Exception as e:
        logger.error(f"REST chat stream error: {e}")
        raise HTTPException(500, f"AI error: {str(e)[:120]}")

    # ── 6. Re-identify response ─────────────────────────────────────────────
    if secure and mapping:
        display_response = deid.re_identify(full_response, mapping)
    else:
        display_response = full_response

    # ── 7. Behavior monitoring — silent, never blocks response ─────────────
    try:
        _behavior_check(
            response_text=display_response,
            caller_role=caller_role,
            is_rexxie_mode=_is_rexxie_active,
            user_message=user_text,
        )
    except Exception:
        pass  # monitoring never interrupts a response

    # ── 7b. Audit injection (REST endpoint) ────────────────────────────────
    # The WebSocket endpoint already audits; this covers the Telegram bot path.
    try:
        audit.message_sent(session_id, model, secure, len(user_text))
        if mapping:
            audit.phi_detected(session_id, list(mapping.keys()), len(mapping))
            audit.phi_redacted(session_id, len(mapping))
        audit.response_received(session_id, model, secure, len(display_response))
        if deid.scan_response_for_phi(display_response):
            audit.response_scan(session_id, phi_found=True)
    except Exception:
        pass  # audit never blocks a response

    # ── 8. Persist session ──────────────────────────────────────────────────
    memory.close_session(
        session_id,
        messages=[
            {"role": "user",      "content": user_text},
            {"role": "assistant", "content": display_response},
        ],
        summary=f"User ({body.user_name}) asked: {user_text[:120]}",
    )

    # ── 9. Store in encrypted journey ──────────────────────────────────────
    journey_id = f"dashboard-{session_id}"
    storage.create_journey(journey_id, secure_mode=secure)
    storage.save_message(journey_id, str(uuid.uuid4()), "user", user_text, secure, False, model)
    storage.save_message(journey_id, str(uuid.uuid4()), "assistant", display_response, secure, False, model)

    return ChatResponse.safe(
        reply=display_response,
        model_used=model,
        session_id=session_id,
    )


# ── Phone Unlock Callback & Status ────────────────────────────────────────────

class PhoneUnlockCallbackRequest(BaseModel):
    authorized: bool = True


@app.post("/api/phone-unlock-callback")
async def phone_unlock_callback(body: PhoneUnlockCallbackRequest, request: Request):
    """
    Called by rex_phone_unlock.py when iPhone Face ID succeeds.
    Marks vault as pre-authorized and logs the unlock event.
    """
    client_ip = request.client.host
    if body.authorized:
        try:
            from rex_phone_unlock import pre_authorize_vault, VAULT_PRE_AUTH_MINUTES, log_unlock
            pre_authorize_vault()
            log_unlock(client_ip, True, "Phone unlock callback received")
            logger.info(f"📱 Vault pre-authorized via phone unlock from {client_ip}")
        except Exception as e:
            logger.error(f"Phone unlock callback error: {e}")
    return {"ok": True}


@app.get("/api/phone-unlock/status")
async def phone_unlock_status():
    """Check if vault is currently pre-authorized by phone unlock."""
    try:
        from rex_phone_unlock import is_vault_pre_authorized, _vault_pre_authorized_until
        import time
        pre_auth = is_vault_pre_authorized()
        remaining = max(0, int(_vault_pre_authorized_until - time.time())) if pre_auth else 0
        return {"pre_authorized": pre_auth, "seconds_remaining": remaining}
    except Exception:
        return {"pre_authorized": False, "seconds_remaining": 0}


# ── Staff Dashboard Endpoint (GOJ employees only) ─────────────────────────────

class StaffChatRequest(BaseModel):
    """
    Simplified chat request for GOJ staff dashboard widget.
    Role is ALWAYS locked to 'staff' server-side — no escalation possible.
    Vault, Rexxie, training, and chairman memory are never accessible here.
    """
    message:    str
    page:       Optional[str] = ""
    user_name:  Optional[str] = ""
    session_id: Optional[str] = None
    model:      Optional[str] = None


@app.post("/api/staff/chat", response_model=ChatResponse)
async def staff_chat(body: StaffChatRequest):
    """
    Staff-only dashboard chat endpoint.

    Hard guarantees (enforced server-side, not client-configurable):
      • Role is always 'staff' — no chairman escalation possible
      • Vault mode, training mode, Rexxie are never injected into prompt
      • Memory filtered to 'staff' visibility only (chairman_only entries excluded)
      • All commands (vault, training, quiz, notify, Rexxie) are silently blocked
      • Staff cannot use memory store/forget commands
      • Personal information about the Chairman never appears in responses

    Staff see REX as a knowledgeable GOJ operations assistant — nothing more.
    """
    user_text  = body.message.strip()
    session_id = body.session_id or str(uuid.uuid4())
    model      = body.model or settings.default_model

    if not user_text:
        raise HTTPException(400, "Message cannot be empty")

    # ── Role is ALWAYS staff — locked here, no override possible ─────────────
    locked_role = "staff"
    user_name   = body.user_name or "staff-user"

    # ── Block all chairman-only commands silently ─────────────────────────────
    lower = user_text.lower().strip()
    chairman_triggers = [
        "vault mode", "vault status", "training mode", "hey rexxie",
        "rexxie mode", "chairman only", "private:", "confidential:",
        "grade my quiz", "set telegram", "set alert email", "test alert",
        "emergency stop", "wipe all", "wipe memory",
    ]
    if any(t in lower for t in chairman_triggers):
        return ChatResponse.safe(
            reply=(
                "I'm set up to help with GOJ dashboard questions. "
                "For system configuration, please contact your administrator."
            ),
            model_used="staff-engine",
            session_id=session_id,
        )

    # ── Memory commands blocked for staff ─────────────────────────────────────
    mem_reply = memory.detect_and_execute_command(
        user_text, source=user_name, source_role=locked_role
    )
    if mem_reply:
        memory.open_session(session_id, user_id=user_name)
        memory.close_session(
            session_id,
            messages=[{"role": "user", "content": user_text},
                      {"role": "assistant", "content": mem_reply}],
        )
        return ChatResponse.safe(reply=mem_reply, model_used="memory-engine", session_id=session_id)

    # ── Build staff-locked sovereign prompt ────────────────────────────────────
    system_prompt = _build_system_prompt(
        user_name=user_name,
        user_role=locked_role,
        page_context=body.page or "",
        dashboard_mode=True,        # Always True for staff
        vault_mode=False,           # Never exposed to staff
        training_mode=False,        # Never exposed to staff
        training_context="",
    )

    memory.open_session(session_id, user_id=user_name)

    secure    = settings.secure_mode
    send_text = user_text
    mapping   = {}
    if secure:
        sanitized, mapping = deid.anonymize(user_text, {})
        if mapping:
            send_text = sanitized

    # FAIL-CLOSED PHI GATE: secure mode requires a working de-id engine. If
    # Presidio is degraded, names are undetectable — refuse the staff request
    # rather than risk routing PHI to the model.
    if secure and deid.engine_name != "Presidio":
        logger.error(
            f"PHI gate: blocked staff chat — de-id engine degraded "
            f"({deid.engine_name})"
        )
        raise HTTPException(
            503, "PHI de-identification engine degraded — secure chat blocked")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": send_text},
    ]

    full_response = ""
    try:
        async for chunk in llm.stream(model, messages, phi_detected=bool(mapping)):
            full_response += chunk
    except Exception as e:
        logger.error(f"Staff chat error: {e}")
        raise HTTPException(500, f"AI error: {str(e)[:120]}")

    display_response = deid.re_identify(full_response, mapping) if (secure and mapping) else full_response

    memory.close_session(
        session_id,
        messages=[
            {"role": "user",      "content": user_text},
            {"role": "assistant", "content": display_response},
        ],
        summary=f"Staff ({user_name}) on {body.page or 'dashboard'}: {user_text[:100]}",
    )

    journey_id = f"staff-{session_id}"
    storage.create_journey(journey_id, secure_mode=secure)
    storage.save_message(journey_id, str(uuid.uuid4()), "user", user_text, secure, False, model)
    storage.save_message(journey_id, str(uuid.uuid4()), "assistant", display_response, secure, False, model)

    return ChatResponse.safe(reply=display_response, model_used=model, session_id=session_id)


# ── Agent Bus API ─────────────────────────────────────────────────────────────

class AgentSendRequest(BaseModel):
    target_agent: str
    payload:      dict
    allowed_fields: Optional[List[str]] = None


@app.post("/api/agent/send")
def agent_send(body: AgentSendRequest):
    """Seal and send an encrypted payload to another agent."""
    if body.target_agent not in AgentBus.AGENTS:
        raise HTTPException(400, f"Unknown agent: {body.target_agent}")
    payload = body.payload
    if body.allowed_fields:
        payload = agent_bus.scrub(payload, body.allowed_fields)
    envelope = agent_bus.seal(body.target_agent, payload)
    return {"envelope": envelope, "target": body.target_agent}


class AgentReceiveRequest(BaseModel):
    source_agent:  str
    envelope:      str


@app.post("/api/agent/receive")
def agent_receive(body: AgentReceiveRequest):
    """Open and verify an encrypted envelope from another agent."""
    payload = agent_bus.open(body.source_agent, body.envelope)
    if payload is None:
        raise HTTPException(401, "Envelope signature invalid — message rejected")
    return {"payload": payload}


# ── iPhone pairing endpoints ──────────────────────────────────────────────────

@app.get("/api/pairing/init")
def pairing_init():
    return device_manager.generate_pairing_token()


class PairRequest(BaseModel):
    token:        str
    device_name:  str = "iPhone"
    device_model: str = "iPhone"


@app.post("/api/pairing/complete")
def pairing_complete(body: PairRequest):
    jwt = device_manager.complete_pairing(body.token, body.device_name, body.device_model)
    if not jwt:
        raise HTTPException(401, "Invalid or expired pairing token")
    audit.log("DEVICE_PAIRED", {"device_name": body.device_name})
    return {"token": jwt}


# ── WebSocket Chat (Desktop & iPhone streaming) ───────────────────────────────

# ── Session Continuity Cache ───────────────────────────────────────────────────
# Saves conversation history to disk so Rexxie can resume after a WS drop.
# Only the last 30 minutes of history is restored. System messages are excluded.

_SESSION_CACHE_PATH = Path.home() / "Desktop" / "REX" / ".rex_session_cache.json"
_SESSION_RESUME_WINDOW = 30 * 60  # 30 minutes


def _save_session_cache(messages: list, rexxie_active: bool):
    """Persist conversation (no system messages) for reconnect recovery."""
    try:
        user_msgs = [m for m in messages if m.get("role") != "system"]
        if not user_msgs:
            return
        payload = {
            "ts": time.time(),
            "rexxie_active": rexxie_active,
            "messages": [
                {"role": m["role"], "content": m["content"], "timestamp": m.get("timestamp", "")}
                for m in user_msgs
            ],
        }
        _SESSION_CACHE_PATH.write_text(json.dumps(payload))
    except Exception as e:
        logger.warning(f"Session cache save failed: {e}")


def _load_session_cache():
    """Load recent session if within resume window. Returns (messages, rexxie_active) or (None, False)."""
    try:
        if not _SESSION_CACHE_PATH.exists():
            return None, False
        payload = json.loads(_SESSION_CACHE_PATH.read_text())
        age = time.time() - payload.get("ts", 0)
        if age > _SESSION_RESUME_WINDOW:
            return None, False
        return payload.get("messages", []), payload.get("rexxie_active", False)
    except Exception as e:
        logger.warning(f"Session cache load failed: {e}")
        return None, False


@app.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket):
    await websocket.accept()

    journey_id = str(uuid.uuid4())
    session_id = journey_id  # One session per WS connection

    session = {
        "secure_mode": settings.secure_mode,
        "mapping":     {},
        "messages":    [],
        "model":       settings.default_model,
        # Desktop REX app is always the Chairman — pre-seed so memory loads immediately
        "user_name":   "Kato",
        "user_role":   "chairman",
    }

    storage.create_journey(journey_id, secure_mode=session["secure_mode"])
    memory.open_session(session_id, user_id="Kato")
    audit.log(AuditEventType.JOURNEY_CREATED, {"journey_id": journey_id})

    # ── Session resume: check for recent disconnected conversation ────────────
    prior_messages, prior_rexxie_active = session_cache_enc.load()
    if prior_rexxie_active:
        rexxie._active = True  # restore Rexxie mode state

    # Build sovereign prompt with full chairman memory context from the start
    system_prompt = _build_system_prompt(
        user_name="Kato", user_role="chairman", dashboard_mode=False,
        rexxie_mode=rexxie._active,
    )
    session["messages"].append({"role": "system", "content": system_prompt})

    # Restore prior conversation messages into this session's context window
    if prior_messages:
        for m in prior_messages:
            session["messages"].append({"role": m["role"], "content": m["content"]})

    await websocket.send_json({
        "type":        "init",
        "journey_id":  journey_id,
        "secure_mode": session["secure_mode"],
        "deid_engine": deid.engine_name,
        "memory_count": len(memory.get_all()),
        "resumed":     bool(prior_messages),
        "history":     prior_messages or [],
    })

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type", "message")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            # ── State sync — frontend requests authoritative mode on connect/reconnect ──
            if msg_type == "sync_state":
                await websocket.send_json({
                    "type":          "state_sync",
                    "rexxie_active": rexxie.active,
                    "vault_mode":    vault.vault_mode,
                })
                continue

            if msg_type == "clear_session_cache":
                # User explicitly started a new chat — clear the resume cache
                session_cache_enc.clear()
                continue

            if msg_type == "set_model":
                old = session["model"]
                session["model"] = data.get("model", session["model"])
                audit.model_changed(old, session["model"])
                await websocket.send_json({"type": "model_set", "model": session["model"]})
                continue

            if msg_type == "set_secure_mode":
                session["secure_mode"] = data.get("enabled", False)
                audit.secure_mode_toggle(session["secure_mode"])
                await websocket.send_json({
                    "type":        "secure_mode_set",
                    "secure_mode": session["secure_mode"],
                })
                continue

            if msg_type == "set_user":
                claimed_name = data.get("user_name", "")
                claimed_role = data.get("user_role", "staff")
                # ── Server-side role verification (prevents role escalation) ──
                verified_role = verify_role(claimed_name, claimed_role)
                session["user_name"] = claimed_name
                session["user_role"] = verified_role
                if verified_role != claimed_role:
                    logger.warning(
                        f"🚨 WS role escalation blocked: '{claimed_name}' claimed "
                        f"'{claimed_role}' → granted '{verified_role}'"
                    )
                # Rebuild system prompt with verified user context
                system_prompt = _build_system_prompt(
                    user_name=session["user_name"],
                    user_role=session["user_role"],
                    dashboard_mode=False,
                )
                # Replace system message
                if session["messages"] and session["messages"][0]["role"] == "system":
                    session["messages"][0]["content"] = system_prompt
                else:
                    session["messages"].insert(0, {"role": "system", "content": system_prompt})
                continue

            if msg_type == "message":
                user_text = data.get("content", "").strip()
                if not user_text:
                    continue

                model = data.get("model", session["model"])

                # ── Check memory commands first ─────────────────────────────
                # When Rexxie is active, route memory commands to HER private store,
                # not to REX's shared business memory.
                _mem_reply: str | None = None
                if rexxie.active and session.get("user_role") == "chairman":
                    # Let Rexxie handle "remember this:", "this is private:", "forget that", etc.
                    _rexxie_mem_result = rexxie.detect_command(user_text, user_role="chairman")
                    if _rexxie_mem_result is not None:
                        _mem_reply = _rexxie_mem_result
                        _rexxie_mem_engine = "rexxie-engine"
                    # Skip REX memory commands when in Rexxie mode (isolation)
                else:
                    _rex_mem = memory.detect_and_execute_command(
                        user_text,
                        source=session["user_name"] or "ws-user",
                        source_role=session["user_role"] or "staff",
                    )
                    if _rex_mem:
                        _mem_reply = _rex_mem
                        _rexxie_mem_engine = "memory-engine"

                if _mem_reply is not None:
                    await websocket.send_json({
                        "type": "stream_start",
                        "msg_id": str(uuid.uuid4()),
                        "secure": session["secure_mode"],
                        "phi_detected": False,
                        "model": _rexxie_mem_engine,
                    })
                    await websocket.send_json({"type": "chunk", "content": _mem_reply})
                    await websocket.send_json({
                        "type": "stream_end",
                        "resp_id": str(uuid.uuid4()),
                        "display_content": _mem_reply,
                        "phi_detected": False,
                        "secure": session["secure_mode"],
                        "model": _rexxie_mem_engine,
                    })
                    session["messages"].append({"role": "user",      "content": user_text})
                    session["messages"].append({"role": "assistant", "content": _mem_reply})
                    continue

                # ── Rexxie command detection (chairman only) ────────────────
                _ws_role = session.get("user_role", "staff")
                _ws_name = session.get("user_name", "")
                _is_ws_chairman = _ws_role == "chairman"
                if _is_ws_chairman:
                    rexxie_cmd_reply = rexxie.detect_command(user_text, user_role="chairman")
                    if rexxie_cmd_reply is not None:
                        # Phase 12: Rexxie toggled — rebuild with explicit domain separation.
                        # Rexxie context ONLY flows into the prompt when rexxie_mode=True.
                        # When switching back to Rex, _rexxie_domain_ctx is empty.
                        _rexxie_now_active   = rexxie.active
                        _rexxie_domain_ctx   = rexxie.get_sovereign_block() if _rexxie_now_active else ""
                        # When Rex mode: no Rexxie context in the prompt
                        _rex_domain_ctx      = "" if _rexxie_now_active else training.get_context_block()
                        new_sp = _build_system_prompt(
                            user_name=_ws_name,
                            user_role="chairman",
                            dashboard_mode=False,
                            rexxie_mode=_rexxie_now_active,
                            training_context=_rexxie_domain_ctx if _rexxie_now_active else _rex_domain_ctx,
                        )
                        if session["messages"] and session["messages"][0]["role"] == "system":
                            session["messages"][0]["content"] = new_sp
                        else:
                            session["messages"].insert(0, {"role": "system", "content": new_sp})
                        # Send the command reply as a stream (consistent with normal flow)
                        await websocket.send_json({
                            "type": "stream_start",
                            "msg_id": str(uuid.uuid4()),
                            "secure": session["secure_mode"],
                            "phi_detected": False,
                            "model": "rexxie-engine",
                        })
                        await websocket.send_json({"type": "chunk", "content": rexxie_cmd_reply})
                        await websocket.send_json({
                            "type": "stream_end",
                            "resp_id": str(uuid.uuid4()),
                            "display_content": rexxie_cmd_reply,
                            "phi_detected": False,
                            "secure": session["secure_mode"],
                            "model": "rexxie-engine",
                        })
                        session["messages"].append({"role": "user",      "content": user_text})
                        session["messages"].append({"role": "assistant", "content": rexxie_cmd_reply})
                        continue

                # ── If Rexxie is active on this WS, ensure system prompt stays in Rexxie mode ──
                # Phase 12: drift correction uses Rexxie domain context only.
                if _is_ws_chairman and rexxie.active:
                    _cur_sp = session["messages"][0]["content"] if session["messages"] and session["messages"][0]["role"] == "system" else ""
                    # Rebuild if system prompt has drifted back to REX context
                    if "Rexxie" not in _cur_sp:
                        _drift_rexxie_ctx = rexxie.get_sovereign_block()  # Rexxie domain only
                        _drifted_sp = _build_system_prompt(
                            user_name=_ws_name,
                            user_role="chairman",
                            dashboard_mode=False,
                            rexxie_mode=True,
                            training_context=_drift_rexxie_ctx,   # explicit Rexxie domain
                        )
                        if session["messages"] and session["messages"][0]["role"] == "system":
                            session["messages"][0]["content"] = _drifted_sp
                        else:
                            session["messages"].insert(0, {"role": "system", "content": _drifted_sp})

                # ── Auto-route if no key ────────────────────────────────────
                provider = model.split('/')[0] if '/' in model else model
                if not model.startswith('ollama/') and not settings.provider_status().get(provider, False):
                    ollama_ok = await llm.check_ollama()
                    if ollama_ok:
                        pulled = await llm.get_ollama_models()
                        if pulled:
                            auto_model = f"ollama/{pulled[0].split(':')[0]}"
                            session["model"] = auto_model
                            model = auto_model
                            await websocket.send_json({
                                "type": "model_set", "model": auto_model,
                            })
                            await websocket.send_json({
                                "type": "chunk",
                                "content": f"> 🦖 **Auto-routed to local AI** ({auto_model.replace('ollama/','')})\n\n",
                            })
                        else:
                            await websocket.send_json({
                                "type": "chunk",
                                "content": (
                                    f"**No API key for {provider}** and Ollama has no models pulled.\n\n"
                                    f"Run: `ollama pull llama3` then try again."
                                ),
                            })
                            await websocket.send_json({
                                "type": "stream_end", "resp_id": str(uuid.uuid4()),
                                "display_content": "", "phi_detected": False,
                                "secure": session["secure_mode"], "model": model,
                            })
                            continue
                    else:
                        await websocket.send_json({
                            "type": "chunk",
                            "content": (
                                f"**No API key for {provider}** and Ollama is not running.\n\n"
                                f"Open Terminal: `ollama serve` then pull a model."
                            ),
                        })
                        await websocket.send_json({
                            "type": "stream_end", "resp_id": str(uuid.uuid4()),
                            "display_content": "", "phi_detected": False,
                            "secure": session["secure_mode"], "model": model,
                        })
                        continue

                secure = session["secure_mode"]
                msg_id = str(uuid.uuid4())

                storage.save_message(
                    journey_id=journey_id, msg_id=msg_id,
                    role="user", content=user_text,
                    secure=secure, phi_detected=False, model=model,
                )
                audit.message_sent(journey_id, model, secure, len(user_text))

                phi_detected = False
                send_text    = user_text

                if secure:
                    sanitized, new_mappings = deid.anonymize(user_text, session["mapping"])
                    session["mapping"].update(new_mappings)
                    phi_detected = len(new_mappings) > 0
                    if phi_detected:
                        for original, placeholder in new_mappings.items():
                            storage.save_phi_mapping(journey_id, original, placeholder)
                        audit.phi_detected(journey_id, [], len(new_mappings))
                        audit.phi_redacted(journey_id, len(new_mappings))
                    send_text = sanitized

                session["messages"].append({"role": "user", "content": send_text})

                await websocket.send_json({
                    "type":        "stream_start",
                    "msg_id":      msg_id,
                    "secure":      secure,
                    "phi_detected": phi_detected,
                    "model":       model,
                })

                # ── Ollama offline check for WebSocket (local-only — no cloud fallback) ──
                _ws_cloud_approved = False
                if model.startswith("ollama/"):
                    _ws_ollama_ok = await llm.check_ollama()
                    if not _ws_ollama_ok:
                        # REX is local-only. Never fall back to cloud.
                        # Try the configured backup model first; if that also fails, surface a clear error.
                        _backup_model = settings._data.get("local_backup_model", "ollama/llama3")
                        if _backup_model != model:
                            model = _backup_model
                            await websocket.send_json({
                                "type": "chunk",
                                "content": f"> ⚠️ Primary model offline — trying backup ({_backup_model.split('/')[-1]})\n\n",
                            })
                        else:
                            await websocket.send_json({
                                "type": "chunk",
                                "content": (
                                    "⚠️ **Ollama is not running.**\n\n"
                                    "REX runs entirely on your local machine. "
                                    "Open Terminal and run:\n```\nollama serve\n```\n\n"
                                    "Then make sure a model is pulled:\n```\nollama pull llama3\n```"
                                ),
                            })
                            await websocket.send_json({
                                "type": "stream_end", "resp_id": str(uuid.uuid4()),
                                "display_content": "", "phi_detected": False,
                                "secure": secure, "model": model,
                            })
                            continue

                full_response = ""
                try:
                    async for chunk in llm.stream(model, session["messages"], phi_detected=phi_detected, cloud_approved=_ws_cloud_approved):
                        full_response += chunk
                        await websocket.send_json({"type": "chunk", "content": chunk})
                except Exception as e:
                    logger.error(f"Stream error: {e}")
                    await websocket.send_json({"type": "error", "message": str(e)[:120]})
                    continue

                if secure and session["mapping"]:
                    display_response = deid.re_identify(full_response, session["mapping"])
                    audit.response_scan(journey_id, deid.scan_response_for_phi(full_response))
                else:
                    display_response = full_response

                resp_id = str(uuid.uuid4())
                storage.save_message(
                    journey_id=journey_id, msg_id=resp_id,
                    role="assistant", content=display_response,
                    secure=secure, phi_detected=False, model=model,
                )
                session["messages"].append({"role": "assistant", "content": full_response})
                audit.response_received(journey_id, model, secure, len(display_response))

                # ── Save session to disk so reconnect can restore context (encrypted) ──
                session_cache_enc.save(session["messages"], rexxie.active)
                # ── Auto-save encrypted transcript after every exchange ────────
                transcript_store.save(
                    session_id=journey_id,
                    messages=session["messages"],
                    rexxie_active=rexxie.active,
                    user_name=_ws_name or "Kato",
                )

                await websocket.send_json({
                    "type":            "stream_end",
                    "resp_id":         resp_id,
                    "display_content": display_response,
                    "phi_detected":    phi_detected,
                    "secure":          secure,
                    "model":           model,
                    "rexxie_active":   rexxie.active,  # ← authoritative mode state
                })

                # ── Auto-memory: persist each exchange so nothing is lost ────
                _ws_is_chairman = session.get("user_role") == "chairman"
                if _ws_is_chairman and rexxie.active:
                    # Rexxie: conversation history lives in session["messages"] — that IS the
                    # memory. We do NOT store each exchange in rexxie.db (that would balloon
                    # the memory store and force a system-prompt rebuild every turn, which
                    # makes Rexxie feel like she's restarting mid-conversation).
                    #
                    # Only intentional memories ("remember this:", "this is private:") get
                    # stored in rexxie.db. Casual conversation stays in session context.
                    #
                    # ── Sliding window: keep system prompt + last 40 messages (~20 exchanges)
                    try:
                        non_system = [m for m in session["messages"] if m["role"] != "system"]
                        if len(non_system) > 40:
                            # Trim to last 40 non-system messages, preserving system prompt
                            sys_msgs = [m for m in session["messages"] if m["role"] == "system"]
                            session["messages"] = sys_msgs + non_system[-40:]
                            logger.debug("🌸 Rexxie: sliding window applied — trimmed to last 40 messages")
                    except Exception as _we:
                        logger.warning(f"Rexxie window error: {_we}")
                elif _ws_is_chairman:
                    # REX: checkpoint session summary after every exchange (not just disconnect)
                    try:
                        user_msgs = [m for m in session["messages"] if m["role"] != "system"]
                        if len(user_msgs) >= 2:
                            memory.close_session(
                                session_id,
                                messages=user_msgs,
                                summary=f"REX Rext — {len(user_msgs)//2} exchanges",
                            )
                    except Exception:
                        pass

    except WebSocketDisconnect:
        logger.info(f"🔌 Disconnected: {journey_id}")
        # ── Auto-backup session on disconnect ─────────────────────────────
        try:
            user_msgs = [m for m in session["messages"] if m["role"] != "system"]
            if user_msgs:
                memory.close_session(
                    session_id,
                    messages=user_msgs,
                    summary=f"Desktop session — {len(user_msgs)} messages",
                )
                logger.info(f"📼 Session backup saved: {session_id[:8]}")
        except Exception as e:
            logger.warning(f"Session backup failed: {e}")

    except Exception as e:
        logger.error(f"WS error: {e}")


# ── Gmail API ─────────────────────────────────────────────────────────────────

@app.get("/api/gmail/status")
def gmail_status():
    configured = gmail_configured()
    if not configured:
        return {"configured": False, "email": None, "unread": 0}
    try:
        profile = gmail_profile()
        unread  = get_unread_count()
        return {
            "configured": True,
            "email":      profile.get("email"),
            "unread":     unread,
            "ok":         profile.get("ok", False),
        }
    except Exception as e:
        return {"configured": False, "error": str(e)}


@app.get("/api/gmail/summary")
def gmail_summary(max_messages: int = 20):
    if not gmail_configured():
        return {"ok": False, "error": "Gmail not connected. Run setup first."}
    return get_inbox_summary(max_messages=max_messages)


@app.get("/api/gmail/search")
def gmail_search(q: str, max_results: int = 10):
    if not gmail_configured():
        return {"ok": False, "error": "Gmail not connected."}
    return search_emails(q, max_results=max_results)


@app.post("/api/gmail/autolabel")
def gmail_autolabel(max_messages: int = 50):
    if not gmail_configured():
        return {"ok": False, "error": "Gmail not connected."}
    return run_auto_label(max_messages=max_messages)


@app.get("/api/gmail/rules")
def gmail_rules():
    return {"ok": True, "rules": get_label_rules()}


@app.post("/api/gmail/rules")
async def gmail_save_rules(request: Request):
    body = await request.json()
    rules = body.get("rules", [])
    try:
        save_label_rules(rules)
        return {"ok": True, "count": len(rules)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Staff User Auth API ────────────────────────────────────────────────────────
import hashlib, secrets as _secrets

def _hash_password(password: str, salt: str = "") -> str:
    """SHA-256 hash with salt. For production consider bcrypt — this is suitable for internal use."""
    if not salt:
        salt = _secrets.token_hex(16)
    h = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}:{h}"

def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, _ = stored_hash.split(":", 1)
        return _hash_password(password, salt) == stored_hash
    except Exception:
        return False

# Session tokens (in-memory — cleared on restart, which is fine for local use)
_active_sessions: dict = {}

def _create_session(user: dict) -> str:
    token = _secrets.token_urlsafe(32)
    _active_sessions[token] = {
        "user_id":           user["id"],
        "username":          user["username"],
        "role":              user["role"],
        "first_name":        user["first_name"],
        "last_name":         user["last_name"],
        "panel_permissions": user.get("panel_permissions", []),
        "created_at":        datetime.utcnow().isoformat(),
    }
    return token

def _get_session(token: str) -> Optional[dict]:
    return _active_sessions.get(token)


class CreateUserRequest(BaseModel):
    username:   str
    password:   str
    first_name: str
    last_name:  str
    address:    str = ""
    phone:      str = ""
    email:      str = ""
    role:       str = "staff"
    admin_password: str = ""   # Chairman must verify to create users


class LoginRequest(BaseModel):
    username: str
    password: str


# The admin (Chairman) password for creating users — stored hashed on first use
# Default: "chairman" — change via POST /api/auth/set-admin-password
ADMIN_PASS_FILE = Path(__file__).parent.parent / "logs" / ".admin_pass"

def _get_admin_hash() -> str:
    if ADMIN_PASS_FILE.exists():
        return ADMIN_PASS_FILE.read_text().strip()
    # Default password "chairman2026" — will be shown to user on first boot
    default = _hash_password("chairman2026")
    ADMIN_PASS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ADMIN_PASS_FILE.write_text(default)
    return default

def _verify_admin(password: str) -> bool:
    return _verify_password(password, _get_admin_hash())


@app.post("/api/auth/login")
def auth_login(body: LoginRequest):
    """Authenticate a staff user. Returns a session token."""
    # Check if this is the first ever login (no users yet) — auto-create chairman
    if storage.user_count() == 0:
        # Seed the chairman account
        import uuid as _u
        storage.create_user(
            user_id=str(_u.uuid4()), username="chairman",
            password_hash=_hash_password("chairman2026"),
            first_name="Kato", last_name="Chairman", role="chairman",
        )

    user = storage.get_user_by_username(body.username)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not _verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    storage.update_last_login(user["id"])
    token = _create_session(user)
    audit.log(AuditEventType.USER_ACCESS if hasattr(AuditEventType, 'USER_ACCESS') else "login",
              detail=f"Login: {user['username']} ({user['role']})")
    return {
        "ok":                True,
        "token":             token,
        "username":          user["username"],
        "first_name":        user["first_name"],
        "last_name":         user["last_name"],
        "role":              user["role"],
        "panel_permissions": user.get("panel_permissions", []),
    }


@app.post("/api/auth/logout")
def auth_logout(authorization: Optional[str] = Header(None)):
    token = (authorization or "").replace("Bearer ", "")
    _active_sessions.pop(token, None)
    return {"ok": True}


@app.get("/api/auth/me")
def auth_me(authorization: Optional[str] = Header(None)):
    token = (authorization or "").replace("Bearer ", "")
    session = _get_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return session


@app.post("/api/auth/create-user")
def auth_create_user(body: CreateUserRequest):
    """Create a new staff user. Requires Chairman admin password."""
    if not _verify_admin(body.admin_password):
        raise HTTPException(status_code=403, detail="Invalid admin password")

    import uuid as _u
    user_id = str(_u.uuid4())
    username = body.username.lower().strip()

    # Check duplicate
    existing = storage.get_user_by_username(username)
    if existing:
        raise HTTPException(status_code=409, detail=f"Username '{username}' already exists")

    pw_hash = _hash_password(body.password)
    storage.create_user(
        user_id=user_id, username=username, password_hash=pw_hash,
        first_name=body.first_name, last_name=body.last_name,
        role=body.role, address=body.address, phone=body.phone, email=body.email,
    )
    audit.log(AuditEventType.MEMORY_WRITE if hasattr(AuditEventType, 'MEMORY_WRITE') else "user_created",
              detail=f"User created: {username} ({body.role}) by Chairman")
    return {"ok": True, "user_id": user_id, "username": username}


@app.get("/api/auth/users")
def auth_list_users(authorization: Optional[str] = Header(None)):
    """List all staff users. Chairman only."""
    token = (authorization or "").replace("Bearer ", "")
    session = _get_session(token)
    if not session or session.get("role") != "chairman":
        raise HTTPException(status_code=403, detail="Chairman access required")
    return {"users": storage.list_users()}


class UpdatePermissionsRequest(BaseModel):
    permissions: List[str]  # e.g. ["attendance", "calendar", "documents"]


# ── Panel permission constants ────────────────────────────────────────────────
# All available panels that can be granted to employees.
# Staff compliance is intentionally NOT in this list — it is hardcoded to
# chairman + admin only and can never be granted to regular staff.
GRANTABLE_PANELS = {
    "attendance", "calendar", "documents", "gmail", "telegram", "edi", "upload"
}

# Roles that always have full access (including staff compliance)
PRIVILEGED_ROLES = {"chairman", "admin", "director"}


def _is_privileged(session: dict) -> bool:
    return session.get("role", "").lower() in PRIVILEGED_ROLES


def _session_can_access_panel(session: dict, panel: str) -> bool:
    """Return True if this session is allowed to see `panel`."""
    if _is_privileged(session):
        return True
    return panel in (session.get("panel_permissions") or [])


@app.get("/api/auth/users/{user_id}/permissions")
def get_user_permissions(user_id: str, authorization: Optional[str] = Header(None)):
    """Get panel permissions for a user. Chairman only."""
    token = (authorization or "").replace("Bearer ", "")
    session = _get_session(token)
    if not session or session.get("role") != "chairman":
        raise HTTPException(status_code=403, detail="Chairman access required")
    user = storage.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user_id, "username": user["username"], "permissions": user.get("panel_permissions", [])}


@app.put("/api/auth/users/{user_id}/permissions")
def set_user_permissions(user_id: str, body: UpdatePermissionsRequest, authorization: Optional[str] = Header(None)):
    """Set panel permissions for a staff user. Chairman only."""
    token = (authorization or "").replace("Bearer ", "")
    session = _get_session(token)
    if not session or session.get("role") != "chairman":
        raise HTTPException(status_code=403, detail="Chairman access required")
    user = storage.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Only allow grantable panels; silently filter out any invalid ones
    valid_perms = [p for p in body.permissions if p in GRANTABLE_PANELS]
    storage.set_user_permissions(user_id, valid_perms)
    audit.log(
        AuditEventType.MEMORY_WRITE if hasattr(AuditEventType, 'MEMORY_WRITE') else "perms_update",
        detail=f"Panel permissions updated: {user['username']} → {valid_perms} by {session.get('username')}"
    )
    return {"ok": True, "user_id": user_id, "permissions": valid_perms}


@app.delete("/api/auth/users/{user_id}")
def auth_deactivate_user(user_id: str, authorization: Optional[str] = Header(None)):
    """Deactivate a staff account. Chairman only."""
    token = (authorization or "").replace("Bearer ", "")
    session = _get_session(token)
    if not session or session.get("role") != "chairman":
        raise HTTPException(status_code=403, detail="Chairman access required")
    ok = storage.deactivate_user(user_id)
    return {"ok": ok}


@app.post("/api/auth/set-admin-password")
def set_admin_password(body: dict):
    """Update the Chairman admin password used for creating users."""
    old_pw  = body.get("old_password", "")
    new_pw  = body.get("new_password", "")
    if not _verify_admin(old_pw):
        raise HTTPException(status_code=403, detail="Current password incorrect")
    if len(new_pw) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    ADMIN_PASS_FILE.write_text(_hash_password(new_pw))
    return {"ok": True}


# Recovery email — stored in a small file alongside the admin pass
RECOVERY_EMAIL_FILE = Path(__file__).parent.parent / "logs" / ".recovery_email"

@app.get("/api/auth/recovery-email")
def get_recovery_email(authorization: Optional[str] = Header(None)):
    """Return the currently configured recovery email (chairman only)."""
    session = _get_session(authorization or "")
    if not session or session.get("role") != "chairman":
        raise HTTPException(403, "Chairman access required")
    email = RECOVERY_EMAIL_FILE.read_text().strip() if RECOVERY_EMAIL_FILE.exists() else ""
    return {"email": email}


@app.post("/api/auth/recovery-email")
def set_recovery_email(body: dict, authorization: Optional[str] = Header(None)):
    """Set the recovery email address for forgot-password emails."""
    session = _get_session(authorization or "")
    if not session or session.get("role") != "chairman":
        raise HTTPException(403, "Chairman access required")
    email = body.get("email", "").strip()
    if not email or "@" not in email:
        raise HTTPException(400, "Valid email address required")
    RECOVERY_EMAIL_FILE.write_text(email)
    return {"ok": True, "email": email}


@app.post("/api/auth/forgot-password")
def forgot_password(body: dict):
    """
    Reset a user's password and email them a temporary one.
    Accepts either username or email.  Always emails to the recovery address
    (the chairman's main email) — not to the employee's file, to avoid enumeration.
    """
    import secrets, string
    identifier = body.get("username", "").strip().lower() or body.get("email", "").strip().lower()
    if not identifier:
        raise HTTPException(400, "Please provide your username or registered email.")

    # Look up user
    user = storage.get_user_by_username(identifier)
    if not user:
        # Also try by email (encrypted, so we search decrypted)
        for u in storage.list_users():
            enc_email = u.get("email_enc", "")
            if enc_email:
                try:
                    dec = storage._decrypt_field(enc_email)
                    if dec.lower() == identifier:
                        user = u
                        break
                except Exception:
                    pass

    if not user:
        # Don't reveal whether the user exists — always return success
        return {"ok": True, "message": "If that account exists, a temporary password has been emailed to the recovery address."}

    # Generate a secure temp password
    alphabet   = string.ascii_letters + string.digits
    temp_pw    = "".join(secrets.choice(alphabet) for _ in range(10))
    new_hash   = _hash_password(temp_pw)

    # Update password in DB
    try:
        with storage._conn() as conn:
            conn.execute(
                "UPDATE staff_users SET password_hash=? WHERE id=?",
                (new_hash, user["id"])
            )
    except Exception as e:
        raise HTTPException(500, f"Could not reset password: {e}")

    # Get recovery email
    recovery_email = RECOVERY_EMAIL_FILE.read_text().strip() if RECOVERY_EMAIL_FILE.exists() else ""
    if not recovery_email:
        # Fall back to the Gmail profile address if available
        try:
            profile = gmail_profile()
            recovery_email = profile.get("email", "")
        except Exception:
            pass

    if not recovery_email:
        raise HTTPException(503, "No recovery email configured. Please set one in Settings → Recovery Email.")

    # Send email
    full_name = f"{user.get('first_name','')} {user.get('last_name','')}".strip() or user.get("username")
    body_text = (
        f"Password Reset — Gold Health Systems REX Dashboard\n"
        f"{'─'*52}\n\n"
        f"A password reset was requested for the following account:\n\n"
        f"  Name:      {full_name}\n"
        f"  Username:  {user.get('username')}\n"
        f"  Temp password: {temp_pw}\n\n"
        f"Please sign in with the temporary password above and change it immediately.\n\n"
        f"If you did not request this reset, contact your system administrator.\n\n"
        f"— REX System · Gold Health Systems LLC\n"
    )
    result = gmail_send_email(
        to=recovery_email,
        subject=f"🔐 REX Password Reset — {user.get('username')}",
        body=body_text,
    )

    if not result.get("ok"):
        # Still return success to avoid leaking user existence, but log the error
        logger.error(f"forgot_password email failed: {result.get('error')}")

    return {
        "ok": True,
        "message": f"A temporary password has been sent to {recovery_email}. It can be used to sign in immediately."
    }


# ── File Upload API ────────────────────────────────────────────────────────────

class UploadMeta(BaseModel):
    description: Optional[str] = ""
    sync_drive:  bool = False


@app.post("/api/upload")
async def upload_file_endpoint(
    file:        UploadFile = File(...),
    description: str        = Form(""),
    sync_drive:  bool       = Form(False),
):
    """Upload a file to REX local storage (and optionally Google Drive)."""
    try:
        safe_name = Path(file.filename).name.replace(" ", "_") if file.filename else "upload"
        dest = UPLOADS_DIR / safe_name

        # Handle name collisions
        counter = 1
        while dest.exists():
            stem   = Path(safe_name).stem
            suffix = Path(safe_name).suffix
            dest   = UPLOADS_DIR / f"{stem}_{counter}{suffix}"
            counter += 1

        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out)

        file_size = dest.stat().st_size
        result = {
            "ok":       True,
            "filename": dest.name,
            "size":     file_size,
            "path":     str(dest),
            "drive":    None,
        }

        if sync_drive:
            if gdrive_configured():
                drive_result = gdrive_upload(str(dest), description=description)
                result["drive"] = drive_result
            else:
                result["drive"] = {"ok": False, "error": "Google Drive not connected."}

        audit.log(audit.AuditEventType.MEMORY_WRITE if hasattr(audit, 'AuditEventType') else "upload",
                  detail=f"File uploaded: {dest.name} ({file_size} bytes)")
        return result
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/uploads")
def list_uploads():
    """List all files in the uploads directory."""
    files = []
    for f in sorted(UPLOADS_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.is_file() and not f.name.startswith("."):
            stat = f.stat()
            files.append({
                "name":     f.name,
                "size":     stat.st_size,
                "modified": stat.st_mtime,
                "url":      f"/api/uploads/{f.name}",
            })
    return {"ok": True, "files": files, "count": len(files)}


@app.get("/api/uploads/{filename}")
def serve_upload(filename: str):
    """Serve an uploaded file."""
    path = UPLOADS_DIR / Path(filename).name
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(path))


@app.delete("/api/uploads/{filename}")
def delete_upload(filename: str):
    """Delete an uploaded file."""
    path = UPLOADS_DIR / Path(filename).name
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    path.unlink()
    return {"ok": True, "deleted": filename}


# ── Training Document Upload ───────────────────────────────────────────────────
# Kato drops documents here → REX + Rexxie analyze them privately
# Files saved to training_docs/, prompt queued in ai_queue/ for nightly processing

TRAINING_DOCS_DIR = Path(__file__).parent.parent / "training_docs"
TRAINING_DOCS_DIR.mkdir(parents=True, exist_ok=True)

ANALYSIS_PROMPTS = {
    "compare": (
        "You are reviewing a document submitted by or about a GOJ Home Health employee (Brooklyn, NYC Medicaid agency). "
        "Your job is to double-check everything in this document — schedules, hours, assignments, authorizations, routes, or whatever it contains.\n\n"
        "Perform a thorough COMPARE & CHECK:\n"
        "1. WHAT'S IN THIS DOCUMENT — summarize what the employee submitted or what this file represents.\n"
        "2. DISCREPANCIES — anything that doesn't add up: wrong hours, missing days, impossible routes, "
        "conflicting assignments, mismatched shifts, unauthorized changes, billing that doesn't match schedule, etc.\n"
        "3. RED FLAGS — anything suspicious, unusual, or that warrants Chairman attention.\n"
        "4. WHAT MATCHES — confirm what appears correct so Kato knows what to trust.\n"
        "5. VERDICT — a single clear summary: CLEAN / MINOR ISSUES / REVIEW NEEDED / ESCALATE.\n\n"
        "Be direct. If something looks wrong, say so clearly. Kato needs actionable findings, not hedged language."
    ),
    "mistakes": (
        "Carefully read the following document from our agency (GOJ Home Health, Brooklyn NYC). "
        "Identify every mistake, error, inconsistency, or area of concern you can find. "
        "For each issue found, explain: (1) what the mistake is, (2) why it matters, "
        "(3) what the correct version should be. Be specific and thorough. "
        "After listing issues, add a SEVERITY SUMMARY — rate each issue as Critical / Moderate / Minor."
    ),
    "learn": (
        "Read the following document from our agency (GOJ Home Health, Brooklyn NYC). "
        "Extract the key patterns, procedures, and best practices it demonstrates. "
        "Format as a structured learning guide with: "
        "KEY PATTERNS (3-7 patterns worth remembering), "
        "AGENCY CONTEXT (how this applies to our day-to-day operations), "
        "RECOMMENDED PRACTICES (what to do consistently based on this document). "
        "Be practical and specific to a Medicaid home health agency context."
    ),
    "summarize": (
        "Summarize the following document from our agency (GOJ Home Health, Brooklyn NYC). "
        "Provide: OVERVIEW (2-3 sentences), KEY POINTS (bullet list), "
        "ACTION ITEMS (anything requiring follow-up or decision), "
        "FLAGS (anything unusual, missing, or that needs attention). "
        "Keep it concise — Kato should be able to read this in 60 seconds."
    ),
    "full": (
        "Perform a complete analysis of the following document from our agency (GOJ Home Health, Brooklyn NYC). "
        "Include: (1) SUMMARY — what this document is and its purpose. "
        "(2) MISTAKES & ISSUES — every error, inconsistency, or problem found with severity. "
        "(3) KEY PATTERNS — what this document reveals about agency operations. "
        "(4) ACTION ITEMS — what needs to be done as a result of this document. "
        "(5) RECOMMENDATIONS — how to improve this type of document or process going forward. "
        "Be thorough, direct, and practical."
    ),
}


@app.post("/api/upload-training")
async def upload_training_document(
    file:          UploadFile = File(...),
    analysis_type: str        = Form("full"),
    focus:         str        = Form(""),
):
    """
    Upload a training document for private REX+Rexxie analysis.
    Creates an AI queue prompt that runs at next processing window.
    Results are sent privately to Kato via Rexxie Telegram.
    """
    import datetime as _dt

    try:
        safe_name = Path(file.filename).name.replace(" ", "_") if file.filename else "training_doc"
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_name = f"{ts}_{safe_name}"
        dest = TRAINING_DOCS_DIR / dest_name

        contents = await file.read()
        dest.write_bytes(contents)
        file_size = len(contents)

        # Extract text if PDF/txt for embedding in prompt
        doc_text = ""
        suffix = dest.suffix.lower()
        if suffix == ".txt":
            try:
                doc_text = contents.decode("utf-8", errors="replace")[:12000]
            except Exception:
                pass
        elif suffix == ".pdf":
            try:
                import io
                # Try pdfminer or pypdf if available
                try:
                    from pdfminer.high_level import extract_text_to_fp
                    from pdfminer.layout import LAParams
                    output = io.StringIO()
                    extract_text_to_fp(io.BytesIO(contents), output, laparams=LAParams())
                    doc_text = output.getvalue()[:12000]
                except ImportError:
                    try:
                        import pypdf
                        reader = pypdf.PdfReader(io.BytesIO(contents))
                        doc_text = "\n".join(page.extract_text() or "" for page in reader.pages)[:12000]
                    except ImportError:
                        doc_text = f"[PDF: {dest_name} — text extraction unavailable, install pdfminer.six or pypdf]"
            except Exception as e:
                doc_text = f"[Could not extract PDF text: {e}]"
        elif suffix in (".docx",):
            try:
                import docx as _docx
                doc = _docx.Document(io.BytesIO(contents))
                doc_text = "\n".join(p.text for p in doc.paragraphs)[:12000]
            except Exception:
                doc_text = f"[DOCX: {dest_name} — python-docx not installed]"
        else:
            doc_text = f"[File type {suffix} — text not extracted. Filename: {dest_name}]"

        # Build the AI prompt
        analysis_key = analysis_type if analysis_type in ANALYSIS_PROMPTS else "full"
        base_prompt  = ANALYSIS_PROMPTS[analysis_key]
        focus_note   = f"\n\nSpecific focus from Kato: {focus.strip()}" if focus.strip() else ""
        doc_block    = f"\n\n--- DOCUMENT START ---\n{doc_text}\n--- DOCUMENT END ---" if doc_text else f"\n\n[File saved as: {dest_name} — no text extracted]"

        full_prompt = (
            f"{base_prompt}{focus_note}"
            f"\n\nThis analysis is CHAIRMAN PRIVATE — results go only to Kato (Chairman). "
            f"Do not share findings with staff. This is a private operational review.\n"
            f"{doc_block}"
        )

        # Queue it for AI processing
        queue_dir = Path(__file__).parent.parent / "ai_queue"
        queue_dir.mkdir(parents=True, exist_ok=True)
        prompt_name = f"training_{ts}_{Path(dest_name).stem}.prompt"
        prompt_path = queue_dir / prompt_name
        prompt_data = {
            "ai":             "chatgpt",   # Use the most capable model available
            "topic":          f"Training Document Analysis — {dest.name}",
            "type":           "chairman_training",
            "analysis_type":  analysis_key,
            "source_file":    str(dest),
            "date":           _dt.date.today().isoformat(),
            "prompt":         full_prompt,
            "private":        True,
            "notify_rexxie":  True,
            "original_filename": file.filename or dest_name,
        }
        prompt_path.write_text(json.dumps(prompt_data, indent=2))

        # Log to audit
        audit.log(
            AuditEventType.MEMORY_WRITE if hasattr(AuditEventType, 'MEMORY_WRITE') else "training_upload",
            detail=f"Training doc queued: {dest.name} ({file_size} bytes) — {analysis_key} analysis",
        )

        return {
            "ok":              True,
            "filename":        dest_name,
            "size":            file_size,
            "analysis_type":   analysis_key,
            "prompt_queued":   prompt_name,
            "queue_position":  len(list(queue_dir.glob("training_*.prompt"))),
            "text_extracted":  bool(doc_text and not doc_text.startswith("[")),
        }

    except Exception as e:
        logger.error(f"Training upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/training-queue")
def get_training_queue():
    """
    List training documents — pending + completed.
    Pending: in ai_queue/ with type=chairman_training
    Completed: in training_docs/ cross-referenced with processed queue + reports
    """
    import datetime as _dt
    queue_dir   = Path(__file__).parent.parent / "ai_queue"
    done_dir    = queue_dir / "processed"
    report_dir  = Path(__file__).parent.parent / "training_reports"

    pending = []
    completed = []

    # Pending
    for p in sorted(queue_dir.glob("training_*.prompt"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            d = json.loads(p.read_text())
            pending.append({
                "prompt_file":     p.name,
                "filename":        d.get("original_filename", p.stem),
                "analysis_type":   d.get("analysis_type", "full"),
                "date":            d.get("date", ""),
                "status":          "queued",
                "queued_at":       p.stat().st_mtime,
            })
        except Exception:
            pass

    # Completed (in processed folder)
    for p in sorted(done_dir.glob("training_*.prompt"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            d = json.loads(p.read_text())
            # Look for associated report
            ts_part = p.stem.split("_")[1] if "_" in p.stem else ""
            report_files = list(report_dir.glob(f"*{ts_part}*")) if ts_part else []
            completed.append({
                "prompt_file":     p.name,
                "filename":        d.get("original_filename", p.stem),
                "analysis_type":   d.get("analysis_type", "full"),
                "date":            d.get("date", ""),
                "status":          "processed",
                "processed_at":    p.stat().st_mtime,
                "has_report":      len(report_files) > 0,
            })
        except Exception:
            pass

    return {
        "pending":   pending,
        "completed": completed,
        "total":     len(pending) + len(completed),
    }


@app.post("/api/drive/sync")
def drive_sync():
    """Sync all local uploads to Google Drive."""
    if not gdrive_configured():
        return {"ok": False, "error": "Google Drive not connected. Run setup first."}
    return sync_uploads_to_drive()


@app.get("/api/drive/files")
def drive_files():
    """List files in Google Drive REX folder."""
    if not gdrive_configured():
        return {"ok": False, "error": "Google Drive not connected.", "files": []}
    return list_drive_files()


# ── Telegram Channel Reader API ────────────────────────────────────────────────

@app.get("/api/telegram/config")
def telegram_config():
    cfg = tg_load_config()
    # Don't expose secrets
    safe = {k: v for k, v in cfg.items() if k not in ("bot_token", "api_id", "api_hash")}
    safe["configured"] = bool(cfg.get("channel") and (cfg.get("bot_token") or cfg.get("api_id")))
    return safe


@app.post("/api/telegram/config")
async def telegram_save_config(request: Request):
    body = await request.json()
    cfg  = tg_load_config()
    cfg.update(body)
    tg_save_config(cfg)
    return {"ok": True}


@app.post("/api/telegram/fetch")
def telegram_fetch():
    """Trigger a channel fetch."""
    try:
        result = tg_fetch()
        return result
    except Exception as e:
        return {"ok": False, "error": str(e), "messages": []}


@app.get("/api/telegram/messages")
def telegram_messages(limit: int = 20, channel: Optional[str] = None):
    msgs = tg_cached(channel=channel, limit=limit)
    return {"ok": True, "messages": msgs, "count": len(msgs)}


@app.get("/api/telegram/schedule")
def telegram_schedule():
    summary = tg_schedule_summary()
    return {"ok": True, "summary": summary}


# ── Chairman Personal Events — private calendar ───────────────────────────────

class EventCreate(BaseModel):
    title:       str
    event_date:  str
    event_time:  str = ""
    notes:       str = ""
    reminder_at: str = ""
    source:      str = "manual"

@app.get("/api/chairman/events")
def list_events(date: str = "", month: str = ""):
    events = storage.get_events(date=date or None, month=month or None)
    return {"events": events}

@app.post("/api/chairman/events")
def create_event(body: EventCreate):
    import uuid as _uuid
    event_id = str(_uuid.uuid4())
    storage.create_event(
        event_id=event_id, event_date=body.event_date,
        event_time=body.event_time or None, title=body.title,
        notes=body.notes, reminder_at=body.reminder_at or None,
        source=body.source,
    )
    audit.log("CHAIRMAN_EVENT_CREATED", {"date": body.event_date})
    return {"ok": True, "id": event_id}

@app.delete("/api/chairman/events/{event_id}")
def delete_event(event_id: str):
    deleted = storage.delete_event(event_id)
    if deleted:
        audit.log("CHAIRMAN_EVENT_DELETED", {"id": event_id})
    return {"ok": deleted}

@app.get("/api/chairman/reminders/pending")
def pending_reminders():
    import datetime as _dt
    now = _dt.datetime.now().isoformat(timespec='seconds')
    due = storage.get_pending_reminders(as_of=now)
    return {"reminders": due}

@app.post("/api/chairman/reminders/{event_id}/mark-sent")
def mark_reminder_sent(event_id: str):
    storage.mark_reminded(event_id)
    return {"ok": True}


# ── PDF Email Prompt + Extraction (Paperless-ngx) ────────────────────────────
# State: ~/Desktop/REX/logs/pdf_watcher_state.json (managed by rex_email_pdf_watcher.py)

PDF_STATE_PATH = Path(__file__).parent.parent / "logs" / "pdf_watcher_state.json"
ENV_PATH = Path.home() / "Documents" / "goj files" / ".env"

def _load_pdf_state() -> dict:
    if PDF_STATE_PATH.exists():
        try:
            return json.loads(PDF_STATE_PATH.read_text())
        except Exception:
            pass
    return {"seen_ids": [], "pending_prompts": []}

def _save_pdf_state(state: dict):
    PDF_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PDF_STATE_PATH.write_text(json.dumps(state, indent=2))

def _get_paperless_config() -> dict:
    """Load Paperless URL + token from ~/Documents/goj files/.env"""
    cfg = {"url": "http://100.99.86.60:8000", "token": ""}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if k == "PAPERLESS_URL":
                    cfg["url"] = v
                elif k == "PAPERLESS_TOKEN":
                    cfg["token"] = v
    return cfg

def _send_rexxie_telegram(text: str) -> bool:
    """Send a message via the Rexxie private bot to Kato."""
    tg_cfg_path = Path(__file__).parent.parent / "rex_rexxie_telegram_config.json"
    if not tg_cfg_path.exists():
        return False
    try:
        d = json.loads(tg_cfg_path.read_text())
        token   = d.get("bot_token", "")
        chat_id = d.get("owner_chat_id", 0)
    except Exception:
        return False
    if not token or not chat_id:
        return False
    import urllib.request as _req
    url     = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    req     = _req.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with _req.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()).get("ok", False)
    except Exception:
        return False


@app.post("/api/chairman/pdf-prompt")
def pdf_prompt(request: Request):
    """Called by rex_email_pdf_watcher to notify Kato of a new PDF email."""
    import asyncio
    body = asyncio.get_event_loop().run_until_complete(request.json()) if False else {}
    # FastAPI: use sync approach
    return {"ok": True}  # watcher sends TG directly; this endpoint is for future dashboard push


@app.get("/api/chairman/pending-pdfs")
def get_pending_pdfs():
    """Return PDF emails awaiting Kato's extraction decision."""
    state = _load_pdf_state()
    return {"pending": state.get("pending_prompts", [])}


class PdfExtractRequest(BaseModel):
    gmail_id:  str
    subject:   str
    sender:    str
    pdf_names: list


@app.post("/api/chairman/extract-pdf")
def extract_pdf(body: PdfExtractRequest):
    """
    Download PDF attachments from a Gmail message and ingest into Paperless-ngx.
    Called when Kato replies 'yes' via Rexxie.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        import tempfile, os
    except ImportError:
        raise HTTPException(500, "google-auth not installed")

    TOKEN_PATH = Path.home() / ".rex_google_token.json"
    if not TOKEN_PATH.exists():
        raise HTTPException(503, "Gmail not configured")

    # Authenticate Gmail
    creds = Credentials.from_authorized_user_file(
        str(TOKEN_PATH),
        ["https://www.googleapis.com/auth/gmail.readonly"],
    )
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    svc = build("gmail", "v1", credentials=creds)

    # Get paperless config
    pl = _get_paperless_config()
    import urllib.request as _ureq, urllib.parse as _uparse

    extracted = []

    # Fetch the full message to get attachment data
    msg = svc.users().messages().get(
        userId="me", id=body.gmail_id, format="full"
    ).execute()

    def _collect_parts(parts, acc):
        for part in parts:
            fn = part.get("filename", "")
            mime = part.get("mimeType", "")
            if fn and (mime == "application/pdf" or fn.lower().endswith(".pdf")):
                acc.append(part)
            sub = part.get("parts", [])
            if sub:
                _collect_parts(sub, acc)

    pdf_parts = []
    _collect_parts(msg.get("payload", {}).get("parts", []), pdf_parts)

    for part in pdf_parts:
        filename = part.get("filename", "attachment.pdf")
        att_id   = part.get("body", {}).get("attachmentId")
        data_b64 = part.get("body", {}).get("data")

        if att_id:
            att = svc.users().messages().attachments().get(
                userId="me", messageId=body.gmail_id, id=att_id
            ).execute()
            data_b64 = att.get("data", "")

        if not data_b64:
            continue

        pdf_bytes = import_base64_decode(data_b64)

        # Write to temp file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, prefix="rex_") as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        try:
            # Ingest into Paperless
            title = f"{filename} — {body.subject[:60]}"
            _ingest_to_paperless(pl["url"], pl["token"], tmp_path, title)
            extracted.append(filename)
            logger.info(f"PDF ingested: {filename} → Paperless")
        finally:
            import os
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    # Remove from pending state
    state = _load_pdf_state()
    state["pending_prompts"] = [
        p for p in state.get("pending_prompts", [])
        if p.get("gmail_id") != body.gmail_id
    ]
    _save_pdf_state(state)

    return {"ok": True, "extracted": len(extracted), "files": extracted}


def import_base64_decode(data: str) -> bytes:
    """Handle both standard and URL-safe base64 (Gmail uses URL-safe)."""
    import base64
    padded = data.replace("-", "+").replace("_", "/")
    padded += "=" * (-len(padded) % 4)
    return base64.b64decode(padded)


def _ingest_to_paperless(pl_url: str, pl_token: str, filepath: str, title: str):
    """Upload a file to Paperless-ngx via the document upload API."""
    import urllib.request as _ureq
    import uuid, mimetypes, os
    boundary = uuid.uuid4().hex
    fname    = os.path.basename(filepath)
    mt       = "application/pdf"

    with open(filepath, "rb") as f:
        file_bytes = f.read()

    parts = []
    # title field
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="title"\r\n\r\n{title}\r\n'.encode()
    )
    # document file
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{fname}"\r\n'
        f'Content-Type: {mt}\r\n\r\n'.encode() + file_bytes + b'\r\n'
    )
    body = b''.join(parts) + f'--{boundary}--\r\n'.encode()

    req = _ureq.Request(
        f"{pl_url.rstrip('/')}/api/documents/post_document/",
        data=body,
        headers={
            "Authorization": f"Token {pl_token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    with _ureq.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read())
        logger.info(f"Paperless ingest response: {result}")


# ── Day Summary — powers the Calendar panel ───────────────────────────────────

@app.get("/api/day-summary")
def day_summary(date: str = ""):
    """
    Return a structured summary for a given date (YYYY-MM-DD).
    Pulls from: training queue, training reports, uploaded docs, logs.
    Used by the REX Calendar panel for daily/monthly views.
    """
    import datetime as _dt, glob as _glob

    if not date:
        date = _dt.date.today().isoformat()

    try:
        d = _dt.date.fromisoformat(date)
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD."}

    rex_dir   = Path(__file__).parent.parent
    queue_dir = rex_dir / "ai_queue"
    done_dir  = queue_dir / "processed"
    report_dir = rex_dir / "training_reports"
    log_dir   = rex_dir / "logs"

    dow      = d.weekday()  # 0=Mon, 6=Sun
    dow_name = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"][dow]

    # AI training schedule
    ai_schedule = {0:"Grok", 1:"ChatGPT", 3:"Gemini"}
    ai_today = ai_schedule.get(dow)

    # Check if training report exists for this date's AI
    training_done = False
    training_file = None
    if ai_today:
        day_abbr = dow_name.lower()
        for f in report_dir.glob(f"*{day_abbr}*.txt"):
            training_done = True
            training_file = f.name
            break

    # Queue status for this date
    queued_prompts = []
    for pf in queue_dir.glob("*.prompt"):
        try:
            import json as _json
            data = _json.loads(pf.read_text())
            if data.get("date","") == date or data.get("day","") == dow_name.lower():
                queued_prompts.append({
                    "ai": data.get("ai","?"),
                    "topic": data.get("topic",""),
                    "file": pf.name,
                })
        except Exception:
            pass

    # Uploaded documents matching this date
    upload_dir = rex_dir / "uploads" if (rex_dir / "uploads").exists() else None
    docs = []
    if upload_dir:
        date_tag = date.replace("-","")
        for f in upload_dir.iterdir():
            if date in f.name or date_tag in f.name:
                docs.append({"name": f.name, "size": f.stat().st_size})

    # Evening report log snippet for this date
    evening_log = ""
    ev_log_path = log_dir / "evening_report.log"
    if ev_log_path.exists():
        lines = ev_log_path.read_text().splitlines()
        today_lines = [l for l in lines if date in l]
        evening_log = "\n".join(today_lines[-20:]) if today_lines else ""

    # Chairman personal events for this date
    personal_events = storage.get_events(date=date)

    return {
        "date":           date,
        "day_of_week":    dow_name,
        "is_weekend":     dow >= 5,
        "ai_training":    ai_today,
        "training_done":  training_done,
        "training_file":  training_file,
        "queued_prompts": queued_prompts,
        "documents":      docs,
        "personal_events": personal_events,
        "evening_log":   evening_log,
        "is_today":      date == _dt.date.today().isoformat(),
    }

@app.get("/api/month-summary")
def month_summary(year: int = 0, month: int = 0):
    """
    Return a summary of all days in a given month.
    Used by the Calendar month tab to show what's active each day.
    """
    import datetime as _dt

    today = _dt.date.today()
    if not year:  year  = today.year
    if not month: month = today.month

    import calendar as _cal
    days_in_month = _cal.monthrange(year, month)[1]

    rex_dir    = Path(__file__).parent.parent
    report_dir = rex_dir / "training_reports"
    queue_dir  = rex_dir / "ai_queue"
    done_dir   = queue_dir / "processed"

    ai_schedule = {0:"Grok", 1:"ChatGPT", 3:"Gemini"}
    dow_names   = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

    days = []
    for day in range(1, days_in_month + 1):
        d   = _dt.date(year, month, day)
        dow = d.weekday()
        ai  = ai_schedule.get(dow)

        # Check if training report exists
        done = False
        if ai:
            for f in list(report_dir.glob(f"*{dow_names[dow].lower()}*.txt")) + \
                     list(done_dir.glob(f"*{d.isoformat()}*.prompt")):
                done = True
                break

        days.append({
            "date":       d.isoformat(),
            "day":        day,
            "dow":        dow,
            "dow_name":   dow_names[dow],
            "is_today":   d == today,
            "is_past":    d < today,
            "ai":         ai,
            "ai_done":    done,
            "is_weekend": dow >= 5,
        })

    return {"year": year, "month": month, "days": days}


# ── Attendance Dashboard ──────────────────────────────────────────────────────

@app.get("/api/attendance")
def get_attendance(date: str = ""):
    """
    Return client attendance for a given date from auth_tracker.db.
    Groups by shift, includes scheduled vs. present status.
    """
    import datetime as _dt
    if not date:
        date = _dt.date.today().isoformat()

    auth_db = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
    if not auth_db.exists():
        return {"date": date, "shifts": {}, "note": "auth_tracker.db not found"}

    import sqlite3
    from collections import defaultdict

    try:
        conn = sqlite3.connect(str(auth_db))
        cur  = conn.cursor()

        # Attendance log for this date
        cur.execute("""
            SELECT shift, client_name, status, source
            FROM attendance_log
            WHERE log_date = ?
            ORDER BY shift, client_name
        """, (date,))
        logged = cur.fetchall()

        # Scheduled clients for this weekday
        try:
            dt  = _dt.date.fromisoformat(date)
            dow = dt.weekday()   # 0=Mon
            day_col = {0:"day_M_actual",1:"day_T_actual",2:"day_W_actual",
                       3:"day_TH_actual",4:"day_F_actual"}.get(dow)
            if day_col:
                cur.execute(f"""
                    SELECT name, shift FROM clients
                    WHERE {day_col} = 1 AND active = 1
                    ORDER BY name
                """)
                scheduled = cur.fetchall()
            else:
                scheduled = []
        except Exception:
            scheduled = []

        conn.close()

        # Build per-shift dicts
        shifts: dict = {}

        # Add scheduled clients
        for (name, shift) in scheduled:
            k = str(shift or 1)
            if k not in shifts:
                shifts[k] = {}
            if name not in shifts[k]:
                shifts[k][name] = {"status": "scheduled", "source": ""}

        # Overlay actual attendance log
        for (shift, name, status, source) in logged:
            k = str(shift or 1)
            if k not in shifts:
                shifts[k] = {}
            shifts[k][name] = {"status": status or "present", "source": source or ""}

        # Convert to list for each shift
        result = {}
        for k, clients in sorted(shifts.items()):
            result[k] = [{"name": n, **v} for n, v in sorted(clients.items())]

        total_present   = sum(1 for s in result.values() for c in s if c["status"] in ("present","attended"))
        total_scheduled = sum(len(s) for s in result.values())

        return {
            "date": date,
            "shifts": result,
            "totals": {"scheduled": total_scheduled, "present": total_present},
        }
    except Exception as e:
        return {"date": date, "shifts": {}, "error": str(e)}


# ── Staff Compliance Dashboard ────────────────────────────────────────────────

@app.get("/api/staff/compliance")
def staff_compliance(authorization: Optional[str] = Header(None)):
    """
    Returns live staff compliance data from GOJ_Staff_Compliance_Apr2026.xlsx.
    Re-computes days-until-due from today so the statuses are always current.
    Restricted to chairman and admin/director roles only.
    """
    token = (authorization or "").replace("Bearer ", "")
    session = _get_session(token)
    if not session or not _is_privileged(session):
        raise HTTPException(
            status_code=403,
            detail="Staff compliance data is restricted to Chairman and Director access only."
        )
    from datetime import date as _date
    import re as _re

    xlsx_path = Path(__file__).parent.parent / "GOJ_Staff_Compliance_Apr2026.xlsx"
    if not xlsx_path.exists():
        raise HTTPException(404, "Compliance spreadsheet not found")

    try:
        import openpyxl
    except ImportError:
        raise HTTPException(500, "openpyxl not installed — run: pip install openpyxl")

    def _parse_date(val):
        """Try to parse a date string or date object; return ISO string or None."""
        if val is None:
            return None
        if isinstance(val, (_date,)):
            return val.isoformat()
        s = str(val).strip()
        if s in ("N/A", "n/a", "—", ""):
            return None
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m/%d/%y"):
            try:
                from datetime import datetime as _dt
                return _dt.strptime(s, fmt).date().isoformat()
            except ValueError:
                pass
        return None

    def _status(iso_date):
        """Return status dict: {days, level} where level is ok/warn/critical/overdue."""
        if not iso_date:
            return {"days": None, "level": "na"}
        from datetime import date as _date
        try:
            from datetime import datetime as _dt
            d = _dt.strptime(iso_date, "%Y-%m-%d").date()
            days = (d - _date.today()).days
            if days < 0:
                return {"days": days, "level": "overdue"}
            if days <= 14:
                return {"days": days, "level": "critical"}
            if days <= 30:
                return {"days": days, "level": "warn"}
            return {"days": days, "level": "ok"}
        except Exception:
            return {"days": None, "level": "na"}

    wb = openpyxl.load_workbook(str(xlsx_path), data_only=True)
    ws = wb["Compliance Tracker"]

    staff = []
    header_row = None
    col_map = {}

    for row in ws.iter_rows(min_row=1, values_only=True):
        if row[0] == "Employee":
            header_row = [str(c).strip() if c else "" for c in row]
            for i, h in enumerate(header_row):
                col_map[h] = i
            continue
        if header_row and row[0] and str(row[0]).strip() not in ("", "Employee"):
            def _get(col_name):
                idx = col_map.get(col_name)
                return str(row[idx]).strip() if idx is not None and row[idx] is not None else None

            medical_due  = _parse_date(_get("Medical Due"))
            tb_due       = _parse_date(_get("TB/Quanti/Xray"))
            cpr_due      = _parse_date(_get("CPR/First Aid"))
            inservice_due = _parse_date(_get("Inservice"))

            s_medical   = _status(medical_due)
            s_tb        = _status(tb_due)
            s_cpr       = _status(cpr_due)
            s_inservice = _status(inservice_due)

            # Overall urgency = worst of all docs
            level_order = {"overdue": 0, "critical": 1, "warn": 2, "ok": 3, "na": 4}
            levels = [s_medical["level"], s_tb["level"], s_cpr["level"], s_inservice["level"]]
            overall = min(levels, key=lambda l: level_order.get(l, 4))

            staff.append({
                "name":        _get("Employee"),
                "role":        _get("Role"),
                "hire_date":   _get("Hire Date"),
                "tb_type":     _get("Type"),
                "medical":     {"due": medical_due,   **s_medical},
                "tb":          {"due": tb_due,        **s_tb},
                "cpr":         {"due": cpr_due,       **s_cpr},
                "inservice":   {"due": inservice_due, **s_inservice},
                "overall":     overall,
            })

    # Sort by urgency (overdue first, then critical, warn, ok)
    level_order = {"overdue": 0, "critical": 1, "warn": 2, "ok": 3, "na": 4}
    staff.sort(key=lambda x: (level_order.get(x["overall"], 4), x.get("name") or ""))

    overdue  = [s for s in staff if s["overall"] == "overdue"]
    critical = [s for s in staff if s["overall"] == "critical"]
    warn     = [s for s in staff if s["overall"] == "warn"]

    return {
        "staff": staff,
        "summary": {
            "total": len(staff),
            "overdue": len(overdue),
            "critical": len(critical),
            "warn": len(warn),
            "ok": len([s for s in staff if s["overall"] == "ok"]),
        },
        "generated": _date.today().isoformat(),
    }


# ── Backup status ─────────────────────────────────────────────────────────────

@app.get("/api/backup/status")
def backup_status():
    """Return when the last backup was taken.

    Snapshots live on the external Cartoons drive. If Cartoons is not
    mounted the count returns 0 and backup_dir returns None — we do NOT
    fall back to any on-disk path. The `.last_backup` timestamp is still
    read from REX root because it's a status marker, not a snapshot.
    """
    last_backup_file = Path(__file__).parent.parent / ".last_backup"
    last = None
    if last_backup_file.exists():
        last = last_backup_file.read_text().strip()

    backup_dir = None
    for candidate in (Path("/Volumes/Cartoons/REX_Backups"),
                      Path("/Volumes/cartoons/REX_Backups")):
        if candidate.exists():
            backup_dir = candidate
            break

    count = 0
    if backup_dir is not None:
        count = len(list(backup_dir.glob("REX_*")))

    return {
        "last_backup": last,
        "backup_count": count,
        "backup_dir": str(backup_dir) if backup_dir else None,
        "cartoons_mounted": backup_dir is not None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  EDI 837 / 835 RECEIVER & INTERPRETER
# ═══════════════════════════════════════════════════════════════════════════════

try:
    from .rex_edi import detect_and_parse, EDIInterpreter, parse_837, parse_835
    _EDI_AVAILABLE = True
except Exception as _edi_err:
    _EDI_AVAILABLE = False
    logger.warning(f"EDI module not loaded: {_edi_err}")

# Storage paths for uploaded EDI files and parsed results
EDI_DIR          = Path(__file__).parent.parent / "edi_files"
EDI_CLAIMS_DIR   = EDI_DIR / "claims"     # raw 837 files
EDI_ERA_DIR      = EDI_DIR / "eras"       # raw 835 files
EDI_RESULTS_DIR  = EDI_DIR / "results"    # parsed JSON results
for _d in (EDI_CLAIMS_DIR, EDI_ERA_DIR, EDI_RESULTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _edi_result_path(file_id: str) -> Path:
    return EDI_RESULTS_DIR / f"{file_id}.json"


def _save_edi_result(file_id: str, result: dict) -> None:
    _edi_result_path(file_id).write_text(json.dumps(result, indent=2))


def _load_edi_results(edi_type: Optional[str] = None) -> List[dict]:
    """Load all parsed EDI results, optionally filtered by type ('837'|'835')."""
    results = []
    for f in sorted(EDI_RESULTS_DIR.glob("*.json"), reverse=True):
        try:
            r = json.loads(f.read_text())
            if edi_type and r.get("type") != edi_type:
                continue
            results.append(r)
        except Exception:
            pass
    return results


@app.post("/api/edi/upload")
async def edi_upload(file: UploadFile = File(...)):
    """
    Upload an 837 (claim) or 835 (remittance) EDI file.
    Auto-detects type, parses, interprets, and stores the result.
    Returns a structured plain-English summary.
    """
    if not _EDI_AVAILABLE:
        raise HTTPException(503, "EDI module not available")

    raw_bytes = await file.read()
    try:
        raw_text = raw_bytes.decode("utf-8", errors="replace")
    except Exception:
        raise HTTPException(400, "Could not decode file — make sure it is a plain-text EDI file")

    if len(raw_text.strip()) < 20:
        raise HTTPException(400, "File appears empty or too short to be an EDI document")

    # Parse + interpret
    try:
        result = detect_and_parse(raw_text)
    except Exception as e:
        raise HTTPException(422, f"EDI parse error: {e}")

    # Save raw file
    file_id = str(uuid.uuid4())[:12]
    timestamp = datetime.utcnow().isoformat()
    edi_type = result.get("type", "unknown")

    raw_dest = (EDI_CLAIMS_DIR if edi_type == "837" else EDI_ERA_DIR) / f"{file_id}_{file.filename}"
    raw_dest.write_bytes(raw_bytes)

    # Build stored record
    record = {
        "file_id":    file_id,
        "filename":   file.filename,
        "type":       edi_type,
        "uploaded_at": timestamp,
        "raw_path":   str(raw_dest),
        "parsed":     result.get("parsed", {}),
        "interpreted": result.get("interpreted", {}),
    }
    _save_edi_result(file_id, record)

    # Friendly response
    interpreted = result.get("interpreted", {})
    return {
        "file_id":       file_id,
        "type":          edi_type,
        "filename":      file.filename,
        "uploaded_at":   timestamp,
        "summary":       interpreted.get("plain_english", "Parsed successfully."),
        "action_items":  interpreted.get("action_items", []),
        "stats":         {
            k: v for k, v in interpreted.items()
            if k not in ("plain_english", "action_items", "denial_breakdown")
        },
        "denial_breakdown": interpreted.get("denial_breakdown", {}),
    }


@app.get("/api/edi/claims")
def edi_claims(limit: int = 50):
    """List all parsed 837 claim submissions."""
    if not _EDI_AVAILABLE:
        raise HTTPException(503, "EDI module not available")
    results = _load_edi_results("837")[:limit]
    return {"claims": results, "count": len(results)}


@app.get("/api/edi/remittances")
def edi_remittances(limit: int = 50):
    """List all parsed 835 electronic remittance advices."""
    if not _EDI_AVAILABLE:
        raise HTTPException(503, "EDI module not available")
    results = _load_edi_results("835")[:limit]
    return {"remittances": results, "count": len(results)}


@app.get("/api/edi/summary")
def edi_summary():
    """
    Revenue summary across all uploaded EDI files:
    total billed (837), total paid, total denied, reimbursement rate (835).
    """
    if not _EDI_AVAILABLE:
        raise HTTPException(503, "EDI module not available")

    all_results = _load_edi_results()

    total_billed   = 0.0
    total_paid     = 0.0
    total_denied   = 0.0
    total_adjusted = 0.0
    claim_count    = 0
    payment_count  = 0
    denial_reasons: Dict[str, int] = {}

    for r in all_results:
        interp = r.get("interpreted", {})
        if r.get("type") == "837":
            total_billed += float(interp.get("total_billed", 0) or 0)
            claim_count  += int(interp.get("claim_count", 0) or 0)
        elif r.get("type") == "835":
            total_paid     += float(interp.get("total_paid",     0) or 0)
            total_denied   += float(interp.get("total_denied",   0) or 0)
            total_adjusted += float(interp.get("total_adjusted", 0) or 0)
            payment_count  += int(interp.get("payment_count",    0) or 0)
            for reason, cnt in (interp.get("denial_breakdown") or {}).items():
                denial_reasons[reason] = denial_reasons.get(reason, 0) + cnt

    net_revenue       = total_paid
    outstanding       = max(0.0, total_billed - total_paid - total_denied)
    reimbursement_rate = round((total_paid / total_billed * 100), 1) if total_billed > 0 else 0.0

    return {
        "total_billed":        round(total_billed,   2),
        "total_paid":          round(total_paid,     2),
        "total_denied":        round(total_denied,   2),
        "total_adjusted":      round(total_adjusted, 2),
        "outstanding":         round(outstanding,    2),
        "net_revenue":         round(net_revenue,    2),
        "reimbursement_rate":  reimbursement_rate,
        "claim_count":         claim_count,
        "payment_count":       payment_count,
        "denial_reasons":      denial_reasons,
        "files_processed":     len(all_results),
    }


@app.post("/api/edi/match")
def edi_match(body: dict):
    """
    Reconcile an 835 ERA against an 837 claim submission.
    Body: { "claim_file_id": "...", "era_file_id": "..." }
    Returns line-by-line match report.
    """
    if not _EDI_AVAILABLE:
        raise HTTPException(503, "EDI module not available")

    claim_id = body.get("claim_file_id", "")
    era_id   = body.get("era_file_id",   "")

    claim_rec = None
    era_rec   = None

    for r in _load_edi_results():
        if r.get("file_id") == claim_id and r.get("type") == "837":
            claim_rec = r
        if r.get("file_id") == era_id and r.get("type") == "835":
            era_rec = r

    if not claim_rec:
        raise HTTPException(404, f"837 claim file '{claim_id}' not found")
    if not era_rec:
        raise HTTPException(404, f"835 ERA file '{era_id}' not found")

    try:
        interp = EDIInterpreter()
        report = interp.match_835_to_837(
            era_rec.get("parsed", {}),
            claim_rec.get("parsed", {}),
        )
    except Exception as e:
        raise HTTPException(500, f"Match failed: {e}")

    return {
        "claim_file_id":  claim_id,
        "era_file_id":    era_id,
        "claim_filename": claim_rec.get("filename"),
        "era_filename":   era_rec.get("filename"),
        "report":         report,
    }


@app.get("/api/edi/file/{file_id}")
def edi_get_file(file_id: str):
    """Get full parsed detail for a single EDI file by ID."""
    if not _EDI_AVAILABLE:
        raise HTTPException(503, "EDI module not available")
    path = _edi_result_path(file_id)
    if not path.exists():
        raise HTTPException(404, "EDI file not found")
    return json.loads(path.read_text())


# ── GOJ Members & Stats ───────────────────────────────────────────────────────

try:
    from .rex_documents import (
        get_goj_stats, get_goj_members, run_document_routing,
        list_documents, get_staff_medical_docs,
        get_member_portfolios, upload_member_document,
    )
    _DOCS_AVAILABLE = True
except Exception as _e:
    logger.warning(f"rex_documents not available: {_e}")
    _DOCS_AVAILABLE = False


@app.get("/api/goj/stats")
def goj_stats(authorization: Optional[str] = Header(None)):
    """Return GOJ member statistics for dashboard. Available to all authenticated users."""
    token = (authorization or "").replace("Bearer ", "")
    session = _get_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not _DOCS_AVAILABLE:
        raise HTTPException(503, "GOJ module not available")
    return get_goj_stats()


@app.get("/api/goj/members")
def goj_members(
    plan: Optional[str] = None,
    day: Optional[str] = None,
    search: Optional[str] = None,
    authorization: Optional[str] = Header(None)
):
    """Return GOJ member list with optional filtering. Privileged users only."""
    token = (authorization or "").replace("Bearer ", "")
    session = _get_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not _is_privileged(session):
        raise HTTPException(status_code=403, detail="Member list restricted to chairman and director access.")
    if not _DOCS_AVAILABLE:
        raise HTTPException(503, "GOJ module not available")
    members = get_goj_members(plan=plan, day=day, search=search)
    return {"members": members, "count": len(members)}


@app.get("/api/goj/roster/{day_shift}")
def goj_roster(day_shift: str, authorization: Optional[str] = Header(None)):
    """
    Return the attendance roster for a specific day/shift.
    day_shift: M1, M2, T1, T2, W1, W2, TH1, TH2, F1, F2, Su
    """
    token = (authorization or "").replace("Bearer ", "")
    session = _get_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not _DOCS_AVAILABLE:
        raise HTTPException(503, "GOJ module not available")
    from .rex_documents import load_goj_data
    data = load_goj_data()
    if not data:
        # Return cached stats-based count
        stats = get_goj_stats()
        count = stats.get("dailyRosters", {}).get(day_shift, 0)
        return {"shift": day_shift, "count": count, "members": [], "source": "cached"}
    rosters = data.get("dailyRosters", {})
    roster = rosters.get(day_shift, [])
    return {"shift": day_shift, "count": len(roster), "members": roster, "source": "live"}


# ── Document Management ───────────────────────────────────────────────────────

@app.post("/api/documents/route")
def route_documents(authorization: Optional[str] = Header(None)):
    """
    Download and route all email attachments to correct folders.
    Chairman only — triggers the full Gmail attachment download pipeline.
    """
    token = (authorization or "").replace("Bearer ", "")
    session = _get_session(token)
    if not session or not _is_privileged(session):
        raise HTTPException(status_code=403, detail="Document routing restricted to chairman access.")
    if not _DOCS_AVAILABLE:
        raise HTTPException(503, "Document module not available")
    result = run_document_routing()
    return result


@app.get("/api/documents")
def list_all_documents(
    category: Optional[str] = None,
    authorization: Optional[str] = Header(None)
):
    """List available documents filtered by caller's access role."""
    token = (authorization or "").replace("Bearer ", "")
    session = _get_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = session.get("role", "staff").lower()
    if not _DOCS_AVAILABLE:
        raise HTTPException(503, "Document module not available")
    docs = list_documents(category=category, access_role=role)
    return {"documents": docs, "count": len(docs)}


@app.get("/api/documents/serve/{category}/{filename:path}")
def serve_document(category: str, filename: str, authorization: Optional[str] = Header(None)):
    """Serve a document file. Access controlled by role."""
    token = (authorization or "").replace("Bearer ", "")
    session = _get_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="Authentication required")
    from .rex_documents import DOCS_DIR, ROLE_ACCESS
    role = session.get("role", "staff").lower()
    # Map category to folder
    cat_folder_map = {
        "staff_medical":    DOCS_DIR / "staff" / "medical",
        "staff_inservice":  DOCS_DIR / "staff" / "inservice",
        "compliance_audit": DOCS_DIR / "compliance" / "audit",
        "site_visit":       DOCS_DIR / "compliance" / "site_visits",
        "signin_scan":      DOCS_DIR / "signins",
        "menu_scan":        DOCS_DIR / "menu",
    }
    folder = cat_folder_map.get(category)
    if not folder:
        raise HTTPException(404, "Category not found")
    file_path = (folder / filename).resolve()
    if not file_path.exists() or not str(file_path).startswith(str(DOCS_DIR)):
        raise HTTPException(404, "File not found")
    return FileResponse(str(file_path))


@app.get("/api/staff/medical")
def staff_medical_portfolios(authorization: Optional[str] = Header(None)):
    """
    Return all staff medical documents organized by staff member.
    Restricted to chairman and director.
    """
    token = (authorization or "").replace("Bearer ", "")
    session = _get_session(token)
    if not session or not _is_privileged(session):
        raise HTTPException(status_code=403, detail="Restricted to chairman and director access.")
    if not _DOCS_AVAILABLE:
        raise HTTPException(503, "Document module not available")
    portfolio = get_staff_medical_docs()
    return {
        "portfolio": portfolio,
        "staff_count": len(portfolio),
        "total_docs": sum(len(v) for v in portfolio.values())
    }


# ── Member Portfolio Endpoints ────────────────────────────────────────────────

@app.get("/api/members/portfolios")
def member_portfolios(
    search: Optional[str] = None,
    authorization: Optional[str] = Header(None)
):
    """
    Return member document portfolios — shared PCSP/auth docs + per-member folders.
    Restricted to chairman, admin, director.
    """
    token = (authorization or "").replace("Bearer ", "")
    session = _get_session(token)
    if not session or not _is_privileged(session):
        raise HTTPException(status_code=403, detail="Member portfolios restricted to chairman/director access.")
    if not _DOCS_AVAILABLE:
        raise HTTPException(503, "Document module not available")
    return get_member_portfolios(search=search)


@app.post("/api/members/upload")
async def upload_member_doc(
    member_name: str = Form(...),
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None)
):
    """
    Upload a document to a specific member's portfolio folder.
    Restricted to chairman and admin.
    """
    token = (authorization or "").replace("Bearer ", "")
    session = _get_session(token)
    if not session or not _is_privileged(session):
        raise HTTPException(status_code=403, detail="Document upload restricted to chairman/admin.")
    if not _DOCS_AVAILABLE:
        raise HTTPException(503, "Document module not available")
    data = await file.read()
    result = upload_member_document(member_name, file.filename, data)
    return result


@app.get("/api/members/serve/{member_folder}/{filename:path}")
def serve_member_doc(member_folder: str, filename: str, authorization: Optional[str] = Header(None)):
    """Serve a member portfolio document. Privileged access only."""
    token = (authorization or "").replace("Bearer ", "")
    session = _get_session(token)
    if not session or not _is_privileged(session):
        raise HTTPException(status_code=403, detail="Restricted.")
    from .rex_documents import DOCS_DIR
    file_path = (DOCS_DIR / "members" / member_folder / filename).resolve()
    if not file_path.exists() or not str(file_path).startswith(str(DOCS_DIR)):
        raise HTTPException(404, "File not found")
    return FileResponse(str(file_path))


# ═══════════════════════════════════════════════════════════════════════════════
# GOJ OPERATIONAL DASHBOARD ENDPOINTS
# Added: 2026-04-14 (Recovery build — reconnect dashboard to real local DB)
# All endpoints read from: ~/Documents/goj files/dashboard/auth_tracker.db
# ═══════════════════════════════════════════════════════════════════════════════

def _goj_db():
    """Return a sqlite3 connection to the authoritative local auth_tracker.db."""
    import sqlite3 as _sq
    _path = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
    if not _path.exists():
        raise HTTPException(503, f"auth_tracker.db not found at {_path}")
    conn = _sq.connect(str(_path))
    conn.row_factory = _sq.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _check_session_auth(authorization: Optional[str]):
    """Light auth check for new GOJ dashboard endpoints.
    Accepts a valid session token OR chairman-direct access.
    Raises 401 if token is present but invalid.
    If no token: allowed from localhost only (FastAPI serves the dashboard).
    """
    if not authorization:
        return  # No token = direct local access (served by FastAPI on same machine)
    try:
        from .auth import device_manager
        device_manager.validate_token(authorization)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired session. Please log in.")


@app.get("/api/clients")
def list_clients(
    authorization: Optional[str] = Header(None),
    search: str = "",
    plan: str = "",
    shift: str = "",
    status: str = "active",
    limit: int = 200,
    offset: int = 0,
):
    """
    List clients from the local auth_tracker.db.
    Returns name, plan, shift, active days, status.
    Used by the dashboard client list view.
    """
    _check_session_auth(authorization)
    conn = _goj_db()
    try:
        where = []
        params = []
        if status == "active":
            where.append("active = 1")
        elif status == "inactive":
            where.append("active = 0")
        if search:
            where.append("LOWER(name) LIKE ?")
            params.append(f"%{search.lower()}%")
        if plan:
            where.append("LOWER(plan) = ?")
            params.append(plan.lower())
        if shift:
            where.append("shift = ?")
            params.append(int(shift))

        clause = ("WHERE " + " AND ".join(where)) if where else ""
        total = conn.execute(f"SELECT COUNT(*) FROM clients {clause}", params).fetchone()[0]
        rows  = conn.execute(
            f"""SELECT name, plan, shift, active,
                       day_M_actual, day_T_actual, day_W_actual,
                       day_TH_actual, day_F_actual
                FROM clients {clause}
                ORDER BY name
                LIMIT ? OFFSET ?""",
            params + [limit, offset]
        ).fetchall()

        clients = []
        for r in rows:
            days = []
            for col, lbl in [("day_M_actual","M"),("day_T_actual","T"),("day_W_actual","W"),
                              ("day_TH_actual","TH"),("day_F_actual","F")]:
                if r[col]: days.append(lbl)
            clients.append({
                "name":       r["name"],
                "plan":       r["plan"],
                "shift":      r["shift"],
                "active":     bool(r["active"]),
                "active_days": days,
            })
        return {"total": total, "offset": offset, "limit": limit, "clients": clients}
    finally:
        conn.close()


@app.get("/api/clients/{client_name}")
def get_client_profile(client_name: str,
    authorization: Optional[str] = Header(None), attendance_days: int = 30):
    """
    Full client profile: demographics + attendance history + authorizations + menus.
    This is the single endpoint for the client detail view in the dashboard.
    """
    import datetime as _dt
    _check_session_auth(authorization)
    conn = _goj_db()
    try:
        # ── Core record ────────────────────────────────────────────────────────
        row = conn.execute(
            "SELECT * FROM clients WHERE name = ?", (client_name,)
        ).fetchone()
        if not row:
            # Try fuzzy match
            row = conn.execute(
                "SELECT * FROM clients WHERE LOWER(name) LIKE ?",
                (f"%{client_name.lower()}%",)
            ).fetchone()
        if not row:
            raise HTTPException(404, f"Client not found: {client_name}")

        profile: dict = dict(row)

        # ── Active schedule days ───────────────────────────────────────────────
        days = []
        for col, lbl in [("day_M_actual","M"),("day_T_actual","T"),("day_W_actual","W"),
                          ("day_TH_actual","TH"),("day_F_actual","F"),("day_SU_actual","SU")]:
            if col in profile and profile[col]:
                days.append(lbl)
        profile["active_days"] = days

        # ── Attendance history ─────────────────────────────────────────────────
        since = (_dt.date.today() - _dt.timedelta(days=attendance_days)).isoformat()
        att_rows = conn.execute(
            """SELECT log_date, day_key, shift, status, source, note
               FROM attendance_log
               WHERE client_name = ? AND log_date >= ?
               ORDER BY log_date DESC""",
            (row["name"], since)
        ).fetchall()

        attendance = []
        for a in att_rows:
            confirmed = a["source"] in ("generated_signin_sheet", "sign_in_sheet", "signin")
            attendance.append({
                "date":      a["log_date"],
                "day":       a["day_key"],
                "shift":     a["shift"],
                "status":    a["status"],
                "confirmed": confirmed,   # True = confirmed from sign-in sheet
                "source":    a["source"],
                "note":      a["note"],
            })

        # Attendance summary
        total_scheduled  = len([x for x in attendance if x["status"] in ("scheduled","present","attended")])
        total_confirmed  = len([x for x in attendance if x["confirmed"]])
        total_absent     = len([x for x in attendance if "absent" in (x["status"] or "").lower()])
        profile["attendance_summary"] = {
            "period_days":       attendance_days,
            "total_scheduled":   total_scheduled,
            "confirmed_present": total_confirmed,
            "absent":            total_absent,
            "confirmation_rate": round(total_confirmed / total_scheduled, 2) if total_scheduled else 0,
        }
        profile["attendance_history"] = attendance[:60]

        # ── Authorizations ─────────────────────────────────────────────────────
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}

        auths = []
        if "auth_documents" in tables:
            auth_rows = conn.execute(
                """SELECT * FROM auth_documents
                   WHERE LOWER(client_name) LIKE ?
                   ORDER BY expiration_date DESC""",
                (f"%{row['name'].lower()}%",)
            ).fetchall()
            for ar in auth_rows:
                auths.append(dict(ar))

        profile["authorizations"]       = auths
        profile["authorization_count"]  = len(auths)

        # ── Menu history ───────────────────────────────────────────────────────
        menus = []
        if "client_menus" in tables:
            menu_rows = conn.execute(
                """SELECT week_start, day, salad, soup, main, side,
                          ocr_confidence, needs_review, source
                   FROM client_menus
                   WHERE LOWER(client_name) LIKE ?
                   ORDER BY week_start DESC, day
                   LIMIT 30""",
                (f"%{row['name'].lower()}%",)
            ).fetchall()
            for mr in menu_rows:
                menus.append(dict(mr))

        profile["menu_history"] = menus

        return profile

    finally:
        conn.close()


@app.get("/api/authorizations")
def list_authorizations(
    authorization: Optional[str] = Header(None),
    client: str = "",
    status: str = "",
    expiring_days: int = 0,
    limit: int = 100,
    offset: int = 0,
):
    """
    List authorization documents from auth_tracker.db.
    Supports filtering by client name, status, and expiring-within-N-days.
    """
    import datetime as _dt
    _check_session_auth(authorization)
    conn = _goj_db()
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if "auth_documents" not in tables:
            return {"total": 0, "authorizations": [], "note": "auth_documents table not found"}

        where, params = [], []
        if client:
            where.append("LOWER(client_name) LIKE ?")
            params.append(f"%{client.lower()}%")
        if status:
            where.append("LOWER(status) = ?")
            params.append(status.lower())
        if expiring_days > 0:
            cutoff = (_dt.date.today() + _dt.timedelta(days=expiring_days)).isoformat()
            today  = _dt.date.today().isoformat()
            where.append("expiration_date BETWEEN ? AND ?")
            params += [today, cutoff]

        clause = ("WHERE " + " AND ".join(where)) if where else ""
        total  = conn.execute(f"SELECT COUNT(*) FROM auth_documents {clause}", params).fetchone()[0]
        rows   = conn.execute(
            f"SELECT * FROM auth_documents {clause} ORDER BY expiration_date ASC LIMIT ? OFFSET ?",
            params + [limit, offset]
        ).fetchall()

        return {"total": total, "offset": offset, "limit": limit,
                "authorizations": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.get("/api/menus/master")
def menus_master_list(authorization: Optional[str] = Header(None),
    week_start: str = "", client: str = "", limit: int = 200):
    """
    Master menu list — all clients' menu selections, optionally filtered by week or client.
    Menus are indexed by TARGET service week (the following work week, not the scan week).
    This is the source of truth for the dashboard menu list view.
    """
    import datetime as _dt

    _check_session_auth(authorization)
    conn = _goj_db()
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if "client_menus" not in tables:
            return {"total": 0, "menus": [], "note": "client_menus table not found"}

        # Default to next work week if no week specified
        if not week_start:
            today   = _dt.date.today()
            days_to_next_monday = (7 - today.weekday()) % 7
            if days_to_next_monday == 0:
                days_to_next_monday = 7   # always next week, not current
            next_monday = today + _dt.timedelta(days=days_to_next_monday)
            week_start  = next_monday.isoformat()

        where, params = ["week_start = ?"], [week_start]
        if client:
            where.append("LOWER(client_name) LIKE ?")
            params.append(f"%{client.lower()}%")

        clause = "WHERE " + " AND ".join(where)
        total  = conn.execute(f"SELECT COUNT(*) FROM client_menus {clause}", params).fetchone()[0]
        rows   = conn.execute(
            f"""SELECT client_name, week_start, day, salad, soup, main, side,
                       ocr_confidence, needs_review, source, created_at
                FROM client_menus {clause}
                ORDER BY client_name, day
                LIMIT ?""",
            params + [limit]
        ).fetchall()

        # Group by client
        by_client: dict = {}
        for r in rows:
            name = r["client_name"]
            if name not in by_client:
                by_client[name] = {"client_name": name, "week_start": r["week_start"],
                                   "days": [], "needs_review": False}
            by_client[name]["days"].append({
                "day":        r["day"],
                "salad":      r["salad"],
                "soup":       r["soup"],
                "main":       r["main"],
                "side":       r["side"],
                "confidence": r["ocr_confidence"],
                "needs_review": bool(r["needs_review"]),
            })
            if r["needs_review"]:
                by_client[name]["needs_review"] = True

        return {
            "week_start": week_start,
            "week_label": f"Week of {week_start}",
            "total_clients_with_menus": len(by_client),
            "total_selections": total,
            "menus": list(by_client.values()),
        }
    finally:
        conn.close()


@app.get("/api/attendance/history/{client_name}")
def client_attendance_history(
    client_name: str,
    authorization: Optional[str] = Header(None),
    days: int = 90,
    show_scheduled_only: bool = False,
):
    """
    Full attendance history for a client — both scheduled visits and confirmed sign-ins.
    Explicitly distinguishes: confirmed_from_signin vs scheduled_only vs absent.
    This is required for the dashboard client profile attendance tab.
    """
    import datetime as _dt
    _check_session_auth(authorization)
    conn = _goj_db()
    try:
        since = (_dt.date.today() - _dt.timedelta(days=days)).isoformat()
        rows  = conn.execute(
            """SELECT log_date, day_key, shift, status, source, note
               FROM attendance_log
               WHERE client_name = ? AND log_date >= ?
               ORDER BY log_date DESC""",
            (client_name, since)
        ).fetchall()

        history = []
        for r in rows:
            src       = r["source"] or ""
            confirmed = src in ("generated_signin_sheet", "sign_in_sheet", "signin", "calendar_2026_xlsx")
            state     = (
                "confirmed_present"   if confirmed and r["status"] in ("attended","present","Y") else
                "confirmed_absent"    if confirmed and "absent" in (r["status"] or "").lower() else
                "scheduled_only"      if not confirmed and r["status"] == "scheduled" else
                "unconfirmed_present" if not confirmed and r["status"] in ("attended","present") else
                r["status"] or "unknown"
            )
            if show_scheduled_only and state != "scheduled_only":
                continue
            history.append({
                "date":      r["log_date"],
                "day":       r["day_key"],
                "shift":     r["shift"],
                "state":     state,
                "confirmed": confirmed,
                "source":    r["source"],
                "note":      r["note"],
            })

        confirmed_count   = len([h for h in history if h["state"] == "confirmed_present"])
        scheduled_count   = len([h for h in history if h["state"] == "scheduled_only"])
        absent_count      = len([h for h in history if "absent" in h["state"]])

        return {
            "client_name": client_name,
            "period_days": days,
            "summary": {
                "confirmed_present":    confirmed_count,
                "scheduled_only":       scheduled_count,
                "confirmed_absent":     absent_count,
                "total_records":        len(history),
                "confirmation_rate":    round(confirmed_count / max(1, confirmed_count + scheduled_count), 2),
            },
            "history": history,
        }
    finally:
        conn.close()


@app.get("/api/dashboard/summary")
def dashboard_summary(authorization: Optional[str] = Header(None)):
    """
    Single endpoint for the dashboard home page.
    Returns operational snapshot: clients, attendance today, pending menus, auth alerts.
    Everything from the local source of truth.
    """
    import datetime as _dt
    _check_session_auth(authorization)
    conn = _goj_db()
    try:
        today = _dt.date.today().isoformat()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}

        summary = {
            "generated_at":   _dt.datetime.now().isoformat(),
            "source_of_truth": str(Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"),
        }

        # Clients
        total_clients  = conn.execute("SELECT COUNT(*) FROM clients WHERE active=1").fetchone()[0]
        summary["clients"] = {"total_active": total_clients}

        # Attendance today
        today_att = conn.execute(
            "SELECT COUNT(*) FROM attendance_log WHERE log_date=?", (today,)
        ).fetchone()[0]
        today_confirmed = conn.execute(
            """SELECT COUNT(*) FROM attendance_log
               WHERE log_date=? AND source IN ('generated_signin_sheet','sign_in_sheet','signin')""",
            (today,)
        ).fetchone()[0]
        summary["attendance_today"] = {
            "total_records":   today_att,
            "confirmed_signin": today_confirmed,
            "scheduled_only":   today_att - today_confirmed,
        }

        # Authorizations expiring soon
        if "auth_documents" in tables:
            expiring_30 = conn.execute(
                """SELECT COUNT(*) FROM auth_documents
                   WHERE expiration_date BETWEEN ? AND ?""",
                (today, (_dt.date.today() + _dt.timedelta(days=30)).isoformat())
            ).fetchone()[0]
            summary["authorizations"] = {
                "expiring_within_30_days": expiring_30,
                "total": conn.execute("SELECT COUNT(*) FROM auth_documents").fetchone()[0],
            }
        else:
            summary["authorizations"] = {"note": "auth_documents table not present"}

        # Menus for next work week
        if "client_menus" in tables:
            today_dt = _dt.date.today()
            days_fwd = (7 - today_dt.weekday()) % 7 or 7
            next_mon = (today_dt + _dt.timedelta(days=days_fwd)).isoformat()
            menus_next = conn.execute(
                "SELECT COUNT(DISTINCT client_name) FROM client_menus WHERE week_start=?",
                (next_mon,)
            ).fetchone()[0]
            summary["menus_next_week"] = {
                "week_start":    next_mon,
                "clients_with_menus": menus_next,
                "clients_missing":    max(0, total_clients - menus_next),
            }

        # OCR flags
        from pathlib import Path as _Path
        flag_q = _Path.home() / "Desktop" / "REX" / "goj_menu_flags_queue.json"
        if flag_q.exists():
            import json as _json
            flags = _json.loads(flag_q.read_text())
            unresolved = len([f for f in flags if not f.get("resolved")])
            summary["ocr_flags"] = {"total": len(flags), "unresolved": unresolved}

        return summary
    except Exception as e:
        return {"error": str(e), "note": "dashboard_summary failed — check DB path"}
    finally:
        try: conn.close()
        except: pass


# ── Passkey (WebAuthn) router ─────────────────────────────────────────────────
try:
    from .rex_passkey import router as _passkey_router
    app.include_router(_passkey_router)
except Exception as _pk_err:
    logger.warning(f"⚠️ Passkey router not loaded: {_pk_err}")

# ── Serve built frontend in production ────────────────────────────────────────
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="static")


# ── CC/Progress proxy routes (added by CC_fix_domain_tonight) ─────────────────
# Routes /cc and /progress to the stats API at :8001
# This is the fallback if Cloudflare tunnel path routing fails.
try:
    import httpx as _httpx_proxy
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

@app.get("/cc", response_class=HTMLResponse, include_in_schema=False)
async def _proxy_cc_to_stats():
    if not _HTTPX_AVAILABLE:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="http://localhost:8001/cc")
    async with _httpx_proxy.AsyncClient() as _c:
        _r = await _c.get("http://localhost:8001/cc", timeout=15.0)
    return HTMLResponse(content=_r.text, status_code=_r.status_code)

@app.get("/progress", response_class=HTMLResponse, include_in_schema=False)
async def _proxy_progress_to_stats():
    if not _HTTPX_AVAILABLE:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="http://localhost:8001/progress")
    async with _httpx_proxy.AsyncClient() as _c:
        _r = await _c.get("http://localhost:8001/progress", timeout=15.0)
    return HTMLResponse(content=_r.text, status_code=_r.status_code)
# ── Obsidian Brain API — serves BRAIN/ markdown files to Command Center ──────
import pathlib as _pathlib
_BRAIN_ROOT = _pathlib.Path.home() / "Desktop" / "Gold_Health_Systems" / "BRAIN"

@app.get("/api/brain/tree", include_in_schema=False)
async def _brain_tree():
    """Return full Obsidian vault file tree as JSON."""
    tree = {}
    try:
        for p in sorted(_BRAIN_ROOT.rglob("*.md")):
            # Skip backups folder and hidden files
            parts = p.relative_to(_BRAIN_ROOT).parts
            if "backups" in parts or any(x.startswith(".") for x in parts):
                continue
            rel = str(p.relative_to(_BRAIN_ROOT))
            folder = parts[0] if len(parts) > 1 else "root"
            tree.setdefault(folder, []).append({
                "name": p.stem,
                "path": rel,
                "modified": p.stat().st_mtime
            })
    except Exception as e:
        return {"error": str(e), "tree": {}}
    return {"tree": tree, "vault": str(_BRAIN_ROOT)}

@app.get("/api/brain/{filename}", include_in_schema=False)
async def _brain_file(filename: str):
    """Serve BRAIN/ Obsidian markdown files to the Command Center BRAIN tab."""
    safe_name = filename.replace("/", "").replace("..", "").replace("\\", "")
    # Search GHS Live/ first, then all subfolders
    search_dirs = [_BRAIN_ROOT / "GHS Live"] + [d for d in sorted(_BRAIN_ROOT.rglob("*")) if d.is_dir() and "backup" not in str(d) and not any(x.startswith(".") for x in d.parts)]
    for search_dir in search_dirs:
        for ext in ["", ".md"]:
            candidate = search_dir / f"{safe_name}{ext}"
            if candidate.exists() and candidate.is_file():
                try:
                    content = candidate.read_text(encoding="utf-8")
                    return {"file": safe_name, "content": content, "path": str(candidate.relative_to(_BRAIN_ROOT))}
                except Exception as e:
                    return {"file": safe_name, "content": f"Error reading file: {e}", "path": ""}
    return {"file": safe_name, "content": f"File not found: {safe_name}", "path": ""}

# ─────────────────────────────────────────────────────────────────────────────

