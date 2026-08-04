#!/usr/bin/env python3
"""CC_khoj_gate.py — password-protected reverse proxy in front of Khoj.
Cookie-based login (works on iOS Safari reliably, unlike Basic Auth):
  GET  /              → login page if no valid cookie, else proxy to Khoj
  POST /login         → check password → set signed cookie
  POST /logout        → clear cookie
  everything else     → proxy to Khoj (requires valid cookie)
Unauthenticated page/asset requests → 302 redirect to / (login page) so stale
cached app shells recover into the login page instead of hanging on "Loading".
Pure API calls (/api/, /auth/) without cookie → 401.
Handles SSE/streaming. Zero cloud deps.
"""
import asyncio, hashlib, hmac, os, secrets, sys, time
from aiohttp import web, ClientSession

KHOJ_TARGET = os.environ.get("KHOJ_TARGET", "http://127.0.0.1:42110")
GATE_USER = os.environ.get("GATE_USER", "kato")
GATE_PASS = os.environ.get("GATE_PASS", "")
GATE_PORT = int(os.environ.get("GATE_PORT", "42120"))
COOKIE_NAME = "khoj_gate"
COOKIE_TTL = 60 * 60 * 24 * 30  # 30 days

if len(GATE_PASS) < 8:
    print("FATAL: GATE_PASS must be set (>=8 chars)", flush=True)
    sys.exit(1)

_SECRET = hashlib.sha256(GATE_PASS.encode() + b"khoj-gate-salt").hexdigest()
_PW_HASH = hashlib.sha256(GATE_PASS.encode()).hexdigest()

NO_STORE = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}

LOGIN_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Khoj — Sign in</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0f1216; color: #e6e9ef; display: flex; align-items: center; justify-content: center;
         min-height: 100vh; }
  .card { background: #171c23; border: 1px solid #262d37; border-radius: 14px; padding: 40px 36px;
          width: 340px; max-width: 92%; box-shadow: 0 10px 40px rgba(0,0,0,.4); }
  .logo { font-size: 34px; text-align: center; margin-bottom: 8px; }
  h1 { font-size: 20px; text-align: center; margin-bottom: 4px; letter-spacing: .5px; }
  p.sub { font-size: 12px; color: #8b94a3; text-align: center; margin-bottom: 28px; }
  label { font-size: 12px; color: #8b94a3; display: block; margin-bottom: 6px; }
  input { width: 100%; padding: 12px 14px; border-radius: 9px; border: 1px solid #2a323d;
          background: #0f1216; color: #e6e9ef; font-size: 15px; margin-bottom: 18px; outline: none; }
  input:focus { border-color: #4a7dff; }
  button { width: 100%; padding: 13px; border: 0; border-radius: 9px; background: #4a7dff;
           color: #fff; font-size: 15px; font-weight: 600; cursor: pointer; }
  button:hover { background: #3a6ae0; }
  .err { color: #ff5c5c; font-size: 12px; text-align: center; margin-top: 12px; min-height: 16px; }
  .hint { font-size: 11px; color: #5b6470; text-align: center; margin-top: 18px; }
</style></head><body>
<div class="card">
  <div class="logo">🏮</div>
  <h1>Khoj</h1>
  <p class="sub">Your second brain — sign in to continue</p>
  <form method="post" action="/login">
    <label for="u">Username</label>
    <input type="text" id="u" name="username" placeholder="Username" autocomplete="username" required autofocus>
    <label for="p">Password</label>
    <input type="password" id="p" name="password" placeholder="Password" autocomplete="current-password" required>
    <button type="submit">Sign in</button>
    <div class="err" id="err"></div>
  </form>
  <div class="hint">Private local access</div>
</div>
<script>
  const u = new URLSearchParams(location.search).get('e');
  if (u === '1') document.getElementById('err').textContent = 'Incorrect username or password';
  document.querySelector('form').addEventListener('submit', function(){ document.getElementById('err').textContent = 'Signing in…'; });
</script>
</body></html>"""

def make_cookie():
    val = secrets.token_hex(16)
    exp = int(time.time()) + COOKIE_TTL
    sig = hmac.new(_SECRET.encode(), f"{val}.{exp}".encode(), hashlib.sha256).hexdigest()
    return f"{val}.{exp}.{sig}"

def check_cookie(request) -> bool:
    raw = request.cookies.get(COOKIE_NAME, "")
    if not raw:
        return False
    parts = raw.split(".")
    if len(parts) != 3:
        return False
    val, exp, sig = parts
    try:
        exp = int(exp)
    except ValueError:
        return False
    if time.time() > exp:
        return False
    expect = hmac.new(_SECRET.encode(), f"{val}.{exp}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expect)

def is_authenticated(request) -> bool:
    # valid cookie OR correct Basic Auth (for API clients / curl)
    if check_cookie(request):
        return True
    ah = request.headers.get("Authorization", "")
    if ah.startswith("Basic "):
        import base64
        try:
            decoded = base64.b64decode(ah[6:]).decode()
            user, _, pw = decoded.partition(":")
            return user == GATE_USER and hashlib.sha256(pw.encode()).hexdigest() == _PW_HASH
        except Exception:
            return False
    return False

async def login_page(request):
    return web.Response(content_type="text/html", body=LOGIN_HTML, headers=dict(NO_STORE))

async def do_login(request):
    data = await request.post()
    user = data.get("username", "")
    pw = data.get("password", "")
    if user == GATE_USER and hashlib.sha256(pw.encode()).hexdigest() == _PW_HASH:
        resp = web.HTTPFound("/")
        resp.headers.update(NO_STORE)
        resp.set_cookie(COOKIE_NAME, make_cookie(), max_age=COOKIE_TTL, httponly=True, samesite="lax", secure=True, path="/")
        return resp
    resp = web.HTTPFound("/?e=1")
    resp.headers.update(NO_STORE)
    return resp

async def do_logout(request):
    resp = web.HTTPFound("/")
    resp.headers.update(NO_STORE)
    resp.del_cookie(COOKIE_NAME, path="/")
    return resp

async def proxy(request: web.Request):
    authed = is_authenticated(request)
    print(f"[gate:{time.strftime('%H:%M:%S')}] {request.method} {request.path} authed={authed} cookie={'khoj_gate' in request.cookies}", flush=True)
    if not authed:
        # Pure API calls → 401. Root and /login → serve login page directly (200).
        # Everything else (pages, /_next/, /static/, favicon, manifest, any Accept
        # incl. text/html) → 302 to login page so stale cached app shells recover
        # instead of hanging on "Loading".
        if request.path.startswith(("/api/", "/auth/")):
            return web.Response(status=401, headers={**NO_STORE, "Content-Type": "text/plain"}, text="Unauthorized")
        if request.path in ("/", "/login"):
            return await login_page(request)
        resp = web.HTTPFound("/")
        resp.headers.update(NO_STORE)
        return resp

    path = request.path_qs
    target = KHOJ_TARGET + path
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("authorization", "connection", "upgrade", "cookie")}
    # Forward the ORIGINAL Host header (khoj.hermestigerclaw.com) so Khoj builds
    # correct absolute URLs (wss://, oauth redirects) instead of ws://localhost
    if "host" in request.headers and "host" not in headers:
        headers["host"] = request.headers["host"]
    body = await request.read()
    async with ClientSession() as session:
        async with session.request(request.method, target, headers=headers, data=body, timeout=None) as resp:
            resp_headers = {k: v for k, v in resp.headers.items()
                            if k.lower() not in ("connection", "upgrade", "transfer-encoding", "content-length", "set-cookie")}
            # ALWAYS stream (Khoj uses text/plain framing, not text/event-stream — buffering
            # makes the UI show "Loading" until the entire answer completes)
            resp_headers.update(NO_STORE)
            resp_headers["X-Accel-Buffering"] = "no"
            out = web.StreamResponse(status=resp.status, headers=resp_headers)
            await out.prepare(request)
            async for chunk in resp.content.iter_any():
                await out.write(chunk)
            await out.write_eof()
            return out

async def main():
    app = web.Application()
    app.router.add_get("/login", login_page)
    app.router.add_post("/login", do_login)
    app.router.add_get("/logout", do_logout)
    app.router.add_route("*", "/{tail:.*}", proxy)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", GATE_PORT)
    await site.start()
    print(f"[khoj_gate] listening on :{GATE_PORT} → {KHOJ_TARGET} (user={GATE_USER})", flush=True)
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
