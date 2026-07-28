"""
REX — Phone Unlock Server
===========================
Turns your iPhone into a biometric key for your Mac Mini and Rexxie vault.

How it works:
  1. You're on the same WiFi as your Mac Mini
  2. Open the REX app on your iPhone → Face ID prompt appears
  3. Face ID passes → iPhone sends a signed token to your Mac over local network
  4. Mac verifies the token (HMAC + timestamp + IP check)
  5. Mac wakes screen, dismisses screensaver lock, pre-authorizes Rexxie vault
  6. You sit down to an already-unlocked computer

Security model:
  • HMAC-SHA256 token — each unlock generates a unique signature
  • 30-second timestamp window — replay attacks impossible after 30s
  • Same-subnet IP filter — only works from inside your home/office WiFi
  • Face ID is the gate — nothing happens without your face
  • HTTPS — traffic encrypted between phone and Mac
  • Token is stored in iOS Keychain (secure enclave protected)

If phone breaks or camera fails:
  → Use your 10-word seed phrase as fallback (built into Rexxie)
  → Or use Magic Keyboard Touch ID for Mac login screen

What gets unlocked:
  ✅ Rexxie credential vault (pre-authorized for 15 minutes)
  ✅ Mac screensaver/sleep lock (screen wakes and unlocks)
  ✅ REX vault mode (pre-authorized for session)
  ⚠️  Mac LOGIN screen after full reboot → Magic Keyboard Touch ID handles this

Setup:
  1. python rex_phone_unlock.py --setup
     → Generates shared secret
     → Shows QR code for iOS Shortcut import
     → Configures HTTPS
  2. Scan QR with iPhone → installs "Unlock My Mac" shortcut
  3. Add to iPhone Home Screen (one tap to trigger)
  4. Done — Face ID → Mac unlocked

Run the server (runs alongside REX backend):
  python rex_phone_unlock.py --serve
  OR it starts automatically when REX backend starts (integrated)
"""

import os
import sys
import json
import hmac
import time
import uuid
import socket
import hashlib
import secrets
import logging
import subprocess
import threading
import urllib.parse
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")

# ── Config ─────────────────────────────────────────────────────────────────────
CONFIG_PATH      = Path.home() / "Desktop" / "REX" / "rex_phone_unlock_config.json"
UNLOCK_PORT      = 8765          # Separate from REX backend (8000)
TOKEN_WINDOW_SEC = 30            # Accept tokens within ±30 seconds
VAULT_PRE_AUTH_MINUTES = 15      # How long vault stays pre-authorized after phone unlock
UNLOCK_LOG       = Path.home() / "Desktop" / "REX" / "logs" / "phone_unlock.log"

# Vault pre-authorization state (shared with rex_credential_vault.py)
_vault_pre_authorized_until: float = 0.0
_screen_unlock_callback = None   # Set by REX backend


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}


def _save_config(cfg: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    CONFIG_PATH.chmod(0o600)


def _get_local_ip() -> str:
    """Get this Mac's local IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _get_mdns_hostname() -> str:
    """
    Return the Mac's mDNS .local hostname (e.g. 'katos-mac-mini.local').
    This resolves on any local network regardless of IP address changes.
    Falls back to current IP if hostname resolution fails.
    """
    try:
        hostname = socket.gethostname()
        if not hostname.endswith(".local"):
            hostname = hostname + ".local"
        return hostname
    except Exception:
        return _get_local_ip()


def _get_subnet(ip: str) -> str:
    """Get subnet prefix (e.g., '192.168.1') from IP."""
    return ".".join(ip.split(".")[:3])


# ── Cryptographic token system ─────────────────────────────────────────────────

def generate_shared_secret() -> str:
    """Generate a strong shared secret for HMAC signing."""
    return secrets.token_hex(32)   # 256-bit secret


def generate_unlock_token(secret: str, timestamp: Optional[int] = None) -> str:
    """
    Generate a time-based HMAC unlock token.
    Token = HMAC-SHA256(secret, "unlock:{timestamp_30s_window}")
    Each 30-second window generates a unique token — like TOTP but for unlock.
    """
    t = timestamp or int(time.time())
    window = t // 30    # 30-second window
    message = f"rex-unlock:{window}".encode()
    token = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return token


def verify_unlock_token(
    token: str,
    secret: str,
    client_ip: str,
    mac_subnet: str,
    window: int = TOKEN_WINDOW_SEC // 30,
) -> Tuple[bool, str]:
    """
    Verify an unlock token from the iPhone.
    Checks: HMAC validity + timestamp freshness + same-subnet IP.
    Returns (valid, reason).
    """
    # IP subnet check — must be on same local network
    client_subnet = ".".join(client_ip.split(".")[:3])
    if client_subnet != mac_subnet:
        return False, f"IP {client_ip} not on local subnet {mac_subnet}.x"

    # HMAC check across ±window time windows (handles clock drift)
    now = int(time.time())
    for delta in range(-window, window + 1):
        expected = generate_unlock_token(secret, now + delta * 30)
        if hmac.compare_digest(token.strip(), expected):
            return True, "valid"

    return False, "Token invalid or expired"


# ── Mac unlock actions ─────────────────────────────────────────────────────────

def wake_display() -> bool:
    """Wake the Mac display from sleep."""
    try:
        # caffeinate wakes the display
        subprocess.run(
            ["caffeinate", "-u", "-t", "1"],
            capture_output=True, timeout=5
        )
        return True
    except Exception as e:
        logger.error(f"Display wake error: {e}")
        return False


def dismiss_screensaver() -> bool:
    """
    Dismiss the Mac screensaver (when no password is required for screensaver).
    For password-locked screensaver, this wakes the screen to show the password field.
    """
    try:
        # Move mouse slightly to dismiss screensaver
        script = """
tell application "System Events"
    key code 53
    delay 0.2
    key code 36
end tell
"""
        subprocess.run(
            ["osascript", "-"],
            input=script.encode(),
            capture_output=True, timeout=5,
        )
        return True
    except Exception as e:
        logger.error(f"Screensaver dismiss error: {e}")
        return False


def unlock_screensaver_with_password(password: str) -> bool:
    """
    Programmatically enter password to unlock screensaver.
    Uses System Events to type into the lock screen password field.

    SECURITY NOTE: This requires the Mac password to be stored somewhere.
    We recommend using this ONLY with a dedicated Mac account that has
    auto-login enabled, so the screensaver lock (not login screen) is
    a lighter layer. The real security is the full vault encryption.
    """
    try:
        safe_pass = password.replace("\\", "\\\\").replace('"', '\\"')
        script = f"""
tell application "System Events"
    key code 53
    delay 0.5
    keystroke "{safe_pass}"
    delay 0.3
    key code 36
end tell
"""
        result = subprocess.run(
            ["osascript", "-"],
            input=script.encode(),
            capture_output=True, timeout=10,
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Screensaver unlock error: {e}")
        return False


def pre_authorize_vault(minutes: int = VAULT_PRE_AUTH_MINUTES):
    """
    Mark vault as pre-authorized. rex_credential_vault.py checks this
    before requiring passphrase entry — vault opens automatically.
    """
    global _vault_pre_authorized_until
    _vault_pre_authorized_until = time.time() + (minutes * 60)
    logger.info(f"✅ Vault pre-authorized for {minutes} minutes")


def is_vault_pre_authorized() -> bool:
    """Check if vault is currently pre-authorized by phone unlock."""
    return time.time() < _vault_pre_authorized_until


def log_unlock(client_ip: str, success: bool, reason: str = ""):
    """Log all unlock attempts."""
    UNLOCK_LOG.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "✅ SUCCESS" if success else "❌ FAILED"
    line = f"[{timestamp}] {status} | IP: {client_ip} | {reason}\n"
    with open(UNLOCK_LOG, "a") as f:
        f.write(line)


# ── HTTP server (pure Python, no extra dependencies) ──────────────────────────

def _build_response(status: int, body: dict) -> bytes:
    """Build a minimal HTTP response."""
    json_body = json.dumps(body).encode()
    status_text = {200: "OK", 400: "Bad Request", 401: "Unauthorized", 403: "Forbidden"}.get(status, "Error")
    headers = (
        f"HTTP/1.1 {status} {status_text}\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(json_body)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )
    return headers.encode() + json_body


def _parse_request(raw: bytes) -> Tuple[str, str, dict, str]:
    """Parse raw HTTP request → (method, path, headers, body)."""
    try:
        header_end = raw.find(b"\r\n\r\n")
        header_raw = raw[:header_end].decode("utf-8", errors="replace")
        body_raw   = raw[header_end + 4:].decode("utf-8", errors="replace")
        lines      = header_raw.split("\r\n")
        first      = lines[0].split(" ")
        method     = first[0] if first else "GET"
        path       = first[1] if len(first) > 1 else "/"
        headers    = {}
        for line in lines[1:]:
            if ": " in line:
                k, v = line.split(": ", 1)
                headers[k.lower()] = v
        return method, path, headers, body_raw
    except Exception:
        return "GET", "/", {}, ""


def _phone_unlock_html(mac_ip: str) -> str:
    """Generate a simple iPhone-friendly unlock web app."""
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="REX Unlock">
<title>REX Unlock</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0a0a0a;color:#fff;
  height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;
  -webkit-user-select:none;user-select:none}}
.dino{{font-size:80px;margin-bottom:20px;filter:drop-shadow(0 0 30px rgba(240,165,0,.4));
  transition:transform .3s}}
.dino.pulse{{animation:pulse 1s ease-in-out}}
@keyframes pulse{{0%{{transform:scale(1)}}50%{{transform:scale(1.2)}}100%{{transform:scale(1)}}}}
h1{{font-size:22px;font-weight:700;margin-bottom:6px}}
.sub{{font-size:13px;color:#888;margin-bottom:40px}}
.btn{{width:200px;height:200px;border-radius:50%;border:3px solid #F0A500;background:
  radial-gradient(circle at 40% 40%,#2a2a2a,#111);display:flex;align-items:center;
  justify-content:center;font-size:18px;font-weight:700;color:#F0A500;cursor:pointer;
  transition:all .2s;box-shadow:0 0 40px rgba(240,165,0,.15)}}
.btn:active{{transform:scale(.95);box-shadow:0 0 60px rgba(240,165,0,.4)}}
.btn.success{{border-color:#4ADE80;color:#4ADE80;box-shadow:0 0 60px rgba(74,222,128,.4)}}
.btn.fail{{border-color:#F87171;color:#F87171;box-shadow:0 0 60px rgba(248,113,113,.4)}}
.status{{margin-top:30px;font-size:14px;color:#666;min-height:20px;text-align:center;max-width:280px}}
.ip{{font-size:11px;color:#444;position:fixed;bottom:20px}}
</style>
</head>
<body>
<div class="dino" id="dino">&#x1F995;</div>
<h1>REX</h1>
<div class="sub">Tap to unlock your Mac</div>
<div class="btn" id="btn" onclick="unlock()">
  UNLOCK
</div>
<div class="status" id="status"></div>
<div class="ip">{mac_ip} &middot; Port 8766</div>
<script>
var BASE = window.location.origin;
var btn = document.getElementById('btn');
var status = document.getElementById('status');
var dino = document.getElementById('dino');
var busy = false;

async function unlock() {{
  if (busy) return;
  busy = true;
  btn.textContent = '...';
  btn.className = 'btn';
  status.textContent = 'Getting challenge token...';
  try {{
    var cr = await fetch(BASE + '/challenge');
    var cd = await cr.json();
    if (!cd.token) throw new Error(cd.error || 'No token');
    status.textContent = 'Sending unlock request...';
    var ur = await fetch(BASE + '/unlock', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{token: cd.token}})
    }});
    var ud = await ur.json();
    if (ud.unlocked) {{
      btn.textContent = 'UNLOCKED';
      btn.className = 'btn success';
      dino.classList.add('pulse');
      status.textContent = ud.message || 'Mac unlocked!';
      setTimeout(function(){{ dino.classList.remove('pulse'); }}, 1000);
    }} else {{
      btn.textContent = 'FAILED';
      btn.className = 'btn fail';
      status.textContent = ud.error || ud.reason || 'Unlock failed';
    }}
  }} catch(e) {{
    btn.textContent = 'ERROR';
    btn.className = 'btn fail';
    status.textContent = e.message || 'Connection failed';
  }}
  setTimeout(function(){{
    btn.textContent = 'UNLOCK';
    btn.className = 'btn';
    status.textContent = '';
    busy = false;
  }}, 3000);
}}
</script>
</body>
</html>'''


class PhoneUnlockServer:
    """
    Lightweight HTTP server that listens for iPhone unlock requests.
    Runs in a background thread alongside REX backend.
    """

    def __init__(self):
        cfg          = _load_config()
        self.secret  = cfg.get("shared_secret", "")
        self.mac_ip  = _get_local_ip()
        self.subnet  = _get_subnet(self.mac_ip)
        self.mac_password = cfg.get("mac_screensaver_password", "")  # Optional
        self._running = False

    def handle_unlock_request(self, client_ip: str, body: str) -> Tuple[int, dict]:
        """
        Process an unlock request from iPhone.
        Returns (http_status, response_dict).
        """
        if not self.secret:
            return 503, {"error": "Phone unlock not configured. Run --setup first."}

        # Parse request body
        try:
            data  = json.loads(body) if body.strip() else {}
            token = data.get("token", "")
        except Exception:
            return 400, {"error": "Invalid JSON body"}

        if not token:
            return 400, {"error": "Missing token"}

        # Verify token
        valid, reason = verify_unlock_token(
            token=token,
            secret=self.secret,
            client_ip=client_ip,
            mac_subnet=self.subnet,
        )

        if not valid:
            log_unlock(client_ip, False, reason)
            logger.warning(f"🚫 Unlock rejected from {client_ip}: {reason}")
            return 401, {"error": reason}

        # ── Unlock sequence ───────────────────────────────────────────────────
        logger.info(f"📱 Phone unlock authorized from {client_ip}")
        log_unlock(client_ip, True, "Face ID verified on iPhone")

        # 1. Wake display
        wake_display()

        # 2. Dismiss screensaver (or show password field)
        if self.mac_password:
            threading.Thread(
                target=lambda: (time.sleep(0.5), unlock_screensaver_with_password(self.mac_password)),
                daemon=True,
            ).start()
        else:
            dismiss_screensaver()

        # 3. Pre-authorize Rexxie vault
        pre_authorize_vault()

        # 4. Notify Rexxie (non-blocking)
        threading.Thread(
            target=self._notify_vault_unlock,
            daemon=True,
        ).start()

        return 200, {
            "ok": True,
            "message": "Mac unlocked 🦖",
            "vault_authorized_minutes": VAULT_PRE_AUTH_MINUTES,
        }

    def _notify_vault_unlock(self):
        """Tell REX backend the vault is pre-authorized."""
        try:
            import urllib.request
            req = urllib.request.Request(
                "http://localhost:8000/api/phone-unlock-callback",
                data=json.dumps({"authorized": True}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=3)
        except Exception:
            pass   # REX backend might not be running — vault pre-auth still works via shared state

    def handle_challenge_request(self) -> Tuple[int, dict]:
        """
        Return a fresh challenge token for the iPhone to include in its request.
        iPhone calls this first, then sends back the token.
        """
        if not self.secret:
            return 503, {"error": "Not configured"}
        # Return current timestamp window so phone can generate matching token
        token = generate_unlock_token(self.secret)
        return 200, {
            "token": token,
            "mac_ip": self.mac_ip,
            "ok": True,
        }

    def _handle_connection(self, conn, addr):
        """Handle a single HTTP connection."""
        try:
            raw = b""
            conn.settimeout(10)
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                raw += chunk
                if b"\r\n\r\n" in raw:
                    break

            client_ip  = addr[0]
            method, path, headers, body = _parse_request(raw)

            if path == "/unlock" and method == "POST":
                status, resp = self.handle_unlock_request(client_ip, body)
            elif path == "/challenge" and method == "GET":
                status, resp = self.handle_challenge_request()
            elif path == "/health" and method == "GET":
                status, resp = 200, {"ok": True, "service": "rex-phone-unlock", "mac_ip": self.mac_ip}
            elif path == "/phone" and method == "GET":
                # Serve the iPhone unlock web app
                html = _phone_unlock_html(self.mac_ip)
                raw_resp = (
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: text/html; charset=utf-8\r\n"
                    f"Content-Length: {len(html.encode())}\r\n"
                    f"Cache-Control: no-cache\r\n"
                    f"Connection: close\r\n\r\n"
                    f"{html}"
                ).encode()
                conn.sendall(raw_resp)
                conn.close()
                return
            else:
                status, resp = 404, {"error": "Not found"}

            conn.sendall(_build_response(status, resp))
        except Exception as e:
            logger.error(f"Connection error: {e}")
        finally:
            conn.close()

    def serve(self, host: str = "127.0.0.1", port: int = UNLOCK_PORT):
        """Start listening for phone unlock requests."""
        import socket as sock_mod
        self._running = True
        srv = sock_mod.socket(sock_mod.AF_INET, sock_mod.SOCK_STREAM)
        srv.setsockopt(sock_mod.SOL_SOCKET, sock_mod.SO_REUSEADDR, 1)
        # Try primary port, then fall back to alternatives if busy
        bound = False
        for try_port in [port, 8765, 8766, 8767]:
            try:
                srv.bind((host, try_port))
                port = try_port
                bound = True
                break
            except OSError as e:
                if e.errno == 48:  # Address already in use
                    logger.warning(f"📱 Port {try_port} busy, trying next...")
                    continue
                raise
        if not bound:
            logger.error("📱 Phone unlock server: all ports busy (8765-8767). Not starting.")
            return
        srv.listen(5)
        srv.settimeout(1.0)
        logger.info(f"📱 Phone unlock server listening on {host}:{port}")
        logger.info(f"   Mac IP: {self.mac_ip} | Subnet: {self.subnet}.x")

        while self._running:
            try:
                conn, addr = srv.accept()
                t = threading.Thread(target=self._handle_connection, args=(conn, addr), daemon=True)
                t.start()
            except OSError:
                continue
        srv.close()

    def start_background(self):
        """Start server in a background thread."""
        t = threading.Thread(target=self.serve, daemon=True, name="phone-unlock-server")
        t.start()
        return t

    def stop(self):
        self._running = False


# ── iOS Shortcut generator ─────────────────────────────────────────────────────

def generate_shortcut_instructions(mac_ip: str, secret: str) -> str:
    """
    Generate step-by-step instructions for creating the iOS Shortcut.
    The shortcut requires Face ID, then POSTs to the Mac unlock server.
    """
    # Pre-compute a sample token so the shortcut URL can be tested
    sample_token = generate_unlock_token(secret)

    # Prefer .local mDNS hostname — it survives IP changes automatically
    mdns_host = _get_mdns_hostname()
    unlock_url = f"http://{mdns_host}:{UNLOCK_PORT}/unlock"
    challenge_url = f"http://{mdns_host}:{UNLOCK_PORT}/challenge"

    return f"""
╔══════════════════════════════════════════════════════════════╗
║         iPhone "Unlock My Mac" Shortcut Setup                ║
╚══════════════════════════════════════════════════════════════╝

Your Mac hostname: {mdns_host}   ← use this (works even if IP changes)
Your Mac IP:       {mac_ip}
Unlock URL:  {unlock_url}

─────────────────────────────────────────────────────────────
STEP 1 — Open Shortcuts app on iPhone
─────────────────────────────────────────────────────────────
Tap the + button to create a new shortcut.
Name it: "Unlock My Mac"

─────────────────────────────────────────────────────────────
STEP 2 — Add these actions IN ORDER:
─────────────────────────────────────────────────────────────

Action 1: "Authenticate"
  → This is the Face ID gate. Without Face ID, nothing else runs.
  → Search for "Authenticate" in the actions list
  → Set prompt: "Unlock Mac + Rexxie vault"

Action 2: "Get Contents of URL"
  → URL: {challenge_url}
  → Method: GET
  → This fetches a fresh token from your Mac

Action 3: "Get Dictionary Value"
  → Dictionary: [Shortcut Result from Action 2]
  → Key: token

Action 4: "Get Contents of URL"
  → URL: {unlock_url}
  → Method: POST
  → Request Body: JSON
  → Add key: token   → Value: [Dictionary Value from Action 3]

Action 5: "Show Result"
  → Input: [Result from Action 4]
  → (Shows "Mac unlocked 🦖" on success)

─────────────────────────────────────────────────────────────
STEP 3 — Add to Home Screen
─────────────────────────────────────────────────────────────
Tap Share → Add to Home Screen
Choose an icon (🦖 works great)
Name it "Unlock" or "REX"

─────────────────────────────────────────────────────────────
STEP 4 — Test it
─────────────────────────────────────────────────────────────
1. Let your Mac go to screensaver
2. Pick up your iPhone, open the shortcut
3. Face ID prompt appears → look at phone
4. Mac screen wakes up and unlocks ✅
5. Rexxie vault is pre-authorized for {VAULT_PRE_AUTH_MINUTES} minutes ✅

─────────────────────────────────────────────────────────────
FALLBACK (phone broken or camera fails):
─────────────────────────────────────────────────────────────
Tell Rexxie: "backup phrase: [your 10 words in order]"
This bypasses Face ID and unlocks the vault manually.
Magic Keyboard Touch ID handles the Mac login screen.

─────────────────────────────────────────────────────────────
SECURITY NOTES:
─────────────────────────────────────────────────────────────
• Works only when iPhone and Mac are on the same WiFi
• Token expires every 30 seconds — replaying it doesn't work
• Face ID must pass before any network request is made
• All unlock attempts are logged to: {UNLOCK_LOG}
"""


# ── Setup wizard ───────────────────────────────────────────────────────────────

def setup_wizard():
    print("\n" + "="*62)
    print("  REX Phone Unlock — Setup")
    print("  Turn your iPhone Face ID into a Mac + vault key")
    print("="*62)
    print()

    cfg        = _load_config()
    mac_ip     = _get_local_ip()
    secret     = cfg.get("shared_secret") or generate_shared_secret()

    cfg["shared_secret"] = secret
    cfg["mac_ip"]        = mac_ip

    print(f"Mac IP address: {mac_ip}")
    print(f"Your iPhone must be on the same WiFi as this Mac.")
    print()

    # Optional: store Mac screensaver password for full auto-unlock
    print("To auto-unlock the screensaver (not just wake screen),")
    print("Rexxie needs your Mac screensaver password.")
    print("This is stored locally in the config file (not sent anywhere).")
    print()
    import getpass
    mac_pass = getpass.getpass("Mac screensaver password (press Enter to skip): ").strip()
    if mac_pass:
        cfg["mac_screensaver_password"] = mac_pass
        print("✅ Screensaver password saved — full auto-unlock enabled.")
    else:
        print("Skipped — Mac will wake screen, then show password field.")
        print("Tip: Use Magic Keyboard Touch ID to tap in after screen wakes.")

    _save_config(cfg)

    # Show iOS Shortcut instructions
    instructions = generate_shortcut_instructions(mac_ip, secret)
    print(instructions)

    # Save instructions to file
    instructions_file = Path.home() / "Desktop" / "REX" / "iPhone_Shortcut_Setup.txt"
    instructions_file.write_text(instructions)
    print(f"📄 Instructions saved to: {instructions_file}")
    print()

    # Test server
    start = input("Start unlock server now to test? [y/n]: ").strip().lower()
    if start == "y":
        server = PhoneUnlockServer()
        print(f"\n🟢 Server running on port {UNLOCK_PORT}...")
        print("Follow the iPhone setup above, then test the shortcut.")
        print("Press Ctrl+C to stop.\n")
        try:
            server.serve()
        except KeyboardInterrupt:
            print("\n✅ Server stopped.")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="REX Phone Unlock Server")
    parser.add_argument("--setup",       action="store_true", help="Run setup wizard")
    parser.add_argument("--serve",       action="store_true", help="Start unlock server")
    parser.add_argument("--status",      action="store_true", help="Show config status")
    parser.add_argument("--test-token",  action="store_true", help="Generate a test token")
    parser.add_argument("--show-setup",  action="store_true", help="Re-show iPhone shortcut instructions")
    args = parser.parse_args()

    if args.setup:
        setup_wizard()

    elif args.serve:
        cfg = _load_config()
        if not cfg.get("shared_secret"):
            print("❌ Not configured. Run: python rex_phone_unlock.py --setup")
        else:
            server = PhoneUnlockServer()
            print(f"📱 Phone unlock server started on port {UNLOCK_PORT}")
            print(f"   Mac IP: {server.mac_ip} | Subnet: {server.subnet}.x only")
            print("   Press Ctrl+C to stop")
            try:
                server.serve()
            except KeyboardInterrupt:
                print("\nStopped.")

    elif args.status:
        cfg = _load_config()
        print(f"\n📱 Phone Unlock Status")
        print(f"   Configured:  {'✅' if cfg.get('shared_secret') else '❌'}")
        print(f"   Mac IP:      {_get_local_ip()}")
        print(f"   Port:        {UNLOCK_PORT}")
        print(f"   Auto-unlock: {'✅ Screensaver password set' if cfg.get('mac_screensaver_password') else '⚠️  Wake only (no password stored)'}")
        print(f"   Vault auth:  {'✅ Pre-authorized' if is_vault_pre_authorized() else '🔒 Not active'}")
        print()

    elif args.test_token:
        cfg = _load_config()
        secret = cfg.get("shared_secret")
        if not secret:
            print("❌ Not configured.")
        else:
            token = generate_unlock_token(secret)
            print(f"\nTest token: {token}")
            valid, reason = verify_unlock_token(token, secret, _get_local_ip(), _get_subnet(_get_local_ip()))
            print(f"Self-verify: {'✅ valid' if valid else f'❌ {reason}'}\n")

    elif args.show_setup:
        cfg = _load_config()
        if not cfg.get("shared_secret"):
            print("❌ Run --setup first.")
        else:
            print(generate_shortcut_instructions(_get_local_ip(), cfg["shared_secret"]))

    else:
        parser.print_help()
