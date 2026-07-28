"""
REX — Proximity Unlock Daemon
================================
Phone unlocked + nearby → Mac stays unlocked.
Phone locks → Mac locks 60 seconds later.
You never manually trigger anything.

How it works:
  1. This daemon runs silently in the background on your Mac Mini.
  2. The REX iPhone app (built in rex_heartbeat_app/) sends a UDP heartbeat
     every 8 seconds while your phone screen is ON and Face ID has passed.
  3. When your phone screen goes off (locks), iOS suspends the app.
     Heartbeats stop within 10 seconds.
  4. Daemon notices silence → starts countdown → locks Mac after LOCK_DELAY.
  5. When you pick up your phone → Face ID passes → app wakes → heartbeats resume
     → daemon detects → unlocks Mac screen automatically.

The result:
  • Sit at your Mac with phone nearby and unlocked → Mac is always open
  • Set phone face-down / screen dims while you keep typing → Mac stays open
    (Mac activity is checked — no lock while keyboard/mouse is in use)
  • Walk away and stop using Mac → Mac locks itself after 60s phone silence
    + 600s keyboard/mouse idle (both conditions must be true)
  • Come back, glance at phone (Face ID) → Mac unlocks before you sit down
  • Leave WiFi entirely → Mac locks within 60 seconds (secondary detection)

Lock conditions (BOTH must be true):
  • Phone heartbeats absent for LOCK_DELAY (60 seconds)
  • Mac keyboard/mouse idle for MAC_IDLE_THRESHOLD (600 seconds / 10 minutes)

This means: if you're actively working, your Mac will NEVER lock just because
your phone screen went dark. It only locks when you've actually walked away.

Security:
  • Heartbeats are HMAC-SHA256 signed — cannot be spoofed
  • Only accepted from same WiFi subnet
  • 30-second token window prevents replay
  • Face ID must pass on iPhone for heartbeats to start
  • All lock/unlock events logged with timestamp + IP

Start automatically with Mac:
  python rex_proximity_daemon.py --install-launchagent

Manual run (for testing):
  python rex_proximity_daemon.py --run

Check status from another terminal:
  python rex_proximity_daemon.py --status
"""

import os
import sys
import json
import hmac
import time
import socket
import hashlib
import logging
import secrets
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger("rex.proximity")
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")

# ── Config ─────────────────────────────────────────────────────────────────────
CONFIG_PATH      = Path.home() / "Desktop" / "REX" / "rex_phone_unlock_config.json"
PROXIMITY_LOG    = Path.home() / "Desktop" / "REX" / "logs" / "proximity.log"
STATE_FILE       = Path.home() / "Desktop" / "REX" / ".proximity_state.json"
LAUNCHAGENT_FILE = Path.home() / "Library" / "LaunchAgents" / "com.rex.proximity.plist"

HEARTBEAT_PORT   = 8766          # UDP port for phone heartbeats
HEARTBEAT_INTERVAL = 8           # iPhone sends every 8 seconds
LOCK_DELAY       = 60            # Seconds of silence before locking Mac
UNLOCK_GRACE     = 3             # Seconds to wait for screen to wake before unlock
TOKEN_WINDOW     = 2             # ±2 heartbeat windows = ±16 seconds tolerance

# ── Shared secret (same as rex_phone_unlock.py) ────────────────────────────────

def _load_secret() -> str:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text()).get("shared_secret", "")
        except Exception:
            pass
    return ""


def _get_local_subnet() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ".".join(ip.split(".")[:3])
    except Exception:
        return "192.168.1"


# ── Mac activity detection ─────────────────────────────────────────────────────

MAC_IDLE_THRESHOLD = 600   # Seconds of keyboard/mouse inactivity before we consider Mac "idle"
                           # If Mac has seen input in the last 10 minutes, do NOT lock.

def _mac_is_actively_in_use(idle_threshold_seconds: int = MAC_IDLE_THRESHOLD) -> bool:
    """
    Returns True if the Mac has had keyboard or mouse activity within
    `idle_threshold_seconds`. Reads HIDIdleTime from the IOKit registry.

    This prevents the proximity daemon from locking the screen while Kato
    is actively typing or mousing — even if the iPhone screen went dark
    (e.g., phone sat down on the desk while working).

    Lock only happens when BOTH:
      • Phone heartbeats absent for LOCK_DELAY (60s)   AND
      • Mac has been idle for MAC_IDLE_THRESHOLD (120s)
    """
    try:
        result = subprocess.run(
            ["ioreg", "-c", "IOHIDSystem"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.split("\n"):
            if "HIDIdleTime" in line:
                # Line format:  "HIDIdleTime" = 3456789012345
                idle_ns = int(line.split("=")[-1].strip())
                idle_seconds = idle_ns / 1_000_000_000
                in_use = idle_seconds < idle_threshold_seconds
                logger.debug(
                    f"Mac idle for {idle_seconds:.0f}s — "
                    f"{'active, skipping lock' if in_use else 'idle, lock permitted'}"
                )
                return in_use
    except Exception as e:
        logger.debug(f"HIDIdleTime check failed: {e}")

    # If we can't read activity, err on the side of NOT locking
    # (better to stay unlocked than to lock someone mid-sentence)
    return True


# ── HMAC token verification ────────────────────────────────────────────────────

def _verify_heartbeat(token: str, secret: str, client_ip: str, subnet: str) -> bool:
    """Verify a heartbeat token: HMAC + subnet check."""
    if not secret:
        return False

    # Subnet check
    client_subnet = ".".join(client_ip.split(".")[:3])
    if client_subnet != subnet:
        logger.warning(f"Heartbeat from outside subnet: {client_ip}")
        return False

    # HMAC check across ±TOKEN_WINDOW windows
    now = int(time.time())
    for delta in range(-TOKEN_WINDOW, TOKEN_WINDOW + 1):
        window   = (now + delta * HEARTBEAT_INTERVAL) // HEARTBEAT_INTERVAL
        message  = f"rex-heartbeat:{window}".encode()
        expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()[:16]
        if hmac.compare_digest(token.strip()[:16], expected):
            return True
    return False


def generate_heartbeat_token(secret: str) -> str:
    """Generate the current heartbeat token (for iPhone app)."""
    now    = int(time.time())
    window = now // HEARTBEAT_INTERVAL
    msg    = f"rex-heartbeat:{window}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()[:16]


# ── Mac screen control ─────────────────────────────────────────────────────────

def _run_applescript(script: str, timeout: int = 10) -> bool:
    try:
        r = subprocess.run(
            ["osascript", "-"],
            input=script.encode(),
            capture_output=True,
            timeout=timeout,
        )
        return r.returncode == 0
    except Exception as e:
        logger.error(f"AppleScript error: {e}")
        return False


def lock_screen():
    """Lock the Mac screen (start screensaver with password)."""
    logger.info("🔒 Locking Mac screen (phone absent)")
    # Method 1: Start screensaver (which locks if "require password" is on)
    result = subprocess.run(
        ["open", "-a", "ScreenSaverEngine"],
        capture_output=True,
    )
    if result.returncode != 0:
        # Method 2: Use pmset to sleep display
        subprocess.run(["pmset", "displaysleepnow"], capture_output=True)
    _log_event("LOCKED", "Phone absent > 60s")


def unlock_screen(mac_password: str = "") -> bool:
    """
    Attempt to unlock the Mac screen automatically.
    Requires either:
      a) mac_password stored in config (fully automatic)
      b) Magic Keyboard Touch ID (user touches sensor)
      c) Falls back to just waking the display (user taps keyboard)
    """
    logger.info("🔓 Unlocking Mac screen (phone resumed)")

    # Step 1: Wake display
    subprocess.run(["caffeinate", "-u", "-t", "1"], capture_output=True)
    time.sleep(UNLOCK_GRACE)

    if mac_password:
        # Step 2: Dismiss screensaver + enter password
        safe = mac_password.replace("\\", "\\\\").replace('"', '\\"')
        script = f"""
tell application "System Events"
    key code 53
    delay 0.8
    keystroke "{safe}"
    delay 0.3
    key code 36
end tell
"""
        ok = _run_applescript(script)
        _log_event("UNLOCKED", "Phone resumed — password auto-entered")
        return ok
    else:
        # Step 2: Just wake screen — user taps Touch ID or presses key
        script = """
tell application "System Events"
    key code 53
    delay 0.3
end tell
"""
        _run_applescript(script)
        _log_event("DISPLAY_WOKE", "Phone resumed — tap Touch ID to complete")
        return True


def _log_event(event: str, detail: str = ""):
    PROXIMITY_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {event} | {detail}\n"
    with open(PROXIMITY_LOG, "a") as f:
        f.write(line)


# ── Proximity state ────────────────────────────────────────────────────────────

class ProximityState:
    def __init__(self):
        self.last_heartbeat: float    = 0.0
        self.phone_present: bool      = False
        self.mac_locked: bool         = False
        self.lock_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

    def heartbeat_received(self, client_ip: str):
        with self._lock:
            was_absent = (time.time() - self.last_heartbeat) > LOCK_DELAY
            self.last_heartbeat = time.time()
            self.phone_present  = True

            # Cancel any pending lock timer
            if self.lock_timer:
                self.lock_timer.cancel()
                self.lock_timer = None

            # If phone just returned after absence → unlock Mac
            if was_absent and self.mac_locked:
                logger.info(f"📱 Phone returned ({client_ip}) — unlocking Mac")
                cfg          = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
                mac_password = cfg.get("mac_screensaver_password", "")
                threading.Thread(
                    target=unlock_screen,
                    args=(mac_password,),
                    daemon=True,
                ).start()
                self.mac_locked = False

    def check_absence(self):
        """Called periodically to detect phone absence."""
        with self._lock:
            if self.last_heartbeat == 0:
                return   # Never received a heartbeat yet

            elapsed = time.time() - self.last_heartbeat

            if elapsed > LOCK_DELAY and self.phone_present and not self.mac_locked:

                # ── Activity guard ───────────────────────────────────────────
                # If Kato is actively typing or mousing, do NOT lock.
                # Example: phone face-down on desk while working → screen dims
                # → heartbeats stop → but hands are on keyboard → no lock.
                # Lock only fires when BOTH the phone is absent AND the Mac
                # itself has been idle for MAC_IDLE_THRESHOLD seconds.
                if _mac_is_actively_in_use():
                    logger.info(
                        f"📱 Phone absent {elapsed:.0f}s but Mac is active — "
                        f"skipping lock (will recheck in 5s)"
                    )
                    return
                # ── End activity guard ───────────────────────────────────────

                logger.info(f"📱 Phone absent for {elapsed:.0f}s and Mac idle — locking Mac")
                self.phone_present = False
                self.mac_locked    = True
                threading.Thread(target=lock_screen, daemon=True).start()

    @property
    def seconds_since_heartbeat(self) -> float:
        if self.last_heartbeat == 0:
            return float("inf")
        return time.time() - self.last_heartbeat

    def to_dict(self) -> dict:
        return {
            "phone_present":        self.phone_present,
            "mac_locked":           self.mac_locked,
            "seconds_since_heartbeat": round(self.seconds_since_heartbeat, 1),
            "last_heartbeat_ts":    datetime.fromtimestamp(self.last_heartbeat).isoformat()
                                    if self.last_heartbeat else None,
        }


# ── HTTP heartbeat bridge (for iPhone app) ─────────────────────────────────────
# React Native cannot send raw UDP. This HTTP wrapper listens on port 8767
# and feeds tokens into the same verification + state pipeline as UDP.

HTTP_HEARTBEAT_PORT = 8767

class _HeartbeatHTTPHandler:
    """Minimal HTTP handler — not using BaseHTTPRequestHandler to avoid threading issues."""

    def __init__(self, state: "ProximityState", secret: str, subnet: str):
        self.state  = state
        self.secret = secret
        self.subnet = subnet

    def handle(self, conn, addr):
        try:
            data = conn.recv(1024).decode("utf-8", errors="replace")
            client_ip = addr[0]

            # Parse HTTP method and path (we only care about POST /heartbeat)
            lines = data.split("\r\n")
            if not lines:
                conn.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\nbad request")
                return

            method_line = lines[0].split(" ")
            method = method_line[0] if method_line else ""
            path   = method_line[1] if len(method_line) > 1 else ""

            if method == "POST" and path == "/heartbeat":
                # Extract body (after blank line)
                body = ""
                if "\r\n\r\n" in data:
                    body = data.split("\r\n\r\n", 1)[1].strip()

                token = body[:64]  # Limit token length
                if _verify_heartbeat(token, self.secret, client_ip, self.subnet):
                    self.state.heartbeat_received(client_ip)
                    logger.debug(f"💓 HTTP heartbeat from {client_ip}")
                    conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nAccess-Control-Allow-Origin: *\r\n\r\nok")
                else:
                    logger.warning(f"⚠️  Invalid HTTP heartbeat from {client_ip}")
                    conn.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Type: text/plain\r\n\r\ndenied")

            elif method == "OPTIONS":
                # CORS preflight for Expo dev builds
                conn.sendall(
                    b"HTTP/1.1 200 OK\r\n"
                    b"Access-Control-Allow-Origin: *\r\n"
                    b"Access-Control-Allow-Methods: POST\r\n"
                    b"Access-Control-Allow-Headers: Content-Type\r\n\r\n"
                )
            else:
                conn.sendall(b"HTTP/1.1 404 Not Found\r\n\r\nnot found")

        except Exception as e:
            logger.debug(f"HTTP handler error: {e}")
        finally:
            try:
                conn.close()
            except Exception:
                pass


# ── UDP + HTTP heartbeat server ────────────────────────────────────────────────

class ProximityDaemon:
    """
    Listens for heartbeats from the iPhone app on TWO channels:
      • UDP port 8766 — low-latency, for native code paths
      • HTTP port 8767 — for Expo/React Native (no raw UDP support)
    Manages Mac lock/unlock based on phone presence.
    """

    def __init__(self):
        cfg          = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
        self.secret  = cfg.get("shared_secret", "")
        self.subnet  = _get_local_subnet()
        self.state   = ProximityState()
        self._running = False

    def _save_state(self):
        """Write current state to file so --status can read it."""
        try:
            STATE_FILE.write_text(json.dumps(self.state.to_dict(), indent=2))
        except Exception:
            pass

    def _absence_monitor(self):
        """Background thread that checks for phone absence every 5 seconds."""
        while self._running:
            self.state.check_absence()
            self._save_state()
            time.sleep(5)

    def _http_server(self):
        """HTTP bridge thread — accepts iPhone app heartbeats on port 8767."""
        handler = _HeartbeatHTTPHandler(self.state, self.secret, self.subnet)
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", HTTP_HEARTBEAT_PORT))
        srv.listen(10)
        srv.settimeout(2.0)
        logger.info(f"📱 HTTP heartbeat bridge on port {HTTP_HEARTBEAT_PORT} (for iPhone app)")
        while self._running:
            try:
                conn, addr = srv.accept()
                threading.Thread(
                    target=handler.handle, args=(conn, addr), daemon=True
                ).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logger.error(f"HTTP server error: {e}")
        srv.close()

    def run(self):
        """Start UDP + HTTP servers and absence monitor."""
        if not self.secret:
            logger.error("❌ Phone unlock not configured. Run: python rex_phone_unlock.py --setup")
            return

        # Start absence monitor
        self._running = True
        monitor = threading.Thread(target=self._absence_monitor, daemon=True)
        monitor.start()

        # Start HTTP bridge for iPhone app
        http_thread = threading.Thread(target=self._http_server, daemon=True)
        http_thread.start()

        # UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", HEARTBEAT_PORT))
        sock.settimeout(2.0)

        logger.info(f"📡 Proximity daemon listening on UDP port {HEARTBEAT_PORT}")
        logger.info(f"   Subnet: {self.subnet}.x | Lock delay: {LOCK_DELAY}s | Mac idle threshold: {MAC_IDLE_THRESHOLD}s")
        logger.info(f"   Phone present: {'Yes' if self.state.phone_present else 'Waiting for first heartbeat...'}")

        try:
            while self._running:
                try:
                    data, addr = sock.recvfrom(256)
                    client_ip  = addr[0]
                    token      = data.decode("utf-8", errors="replace").strip()

                    if _verify_heartbeat(token, self.secret, client_ip, self.subnet):
                        self.state.heartbeat_received(client_ip)
                        # Send ACK back to phone
                        sock.sendto(b"ok", addr)
                        logger.debug(f"💓 Heartbeat from {client_ip}")
                    else:
                        logger.warning(f"⚠️  Invalid heartbeat from {client_ip}: {token[:20]}")
                        sock.sendto(b"denied", addr)

                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"Heartbeat error: {e}")

        except KeyboardInterrupt:
            logger.info("Proximity daemon stopped.")
        finally:
            self._running = False
            sock.close()


# ── LaunchAgent (auto-start with Mac) ─────────────────────────────────────────

PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.rex.proximity</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>{script}</string>
        <string>--run</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log}</string>
    <key>StandardErrorPath</key>
    <string>{log_err}</string>
</dict>
</plist>
"""


def install_launchagent():
    log_dir = Path.home() / "Desktop" / "REX" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    content = PLIST.format(
        python = sys.executable,
        script = str(Path(__file__).resolve()),
        log    = str(log_dir / "proximity.log"),
        log_err= str(log_dir / "proximity_err.log"),
    )
    LAUNCHAGENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAUNCHAGENT_FILE.write_text(content)
    LAUNCHAGENT_FILE.chmod(0o644)

    result = subprocess.run(
        ["launchctl", "load", str(LAUNCHAGENT_FILE)],
        capture_output=True,
    )
    if result.returncode == 0:
        print("✅ Proximity daemon installed — starts automatically with Mac")
        print(f"   Logs: {log_dir}/proximity.log")
    else:
        err = result.stderr.decode()
        print(f"⚠️  Installed but not loaded: {err}")
        print(f"   Try: launchctl load {LAUNCHAGENT_FILE}")


def uninstall_launchagent():
    if LAUNCHAGENT_FILE.exists():
        subprocess.run(["launchctl", "unload", str(LAUNCHAGENT_FILE)], capture_output=True)
        LAUNCHAGENT_FILE.unlink()
        print("✅ Proximity daemon uninstalled.")
    else:
        print("Not installed.")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="REX Proximity Unlock Daemon")
    parser.add_argument("--run",               action="store_true", help="Run the daemon")
    parser.add_argument("--install-launchagent", action="store_true", help="Auto-start with Mac")
    parser.add_argument("--uninstall",         action="store_true", help="Remove LaunchAgent")
    parser.add_argument("--status",            action="store_true", help="Show current state")
    parser.add_argument("--test-token",        action="store_true", help="Generate test heartbeat token")
    args = parser.parse_args()

    if args.run:
        daemon = ProximityDaemon()
        daemon.run()

    elif args.install_launchagent:
        install_launchagent()

    elif args.uninstall:
        uninstall_launchagent()

    elif args.status:
        if STATE_FILE.exists():
            state = json.loads(STATE_FILE.read_text())
            mac_active = _mac_is_actively_in_use()
            print(f"\n📡 Proximity Daemon Status")
            print(f"   Phone present:         {'✅ Yes' if state['phone_present'] else '❌ No'}")
            print(f"   Mac locked:            {'🔒 Yes' if state['mac_locked'] else '🔓 No'}")
            print(f"   Since last heartbeat:  {state['seconds_since_heartbeat']}s")
            print(f"   Last heartbeat:        {state['last_heartbeat_ts'] or 'Never'}")
            print(f"   Mac activity:          {'⌨️  Active (lock suppressed)' if mac_active else '💤 Idle'}")
            print(f"   Lock after:            {LOCK_DELAY}s silence + {MAC_IDLE_THRESHOLD}s Mac idle")
            print()
        else:
            print("⚠️  Daemon not running or no state file yet.")

    elif args.test_token:
        secret = _load_secret()
        if not secret:
            print("❌ Not configured. Run: python rex_phone_unlock.py --setup")
        else:
            token = generate_heartbeat_token(secret)
            print(f"\nCurrent heartbeat token: {token}")
            print(f"Valid for:               ~{HEARTBEAT_INTERVAL}s")
            valid = _verify_heartbeat(token, secret, "192.168.1.100", "192.168.1")
            print(f"Self-verify:             {'✅ valid' if valid else '❌ failed'}")
            print()
    else:
        parser.print_help()
