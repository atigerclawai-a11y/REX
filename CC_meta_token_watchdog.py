#!/usr/bin/env python3
"""CC_meta_token_watchdog.py — Daily Meta/IG token health check + refresh + alert cascade.

Cron: 0b29917d09fb runs at 3 AM daily.
Shell wrapper: ~/.hermes/profiles/cloud/scripts/CC_meta_token_watchdog.sh
  exec /Users/mainsobhelper/Desktop/OpenMontage/.venv/bin/python /Users/mainsobhelper/Desktop/REX/CC_meta_token_watchdog.py

Behavior:
  1. Reads tokens from BOTH ~/Desktop/REX/.env AND ~/.hermes/profiles/cloud/.env
  2. Validates each token via /debug_token using app_id|app_secret
  3. Pre-expiry warning cascade: alerts at 14d, 7d, 3d, 1d before expiry
  4. If <14 days and still valid: attempts fb_exchange_token refresh
  5. If expired (code 190): sends immediate Telegram alert
  6. Sends Telegram alerts DIRECTLY (not relay file) to chat_id 5587703834
  7. Logs everything to ~/Desktop/REX/logs/meta_token_watchdog.log
"""
import json
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

# ─── Paths ──────────────────────────────────────────────────────────────────
REX_ENV   = Path.home() / "Desktop" / "REX" / ".env"
CLOUD_ENV = Path.home() / ".hermes" / "profiles" / "cloud" / ".env"
LOG_FILE  = Path.home() / "Desktop" / "REX" / "logs" / "meta_token_watchdog.log"
GRAPH     = "https://graph.facebook.com/v21.0"
TG_CHAT   = "5587703834"

# Check these env files in order
ENV_FILES = [REX_ENV, CLOUD_ENV]

# ─── Helpers ─────────────────────────────────────────────────────────────────

def log(msg: str):
    ts = datetime.now().isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def load_all_env() -> dict:
    """Load env vars from all .env files, later files override earlier ones."""
    env = {}
    for path in ENV_FILES:
        if not path.exists():
            log(f"   ⚠ .env missing: {path}")
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def http_get(url: str, params: dict = None) -> tuple[int, dict | str]:
    """GET with query params, return (status, parsed_json_or_text)."""
    if params:
        qs = urllib.parse.urlencode(params)
        url = f"{url}?{qs}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, raw[:500]
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, body[:500]
    except Exception as e:
        return 0, str(e)


def send_telegram(bot_token: str, message: str) -> bool:
    """Send a Markdown message directly to Kato via Telegram bot API."""
    if not bot_token:
        log("   ⚠ No TELEGRAM_BOT_TOKEN — cannot send alert")
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": TG_CHAT,
        "text": message,
        "parse_mode": "Markdown",
    }).encode()
    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=15) as r:
            ok = r.status == 200
            log(f"   Telegram → {'OK' if ok else 'FAIL ' + str(r.status)}")
            return ok
    except Exception as e:
        log(f"   Telegram ✗ {e}")
        return False


# ─── Token operations ────────────────────────────────────────────────────────

def get_app_secret(env: dict) -> str | None:
    """Find the working Facebook app secret. Try META_APP_SECRET first, then META_IG_APP_SECRET."""
    for key in ["META_APP_SECRET", "META_IG_APP_SECRET"]:
        secret = env.get(key, "")
        if secret and len(secret) > 20:
            return secret
    return None


def validate_token(app_id: str, app_secret: str, token: str) -> dict:
    """Validate a token via /debug_token."""
    app_token = f"{app_id}|{app_secret}"
    status, body = http_get(
        f"{GRAPH}/debug_token",
        {"input_token": token, "access_token": app_token},
    )
    if status != 200:
        return {"ok": False, "status": status, "error": body}
    data = body.get("data", {}) if isinstance(body, dict) else {}
    return {
        "ok": data.get("is_valid", False),
        "expires_at": data.get("expires_at"),
        "scopes": data.get("scopes", []),
        "app_id": data.get("app_id"),
        "user_id": data.get("user_id"),
        "type": data.get("type"),
    }


def days_to_expiry(expires_at_unix: int | None) -> int:
    """Days until token expires. -999 if no expiry, -1 if already expired."""
    if not expires_at_unix:
        return -999  # never expires (system token)
    expiry = datetime.fromtimestamp(expires_at_unix)
    delta = expiry - datetime.now()
    return delta.days


def refresh_token(app_id: str, app_secret: str, short_token: str) -> dict:
    """Exchange short-lived token → long-lived token."""
    status, body = http_get(
        f"{GRAPH}/oauth/access_token",
        {
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_token,
        },
    )
    if status != 200:
        return {"ok": False, "status": status, "error": body}
    if isinstance(body, dict) and "access_token" in body:
        return {
            "ok": True,
            "access_token": body["access_token"],
            "expires_in": body.get("expires_in"),
        }
    return {"ok": False, "status": status, "error": body}


def save_token(env_path: Path, key: str, value: str):
    """Update a single var in an .env file."""
    text = env_path.read_text()
    lines = text.splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}=") or line.startswith(f"{key} ="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n")
    log(f"   wrote {key} (len={len(value)}) → {env_path}")


# ─── Alert formatting ────────────────────────────────────────────────────────

def alert_expired(label: str, app_id: str, error: str, days_dead: int) -> str:
    return (
        f"🔴 *META TOKEN EXPIRED — {label}*\n\n"
        f"App ID: `{app_id}`\n"
        f"Days dead: *{days_dead}*\n"
        f"Error: `{error}`\n\n"
        f"*Action required NOW:* Re\\-authorize at\n"
        f"https://developers\\.facebook\\.com/tools/explorer/{app_id}/\n"
        f"Add scopes: `instagram_basic` \\+ `instagram_content_publish`\n"
        f"Then paste new token here\\."
    )


def alert_expiring_soon(label: str, days: int) -> str:
    urgency = "🟡" if days > 3 else "🟠" if days > 1 else "🔴"
    return (
        f"{urgency} *Meta token expiring in {days} days — {label}*\n\n"
        f"Token `{label}` expires on "
        f"{(datetime.now() + timedelta(days=days)).strftime('%B %d')}\\.\n"
        f"Auto\\-refresh attempted but may need manual OAuth\\.\n\n"
        f"Re\\-auth: https://developers\\.facebook\\.com/tools/explorer/1283301350582072/"
    )


def alert_refreshed(label: str, new_days: int) -> str:
    return f"✅ Meta token auto\\-refreshed \\({label}\\)\\. New expiry \\~{new_days} days\\."


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    log("=== Meta token watchdog started ===")
    env = load_all_env()

    app_id = env.get("META_APP_ID") or env.get("META_IG_APP_ID", "")
    app_secret = get_app_secret(env)
    bot_token = env.get("TELEGRAM_BOT_TOKEN", "")

    if not app_id:
        log("✗ Missing META_APP_ID in all .env files")
        return 1
    if not app_secret:
        log("✗ No valid app secret found (need META_APP_SECRET or META_IG_APP_SECRET with len>20)")
        send_telegram(bot_token, "⚠️ Meta token watchdog: missing app secret in .env files")
        return 1

    log(f"   app_id: {app_id} | secret: {len(app_secret)} chars | bot_token: {'yes' if bot_token else 'NO'}")

    # Collect all tokens from all .env files
    tokens_found = []
    seen = set()
    for env_path in ENV_FILES:
        if not env_path.exists():
            continue
        local_env = {}
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                local_env[k.strip()] = v.strip().strip('"').strip("'")
        token = local_env.get("META_IG_ACCESS_TOKEN", "")
        if token and len(token) > 50 and token not in seen:
            seen.add(token)
            tokens_found.append({
                "token": token,
                "source": str(env_path),
                "env_path": env_path,
                "prefix": token[:20],
                "len": len(token),
            })

    if not tokens_found:
        log("✗ No META_IG_ACCESS_TOKEN found in any .env file")
        send_telegram(bot_token, "⚠️ Meta token watchdog: no token found in any .env")
        return 1

    log(f"   Found {len(tokens_found)} unique token(s)")

    any_ok = False
    any_expired = False

    for i, tok in enumerate(tokens_found):
        label = f"token-{i+1} ({tok['prefix']}...)"
        log(f"\n--- Checking {label} from {tok['source']} ---")
        log(f"   len={tok['len']}")

        # 1) Validate
        validation = validate_token(app_id, app_secret, tok["token"])
        if not validation["ok"]:
            error_msg = ""
            if isinstance(validation.get("error"), dict):
                err = validation["error"].get("error", {})
                error_msg = err.get("message", str(validation["error"]))
            elif isinstance(validation.get("error"), str):
                error_msg = validation["error"][:200]
            else:
                error_msg = str(validation.get("error", "unknown"))[:200]

            log(f"   ✗ Token INVALID: {error_msg}")

            # Code 190 = session expired
            if "190" in error_msg or "expired" in error_msg.lower():
                any_expired = True
                send_telegram(bot_token, alert_expired(
                    label, app_id, error_msg,
                    days_dead=7  # we know it expired ~June 22
                ))
            else:
                log(f"   Non-expiry failure, continuing...")
            continue

        # 2) Check expiry
        days = days_to_expiry(validation.get("expires_at", 0))
        scopes = validation.get("scopes", [])
        log(f"   ✓ Token VALID. {days} days to expiry. Scopes: {scopes}")

        any_ok = True

        # 3) Alert cascade
        if days < 0:
            any_expired = True
            send_telegram(bot_token, alert_expired(
                label, app_id, "Token has already expired", abs(days)
            ))
        elif days <= 1:
            send_telegram(bot_token, alert_expiring_soon(label, days))
        elif days <= 3:
            send_telegram(bot_token, alert_expiring_soon(label, days))
        elif days <= 7:
            send_telegram(bot_token, alert_expiring_soon(label, days))
        elif days <= 14:
            send_telegram(bot_token, alert_expiring_soon(label, days))

        # 4) Refresh attempt (only if <14 days and still valid)
        if 0 < days < 14:
            log(f"   Attempting fb_exchange_token refresh...")
            refresh = refresh_token(app_id, app_secret, tok["token"])
            if refresh["ok"]:
                new_token = refresh["access_token"]
                new_days = (refresh.get("expires_in", 0) or 0) // 86400
                save_token(tok["env_path"], "META_IG_ACCESS_TOKEN", new_token)
                log(f"   ✓ Refresh succeeded. New token: ~{new_days} days.")
                send_telegram(bot_token, alert_refreshed(label, new_days))
            else:
                err = refresh.get("error", "unknown")
                log(f"   ✗ Refresh failed: {err}")
                if days <= 5:
                    send_telegram(bot_token,
                        f"🟡 *Meta token refresh failed* \\(_{label}_\\)\\.\n"
                        f"{days} days left\\. Error: `{str(err)[:200]}`\n"
                        f"Manual OAuth may be needed soon\\."
                    )

    # 5) Summary
    if not any_ok and any_expired:
        log("=== ALL TOKENS EXPIRED — manual re-auth required ===")
    elif any_ok:
        log("=== Meta token watchdog done (at least one token valid) ===")
    else:
        log("=== Meta token watchdog done (unexpected state) ===")

    return 0 if any_ok else 1


if __name__ == "__main__":
    sys.exit(main())
