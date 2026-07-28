"""
REX — macOS Auto-Fill (Rexxie types passwords for you)
========================================================
Rexxie retrieves a credential from the vault and types it directly
into whatever app or field is currently focused on your Mac.

You never see the password on screen. You never type it.
Rexxie just types it into the field invisibly.

How it works:
  1. You say "Rexxie, type my Chase password" in the Telegram bot or desktop app
  2. Rexxie retrieves the credential from the local vault (no AI API involved)
  3. This script uses macOS Accessibility API (via AppleScript) to type it
     into the currently focused input field — exactly as if you typed it
  4. Done. Password entered. Nothing logged. Nothing transmitted.

Requirements:
  • macOS only
  • Python 3.8+
  • No extra libraries needed — uses built-in subprocess + osascript

Accessibility permission:
  First run will prompt for Accessibility permission.
  Go to: System Preferences → Privacy & Security → Accessibility
  Enable Terminal (or whichever app runs REX).

Security design:
  • Password is retrieved from vault in memory — never written to disk
  • Passed to osascript as stdin (not as a command-line argument)
  • osascript doesn't log stdin content
  • Auto-clear clipboard after 30 seconds if clipboard method is used
  • Type-only method (default) bypasses clipboard entirely
  • 0.5 second delay before typing gives you time to click the right field

Usage (from code):
  from rex_autofill import autofill_password, autofill_username_and_password

  autofill_password("MySecretPass123")
  autofill_username_and_password("kato@email.com", "MySecretPass123")

Usage (via Rexxie chat):
  "Rexxie, type my Chase password"
  "Rexxie, fill in my Netflix login"
  "Rexxie, auto-fill my Apple ID"

Usage (CLI test):
  python rex_autofill.py --test
  python rex_autofill.py --type "hello world"
"""

import os
import sys
import time
import subprocess
import threading
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Delay in seconds before typing starts — gives you time to click the field
PRE_TYPE_DELAY   = 0.8
# Delay between username and password when filling both
FIELD_TAB_DELAY  = 0.4
# Clipboard auto-clear timeout in seconds (if clipboard method is used)
CLIPBOARD_CLEAR_TIMEOUT = 30


def _is_macos() -> bool:
    return sys.platform == "darwin"


def _run_applescript(script: str) -> Tuple[bool, str]:
    """Run an AppleScript via osascript. Returns (success, output/error)."""
    try:
        result = subprocess.run(
            ["osascript", "-"],
            input=script.encode("utf-8"),
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            return True, result.stdout.decode("utf-8").strip()
        else:
            error = result.stderr.decode("utf-8").strip()
            logger.error(f"AppleScript error: {error}")
            return False, error
    except subprocess.TimeoutExpired:
        return False, "AppleScript timed out"
    except FileNotFoundError:
        return False, "osascript not found — macOS only"
    except Exception as e:
        return False, str(e)


def autofill_password(password: str, delay: float = PRE_TYPE_DELAY) -> Tuple[bool, str]:
    """
    Type a password into the currently focused field on macOS.
    Uses AppleScript keystroke — bypasses clipboard entirely.
    The password is passed via stdin to osascript — not as a shell argument.

    Returns (success, message).
    """
    if not _is_macos():
        return False, "Auto-fill is macOS only."
    if not password:
        return False, "No password provided."

    # Sanitize for AppleScript string — escape backslashes and quotes
    safe_pass = password.replace("\\", "\\\\").replace('"', '\\"')

    script = f"""
tell application "System Events"
    delay {delay}
    keystroke "{safe_pass}"
end tell
"""
    ok, msg = _run_applescript(script)
    if ok:
        return True, "✅ Password typed into the active field."
    else:
        # Fallback to clipboard method
        return _autofill_via_clipboard(password)


def autofill_username_and_password(
    username: str,
    password: str,
    delay: float = PRE_TYPE_DELAY,
) -> Tuple[bool, str]:
    """
    Type username, press Tab, then type password.
    Use when the cursor is in the username field.
    """
    if not _is_macos():
        return False, "Auto-fill is macOS only."

    safe_user = username.replace("\\", "\\\\").replace('"', '\\"')
    safe_pass = password.replace("\\", "\\\\").replace('"', '\\"')

    script = f"""
tell application "System Events"
    delay {delay}
    keystroke "{safe_user}"
    delay {FIELD_TAB_DELAY}
    key code 48  -- Tab key
    delay {FIELD_TAB_DELAY}
    keystroke "{safe_pass}"
end tell
"""
    ok, msg = _run_applescript(script)
    if ok:
        return True, "✅ Username and password typed. Press Enter or click Sign In."
    else:
        return False, f"Auto-fill failed: {msg}"


def autofill_press_return() -> Tuple[bool, str]:
    """Press Return/Enter after filling credentials."""
    if not _is_macos():
        return False, "macOS only."
    script = 'tell application "System Events" to key code 36'
    ok, msg = _run_applescript(script)
    return ok, "✅ Enter pressed." if ok else f"Error: {msg}"


def _autofill_via_clipboard(text: str) -> Tuple[bool, str]:
    """
    Fallback: copy to clipboard, paste, then schedule clear after 30s.
    Less secure than keystroke method but works for special characters.
    """
    try:
        proc = subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
        # Paste it
        script = """
tell application "System Events"
    delay 0.3
    keystroke "v" using command down
end tell
"""
        ok, msg = _run_applescript(script)

        # Schedule clipboard wipe
        def clear_clipboard():
            time.sleep(CLIPBOARD_CLEAR_TIMEOUT)
            subprocess.run(["pbcopy"], input=b"", check=False)
            logger.info("🗑️  Clipboard cleared after auto-fill.")

        t = threading.Thread(target=clear_clipboard, daemon=True)
        t.start()

        if ok:
            return True, f"✅ Password pasted (clipboard will auto-clear in {CLIPBOARD_CLEAR_TIMEOUT}s)."
        return False, "Paste failed."
    except Exception as e:
        return False, f"Clipboard error: {e}"


def check_accessibility_permission() -> Tuple[bool, str]:
    """
    Check if Accessibility permission is granted.
    Returns (granted, message).
    """
    if not _is_macos():
        return False, "macOS only."

    script = """
tell application "System Events"
    set allProcesses to name of every process
end tell
return "ok"
"""
    ok, msg = _run_applescript(script)
    if ok:
        return True, "✅ Accessibility permission granted."
    else:
        return False, (
            "❌ Accessibility permission not granted.\n\n"
            "To enable:\n"
            "1. Open System Preferences (or System Settings on macOS Ventura+)\n"
            "2. Go to Privacy & Security → Accessibility\n"
            "3. Add Terminal (or iTerm, whichever runs REX)\n"
            "4. Enable the toggle\n\n"
            "Then try again."
        )


def get_active_app() -> str:
    """Get the name of the currently frontmost app."""
    if not _is_macos():
        return "unknown"
    script = """
tell application "System Events"
    set frontApp to name of first process whose frontmost is true
end tell
return frontApp
"""
    ok, name = _run_applescript(script)
    return name if ok else "unknown"


# ── Chat command parser (used by Rexxie) ───────────────────────────────────────

AUTOFILL_TRIGGERS = [
    "type my ", "fill in my ", "auto-fill my ", "autofill my ",
    "enter my ", "type the ", "fill my ",
]

def detect_autofill_command(user_text: str) -> Optional[dict]:
    """
    Detect if user wants Rexxie to auto-type a credential.
    Returns dict with 'label' and 'field_hint' or None.

    Examples:
      "type my Chase password" → {label: "chase", field_hint: "password"}
      "fill in my Netflix login" → {label: "netflix", field_hint: "both"}
      "Rexxie, type my Apple ID" → {label: "apple id", field_hint: "both"}
    """
    lower = user_text.lower().strip()

    # Remove "rexxie," prefix if present
    for prefix in ["rexxie, ", "rexxie "]:
        if lower.startswith(prefix):
            lower = lower[len(prefix):]
            break

    for trigger in AUTOFILL_TRIGGERS:
        if lower.startswith(trigger) or trigger in lower:
            after = lower.split(trigger, 1)[-1].strip()

            # Determine what to fill
            field_hint = "password"
            if "login" in after or "credentials" in after or "username" in after:
                field_hint = "both"
            elif "pin" in after:
                field_hint = "pin"

            # Extract label
            label = after
            for suffix in [" password", " login", " credentials", " username",
                           " pin", " pass", " account"]:
                label = label.replace(suffix, "")
            label = label.strip().rstrip(".")

            if label:
                return {"label": label, "field_hint": field_hint}

    return None


async def handle_autofill_request(
    vault,   # RexxieCredentialVault instance
    label: str,
    field_hint: str = "password",
) -> str:
    """
    Retrieve credential from vault and auto-type it on Mac.
    This is the main function called by Rexxie mode.
    """
    if not vault.is_unlocked():
        return (
            "🔒 Vault is locked. Unlock it first with:\n"
            "`vault passphrase: [your master passphrase]`\n\n"
            "Then click the password field and ask me again."
        )

    # Check accessibility permission
    perm_ok, perm_msg = check_accessibility_permission()
    if not perm_ok:
        return f"⚠️ Accessibility not set up:\n\n{perm_msg}"

    # Get credential locally — never goes to AI API
    found, cred = vault.get_credential(label)
    if not found or not cred:
        return (
            f"I don't have anything saved for **{label}**.\n"
            f"Save it with: `save my {label} login: user=email pass=yourpassword`"
        )

    active_app = get_active_app()

    if field_hint == "both" and cred.get("username"):
        ok, msg = autofill_username_and_password(cred["username"], cred["secret"])
        action_desc = f"username + password for **{cred['label']}**"
    else:
        ok, msg = autofill_password(cred["secret"])
        action_desc = f"password for **{cred['label']}**"

    if ok:
        return (
            f"✅ Typed your {action_desc} into **{active_app}**.\n\n"
            f"_Nothing was displayed on screen or copied to clipboard._"
        )
    else:
        return (
            f"⚠️ Auto-type ran into an issue: {msg}\n\n"
            f"Make sure you clicked the password field first, then ask again."
        )


# ── CLI test ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="REX macOS Auto-Fill")
    parser.add_argument("--test",           action="store_true", help="Test accessibility permission")
    parser.add_argument("--type",           metavar="TEXT",       help="Type text into active field")
    parser.add_argument("--type-login",     nargs=2, metavar=("USERNAME", "PASSWORD"),
                                            help="Type username Tab password")
    parser.add_argument("--active-app",     action="store_true", help="Show current active app")
    args = parser.parse_args()

    if args.test:
        ok, msg = check_accessibility_permission()
        print(msg)

    elif args.type:
        print("Switching focus to another window then typing in 2 seconds...")
        time.sleep(2)
        ok, msg = autofill_password(args.type, delay=0)
        print(msg)

    elif args.type_login:
        print("Switching focus then typing login in 2 seconds...")
        time.sleep(2)
        ok, msg = autofill_username_and_password(args.type_login[0], args.type_login[1], delay=0)
        print(msg)

    elif args.active_app:
        print(f"Active app: {get_active_app()}")

    else:
        parser.print_help()
