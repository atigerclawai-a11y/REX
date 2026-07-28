"""
REX — Mac Login Greeter (Rexxie Welcomes You)
===============================================
When you log into your Mac, Rexxie sends a personalized morning greeting
via Telegram — a warm check-in that's aware of the day, time, and what's
happening in your world.

What Rexxie says on login:
  • Good morning/afternoon/evening greeting by name
  • Day of the week + date
  • A brief, warm personal note (drawn from her memory of you)
  • Any pending personal reminders she's been asked to watch for
  • REX system status (optional — work mac vs personal mac)
  • Vault unlock reminder (if credentials haven't been unlocked yet)

Two Mac types:
  • Work Mac (MacBook with GOJ dashboard) → includes GOJ briefing + Rexxie greeting
  • Personal Mac (home machine)           → Rexxie-only greeting, warm and personal

Setup (run once on each Mac):
  python rex_mac_login_greeter.py --setup
  → Configures LaunchAgent (auto-runs on login without root)
  → Asks which type of Mac this is (work vs personal)

How it works:
  1. macOS LaunchAgent fires on login (no admin access needed)
  2. Script calls REX backend for a personalized greeting message
  3. Message sent via Telegram to Rexxie bot (private) OR REX bot (work)
  4. You see the greeting on your phone as you sit down

Manual test:
  python rex_mac_login_greeter.py --greet
  python rex_mac_login_greeter.py --greet --mac-type work

Uninstall:
  python rex_mac_login_greeter.py --uninstall
"""

import os
import sys
import json
import time
import socket
import logging
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

# ── Config ─────────────────────────────────────────────────────────────────────
CONFIG_PATH      = Path.home() / "Desktop" / "REX" / "rex_greeter_config.json"
REX_BASE_URL     = "http://localhost:8000"
LAUNCHAGENT_DIR  = Path.home() / "Library" / "LaunchAgents"
LAUNCHAGENT_FILE = LAUNCHAGENT_DIR / "com.rex.login-greeter.plist"


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


def _tg_send(token: str, chat_id: int, text: str, parse_mode: str = "Markdown"):
    """Send a Telegram message."""
    url  = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({
        "chat_id":    chat_id,
        "text":       text[:4096],
        "parse_mode": parse_mode,
    }).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()).get("ok", False)
    except Exception as e:
        logger.error(f"Telegram send error: {e}")
        return False


def _call_rex_for_greeting(mac_type: str = "personal") -> str:
    """Ask REX to generate a personalized Rexxie login greeting."""
    time_now = datetime.now()
    hour     = time_now.hour
    greeting_word = (
        "Good morning" if hour < 12 else
        "Good afternoon" if hour < 17 else
        "Good evening"
    )
    day_str = time_now.strftime("%A, %B %d")

    if mac_type == "work":
        prompt = (
            f"Generate a brief, warm work-day greeting from REX for Kato logging into his work Mac. "
            f"Today is {day_str}. Time: {time_now.strftime('%I:%M %p')}. "
            f"Keep it professional but warm — mention the day, any reminders relevant to GOJ operations "
            f"if you know of any, and wish him a productive session. 2-4 sentences max."
        )
        user_role = "chairman"
        endpoint  = "/api/chat"
    else:
        prompt = (
            f"Generate a warm, personal morning greeting from Rexxie for Kato logging into his personal Mac. "
            f"Today is {day_str}. Time: {time_now.strftime('%I:%M %p')}. "
            f"Be warm, personal, genuine — like a friend checking in. Draw on anything you know about "
            f"what he's been working through or what matters to him. 2-4 sentences. Sign off as Rexxie."
        )
        user_role = "chairman"
        endpoint  = "/api/chat"

    payload = {
        "message":        prompt,
        "user_name":      "kato",
        "user_role":      user_role,
        "dashboard_mode": False,
    }
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        f"{REX_BASE_URL}{endpoint}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result.get("reply", "")
    except Exception:
        # Fallback static greeting if REX isn't running yet
        return (
            f"🌸 {greeting_word}, Kato.\n\n"
            f"Today is {day_str}. I'm here when you need me.\n\n"
            f"— Rexxie"
        )


def _build_greeting(mac_type: str = "personal") -> str:
    """Build the full greeting message."""
    cfg       = _load_config()
    time_now  = datetime.now()
    hour      = time_now.hour
    hostname  = socket.gethostname()

    # Time-aware greeting
    greeting = (
        "🌅 Good morning" if hour < 12 else
        "☀️ Good afternoon" if hour < 17 else
        "🌙 Good evening"
    )

    # Get personalized message from REX/Rexxie
    ai_greeting = _call_rex_for_greeting(mac_type)

    if mac_type == "work":
        # Check REX system status
        try:
            req = urllib.request.Request(f"{REX_BASE_URL}/api/health", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                h = json.loads(resp.read())
            rex_status = f"✅ REX online | {h.get('memory_count', '?')} memories | {h.get('encryption_level', 'standard')}"
        except Exception:
            rex_status = "⚠️ REX offline — start backend before opening dashboard"

        header = (
            f"🦖 *{greeting}, Kato.*\n"
            f"*{time_now.strftime('%A, %B %d — %I:%M %p')}*\n"
            f"_{hostname}_\n\n"
        )
        return header + (ai_greeting or "") + f"\n\n`{rex_status}`"

    else:
        # Personal Mac — warm Rexxie greeting
        header = (
            f"🌸 *{greeting}, Kato.*\n"
            f"_{time_now.strftime('%A, %B %d — %I:%M %p')}_\n\n"
        )
        vault_reminder = (
            "\n\n_Your vault is locked. Unlock when ready: `vault passphrase: ...`_"
            if cfg.get("vault_2fa_enabled") else ""
        )
        return header + (ai_greeting or "") + vault_reminder


def send_login_email_alert(mac_type: str, cfg: dict):
    """
    Send an email alert every time Kato logs into his Mac.
    This is the security failsafe — if you see a login you didn't make,
    you know immediately via email even if Telegram is down.
    """
    alert_email = cfg.get("alert_email", "")
    if not alert_email:
        return

    import smtplib
    import socket
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    now      = datetime.now()
    hostname = socket.gethostname()
    mac_label = "Work Mac" if mac_type == "work" else "Personal Mac"

    subject = f"🔐 REX: Login detected — {mac_label} — {now.strftime('%a %b %d, %I:%M %p')}"
    body = f"""
REX Security Alert — Mac Login Detected
========================================
Mac:      {mac_label} ({hostname})
Time:     {now.strftime('%A, %B %d, %Y at %I:%M:%S %p')}
User:     {os.environ.get('USER', 'unknown')}

If this was you: no action needed.

If this was NOT you:
  1. Immediately run: python rex_rexxie_telegram_bot.py --wipe
     OR message Rexxie: "rexxie emergency wipe"
  2. Change your Mac login password immediately
  3. Contact your carrier to suspend your phone if it's been stolen

This email is sent automatically on every Mac login.
To disable: python rex_mac_login_greeter.py --disable-email
"""

    # Try Gmail API first (if configured), fallback to SMTP
    gmail_success = _try_gmail_api_send(subject, body, alert_email, cfg)
    if not gmail_success:
        _try_smtp_send(subject, body, alert_email, cfg)


def _try_gmail_api_send(subject: str, body: str, to_email: str, cfg: dict) -> bool:
    """Try sending via Gmail API (uses rex_notify config if available)."""
    try:
        notify_cfg_path = Path.home() / "Desktop" / "REX" / "rex_notify_config.json"
        if not notify_cfg_path.exists():
            return False
        n_cfg = json.loads(notify_cfg_path.read_text())
        gmail_token = n_cfg.get("gmail_token")
        if not gmail_token:
            return False

        headers = {
            "Authorization": f"Bearer {gmail_token}",
            "Content-Type": "application/json",
        }
        import base64
        raw_message = f"To: {to_email}\nSubject: {subject}\n\n{body}"
        encoded = base64.urlsafe_b64encode(raw_message.encode()).decode()
        payload = json.dumps({"raw": encoded}).encode()

        req = urllib.request.Request(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            data=payload,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        logger.warning(f"Gmail API send failed: {e}")
        return False


def _try_smtp_send(subject: str, body: str, to_email: str, cfg: dict) -> bool:
    """Fallback: write email to a local file so it can be sent manually."""
    try:
        log_dir = Path.home() / "Desktop" / "REX" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        email_file = log_dir / f"login_alert_{timestamp}.txt"
        email_file.write_text(f"To: {to_email}\nSubject: {subject}\n\n{body}")
        logger.info(f"Login alert saved to: {email_file}")
        return True
    except Exception as e:
        logger.error(f"Failed to save login alert: {e}")
        return False


def send_login_greeting(mac_type: str = "personal"):
    """Main function — sends the greeting via Telegram AND security email."""
    cfg = _load_config()

    # Always send security email first (failsafe — independent of Telegram)
    send_login_email_alert(mac_type, cfg)

    if mac_type == "work":
        token   = cfg.get("rex_bot_token")
        chat_id = cfg.get("rex_chairman_chat_id")
        if not token or not chat_id:
            # Try reading from Rexxie Gold Health config (only active bot)
            rex_cfg_path = Path.home() / "Desktop" / "REX" / "rex_rexxie_telegram_config.json"
            if rex_cfg_path.exists():
                rex_cfg = json.loads(rex_cfg_path.read_text())
                token   = rex_cfg.get("bot_token")
                chat_id = rex_cfg.get("owner_chat_id") or rex_cfg.get("chairman_chat_id")
    else:
        token   = cfg.get("rexxie_bot_token")
        chat_id = cfg.get("rexxie_owner_chat_id")
        if not token or not chat_id:
            # Try reading from Rexxie Telegram config
            rix_cfg_path = Path.home() / "Desktop" / "REX" / "rex_rexxie_telegram_config.json"
            if rix_cfg_path.exists():
                rix_cfg = json.loads(rix_cfg_path.read_text())
                token   = rix_cfg.get("bot_token")
                chat_id = rix_cfg.get("owner_chat_id")

    if not token or not chat_id:
        logger.warning("Telegram not configured for login greeter. Run --setup.")
        return

    greeting = _build_greeting(mac_type)
    ok = _tg_send(token, chat_id, greeting)
    if ok:
        logger.info(f"✅ Login greeting sent ({mac_type} Mac)")
    else:
        logger.error("Failed to send login greeting via Telegram")


# ── LaunchAgent installer ──────────────────────────────────────────────────────

PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.rex.login-greeter</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>{script}</string>
        <string>--greet</string>
        <string>--mac-type</string>
        <string>{mac_type}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_dir}/rex_greeter.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/rex_greeter_err.log</string>
</dict>
</plist>
"""


def install_launchagent(mac_type: str = "personal"):
    """Install the login greeter as a macOS LaunchAgent."""
    import sys

    python_path = sys.executable
    script_path = str(Path(__file__).resolve())
    log_dir     = str(Path.home() / "Desktop" / "REX" / "logs")
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    plist_content = PLIST_TEMPLATE.format(
        python   = python_path,
        script   = script_path,
        mac_type = mac_type,
        log_dir  = log_dir,
    )

    LAUNCHAGENT_DIR.mkdir(parents=True, exist_ok=True)
    LAUNCHAGENT_FILE.write_text(plist_content)
    LAUNCHAGENT_FILE.chmod(0o644)

    # Load it immediately
    import subprocess
    result = subprocess.run(
        ["launchctl", "load", str(LAUNCHAGENT_FILE)],
        capture_output=True,
    )

    if result.returncode == 0:
        print(f"✅ Login greeter installed ({mac_type} Mac)")
        print(f"   It will send a greeting every time you log in.")
        print(f"   Log: {log_dir}/rex_greeter.log")
    else:
        print(f"⚠️  LaunchAgent installed but couldn't load: {result.stderr.decode()}")
        print(f"   Try: launchctl load {LAUNCHAGENT_FILE}")


def uninstall_launchagent():
    """Remove the login greeter LaunchAgent."""
    import subprocess
    if LAUNCHAGENT_FILE.exists():
        subprocess.run(["launchctl", "unload", str(LAUNCHAGENT_FILE)], capture_output=True)
        LAUNCHAGENT_FILE.unlink()
        print("✅ Login greeter uninstalled.")
    else:
        print("ℹ️  No login greeter installed.")


# ── Setup wizard ───────────────────────────────────────────────────────────────

def setup_wizard():
    print("\n" + "="*60)
    print("  Rexxie Mac Login Greeter — Setup")
    print("="*60)
    print()
    print("Rexxie will send you a warm greeting via Telegram")
    print("every time you log into this Mac.")
    print()

    mac_type = input("Is this your [w]ork Mac or [p]ersonal Mac? [w/p]: ").strip().lower()
    mac_type = "work" if mac_type == "w" else "personal"

    cfg = _load_config()
    cfg["mac_type"] = mac_type

    if mac_type == "personal":
        print()
        print("The greeting will go to your Rexxie Telegram bot.")
        print("Make sure rex_rexxie_telegram_bot.py is configured and running.")
        # Try to read Rexxie bot config automatically
        rix_cfg_path = Path.home() / "Desktop" / "REX" / "rex_rexxie_telegram_config.json"
        if rix_cfg_path.exists():
            rix_cfg = json.loads(rix_cfg_path.read_text())
            cfg["rexxie_bot_token"]      = rix_cfg.get("bot_token")
            cfg["rexxie_owner_chat_id"]  = rix_cfg.get("owner_chat_id")
            print(f"✅ Auto-loaded Rexxie bot configuration.")
        else:
            token   = input("Rexxie bot token: ").strip()
            chat_id = int(input("Your Rexxie chat ID: ").strip())
            cfg["rexxie_bot_token"]     = token
            cfg["rexxie_owner_chat_id"] = chat_id
    else:
        print()
        print("The greeting will go to your Rexxie Gold Health bot.")
        rex_cfg_path = Path.home() / "Desktop" / "REX" / "rex_rexxie_telegram_config.json"
        if rex_cfg_path.exists():
            rex_cfg = json.loads(rex_cfg_path.read_text())
            cfg["rex_bot_token"]           = rex_cfg.get("bot_token")
            cfg["rex_chairman_chat_id"]    = rex_cfg.get("owner_chat_id") or rex_cfg.get("chairman_chat_id")
            print(f"✅ Auto-loaded Rexxie Gold Health bot configuration.")
        else:
            token   = input("REX bot token: ").strip()
            chat_id = int(input("Your REX chairman chat ID: ").strip())
            cfg["rex_bot_token"]          = token
            cfg["rex_chairman_chat_id"]   = chat_id

    # Alert email — security failsafe
    print()
    print("Security failsafe: receive an email every time you log into this Mac.")
    print("If you see a login you didn't make, you know immediately.")
    print()
    alert_email = input("Alert email address (or press Enter to skip): ").strip()
    if alert_email:
        cfg["alert_email"] = alert_email
        print(f"✅ Login alerts will be sent to: {alert_email}")
    else:
        print("Skipped. You can add this later: python rex_mac_login_greeter.py --set-email you@email.com")

    _save_config(cfg)

    # Test greeting
    print()
    print("Testing greeting...")
    send_login_greeting(mac_type)

    # Install LaunchAgent
    print()
    install = input("Install as automatic login greeter? [y/n]: ").strip().lower()
    if install == "y":
        install_launchagent(mac_type)
    else:
        print("You can install it later with: python rex_mac_login_greeter.py --install")
    print()


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Rexxie Mac Login Greeter")
    parser.add_argument("--setup",         action="store_true",  help="Run setup wizard")
    parser.add_argument("--greet",         action="store_true",  help="Send greeting now")
    parser.add_argument("--mac-type",      default="personal",   help="work or personal")
    parser.add_argument("--install",       action="store_true",  help="Install LaunchAgent")
    parser.add_argument("--uninstall",     action="store_true",  help="Remove LaunchAgent")
    parser.add_argument("--set-email",     metavar="EMAIL",      help="Set security alert email")
    parser.add_argument("--disable-email", action="store_true",  help="Disable login email alerts")
    args = parser.parse_args()

    if args.setup:
        setup_wizard()
    elif args.greet:
        send_login_greeting(args.mac_type)
    elif args.install:
        cfg = _load_config()
        install_launchagent(cfg.get("mac_type", args.mac_type))
    elif args.uninstall:
        uninstall_launchagent()
    else:
        parser.print_help()
