#!/usr/bin/env python3
"""Rexxie Portal — premium web interface with streaming, uploads, vision, voice.
FastAPI + SSE streaming + model router. Port 8420.
ADDED: Session management (create/merge/divert), persistent chat history."""
assert __name__ == '__main__'

import json, time, os, base64, hashlib, threading, sqlite3, uuid
from pathlib import Path
from datetime import datetime

import requests
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

app = FastAPI(title="Rexxie Portal")

# ── Paths ──
BASE = Path("/Users/mainsobhelper/Desktop/REX")
VAULT_INDEX = BASE / ".rexxie_vault_index.md"
PERPETUAL = Path("/Users/mainsobhelper/GHS-Vault/Jarvis Perpetual Memory.md")
UPLOADS = BASE / "uploads"
SETTINGS_FILE = BASE / "rexxie_portal_config.json"
LOG = BASE / "logs" / "rexxie_portal.log"
SESSIONS_DB = BASE / "rexxie_sessions.db"

UPLOADS.mkdir(exist_ok=True)
LOG.parent.mkdir(exist_ok=True)

# ── Sessions DB ──
def init_sessions_db():
    conn = sqlite3.connect(str(SESSIONS_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            parent_id TEXT,
            title TEXT DEFAULT 'New Chat',
            created_at REAL,
            updated_at REAL,
            fork_point INTEGER DEFAULT 0,
            merged_ids TEXT DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            model TEXT,
            elapsed REAL DEFAULT 0,
            timestamp REAL,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        )
    """)
    conn.commit()
    conn.close()

init_sessions_db()

def db():
    return sqlite3.connect(str(SESSIONS_DB))

# ── Models ──
# HARD RULE: every session is LOCKED to a model at creation. No silent fallback.
# A Gemma 12B chat only ever talks to Gemma 12B — if its backend is offline,
# the stream errors clearly instead of melting into another model.
MODELS = {
    "gemma-12b": {
        "name": "Gemma 12B Heretic", "short": "12B",
        "ollama": "http://127.0.0.1:11435",
        "model": "jikepjikep_16HEX/gemma-4-12b-nightshift-heretic-uncensored-qat-q4",
        "host": "Office Mac", "color": "#7bc98e",
    },
    "llama-3b": {
        "name": "Llama 3.2 3B", "short": "3B",
        "ollama": "http://127.0.0.1:11434",
        "model": "llama3.2:3b",
        "host": "Home Mac", "color": "#6aa8d8",
    },
    "gemma-vision": {
        "name": "Gemma 4B Vision", "short": "VIS",
        "ollama": "http://127.0.0.1:11434",
        "model": "gemma3:4b",
        "host": "Home Mac", "color": "#c9a86a",
        "vision": True,
    },
}
DEFAULT_MODEL_KEY = "gemma-12b"
OLLAMA_PRIMARY = MODELS[DEFAULT_MODEL_KEY]["ollama"]
MODEL_PRIMARY = MODELS[DEFAULT_MODEL_KEY]["model"]

def model_online(key):
    m = MODELS.get(key)
    if not m: return False
    try:
        r = requests.get(f"{m['ollama']}/api/version", timeout=3)
        return r.status_code == 200
    except: return False

_status_cache = {"t": 0, "data": None}
def models_status_cached(ttl=15):
    now = time.time()
    if _status_cache["data"] and now - _status_cache["t"] < ttl:
        return _status_cache["data"]
    out = [{"key": k, "name": m["name"], "short": m["short"], "host": m["host"],
            "color": m["color"], "online": model_online(k), "default": k == DEFAULT_MODEL_KEY,
            "vision": bool(m.get("vision"))}
           for k, m in MODELS.items()]
    _status_cache["t"] = now
    _status_cache["data"] = out
    return out

def get_session_model_key(sid):
    if sid:
        try:
            conn = db()
            row = conn.execute("SELECT model FROM sessions WHERE id=?", (sid,)).fetchone()
            conn.close()
            if row and row[0] in MODELS: return row[0]
        except: pass
    return DEFAULT_MODEL_KEY

def migrate_sessions_db():
    conn = db()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()]
    if "model" not in cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN model TEXT DEFAULT ''")
        conn.execute("UPDATE sessions SET model=? WHERE model=''", (DEFAULT_MODEL_KEY,))
    mcols = [r[1] for r in conn.execute("PRAGMA table_info(messages)").fetchall()]
    if "attachment" not in mcols:
        conn.execute("ALTER TABLE messages ADD COLUMN attachment TEXT DEFAULT ''")
    conn.commit()
    conn.close()

migrate_sessions_db()

# ── Auth ──
import asyncio, hashlib, json, os, secrets, sys, time as time_mod
import webauthn
from webauthn import generate_registration_options, verify_registration_response
from webauthn import generate_authentication_options, verify_authentication_response
from webauthn.helpers.structs import (
    RegistrationCredential, AuthenticationCredential,
    AuthenticatorSelectionCriteria, UserVerificationRequirement,
)
from webauthn.helpers import bytes_to_base64url

AUTH_PASSWORD = "rexxie"
AUTH_FILE = BASE / ".rexxie_auth"
WEBAUTHN_FILE = BASE / ".rexxie_webauthn.json"
sessions_store = {}

TOKENS_FILE = BASE / ".rexxie_tokens.json"

def _save_tokens():
    try: TOKENS_FILE.write_text(json.dumps(sessions_store))
    except: pass

def _load_tokens():
    global sessions_store
    try:
        if TOKENS_FILE.exists():
            data = json.loads(TOKENS_FILE.read_text())
            now = time.time()
            sessions_store = {t: e for t, e in data.items() if e > now}
    except: sessions_store = {}

_load_tokens()

RP_ID = "rexxie.hermestigerclaw.com"
RP_NAME = "Rexxie"
ORIGIN = "https://rexxie.hermestigerclaw.com"

def check_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest() == hashlib.sha256(AUTH_PASSWORD.encode()).hexdigest()

def create_session():
    token = secrets.token_hex(32)
    sessions_store[token] = time_mod.time() + 86400 * 30
    _save_tokens()
    return token

def validate_session(token):
    if not token: return False
    t = sessions_store.get(token, 0)
    if t < time_mod.time():
        sessions_store.pop(token, None)
        _save_tokens()
        return False
    return True

def log(msg):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG, "a") as f:
            f.write(f"{now} {msg}\n")
    except: pass
    print(f"{now} {msg}", flush=True)

# ── Config ──
DEFAULTS = {
    "default_model": "fast",
    "stream": True,
    "theme": "dark",
    "voice_enabled": True,
    "temperature": 0.7,
    "max_history": 40,
}

def load_settings():
    global SETTINGS
    try:
        if SETTINGS_FILE.exists():
            SETTINGS = json.loads(SETTINGS_FILE.read_text())
        else:
            SETTINGS = {}
    except: SETTINGS = {}
    for k, v in DEFAULTS.items():
        SETTINGS.setdefault(k, v)

load_settings()

def load_perpetual():
    try:
        if PERPETUAL.exists():
            return PERPETUAL.read_text()[-2000:]
    except: pass
    return ""

def load_vault_index():
    try:
        with open(VAULT_INDEX) as f:
            return f.read()[:2000]
    except: return ""

SYSTEM = """You are Rexxie, Kato's personal assistant. Fully local and private.
Same employment contract, 2-source rule, and personality as always.
Answer first. Bad news upfront. Brief by default. No filler. No inventions."""

def build_prompt(user_text=""):
    p = SETTINGS.get("system_prompt") or SYSTEM
    p += "\n\nPerpetual Memory:\n" + load_perpetual()
    p += "\n\nVault Index:\n" + load_vault_index()
    return p

# ── Session Routes ──
@app.get("/sessions")
async def list_sessions(request: Request, offset: int = 0, limit: int = 30):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not validate_session(token):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    limit = max(1, min(limit, 100))
    conn = db()
    total = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    rows = conn.execute("SELECT id, parent_id, title, created_at, updated_at, merged_ids, model FROM sessions ORDER BY updated_at DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    conn.close()
    return {"total": total, "sessions": [
        {"id": r[0], "parent_id": r[1], "title": r[2], "created_at": r[3], "updated_at": r[4], "merged_ids": r[5],
         "model": r[6] if r[6] in MODELS else DEFAULT_MODEL_KEY}
        for r in rows
    ]}

@app.post("/sessions")
async def create_session_route(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not validate_session(token):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    sid = str(uuid.uuid4())
    parent = body.get("parent_id", "")
    model_key = body.get("model", DEFAULT_MODEL_KEY)
    if model_key not in MODELS: model_key = DEFAULT_MODEL_KEY
    now = time.time()
    conn = db()
    if parent:
        # get fork_point + inherit parent's model lock (a fork never changes model)
        parent_row = conn.execute("SELECT updated_at, model FROM sessions WHERE id=?", (parent,)).fetchone()
        fork_point = 0
        if parent_row:
            if parent_row[1] in MODELS: model_key = parent_row[1]
            fp_row = conn.execute("SELECT COUNT(*) FROM messages WHERE session_id=?", (parent,)).fetchone()
            fork_point = fp_row[0] if fp_row else 0
        conn.execute("INSERT INTO sessions (id, parent_id, title, created_at, updated_at, fork_point, model) VALUES (?,?,?,?,?,?,?)",
                     (sid, parent, body.get("title", "New Chat"), now, now, fork_point, model_key))
        # A fork inherits the parent's full history (model stamps preserved) — never its lock
        src_msgs = conn.execute("SELECT role, content, model, elapsed, timestamp, attachment FROM messages WHERE session_id=? ORDER BY id", (parent,)).fetchall()
        for sm in src_msgs:
            conn.execute("INSERT INTO messages (session_id, role, content, model, elapsed, timestamp, attachment) VALUES (?,?,?,?,?,?,?)",
                         (sid, sm[0], sm[1], sm[2], sm[3], sm[4], sm[5]))
    else:
        conn.execute("INSERT INTO sessions (id, title, created_at, updated_at, model) VALUES (?,?,?,?,?)",
                     (sid, body.get("title", "New Chat"), now, now, model_key))
    conn.commit()
    conn.close()
    return {"id": sid, "model": model_key}

@app.post("/sessions/merge")
async def merge_sessions(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not validate_session(token):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    body = await request.json()
    target = body.get("target_id")
    sources = body.get("source_ids", [])
    if not target or not sources:
        return JSONResponse({"error": "target_id and source_ids required"}, status_code=400)
    conn = db()
    conn.execute("UPDATE sessions SET merged_ids=? WHERE id=?", (",".join(sources), target))
    # Copy messages from sources into target (attachments keep their references)
    for src in sources:
        msgs = conn.execute("SELECT role, content, model, elapsed, timestamp, attachment FROM messages WHERE session_id=? ORDER BY id", (src,)).fetchall()
        for m in msgs:
            conn.execute("INSERT INTO messages (session_id, role, content, model, elapsed, timestamp, attachment) VALUES (?,?,?,?,?,?,?)",
                         (target, m[0], m[1], m[2], m[3], m[4], m[5]))
    conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (time.time(), target))
    conn.commit()
    conn.close()
    return {"status": "merged", "sources": sources}

@app.get("/sessions/{sid}/messages")
async def get_messages(sid: str, request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not validate_session(token):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = db()
    rows = conn.execute(
        "SELECT id, role, content, model, elapsed, timestamp, attachment FROM messages WHERE session_id=? ORDER BY id",
        (sid,)
    ).fetchall()
    conn.close()
    return {"messages": [{"id": r[0], "role": r[1], "content": r[2], "model": r[3], "elapsed": r[4], "timestamp": r[5], "attachment": r[6]} for r in rows]}

@app.put("/sessions/{sid}")
async def update_session(sid: str, request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not validate_session(token):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    body = await request.json()
    title = body.get("title")
    conn = db()
    if title:
        conn.execute("UPDATE sessions SET title=?, updated_at=? WHERE id=?", (title, time.time(), sid))
    else:
        conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (time.time(), sid))
    conn.commit()
    conn.close()
    return {"status": "updated"}

@app.delete("/sessions/{sid}")
async def delete_session(sid: str, request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not validate_session(token):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = db()
    conn.execute("DELETE FROM messages WHERE session_id=?", (sid,))
    conn.execute("DELETE FROM sessions WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}

# ── Thinking Model for thought breakdown ──
import re

def stream_with_thoughts(messages, user_text="", model_key=DEFAULT_MODEL_KEY, attachment=None):
    """SSE stream: 'thought' events for thinking tokens, 'token' events for visible output.
    Session model lock is enforced here — offline backend = clear error, NEVER fallback.
    attachment: {saved_as, name, type} from /upload — images go to the model's vision, text files inline."""
    m = MODELS.get(model_key, MODELS[DEFAULT_MODEL_KEY])
    meta = {"model_key": model_key, "name": m["name"], "short": m["short"], "host": m["host"], "color": m["color"]}

    if not model_online(model_key):
        yield {"event": "error", "data": json.dumps({
            "error": f"{m['name']} ({m['host']}) is offline. This chat is locked to {m['name']} — no fallback, so your chats never mix.",
            "model_offline": True, **meta})}
        return

    ollama_url, model_name = m["ollama"], m["model"]
    yield {"event": "meta", "data": json.dumps(meta)}

    prompt = build_prompt(user_text)
    full = [{"role": "system", "content": prompt}] + messages

    user_msg = {"role": "user", "content": user_text}
    if attachment and isinstance(attachment, dict):
        saved = os.path.basename(attachment.get("saved_as", ""))
        fpath = UPLOADS / saved if saved else None
        atype = attachment.get("type", "")
        aname = attachment.get("name", saved)
        try:
            if atype == "image" and fpath and fpath.exists():
                b64 = base64.b64encode(fpath.read_bytes()).decode()
                ext = fpath.suffix.lower().lstrip(".") or "png"
                if ext == "jpg": ext = "jpeg"
                user_msg["content"] = [
                    {"type": "text", "text": user_text or "Describe this image."},
                    {"type": "image_url", "image_url": {"url": f"data:image/{ext};base64,{b64}"}},
                ]
            elif fpath and fpath.exists() and fpath.suffix.lower() in (".txt", ".md", ".csv", ".log"):
                txt = fpath.read_text(errors="ignore")[:3000]
                user_msg["content"] = f"[Attached file: {aname}]\n{txt}\n\n{user_text}"
            elif fpath and fpath.exists():
                user_msg["content"] = f"[Attached: {aname} — saved to uploads/{saved}]\n\n{user_text}"
        except Exception as e:
            log(f"attachment error: {e}")
    full.append(user_msg)

    t0 = time.time()
    model_short = model_name.split("/")[-1][:20]

    try:
        r = requests.post(f"{ollama_url}/v1/chat/completions", json={
            "model": model_name, "messages": full,
            "max_tokens": 4096,
            "options": {"num_ctx": 8192},
            "stream": True,
            "temperature": SETTINGS.get("temperature", 0.7),
        }, timeout=300, stream=True)

        if r.status_code != 200:
            err_txt = ""
            try: err_txt = r.text[:400]
            except: pass
            if "multimodal" in err_txt.lower():
                yield {"event": "error", "data": json.dumps({
                    "error": f"{m['name']} is a text-only build — it can't see images. No vision model is installed yet; ask Kato to add one.",
                    **meta})}
            else:
                yield {"event": "error", "data": json.dumps({
                    "error": f"Model backend error {r.status_code}: {err_txt[:140]}", **meta})}
            return

        thought_buf = []
        token_buf = []
        in_thinking = False
        thought_open = False

        for line in r.iter_lines():
            if not line: continue
            try:
                chunk = json.loads(line.decode().lstrip("data: ").strip())
                choice = chunk.get("choices", [{}])[0]
                delta = choice.get("delta", {}) or choice.get("message", {})
                finish = choice.get("finish_reason")

                # Check for reasoning/thinking field
                reasoning = delta.get("reasoning", "") or delta.get("reasoning_content", "")
                content = delta.get("content", "")

                if reasoning:
                    if not thought_open:
                        yield {"event": "thought_start", "data": json.dumps({"text": ""})}
                        thought_open = True
                    thought_buf.append(reasoning)
                    yield {"event": "thought", "data": json.dumps({"token": reasoning})}

                if content:
                    if thought_open:
                        yield {"event": "thought_end", "data": json.dumps({"text": "".join(thought_buf)})}
                        thought_open = False
                    token_buf.append(content)
                    yield {"event": "token", "data": json.dumps({"token": content})}

                if finish:
                    if thought_open:
                        yield {"event": "thought_end", "data": json.dumps({"text": "".join(thought_buf)})}
                    break
            except: continue

        full_content = "".join(token_buf)
        elapsed = time.time() - t0
        log(f"[{model_short}] {len(full_content)} chars in {elapsed:.1f}s")
        yield {"event": "done", "data": json.dumps({
            "content": full_content, "model": m["short"], "model_key": model_key,
            "model_name": m["name"], "host": m["host"],
            "thoughts": "".join(thought_buf), "elapsed": round(elapsed, 1)
        })}

    except Exception as e:
        log(f"ERROR: {e}")
        yield {"event": "error", "data": json.dumps({"error": f"Rexxie needs a moment. {str(e)[:80]}"})}

@app.get("/", response_class=HTMLResponse)
async def index():
    return load_html()

@app.get("/health")
async def health():
    return {"status": "ok", "primary": MODEL_PRIMARY.split("/")[-1], "default_model_key": DEFAULT_MODEL_KEY}

@app.get("/models/status")
async def models_status():
    return {"models": models_status_cached()}

@app.get("/icon.svg")
async def icon():
    from fastapi.responses import FileResponse
    return FileResponse(BASE / "rexxie_icon.svg", media_type="image/svg+xml")

@app.get("/manifest.json")
async def manifest():
    return {
        "name": "Rexxie", "short_name": "Rexxie",
        "start_url": "/", "display": "standalone",
        "background_color": "#0a0a0f", "theme_color": "#0a0a0f",
        "description": "Your fully local personal AI assistant",
        "icons": [{"src": "/icon.svg", "sizes": "512x512", "type": "image/svg+xml"}]
    }

# ── Auth routes ──
@app.post("/auth/login")
async def auth_login(request: Request):
    body = await request.json()
    pw = body.get("password", "")
    if check_password(pw):
        token = create_session()
        return {"token": token}
    return JSONResponse({"error": "Invalid password"}, status_code=401)

@app.post("/auth/validate")
async def auth_validate(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    return {"valid": validate_session(token)}

# ── WebAuthn ──
challenge_store = {}

def load_webauthn_cred():
    if WEBAUTHN_FILE.exists():
        return json.loads(WEBAUTHN_FILE.read_text())
    return None

def save_webauthn_cred(cred):
    WEBAUTHN_FILE.write_text(json.dumps(cred))

@app.get("/auth/webauthn/status")
async def webauthn_status():
    cred = load_webauthn_cred()
    return {"registered": cred is not None}

@app.post("/auth/webauthn/register/start")
async def webauthn_register_start(request: Request):
    body = await request.json()
    origin = body.get("origin", ORIGIN)
    rp_id = body.get("rpId", RP_ID)
    options = generate_registration_options(
        rp_id=rp_id, rp_name=RP_NAME,
        user_id=b"rexxie-user", user_name="Kato", user_display_name="Kato",
        authenticator_selection=AuthenticatorSelectionCriteria(
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    challenge_store["reg"] = options.challenge
    return json.loads(webauthn.options_to_json(options))

import base64 as b64_mod

@app.post("/auth/webauthn/register/finish")
async def webauthn_register_finish(request: Request):
    body = await request.json()
    origin = body.get("origin", ORIGIN)
    rp_id = body.get("rpId", RP_ID)
    credential = body.get("credential", {})
    try:
        # Decode base64 strings to bytes for the webauthn library
        def b64_to_bytes(s):
            if isinstance(s, bytes): return s
            if isinstance(s, str):
                return b64_mod.urlsafe_b64decode(s + '===' if len(s) % 4 else s)
            return s

        raw_id = credential.get("rawId", credential.get("id", ""))
        verification = verify_registration_response(
            credential=RegistrationCredential(
                id=credential["id"],
                raw_id=b64_to_bytes(raw_id),
                response={
                    "clientDataJSON": b64_to_bytes(credential.get("response", {}).get("clientDataJSON", "")),
                    "attestationObject": b64_to_bytes(credential.get("response", {}).get("attestationObject", "")),
                },
                type=credential.get("type", "public-key"),
            ),
            expected_challenge=challenge_store.get("reg", b""),
            expected_origin=origin, expected_rp_id=rp_id,
        )
        save_webauthn_cred({
            "credential_id": credential["id"],
            "public_key": bytes_to_base64url(verification.credential_public_key),
            "sign_count": verification.sign_count,
        })
        return {"id": credential["id"]}
    except Exception as e:
        log(f"WebAuthn register failed: {e}")
        return JSONResponse({"error": str(e)[:200]}, status_code=400)

@app.post("/auth/webauthn/login/start")
async def webauthn_login_start(request: Request):
    body = await request.json()
    origin = body.get("origin", ORIGIN)
    rp_id = body.get("rpId", RP_ID)
    cred = load_webauthn_cred()
    if not cred:
        return JSONResponse({"error": "Not registered"}, status_code=400)
    options = generate_authentication_options(
        rp_id=rp_id, user_verification=UserVerificationRequirement.REQUIRED,
    )
    from webauthn.helpers import base64url_to_bytes
    options_dict = json.loads(webauthn.options_to_json(options))
    options_dict["allowCredentials"] = [{"id": cred["credential_id"], "type": "public-key"}]
    challenge_store["auth"] = options.challenge
    return options_dict

@app.post("/auth/webauthn/login/finish")
async def webauthn_login_finish(request: Request):
    body = await request.json()
    origin = body.get("origin", ORIGIN)
    rp_id = body.get("rpId", RP_ID)
    credential = body.get("credential", {})
    stored = load_webauthn_cred()
    if not stored:
        return JSONResponse({"error": "Not registered"}, status_code=400)
    try:
        verification = verify_authentication_response(
            credential=AuthenticationCredential(
                id=credential["id"], raw_id=credential["rawId"], type=credential["type"],
                response=credential["response"],
            ),
            expected_challenge=challenge_store.get("auth", b""),
            expected_origin=origin, expected_rp_id=rp_id,
            credential_public_key=stored["public_key"],
            credential_current_sign_count=stored.get("sign_count", 0),
        )
        stored["sign_count"] = verification.new_sign_count
        save_webauthn_cred(stored)
        token = create_session()
        return {"token": token, "verified": True}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=401)

# ── Chat with session persistence ──
@app.post("/chat/stream")
async def chat_stream(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not validate_session(token):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    body = await request.json()
    text = body.get("text", "")
    history = body.get("history", [])
    sid = body.get("session_id", "")
    attachment = body.get("attachment")
    model_key = get_session_model_key(sid)

    if not text and not attachment:
        return JSONResponse({"error": "Empty message"}, status_code=400)

    # HARD ISOLATION: when a session_id is given, history comes from the DB ONLY —
    # the client can never inject another session's (or another model's) context.
    if sid:
        conn = db()
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
            (sid, SETTINGS.get("max_history", 40))
        ).fetchall()
        conn.close()
        msgs = [{"role": r[0], "content": r[1]} for r in reversed(rows)]
    else:
        msgs = [{"role": h["role"], "content": h["content"]} for h in history]

    # Save user message (with attachment reference if present)
    if sid:
        conn = db()
        now = time.time()
        conn.execute("INSERT INTO messages (session_id, role, content, timestamp, attachment) VALUES (?,?,?,?,?)",
                     (sid, "user", text, now, json.dumps(attachment) if attachment else ""))
        conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now, sid))
        conn.commit()
        conn.close()

    async def generate():
        final_content = ""
        had_error = False
        for event in stream_with_thoughts(msgs, text, model_key, attachment):  # sync generator — plain for (blocks loop, single-user OK)
            yield event
            if event["event"] == "error":
                had_error = True
            if event["event"] == "done":
                d = json.loads(event["data"])
                final_content = d.get("content", "")
                elapsed = d.get("elapsed", 0)
                model = d.get("model_key", model_key)
                # Save assistant message
                if sid:
                    conn2 = db()
                    now2 = time.time()
                    conn2.execute("INSERT INTO messages (session_id, role, content, model, elapsed, timestamp) VALUES (?,?,?,?,?,?)",
                                 (sid, "assistant", final_content, model, elapsed, now2))
                    # Auto-title from first user message
                    title_row = conn2.execute("SELECT title FROM sessions WHERE id=?", (sid,)).fetchone()
                    if title_row and title_row[0] == "New Chat":
                        title = text[:50].strip()
                        if title:
                            conn2.execute("UPDATE sessions SET title=? WHERE id=?", (title, sid))
                    conn2.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now2, sid))
                    conn2.commit()
                    conn2.close()

        if not final_content and not had_error:
            yield {"event": "error", "data": json.dumps({"error": "No response received"})}

    return EventSourceResponse(generate())

# ── Existing endpoints ──
@app.post("/chat")
async def chat_sync(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not validate_session(token):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    body = await request.json()
    text = body.get("text", "")
    history = body.get("history", [])
    msgs = [{"role": h["role"], "content": h["content"]} for h in history]
    m = MODELS[DEFAULT_MODEL_KEY]
    if not model_online(DEFAULT_MODEL_KEY):
        return {"reply": f"[{m['name']} is offline right now — try again shortly]", "error": True, "model_offline": True}
    ollama_url, model_name = m["ollama"], m["model"]
    sys_prompt = build_prompt(text)
    full = [{"role": "system", "content": sys_prompt}] + msgs + [{"role": "user", "content": text}]
    try:
        r = requests.post(f"{ollama_url}/v1/chat/completions", json={
            "model": model_name, "messages": full,
            "max_tokens": 2048, "options": {"num_ctx": 8192}
        }, timeout=120)
        choice = r.json().get("choices", [{}])[0].get("message", {})
        content = choice.get("content", "") or choice.get("reasoning", "")
        return {"reply": content}
    except Exception as e:
        return {"reply": f"[Rexxie needs a moment — {str(e)[:80]}]", "error": True}

@app.post("/upload")
async def upload_file(request: Request, file: UploadFile = File(...)):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not validate_session(token):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        content = await file.read()
        ext = Path(file.filename).suffix.lower()
        safe_name = f"{hashlib.md5(content).hexdigest()[:12]}{ext}"
        path = UPLOADS / safe_name
        with open(path, "wb") as f: f.write(content)
        log(f"Upload: {file.filename} → {safe_name} ({len(content)} bytes)")
        if ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
            b64 = base64.b64encode(content).decode()
            return JSONResponse({"filename": file.filename, "saved_as": safe_name, "size": len(content), "type": "image", "base64": b64[:50000]})
        if ext == ".pdf":
            return JSONResponse({"filename": file.filename, "saved_as": safe_name, "size": len(content), "type": "pdf", "note": "OCR available via MinerU"})
        return JSONResponse({"filename": file.filename, "saved_as": safe_name, "size": len(content), "type": "file"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/vision")
async def vision_analyze(request: Request):
    body = await request.json()
    image_b64 = body.get("image", "")
    prompt = body.get("prompt", "Describe this image in detail.")
    try:
        r = requests.post(f"{OLLAMA_PRIMARY}/api/generate", json={
            "model": MODEL_PRIMARY, "prompt": prompt, "images": [image_b64], "stream": False
        }, timeout=120)
        data = r.json()
        return {"analysis": data.get("response", "No analysis available")}
    except:
        return {"error": "Vision model unavailable"}

@app.get("/settings")
async def get_settings(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not validate_session(token):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    out = dict(SETTINGS)
    out["api_keys"] = {k: ("…" + v[-4:] if len(v) >= 4 else "…") for k, v in SETTINGS.get("api_keys", {}).items()}
    return out

@app.post("/settings")
async def update_settings(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not validate_session(token):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    body = await request.json()
    body.pop("api_keys", None)  # keys are managed ONLY via /api-keys endpoints
    global SETTINGS
    SETTINGS.update(body)
    try: SETTINGS_FILE.write_text(json.dumps(SETTINGS, indent=2))
    except: pass
    return await get_settings(request)

@app.get("/skills")
async def list_skills():
    skills_dir = Path("/Users/mainsobhelper/.hermes/profiles/cloud/skills")
    skills = []
    if skills_dir.exists():
        for d in skills_dir.iterdir():
            if d.is_dir():
                md = d / "SKILL.md"
                if md.exists():
                    content = md.read_text()[:200]
                    for line in content.split("\n"):
                        if line.startswith("description:"):
                            skills.append({"name": d.name, "description": line.split(":",1)[1].strip()})
                            break
    return {"skills": skills}

@app.post("/generate")
async def generate_media(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not validate_session(token):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    body = await request.json()
    prompt = body.get("prompt", "")
    media_type = body.get("type", "image")
    sid = body.get("session_id", "")
    if not prompt:
        return JSONResponse({"error": "Prompt required"}, status_code=400)
    try:
        env = os.environ.copy()
        env["PATH"] = "/opt/homebrew/bin:" + env.get("PATH", "/usr/bin:/bin")
        if media_type == "video":
            cmd = ["higgsfield", "generate", "create", "seedance_2_0", "--prompt", prompt, "--duration", "5",
                   "--wait", "--wait-timeout", "15m"]
        else:
            cmd = ["higgsfield", "generate", "create", "nano_banana_2", "--prompt", prompt, "--aspect_ratio", "1:1",
                   "--wait", "--wait-timeout", "5m"]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
        out = stdout.decode().strip()
        if out.startswith("http"):
            url = out
        else:
            data = json.loads(out)
            url = data[0].get("result_url", "") if isinstance(data, list) else data.get("result_url", "")
        log(f"Higgsfield [{media_type}]: {url[:80] if url else 'no url'}")
        if sid and url:
            conn = db()
            now = time.time()
            conn.execute("INSERT INTO messages (session_id, role, content, model, elapsed, timestamp, attachment) VALUES (?,?,?,?,?,?,?)",
                         (sid, "assistant", f"Generated {media_type}: {prompt}", get_session_model_key(sid), 0, now,
                          json.dumps({"kind": "generated", "url": url, "media_type": media_type})))
            conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now, sid))
            conn.commit()
            conn.close()
        return {"url": url, "model": "seedance_2_0" if media_type == "video" else "nano_banana_2"}
    except asyncio.TimeoutError:
        return JSONResponse({"error": "Generation timed out (10min limit)"}, status_code=504)
    except Exception as e:
        log(f"Higgsfield error: {e}")
        return JSONResponse({"error": str(e)[:200]}, status_code=500)

@app.post("/tts")
async def tts_speak(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not validate_session(token):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    body = await request.json()
    text = body.get("text", "")
    if not text: return JSONResponse({"error": "No text"}, status_code=400)
    text = text.strip()[:1000]
    try:
        voice = "en-GB-RyanNeural"
        rate = "-10%"
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "edge_tts", "--voice", voice, "--rate=-10%", "--text", text,
            "--write-media", tmp_path, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await asyncio.wait_for(proc.communicate(), timeout=30)
        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            with open(tmp_path, "rb") as f:
                audio = f.read()
            os.unlink(tmp_path)
            return Response(content=audio, media_type="audio/mpeg")
        else:
            raise Exception("No audio produced")
    except Exception as e:
        log(f"TTS error: {e}")
        return JSONResponse({"error": str(e)[:100]}, status_code=500)

# ── HTML ──
HTML = None
CACHED_MTIME = 0

def load_html():
    global HTML, CACHED_MTIME
    ui = BASE / "ghs_shell.html"
    try:
        mtime = ui.stat().st_mtime
        if HTML is None or mtime > CACHED_MTIME:
            HTML = ui.read_text()
            CACHED_MTIME = mtime
    except:
        if HTML is None:
            HTML = "<h1>UI not found</h1>"
    return HTML

@app.post("/skills/install")
async def install_skill(request: Request):
    body = await request.json()
    name = body.get("name", "")
    if not name: return JSONResponse({"error": "Skill name required"}, status_code=400)
    if "installed_skills" not in SETTINGS: SETTINGS["installed_skills"] = []
    if name not in SETTINGS["installed_skills"]:
        SETTINGS["installed_skills"].append(name)
        SETTINGS_FILE.write_text(json.dumps(SETTINGS, indent=2))
    return {"installed": SETTINGS["installed_skills"]}

@app.post("/skills/uninstall")
async def uninstall_skill(request: Request):
    body = await request.json()
    name = body.get("name", "")
    if name in SETTINGS.get("installed_skills", []):
        SETTINGS["installed_skills"].remove(name)
        SETTINGS_FILE.write_text(json.dumps(SETTINGS, indent=2))
    return {"installed": SETTINGS.get("installed_skills", [])}

# ── Premium extras ──
@app.get("/uploads/{filename}")
async def serve_upload(filename: str):
    from fastapi.responses import FileResponse
    safe = os.path.basename(filename)
    fpath = UPLOADS / safe
    if not fpath.exists():
        return JSONResponse({"error": "Not found"}, status_code=404)
    return FileResponse(fpath)

@app.post("/optimize")
async def optimize_prompt(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not validate_session(token):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        return JSONResponse({"error": "No text"}, status_code=400)
    m = MODELS[DEFAULT_MODEL_KEY]
    if not model_online(DEFAULT_MODEL_KEY):
        return JSONResponse({"error": f"{m['name']} is offline"}, status_code=503)
    try:
        r = requests.post(f"{m['ollama']}/v1/chat/completions", json={
            "model": m["model"],
            "messages": [
                {"role": "system", "content": "You are a prompt optimizer. Rewrite the user's prompt to be clearer, more specific, and more effective for an AI assistant. Return ONLY the rewritten prompt — no preamble, no quotes, no commentary."},
                {"role": "user", "content": text[:2000]},
            ],
            "max_tokens": 1024, "temperature": 0.4, "stream": False,
        }, timeout=120)
        content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        return {"optimized": content or text}
    except Exception as e:
        return JSONResponse({"error": str(e)[:100]}, status_code=500)

@app.get("/api-keys")
async def list_api_keys(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not validate_session(token):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    keys = SETTINGS.get("api_keys", {})
    return {"keys": [{"name": k, "preview": "…" + v[-4:] if len(v) >= 4 else "…"} for k, v in keys.items()]}

@app.post("/api-keys")
async def save_api_key(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not validate_session(token):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    body = await request.json()
    name, value = body.get("name", "").strip(), body.get("value", "").strip()
    if not name or not value:
        return JSONResponse({"error": "name and value required"}, status_code=400)
    if "api_keys" not in SETTINGS: SETTINGS["api_keys"] = {}
    SETTINGS["api_keys"][name] = value
    SETTINGS_FILE.write_text(json.dumps(SETTINGS, indent=2))
    return {"keys": [{"name": k, "preview": "…" + v[-4:]} for k, v in SETTINGS["api_keys"].items()]}

@app.delete("/api-keys/{name}")
async def delete_api_key(name: str, request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not validate_session(token):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    SETTINGS.get("api_keys", {}).pop(name, None)
    SETTINGS_FILE.write_text(json.dumps(SETTINGS, indent=2))
    return {"status": "deleted"}

import uvicorn
log(f"Rexxie Portal starting on :8420 (primary={MODEL_PRIMARY.split('/')[-1][:20]})")
uvicorn.run(app, host="127.0.0.1", port=8420, log_level="warning")
