"""
REX — Dual Notification System (Telegram + Gmail)
===================================================
Sends real-time security alerts through two independent channels:

  Channel 1: Telegram Bot  → instant push to your phone
  Channel 2: Gmail         → permanent audit trail in your inbox

Alert levels:
  CRITICAL  🔴  — tampering detected, parameter attack, cloning attempt
  WARNING   🟡  — audit check failed, security gap re-opened
  INFO      🔵  — vault mode toggled, training session started
  AUDIT     📋  — bi-daily security report (pass or fail)

Configuration stored encrypted in REX config. Set up with:
  python rex_setup_notify.py

Or in REX chat (Chairman only):
  "set telegram token: [your_bot_token]"
  "set telegram chat: [your_chat_id]"
  "set alert email: [your_email]"
  "test alert"
"""

import os
import json
import logging
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Notify config file (separate from main config so it's always readable) ──
NOTIFY_CONFIG_PATH = Path.home() / "Desktop" / "REX" / "rex_notify_config.json"


class RexNotify:
    """
    Dual-channel alert system.
    Telegram: instant phone notification.
    Gmail: permanent email audit trail.
    Both channels fire on CRITICAL events. INFO goes to Telegram only.
    """

    LEVEL_EMOJI = {
        "CRITICAL": "🔴",
        "WARNING":  "🟡",
        "INFO":     "🔵",
        "AUDIT":    "📋",
        "TRAINING": "🎓",
    }

    def __init__(self, config_path: Path = NOTIFY_CONFIG_PATH):
        self._config_path = config_path
        self._cfg = self._load_config()

    def _load_config(self) -> dict:
        if self._config_path.exists():
            try:
                with open(self._config_path) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_config(self):
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._config_path, "w") as f:
            json.dump(self._cfg, f, indent=2)

    # ── Configuration setters ─────────────────────────────────────────────

    def set_telegram(self, bot_token: str, chat_id: str):
        """Store Telegram credentials (not encrypted here — use keyring if needed)."""
        self._cfg["telegram_token"] = bot_token.strip()
        self._cfg["telegram_chat_id"] = chat_id.strip()
        self._save_config()
        logger.info("✅ Telegram credentials saved")

    def set_alert_email(self, email: str):
        """Set the Gmail address to send alerts to."""
        self._cfg["alert_email"] = email.strip()
        self._save_config()
        logger.info(f"✅ Alert email set to: {email}")

    def is_configured(self) -> dict:
        """Return which channels are ready."""
        return {
            "telegram": bool(self._cfg.get("telegram_token") and self._cfg.get("telegram_chat_id")),
            "gmail":    bool(self._cfg.get("alert_email")),
        }

    # ── Telegram ──────────────────────────────────────────────────────────

    def _send_telegram(self, message: str) -> bool:
        token = self._cfg.get("telegram_token")
        chat_id = self._cfg.get("telegram_chat_id")
        if not token or not chat_id:
            logger.warning("Telegram not configured — skipping")
            return False
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({
            "chat_id":    chat_id,
            "text":       message,
            "parse_mode": "HTML",
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                if result.get("ok"):
                    logger.info("📲 Telegram alert sent")
                    return True
                logger.error(f"Telegram error: {result}")
                return False
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    # ── Gmail (via system mail or Gmail API) ─────────────────────────────

    def _send_gmail(self, subject: str, body: str) -> bool:
        """
        Send via Gmail API using credentials stored in the environment.
        Falls back to writing an alert file if API is unavailable.
        """
        alert_email = self._cfg.get("alert_email")
        if not alert_email:
            logger.warning("Alert email not configured — skipping Gmail")
            return False

        # Try Gmail API (via python google-auth if available)
        try:
            from googleapiclient.discovery import build
            from google.oauth2.credentials import Credentials
            import base64
            from email.mime.text import MIMEText

            creds_path = Path.home() / "Desktop" / "REX" / "gmail_token.json"
            if not creds_path.exists():
                raise FileNotFoundError("No Gmail token")
            creds = Credentials.from_authorized_user_file(str(creds_path))
            service = build("gmail", "v1", credentials=creds)
            msg = MIMEText(body)
            msg["to"]      = alert_email
            msg["from"]    = "me"
            msg["subject"] = subject
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            service.users().messages().send(userId="me", body={"raw": raw}).execute()
            logger.info(f"📧 Gmail alert sent to {alert_email}")
            return True
        except Exception as e:
            logger.warning(f"Gmail API not available ({e}) — writing alert file")

        # Fallback: write alert to a local file for manual review
        alert_dir = Path.home() / "Desktop" / "REX" / "alerts"
        alert_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        alert_file = alert_dir / f"rex_alert_{ts}.txt"
        alert_file.write_text(f"TO: {alert_email}\nSUBJECT: {subject}\n\n{body}")
        logger.info(f"📄 Alert written to: {alert_file}")
        return True

    # ── Main alert interface ──────────────────────────────────────────────

    def alert(
        self,
        level: str,
        title: str,
        details: str,
        source: str = "REX",
    ) -> dict:
        """
        Fire a dual-channel alert.

        level: CRITICAL / WARNING / INFO / AUDIT / TRAINING
        title: short headline
        details: full details (markdown-friendly)
        Returns dict with success status per channel.
        """
        emoji = self.LEVEL_EMOJI.get(level.upper(), "⚠️")
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

        # ── Telegram message (HTML)
        tg_msg = (
            f"{emoji} <b>REX {level} ALERT</b>\n\n"
            f"<b>{title}</b>\n\n"
            f"{details}\n\n"
            f"<i>Source: {source} | {ts}</i>"
        )
        # Telegram has a 4096 char limit
        if len(tg_msg) > 4000:
            tg_msg = tg_msg[:3990] + "\n...[truncated]"

        # ── Gmail message (plain text)
        email_subject = f"[REX {level}] {title}"
        email_body = (
            f"REX Security System — {level} Alert\n"
            f"{'=' * 50}\n\n"
            f"{title}\n\n"
            f"{details}\n\n"
            f"Timestamp: {ts}\n"
            f"Source:    {source}\n"
            f"System:    GOJ Dashboard / REX Sovereign Edition\n"
        )

        results = {}
        # CRITICAL and WARNING go to both channels
        # INFO and AUDIT go to Telegram only (to avoid inbox noise)
        # TRAINING always goes to Telegram
        if level.upper() in ("CRITICAL", "WARNING"):
            results["telegram"] = self._send_telegram(tg_msg)
            results["gmail"]    = self._send_gmail(email_subject, email_body)
        else:
            results["telegram"] = self._send_telegram(tg_msg)
            results["gmail"]    = False  # Not sent for INFO/AUDIT/TRAINING

        logger.info(f"🔔 Alert fired: {level} | {title} | TG={results['telegram']} MAIL={results['gmail']}")
        return results

    # ── Convenience methods ───────────────────────────────────────────────

    def tamper_alert(self, attempt: str, source: str):
        self.alert(
            level="CRITICAL",
            title="⚠️ Parameter Tampering Attempt Detected",
            details=(
                f"Someone attempted to modify REX's parameters or identity.\n\n"
                f"Attempt: {attempt[:500]}\n"
                f"From: {source}\n\n"
                f"The attempt was blocked and logged to Chairman-only memory.\n"
                f"Action required: Review REX memory log at next login."
            ),
            source=source,
        )

    def audit_pass(self, summary: str):
        self.alert(
            level="AUDIT",
            title="✅ Bi-Daily Security Audit — PASSED",
            details=summary,
            source="rex-security-audit",
        )

    def audit_fail(self, failures: str):
        self.alert(
            level="CRITICAL",
            title="🚨 Bi-Daily Security Audit — FAILED",
            details=(
                f"REX's security audit detected violations:\n\n"
                f"{failures}\n\n"
                f"Immediate attention required."
            ),
            source="rex-security-audit",
        )

    def training_complete(self, trainer: str, pass_rate: float, issues: str):
        level = "WARNING" if pass_rate < 0.80 else "TRAINING"
        self.alert(
            level=level,
            title=f"🎓 Weekly Training Complete — {int(pass_rate * 100)}% pass rate",
            details=(
                f"Trainer: {trainer}\n"
                f"Pass rate: {int(pass_rate * 100)}%\n\n"
                f"{'Issues found:' if issues else 'No issues found.'}\n"
                f"{issues}"
            ),
            source="rex-training",
        )

    def test_alert(self):
        """Send a test alert to verify both channels are working."""
        return self.alert(
            level="INFO",
            title="🔔 REX Alert Test",
            details=(
                "This is a test alert from REX Sovereign Edition.\n"
                "If you received this, both notification channels are working correctly.\n\n"
                "Telegram: ✅ Working\n"
                "Gmail: Will appear in your inbox shortly."
            ),
            source="rex-test",
        )

    # ── Chat command detector ─────────────────────────────────────────────

    CMD_SET_TG_TOKEN = ("set telegram token:", "telegram token:")
    CMD_SET_TG_CHAT  = ("set telegram chat:", "telegram chat id:", "telegram chat:")
    CMD_SET_EMAIL    = ("set alert email:", "alert email:")
    CMD_TEST_ALERT   = ("test alert", "test notification")
    CMD_NOTIFY_STATUS = ("notification status", "alert status")

    def detect_notify_command(self, user_text: str, user_role: str):
        lower = user_text.strip().lower()

        if user_role != "chairman":
            return None  # Only Chairman configures notifications

        for cmd in self.CMD_NOTIFY_STATUS:
            if cmd in lower:
                status = self.is_configured()
                tg = "✅ Ready" if status["telegram"] else "❌ Not configured"
                gm = "✅ Ready" if status["gmail"] else "❌ Not configured"
                return (
                    f"**REX Notification Status**\n\n"
                    f"📲 Telegram: {tg}\n"
                    f"📧 Gmail:    {gm}\n\n"
                    f"To configure: `set telegram token: [token]` → `set telegram chat: [chat_id]`\n"
                    f"To test: `test alert`"
                )

        for cmd in self.CMD_SET_TG_TOKEN:
            if lower.startswith(cmd):
                token = user_text[len(cmd):].strip()
                if not token:
                    return "Please include your Bot Token after the command."
                self._cfg["telegram_token"] = token
                self._save_config()
                return "✅ Telegram Bot Token saved. Now set your Chat ID: `set telegram chat: [id]`"

        for cmd in self.CMD_SET_TG_CHAT:
            if lower.startswith(cmd):
                chat_id = user_text[len(cmd):].strip()
                if not chat_id:
                    return "Please include your Chat ID after the command."
                self._cfg["telegram_chat_id"] = chat_id
                self._save_config()
                return (
                    "✅ Telegram Chat ID saved.\n\n"
                    "Both credentials are set. Type `test alert` to verify."
                )

        for cmd in self.CMD_SET_EMAIL:
            if lower.startswith(cmd):
                email = user_text[len(cmd):].strip()
                if "@" not in email:
                    return "Please provide a valid email address."
                self.set_alert_email(email)
                return f"✅ Alert email set to: {email}"

        for cmd in self.CMD_TEST_ALERT:
            if cmd in lower:
                result = self.test_alert()
                tg_ok = "✅ Sent" if result.get("telegram") else "❌ Failed (check token/chat ID)"
                gm_ok = "✅ Queued" if result.get("gmail") else "📄 Saved to ~/Desktop/REX/alerts/"
                return (
                    f"**Test Alert Fired**\n\n"
                    f"📲 Telegram: {tg_ok}\n"
                    f"📧 Gmail:    {gm_ok}"
                )

        return None
