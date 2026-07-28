#!/usr/bin/env python3
"""
REX — Notification Setup Wizard
=================================
Run this once to configure your Telegram bot and Gmail alert address.
Your credentials are stored locally at ~/Desktop/REX/rex_notify_config.json

Telegram setup takes about 2 minutes:
  1. Open Telegram → search @BotFather → /newbot
  2. Give it a name (e.g. "REX Alert Bot")
  3. Copy the token BotFather gives you
  4. Open @userinfobot in Telegram to get your Chat ID (it sends it instantly)
  5. Run this script and paste both values

Gmail alert address:
  Just enter where you want alerts sent.
  REX will write alerts to ~/Desktop/REX/alerts/ if Gmail API isn't configured,
  and you can set up the Gmail API later if desired.
"""

import sys
import json
from pathlib import Path

REX_DIR = Path(__file__).parent
sys.path.insert(0, str(REX_DIR))

VENV_PY = REX_DIR / ".venv" / "bin" / "python"
if VENV_PY.exists():
    try:
        import cryptography
    except ImportError:
        import os
        os.execv(str(VENV_PY), [str(VENV_PY)] + sys.argv)


def print_header():
    print("\n" + "=" * 60)
    print("  REX SOVEREIGN — NOTIFICATION SETUP WIZARD")
    print("  Dual channel: Telegram (instant) + Gmail (audit trail)")
    print("=" * 60 + "\n")


def setup_telegram(notify) -> bool:
    print("📲 TELEGRAM SETUP")
    print("-" * 40)
    print("To get your Bot Token:")
    print("  1. Open Telegram → search for @BotFather")
    print("  2. Send /newbot → follow the steps")
    print("  3. Copy the token (looks like: 123456789:ABCdefGHIjklMNOpqrSTUvwxYZ)")
    print()
    print("To get your Chat ID:")
    print("  1. Open Telegram → search for @userinfobot")
    print("  2. Send /start → it replies with your ID (a number like 987654321)")
    print()

    token = input("Paste your Bot Token (or press Enter to skip): ").strip()
    if not token:
        print("⏭️  Skipping Telegram setup\n")
        return False

    chat_id = input("Paste your Chat ID: ").strip()
    if not chat_id:
        print("⏭️  Skipping Telegram setup\n")
        return False

    notify._cfg["telegram_token"]   = token
    notify._cfg["telegram_chat_id"] = chat_id
    notify._save_config()

    print("\nTesting Telegram connection...")
    result = notify._send_telegram(
        "🔵 <b>REX Setup Test</b>\n\n"
        "Your Telegram alerts are configured and working!\n"
        "REX will send you security alerts here in real time.\n\n"
        "<i>REX Sovereign Edition — Kato's GOJ System</i>"
    )
    if result:
        print("✅ Telegram test message sent! Check your phone.\n")
        return True
    else:
        print("❌ Telegram test failed. Check your token and chat ID.\n")
        print("   Common issues:")
        print("   • Token format must be: 123456789:ABCxyz...")
        print("   • You must send /start to the bot at least once before alerts work")
        print("   • Chat ID must be your personal ID, not a group ID\n")
        return False


def setup_email(notify) -> bool:
    print("📧 GMAIL ALERT ADDRESS SETUP")
    print("-" * 40)
    print("Enter the email address where REX should send critical alerts.")
    print("(This is where alerts go — it doesn't have to be your Gmail account)")
    print()

    email = input("Alert email address (or press Enter to skip): ").strip()
    if not email or "@" not in email:
        print("⏭️  Skipping email setup\n")
        return False

    notify.set_alert_email(email)
    print(f"✅ Alert email set to: {email}")
    print("   Note: Gmail API credentials needed for automated sending.")
    print("   Until configured, critical alerts are also saved to ~/Desktop/REX/alerts/\n")
    return True


def run_final_test(notify):
    print("\n🔔 FINAL TEST")
    print("-" * 40)
    status = notify.is_configured()
    print(f"📲 Telegram: {'✅ Ready' if status['telegram'] else '❌ Not configured'}")
    print(f"📧 Gmail:    {'✅ Ready' if status['gmail'] else '⚠️  Will use alert files'}")
    print()

    if not status["telegram"] and not status["gmail"]:
        print("⚠️  No notification channels configured.")
        print("   Alerts will be written to ~/Desktop/REX/alerts/ folder.")
        print("   Run this script again to configure channels.\n")
        return

    run_test = input("Run a test alert now? (y/n): ").strip().lower()
    if run_test == "y":
        result = notify.test_alert()
        if result.get("telegram"):
            print("✅ Telegram: test alert sent successfully")
        elif status["telegram"]:
            print("❌ Telegram: test failed — check token and chat ID")
        print("📄 Alert also written to ~/Desktop/REX/alerts/ for reference\n")


def main():
    print_header()

    from backend.rex_notify import RexNotify
    notify = RexNotify()

    existing = notify.is_configured()
    if existing["telegram"] or existing["gmail"]:
        print("⚙️  Existing configuration found:")
        print(f"   📲 Telegram: {'✅' if existing['telegram'] else '❌'}")
        print(f"   📧 Gmail:    {'✅' if existing['gmail'] else '❌'}")
        update = input("\nReconfigure? (y/n): ").strip().lower()
        if update != "y":
            print("Keeping existing configuration.")
            run_final_test(notify)
            return

    setup_telegram(notify)
    setup_email(notify)
    run_final_test(notify)

    print("=" * 60)
    print("SETUP COMPLETE")
    print()
    print("REX will now send you alerts:")
    print("  🔴 CRITICAL  → Telegram + Gmail (tampering, data leaks)")
    print("  🟡 WARNING   → Telegram + Gmail (audit failures, < 80% training)")
    print("  📋 AUDIT     → Telegram only (bi-daily reports)")
    print("  🎓 TRAINING  → Telegram only (weekly training results)")
    print()
    print("To test at any time, say in REX chat: 'test alert'")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
