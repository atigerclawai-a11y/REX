#!/usr/bin/env python3
"""
CC_claus_orchestrator.py — Gold Health Systems Build Orchestrator
v2.0 · June 4, 2026 · Gold Health Systems

Claus is the system that never sleeps. He monitors all GHS services, guards
the build registry, sends daily orchestration briefings, and keeps Kato
informed without noise.

Modes (--telegram is backward-compatible with the existing plist schedule):
  --telegram   3x-daily snapshot run (plist default; runs once, exits)
  --brief      Manually trigger the 9 AM morning briefing and exit
  --status     Print current system status to stdout and exit
  --loop       Continuous monitoring loop (update plist to KeepAlive for 24/7)

Key files:
  State:  ~/Desktop/REX/CC_claus_state.json
  Logs:   ~/.hermes/claus/watchman.log
  Brief:  reads CC_PHASE_STATUS.md + CC_MASTER_BUILD_LOG.md dynamically

Bot:  @Hermes_Cloud_May_bot  (NEVER @goldhealth_rexxie_bot — zero crossover)
Plist: com.hermes.claus-watchman.plist → points to this file after plist update

Backward compatibility:
  The existing plist passes --telegram and exits. This script handles that flag
  identically to the old claus_watchman.py: run once, alert if something is RED,
  send morning brief if it's the right time, then exit cleanly.
"""

import asyncio
import json
import logging
import os
import re
import socket
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ════════════════════════════════════════════════════════════════════════════════
# PATHS & CONSTANTS
# ════════════════════════════════════════════════════════════════════════════════

HOME              = Path.home()
REX               = HOME / "Desktop/REX"
STATE_FILE        = REX    / "CC_claus_state.json"
PHASE_STATUS_MD   = REX    / "CC_PHASE_STATUS.md"
MASTER_BUILD_LOG  = REX    / "CC_MASTER_BUILD_LOG.md"
MASTER_LIST_JSON  = REX    / "master_list.json"
TG_CONFIG_JSON    = REX    / "rex_telegram_config.json"
HERMES_ENV        = HOME   / ".hermes/profiles/cloud/.env"
PIPELINE_DIR      = HOME   / ".hermes-cloud/home/goj-pipeline/data"
AUTH_DB           = HOME   / "Documents/goj files/dashboard/auth_tracker.db"
GMAIL_TOKEN       = HOME   / ".rex_google_token.json"
LOG_DIR           = HOME   / ".hermes/claus"
LOG_PATH          = LOG_DIR / "watchman.log"

CHAIRMAN_CHAT_ID      = 5587703834
BRIEF_HOUR            = 9      # send morning brief at 9 AM (triggered by 8 AM plist run)
LOOP_CHECK_SECS       = 60     # health check interval in --loop mode
REGISTRY_CHECK_SECS   = 600    # registry guardian every 10 minutes
DIGEST_INTERVAL_SECS  = 3600   # hourly file digest
FAIL_THRESHOLD_URGENT = 3      # consecutive failures before URGENT alert
ATTENDANCE_MAX        = 500    # anomaly ceiling
ATTENDANCE_MIN_WKD    = 50     # anomaly floor (weekdays only)
PIPELINE_STALE_HOURS  = 26     # pipeline JSON older than this → alert

# ════════════════════════════════════════════════════════════════════════════════
# SERVICES REGISTRY
# Each entry: name, port, path, emoji, restart (shown to Kato — never auto-run)
# ════════════════════════════════════════════════════════════════════════════════

SERVICES: List[Dict] = [
    {
        "name":    "Hermes Cloud GW",
        "port":    3002,
        "path":    "/health",
        "emoji":   "🧠",
        "restart": (
            "launchctl unload ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist "
            "&& pkill -f 'hermes_cli.main.*gateway' && sleep 8 "
            "&& launchctl load ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist"
        ),
    },
    {
        "name":    "REX FastAPI",
        "port":    8000,
        "path":    "/api/health",
        "emoji":   "🦖",
        "restart": (
            "launchctl unload ~/Library/LaunchAgents/com.rex.backend.plist "
            "&& sleep 3 && launchctl load ~/Library/LaunchAgents/com.rex.backend.plist"
        ),
    },
    {
        "name":    "GOJ Dashboard",
        "port":    8080,
        "path":    "/",
        "emoji":   "🏥",
        "restart": (
            "launchctl unload ~/Library/LaunchAgents/com.goj.datarex.plist "
            "&& sleep 3 && launchctl load ~/Library/LaunchAgents/com.goj.datarex.plist"
        ),
    },
    {
        "name":    "Tiger Claw API",
        "port":    27226,
        "path":    "/health",
        "emoji":   "🐯",
        "restart": (
            "launchctl unload ~/Library/LaunchAgents/com.tigerclaw.api.plist "
            "&& sleep 3 && launchctl load ~/Library/LaunchAgents/com.tigerclaw.api.plist"
        ),
    },
    {
        "name":    "CC Stats API",
        "port":    8001,
        "path":    "/health",
        "emoji":   "📊",
        "restart": "launchctl load ~/Library/LaunchAgents/com.ghs.cc-stats-api.plist",
    },
    {
        "name":    "Ollama",
        "port":    11434,
        "path":    "/api/tags",
        "emoji":   "🦙",
        "restart": "ollama serve",
    },
    {
        "name":    "LM Studio",
        "port":    1234,
        "path":    "/v1/models",
        "emoji":   "🔬",
        "restart": "(open LM Studio app → Start Server)",
    },
    {
        "name":    "Open WebUI",
        "port":    3000,
        "path":    "/",
        "emoji":   "🌐",
        "restart": "docker start $(docker ps -aq --filter name=open-webui) 2>/dev/null || docker start open-webui",
    },
    {
        "name":    "Hermie Local GW",
        "port":    65001,
        "path":    "/v1/models",
        "emoji":   "🤖",
        "restart": (
            "launchctl unload ~/Library/LaunchAgents/ai.hermes.gateway.plist "
            "&& sleep 3 && launchctl load ~/Library/LaunchAgents/ai.hermes.gateway.plist"
        ),
    },
]

# ════════════════════════════════════════════════════════════════════════════════
# LOGGING
# ════════════════════════════════════════════════════════════════════════════════

LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("claus")

# ════════════════════════════════════════════════════════════════════════════════
# TOKEN / CONFIG HELPERS
# ════════════════════════════════════════════════════════════════════════════════

def _parse_env_file(path: Path) -> Dict[str, str]:
    """Parse a .env file into a dict (ignores comments and blank lines)."""
    result: Dict[str, str] = {}
    try:
        for line in path.read_text(errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                result[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return result


def get_bot_token() -> Optional[str]:
    """
    Resolve the Hermes bot token for system alerts.
    Priority: HERMES_BOT_TOKEN env var → ~/.hermes/profiles/cloud/.env → rex_telegram_config.json

    IMPORTANT: This is the Hermes bot (@Hermes_Cloud_May_bot), NEVER the Rexxie
    bot (@goldhealth_rexxie_bot). Rexxie is Kato's private confidant; she is not
    used for system-level alerts under any circumstances.
    """
    # 1. Environment variable (set by plist EnvironmentVariables section)
    token = os.environ.get("HERMES_BOT_TOKEN")
    if token:
        return token

    # 2. Hermes cloud .env file
    env = _parse_env_file(HERMES_ENV)
    token = env.get("HERMES_BOT_TOKEN") or env.get("TELEGRAM_BOT_TOKEN")
    if token:
        return token

    # 3. rex_telegram_config.json (existing fallback used by other GHS scripts)
    try:
        cfg = json.loads(TG_CONFIG_JSON.read_text())
        token = cfg.get("bot_token")
        if token:
            return token
    except Exception:
        pass

    log.error(
        "Hermes bot token not found. Checked: $HERMES_BOT_TOKEN, %s, %s",
        HERMES_ENV,
        TG_CONFIG_JSON,
    )
    return None

# ════════════════════════════════════════════════════════════════════════════════
# STATE MANAGEMENT
# State persists across plist invocations via CC_claus_state.json
# ════════════════════════════════════════════════════════════════════════════════

def _blank_state() -> Dict:
    return {
        "version": 2,
        # {name: {up: int, total: int, consecutive_fail: int, last_up: bool}}
        "service_stats":       {},
        "core_file_mtimes":    {},   # {filename: mtime_float} for tamper detection
        "known_cc_files":      [],   # CC_ filenames seen in registry check
        "digest_queue":        [],   # files pending hourly digest
        "digest_sent":         [],   # files already digested (bounded to 200)
        "pae_queue":           [],   # [{id, title, description, commands, status, sent_ts}]
        "tg_update_offset":    0,    # Telegram getUpdates offset (loop mode)
        "last_brief_date":     None, # ISO date "YYYY-MM-DD"
        "last_registry_check": None, # ISO datetime
        "last_digest_ts":      None, # ISO datetime
        "last_goj_alert_ts":   None, # ISO datetime (rate-limit GOJ alerts)
    }


def load_state() -> Dict:
    """Load persistent state, merging any new keys from blank template."""
    try:
        data = json.loads(STATE_FILE.read_text())
        defaults = _blank_state()
        for k, v in defaults.items():
            data.setdefault(k, v)
        return data
    except Exception:
        return _blank_state()


def save_state(state: Dict) -> None:
    try:
        REX.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2, default=str))
    except Exception as e:
        log.error("Failed to save state: %s", e)

# ════════════════════════════════════════════════════════════════════════════════
# TELEGRAM HELPERS
# All messages go through tg_send() using stdlib urllib — no external deps.
# ════════════════════════════════════════════════════════════════════════════════

def tg_send(
    text: str,
    bot_token: str,
    chat_id: int = CHAIRMAN_CHAT_ID,
    parse_mode: str = "Markdown",
    reply_markup: Optional[Dict] = None,
) -> bool:
    """
    Send a Telegram message via the Hermes bot.
    Truncates to 4096 chars (Telegram limit). Returns True on success.
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload: Dict[str, Any] = {
        "chat_id":                  chat_id,
        "text":                     text[:4096],
        "parse_mode":               parse_mode,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    data = json.dumps(payload).encode("utf-8")
    try:
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            if not result.get("ok"):
                log.error("Telegram API error: %s", result.get("description", result))
                return False
            return True
    except Exception as e:
        log.error("Telegram send failed: %s", e)
        return False


def tg_send_pae(
    title: str,
    description: str,
    commands: str,
    bot_token: str,
    pae_id: str = "",
) -> bool:
    """
    Send a PAE proposal to Kato with inline keyboard (for loop-mode callback handling).
    Claus NEVER auto-executes approved commands — approval is logged, command shown.
    """
    id_str = f" `[{pae_id}]`" if pae_id else ""
    text = (
        f"📋 *PAE PROPOSAL*{id_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"*{title}*\n\n"
        f"{description}\n\n"
        f"*Commands (copy-paste to execute):*\n"
        f"```\n{commands}\n```\n\n"
        f"_Reply_ `YES {pae_id}` _or_ `NO {pae_id}` _to record decision._"
    )
    keyboard: Optional[Dict] = None
    if pae_id:
        keyboard = {
            "inline_keyboard": [[
                {"text": "✅ APPROVE", "callback_data": f"pae_yes_{pae_id}"},
                {"text": "❌ REJECT",  "callback_data": f"pae_no_{pae_id}"},
            ]]
        }
    return tg_send(text, bot_token, reply_markup=keyboard)

# ════════════════════════════════════════════════════════════════════════════════
# MODULE 1: SERVICE HEALTH MONITOR
# Async concurrent checks with uptime tracking and escalating alerts.
# ════════════════════════════════════════════════════════════════════════════════

def _check_one_service(svc: Dict) -> Dict:
    """
    Check a single service. Returns {name, up, latency_ms, error}.
    Uses a socket probe first, then a quick HTTP GET.
    Treats HTTP 4xx as "alive" (service is responding, even if route is missing).
    """
    name    = svc["name"]
    port    = svc["port"]
    path    = svc["path"]
    t0      = time.monotonic()

    # Phase 1: TCP connection
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=5):
            pass
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        ms = (time.monotonic() - t0) * 1000
        return {"name": name, "up": False, "latency_ms": ms, "error": str(e)[:60]}

    # Phase 2: HTTP response
    try:
        url = f"http://127.0.0.1:{port}{path}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            ms = (time.monotonic() - t0) * 1000
            return {"name": name, "up": resp.getcode() < 500, "latency_ms": ms, "error": ""}
    except urllib.error.HTTPError as e:
        ms = (time.monotonic() - t0) * 1000
        # 4xx → service is alive; 5xx → down
        up = (e.code is not None and e.code < 500)
        return {"name": name, "up": up, "latency_ms": ms, "error": f"HTTP {e.code}" if not up else ""}
    except Exception as e:
        ms = (time.monotonic() - t0) * 1000
        return {"name": name, "up": False, "latency_ms": ms, "error": str(e)[:60]}


async def run_health_checks() -> List[Dict]:
    """Run all service checks concurrently using a thread pool (stdlib HTTP is blocking)."""
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=len(SERVICES)) as pool:
        tasks = [loop.run_in_executor(pool, _check_one_service, svc) for svc in SERVICES]
        return list(await asyncio.gather(*tasks))


def _update_stats(results: List[Dict], state: Dict) -> List[str]:
    """
    Update per-service uptime counters. Returns list of service names that
    just crossed the FAIL_THRESHOLD_URGENT consecutive-failure mark.
    """
    newly_urgent: List[str] = []
    for r in results:
        name  = r["name"]
        stats = state["service_stats"].setdefault(name, {
            "up": 0, "total": 0, "consecutive_fail": 0, "last_up": None
        })
        stats["total"] += 1
        if r["up"]:
            stats["up"] += 1
            stats["consecutive_fail"] = 0
        else:
            stats["consecutive_fail"] += 1
            if stats["consecutive_fail"] == FAIL_THRESHOLD_URGENT:
                newly_urgent.append(name)
        stats["last_up"] = r["up"]
    return newly_urgent


def _uptime_pct(state: Dict, name: str) -> str:
    s = state["service_stats"].get(name, {})
    total = s.get("total", 0)
    up    = s.get("up", 0)
    return f"{up / total * 100:.1f}%" if total > 0 else "?"


def send_failure_alert(name: str, consecutive: int, error: str, bot_token: str) -> None:
    """Alert Kato about a service that has failed FAIL_THRESHOLD_URGENT times in a row."""
    svc = next((s for s in SERVICES if s["name"] == name), {})
    level   = "🚨 *URGENT*" if consecutive >= FAIL_THRESHOLD_URGENT else "⚠️ *WARNING*"
    emoji   = svc.get("emoji", "⚙️")
    restart = svc.get("restart", "check LaunchAgent plist")
    msg = (
        f"{level} — {emoji} *{name}* is DOWN\n"
        f"Consecutive failures: {consecutive}\n"
        f"Error: `{error or 'no response on port'}`\n\n"
        f"*Suggested restart command:*\n`{restart}`\n\n"
        f"_Claus does not auto-restart — run manually after verifying._"
    )
    tg_send(msg, bot_token)
    log.warning("ALERT: %s down, %d consecutive failures", name, consecutive)

# ════════════════════════════════════════════════════════════════════════════════
# MODULE 2: DAILY ORCHESTRATION BRIEFING
# Reads CC_PHASE_STATUS.md and CC_MASTER_BUILD_LOG.md dynamically.
# Sends at 9 AM (triggered by the 8 AM plist run via should_send_brief()).
# ════════════════════════════════════════════════════════════════════════════════

def _parse_phase_table() -> str:
    """Extract compact phase status rows from CC_PHASE_STATUS.md."""
    if not PHASE_STATUS_MD.exists():
        return "_(CC\\_PHASE\\_STATUS.md not found)_"
    try:
        lines = PHASE_STATUS_MD.read_text(errors="replace").splitlines()
        rows  = []
        in_table = False
        for line in lines:
            # Start of phase table
            if "|" in line and ("Phase Name" in line or "| 1 |" in line):
                in_table = True
            if not in_table:
                continue
            if line.strip().startswith("|") and "|" in line[1:]:
                cols = [c.strip() for c in line.split("|")[1:-1]]
                # Skip header / separator rows
                if not cols or not cols[0].replace("*","").replace("#","").strip().isdigit():
                    continue
                num    = re.sub(r"[^0-9V\-]", "", cols[0])
                name   = re.sub(r"\*\*|`", "", cols[1])[:26].strip()
                status = re.sub(r"\*\*|`", "", cols[3])[:22].strip() if len(cols) > 3 else ""
                if   "COMPLETE" in status or "LOCKED" in status: icon = "✅"
                elif "IN PROGRESS" in status or "RUNNING" in status: icon = "🔨"
                elif "NOT RUN" in status or "NOT START" in status:   icon = "🔴"
                elif "SPECCED" in status or "PARTIAL" in status:     icon = "🟡"
                elif "PENDING" in status:                             icon = "🟠"
                else:                                                 icon = "⚪"
                rows.append(f"{icon} Ph{num}: {name}")
            # End of table at blank line after we've found rows
            elif in_table and rows and not line.strip():
                break
        return "\n".join(rows[:16]) if rows else "_(phase table not parseable)_"
    except Exception as e:
        return f"_(parse error: {e})_"


def _parse_open_items() -> str:
    """Pull top 5 recommended actions from CC_PHASE_STATUS.md."""
    if not PHASE_STATUS_MD.exists():
        return "_(not available)_"
    try:
        text  = PHASE_STATUS_MD.read_text(errors="replace")
        items: List[str] = []
        in_section = False
        for line in text.splitlines():
            if re.search(r"Recommended Phase Advancement|OPEN ITEMS|Priority.*today", line, re.I):
                in_section = True
                continue
            if in_section:
                if line.strip().startswith("#") and "Recommended" not in line:
                    break
                clean = re.sub(r"\*\*|`|#+", "", line).strip("- 0123456789.").strip()
                if len(clean) > 10 and not clean.startswith("|"):
                    items.append(f"• {clean[:72]}")
                if len(items) >= 5:
                    break
        return "\n".join(items) if items else "_(check CC\\_PHASE\\_STATUS.md)_"
    except Exception:
        return "_(parse error)_"


def _parse_pae_pending() -> str:
    """Extract pending PAE proposal titles from CC_PHASE_STATUS.md."""
    if not PHASE_STATUS_MD.exists():
        return ""
    try:
        text      = PHASE_STATUS_MD.read_text(errors="replace")
        proposals = re.findall(r"###\s*(PAE-\d+[^\n#]*)", text)
        if not proposals:
            return ""
        lines = ["*Pending PAEs (from CC\\_PHASE\\_STATUS.md):*"]
        for p in proposals[:4]:
            lines.append(f"  📋 {p.strip()[:60]}")
        return "\n".join(lines)
    except Exception:
        return ""


def _recent_build_activity() -> str:
    """Pull the TODAY'S CHANGES headline from CC_MASTER_BUILD_LOG.md."""
    if not MASTER_BUILD_LOG.exists():
        return "_(CC\\_MASTER\\_BUILD\\_LOG.md not found)_"
    try:
        text  = MASTER_BUILD_LOG.read_text(errors="replace")
        # Find "TODAY'S CHANGES" section
        match = re.search(r"##\s*TODAY.S CHANGES.*?\n(.*?)(?=\n##\s)", text, re.S | re.I)
        if not match:
            return "_(TODAY'S CHANGES section not found)_"
        section = match.group(1)
        entries: List[str] = []
        for line in section.splitlines():
            clean = re.sub(r"\*\*|`|#+", "", line).strip("- ").strip()
            # Keep bold headers that describe changes
            if clean and not clean.startswith("|") and len(clean) > 8:
                entries.append(f"• {clean[:72]}")
            if len(entries) >= 4:
                break
        return "\n".join(entries) if entries else "_(no entries today)_"
    except Exception:
        return "_(parse error)_"


def _new_cc_files_today() -> int:
    """Count CC_ files modified today."""
    today = date.today()
    try:
        return sum(
            1 for f in REX.glob("CC_*")
            if f.is_file() and datetime.fromtimestamp(f.stat().st_mtime).date() == today
        )
    except Exception:
        return 0


async def send_morning_brief(
    results: List[Dict],
    state: Dict,
    bot_token: str,
) -> None:
    """Build and send the 9 AM daily orchestration brief to Kato."""
    today_str    = date.today().strftime("%A, %B %-d, %Y")
    services_up  = sum(1 for r in results if r["up"])
    services_dn  = len(results) - services_up
    now_str      = datetime.now().strftime("%H:%M")

    # System status block
    svc_lines: List[str] = []
    for r in results:
        svc   = next((s for s in SERVICES if s["name"] == r["name"]), {})
        emoji = svc.get("emoji", "⚙️")
        port  = svc.get("port", "?")
        if r["up"]:
            uptime = _uptime_pct(state, r["name"])
            svc_lines.append(f"✅ {emoji} {r['name']} :{port} ({uptime} uptime)")
        else:
            cf    = state["service_stats"].get(r["name"], {}).get("consecutive_fail", 0)
            fsufx = f" [{cf}× down]" if cf > 1 else ""
            svc_lines.append(f"❌ {emoji} {r['name']} :{port}{fsufx}")

    phase_summary    = _parse_phase_table()
    open_items       = _parse_open_items()
    pae_pending      = _parse_pae_pending()
    build_activity   = _recent_build_activity()
    new_today        = _new_cc_files_today()
    pae_queue_count  = len([p for p in state.get("pae_queue", []) if p.get("status") == "pending"])

    msg = (
        f"🏛️ *GHS Morning Brief — {today_str}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 *SYSTEM STATUS* — {services_up}/{len(results)} services UP\n"
        f"{chr(10).join(svc_lines)}\n\n"
        f"🔨 *BUILD STATUS* (19-phase plan)\n"
        f"{phase_summary}\n\n"
        f"📋 *OPEN ITEMS*\n"
        f"{open_items}\n\n"
        f"🔧 *TODAY'S BUILD ACTIVITY*\n"
        f"{build_activity}\n"
        f"  CC\\_ files modified today: {new_today}\n"
    )

    if pae_pending:
        msg += f"\n{pae_pending}\n"

    if pae_queue_count:
        msg += f"\n⏳ *Claus PAE queue:* {pae_queue_count} proposal(s) awaiting decision\n"

    msg += (
        f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"_Claus v2 · {now_str} · Gold Health Systems_"
    )

    if tg_send(msg, bot_token):
        state["last_brief_date"] = date.today().isoformat()
        log.info("Morning brief sent (%d up, %d down)", services_up, services_dn)
    else:
        log.error("Morning brief failed to send")


def should_send_brief(state: Dict) -> bool:
    """
    True if: (a) current hour is between 8–10 AM, and
             (b) no brief has been sent today.
    The plist triggers at 8 AM, so the 8 AM run is where we send the 9 AM brief.
    """
    last_date = state.get("last_brief_date")
    now_hour  = datetime.now().hour
    today     = date.today().isoformat()
    return (BRIEF_HOUR - 1) <= now_hour <= (BRIEF_HOUR + 1) and last_date != today

# ════════════════════════════════════════════════════════════════════════════════
# MODULE 3: BUILD REGISTRY GUARDIAN
# Watches master_list.json + new CC_ files; alerts on unregistered files
# and unexpected changes to core production files.
# ════════════════════════════════════════════════════════════════════════════════

_CORE_FILES = [
    HOME / "Desktop/REX/backend/main.py",
    MASTER_LIST_JSON,
    MASTER_BUILD_LOG,
    PHASE_STATUS_MD,
]


def _registered_names(master: Dict) -> set:
    try:
        return {c["name"] for c in master.get("components", [])}
    except Exception:
        return set()


def run_registry_guardian(state: Dict, bot_token: str) -> None:
    """
    Detect new CC_*.py files that aren't in master_list.json and propose
    registry entries to Kato. Also watch core files for unexpected changes.
    """
    # ── Load registry ──
    try:
        master = json.loads(MASTER_LIST_JSON.read_text())
    except Exception as e:
        log.warning("Registry guardian: cannot read master_list.json — %s", e)
        return

    registered   = _registered_names(master)
    current_cc   = sorted(f.name for f in REX.glob("CC_*.py") if f.is_file())
    known        = set(state.get("known_cc_files", []))
    new_files    = [f for f in current_cc if f not in known]

    for fname in new_files:
        stem     = fname.replace(".py", "").replace("CC_", "").replace("_", " ").title()
        proposal = json.dumps({
            "name":        stem,
            "description": f"Auto-detected: {fname}",
            "category":    "auto-detected",
            "milestone":   "unassigned",
            "status":      "building",
            "stage_percent": 10,
            "stage_label": "New",
        }, indent=2)
        msg = (
            f"📂 *New CC\\_ script detected*\n"
            f"`{fname}`\n\n"
            f"Not yet in `master\\_list.json`. Proposed entry:\n"
            f"```json\n{proposal}\n```\n"
            f"Add manually if this is a registered build component."
        )
        tg_send(msg, bot_token)
        log.info("Registry: new file proposal sent for %s", fname)

    if new_files:
        state["known_cc_files"] = current_cc

    # ── Core file tamper detection ──
    prev_mtimes: Dict[str, float] = state.get("core_file_mtimes", {})
    changed: List[str] = []
    new_mtimes: Dict[str, float] = {}
    for cf in _CORE_FILES:
        if cf.exists():
            mtime = cf.stat().st_mtime
            key   = cf.name
            new_mtimes[key] = mtime
            if key in prev_mtimes and abs(prev_mtimes[key] - mtime) > 2:
                changed.append(cf.name)

    state["core_file_mtimes"] = {**prev_mtimes, **new_mtimes}

    if changed:
        msg = (
            f"⚠️ *Core file modified*\n"
            f"File(s): `{'`, `'.join(changed)}`\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"Verify this was an intentional change."
        )
        tg_send(msg, bot_token)
        log.warning("Core files changed: %s", changed)

    state["last_registry_check"] = datetime.now().isoformat()
    log.info("Registry guardian: checked %d CC_ files, %d new", len(current_cc), len(new_files))

# ════════════════════════════════════════════════════════════════════════════════
# MODULE 4: AGENT COMPLETION MONITOR
# Watches for new/modified CC_ files, aggregates into hourly digest.
# Avoids per-file notification spam.
# ════════════════════════════════════════════════════════════════════════════════

def _scan_recent_cc_files(state: Dict, window_minutes: int = 65) -> List[str]:
    """Return CC_ files modified in the last window_minutes that aren't queued yet."""
    cutoff   = time.time() - (window_minutes * 60)
    queued   = set(state.get("digest_queue", []))
    sent     = set(state.get("digest_sent", []))
    new_ones: List[str] = []
    try:
        for f in REX.iterdir():
            if f.name.startswith("CC_") and f.is_file():
                try:
                    if f.stat().st_mtime > cutoff and f.name not in queued and f.name not in sent:
                        new_ones.append(f.name)
                except Exception:
                    pass
    except Exception as e:
        log.debug("scan_recent_cc_files error: %s", e)
    return sorted(new_ones)


def update_digest_queue(state: Dict) -> int:
    """Append newly detected files to the digest queue. Returns count added."""
    new_files = _scan_recent_cc_files(state)
    queue = state.setdefault("digest_queue", [])
    added = 0
    for f in new_files:
        if f not in queue:
            queue.append(f)
            added += 1
    if added:
        log.info("Digest queue: +%d files (total %d pending)", added, len(queue))
    return added


def should_flush_digest(state: Dict) -> bool:
    """True if it's been ≥ DIGEST_INTERVAL_SECS since the last digest flush and queue is non-empty."""
    if not state.get("digest_queue"):
        return False
    last = state.get("last_digest_ts")
    if not last:
        return True
    try:
        elapsed = (datetime.now() - datetime.fromisoformat(last)).total_seconds()
        return elapsed >= DIGEST_INTERVAL_SECS
    except Exception:
        return True


def send_hourly_digest(state: Dict, bot_token: str) -> None:
    """Send the accumulated new-file digest and clear the queue."""
    queue = state.get("digest_queue", [])
    if not queue:
        return
    now     = datetime.now()
    visible = queue[:20]
    extra   = max(0, len(queue) - 20)
    lines   = [f"• `{f}`" for f in visible]
    msg = (
        f"🔧 *Claus Build Digest* — {now.strftime('%H:%M')}\n"
        f"{len(queue)} CC\\_ file(s) created/modified in the last hour:\n\n"
        + "\n".join(lines)
        + (f"\n_...and {extra} more_" if extra else "")
    )
    if tg_send(msg, bot_token):
        sent = state.setdefault("digest_sent", [])
        sent.extend(queue)
        state["digest_sent"]  = sent[-200:]
        state["digest_queue"] = []
        state["last_digest_ts"] = now.isoformat()
        log.info("Hourly digest sent: %d files", len(queue))

# ════════════════════════════════════════════════════════════════════════════════
# MODULE 5: PAE ESCALATION SYSTEM
# Claus can queue PAE proposals and track Kato's decisions.
# Inline keyboard buttons work in --loop mode (callback_query polling).
# Claus NEVER auto-executes approved commands — approval triggers a reminder
# with the commands to run, nothing more.
# ════════════════════════════════════════════════════════════════════════════════

def queue_pae(
    state: Dict,
    title: str,
    description: str,
    commands: str,
    bot_token: str,
) -> str:
    """Queue and immediately send a PAE proposal. Returns the proposal ID."""
    queue  = state.setdefault("pae_queue", [])
    pae_id = f"PAE-C{len(queue) + 1:02d}"
    entry  = {
        "id":          pae_id,
        "title":       title,
        "description": description,
        "commands":    commands,
        "status":      "pending",
        "sent_ts":     datetime.now().isoformat(),
        "resolved_ts": None,
        "resolved_by": None,
    }
    queue.append(entry)
    tg_send_pae(title, description, commands, bot_token, pae_id)
    log.info("PAE proposal queued and sent: %s — %s", pae_id, title)
    return pae_id


def process_pae_callbacks(state: Dict, bot_token: str) -> None:
    """
    Poll Telegram for callback_query updates (inline keyboard presses).
    Used in --loop mode. On approval, sends execution reminder — does NOT execute.
    """
    try:
        offset = state.get("tg_update_offset", 0)
        url    = (
            f"https://api.telegram.org/bot{bot_token}/getUpdates"
            f"?offset={offset}&timeout=1&allowed_updates=[\"callback_query\"]"
        )
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        if not data.get("ok"):
            return

        for update in data.get("result", []):
            uid = update["update_id"]
            state["tg_update_offset"] = uid + 1

            cb = update.get("callback_query")
            if not cb:
                continue

            cb_data = cb.get("data", "")
            cb_user = cb.get("from", {}).get("username", "unknown")

            if cb_data.startswith("pae_yes_"):
                pae_id = cb_data.replace("pae_yes_", "")
                _update_pae_status(state, pae_id, "APPROVED", cb_user)
                # Find the commands for this proposal
                cmds = next(
                    (p["commands"] for p in state.get("pae_queue", []) if p["id"] == pae_id),
                    "(commands not found in state)"
                )
                tg_send(
                    f"✅ *{pae_id} APPROVED* by @{cb_user}\n\n"
                    f"*Commands to run manually:*\n```\n{cmds}\n```\n\n"
                    f"_Claus has logged this approval. Execute at your discretion._",
                    bot_token,
                )
                log.info("PAE %s approved by @%s", pae_id, cb_user)

            elif cb_data.startswith("pae_no_"):
                pae_id = cb_data.replace("pae_no_", "")
                _update_pae_status(state, pae_id, "REJECTED", cb_user)
                tg_send(
                    f"❌ *{pae_id} REJECTED* by @{cb_user}. Logged.",
                    bot_token,
                )
                log.info("PAE %s rejected by @%s", pae_id, cb_user)

    except Exception as e:
        log.debug("PAE callback poll (non-critical): %s", e)


def _update_pae_status(state: Dict, pae_id: str, status: str, by: str) -> None:
    for p in state.get("pae_queue", []):
        if p.get("id") == pae_id:
            p["status"]      = status
            p["resolved_by"] = by
            p["resolved_ts"] = datetime.now().isoformat()
            break

# ════════════════════════════════════════════════════════════════════════════════
# MODULE 6: GOJ PIPELINE MONITOR
# Preserves original Claus watchman behavior + attendance anomaly detection.
# ════════════════════════════════════════════════════════════════════════════════

def check_goj_pipeline(state: Dict, bot_token: str) -> str:
    """
    Check GOJ pipeline health. Sends a Telegram alert only when there are issues.
    Returns a short summary string for --status mode.

    Checks:
    1. Pipeline output files freshness (~/.hermes-cloud/…/data/)
    2. 7:30 AM morning report ran today
    3. Attendance count anomalies (via auth_tracker.db)
    4. Gmail OAuth token validity (original Claus behavior)
    """
    now       = datetime.now()
    today     = date.today()
    alerts:   List[str] = []
    summary:  List[str] = []

    # ── Rate-limit GOJ alerts to once per hour ──
    last_alert = state.get("last_goj_alert_ts")
    if last_alert:
        try:
            elapsed = (now - datetime.fromisoformat(last_alert)).total_seconds()
            if elapsed < 3600:
                return "ℹ️ GOJ check: rate-limited (last alert < 1h ago)"
        except Exception:
            pass

    # ── 1. Pipeline data freshness ──
    if PIPELINE_DIR.exists():
        output_files = list(PIPELINE_DIR.glob("*.json")) + list(PIPELINE_DIR.glob("*.txt"))
        if not output_files:
            alerts.append("No output files found in pipeline data directory")
            summary.append("❌ Pipeline data: empty")
        else:
            stale = [
                f"{f.name} ({(time.time() - f.stat().st_mtime) / 3600:.0f}h old)"
                for f in output_files
                if (time.time() - f.stat().st_mtime) / 3600 > PIPELINE_STALE_HOURS
            ]
            if stale:
                alerts.append(f"Stale pipeline files ({len(stale)}): {', '.join(stale[:3])}")
                summary.append(f"⚠️ Pipeline: {len(stale)} stale file(s)")
            else:
                summary.append(f"✅ Pipeline: {len(output_files)} files, all fresh")
    else:
        summary.append("⚠️ Pipeline data dir not found")

    # ── 2. Morning report ──
    if now.hour >= 8 and now.hour < 13:
        # Check both the pipeline dir and the REX morning_reports dir
        morning_candidates = (
            list(REX.glob("morning_report*.txt"))
            + list((REX / "morning_reports").glob("*.txt"))
            if (REX / "morning_reports").exists() else list(REX.glob("morning_report*.txt"))
        )
        found_today = any(
            datetime.fromtimestamp(f.stat().st_mtime).date() == today
            for f in morning_candidates if f.exists()
        )
        if not found_today:
            alerts.append("7:30 AM morning report not detected for today")
            summary.append("⚠️ Morning report: not found today")
        else:
            summary.append("✅ Morning report: ran today")

    # ── 3. Attendance anomaly ──
    try:
        if AUTH_DB.exists():
            conn = sqlite3.connect(str(AUTH_DB), timeout=5)
            cur  = conn.cursor()
            # Try the attendance table; gracefully skip if schema differs
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='attendance'"
            )
            if cur.fetchone():
                cur.execute(
                    "SELECT COUNT(*) FROM attendance WHERE date = ? AND status = 'PRESENT'",
                    (today.isoformat(),),
                )
                row = cur.fetchone()
                if row and row[0] is not None:
                    count = row[0]
                    is_weekday = (today.weekday() < 5)
                    if count > ATTENDANCE_MAX:
                        alerts.append(f"Attendance anomaly: {count} > {ATTENDANCE_MAX} — possible data error")
                        summary.append(f"🔴 Attendance: {count} (OVER LIMIT — check DB)")
                    elif is_weekday and 0 < count < ATTENDANCE_MIN_WKD:
                        alerts.append(f"Low attendance on weekday: {count} < {ATTENDANCE_MIN_WKD} — pipeline failure?")
                        summary.append(f"⚠️ Attendance: {count} (low for weekday)")
                    elif count > 0:
                        summary.append(f"✅ Attendance: {count} today")
                    else:
                        summary.append("ℹ️ Attendance: no PRESENT entries for today yet")
            conn.close()
    except sqlite3.OperationalError as e:
        log.debug("Attendance check (table may not exist): %s", e)
        summary.append("ℹ️ Attendance: check skipped (table unavailable)")
    except Exception as e:
        log.debug("Attendance check error: %s", e)
        summary.append("ℹ️ Attendance: check skipped")

    # ── 4. Gmail OAuth token ──
    if not GMAIL_TOKEN.exists():
        alerts.append("Gmail token missing — pipeline will stall. Fix: python backend/rex_gmail.py --setup")
        summary.append("🔴 Gmail token: MISSING")
    else:
        try:
            token_data = json.loads(GMAIL_TOKEN.read_text())
            expiry_str = token_data.get("expiry") or token_data.get("token_expiry")
            if expiry_str:
                # Strip microseconds and Z suffix for fromisoformat
                expiry_str = re.sub(r"\.\d+", "", expiry_str).replace("Z", "")
                expiry_dt  = datetime.fromisoformat(expiry_str)
                hours_left = (expiry_dt - now).total_seconds() / 3600
                if hours_left < 1:
                    alerts.append("Gmail OAuth token EXPIRED — re-auth: python backend/rex_gmail.py --setup")
                    summary.append("🔴 Gmail token: EXPIRED")
                elif hours_left < 24:
                    summary.append(f"⚠️ Gmail token: expires in {hours_left:.0f}h")
                else:
                    summary.append(f"✅ Gmail token: valid ({hours_left:.0f}h remaining)")
            else:
                summary.append("✅ Gmail token: present")
        except Exception:
            summary.append("✅ Gmail token: present (no expiry field)")

    # ── Send alert if issues found ──
    if alerts:
        alert_msg = (
            f"🏥 *GOJ Pipeline Alert* — {now.strftime('%H:%M')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            + "\n".join(f"• {a}" for a in alerts)
            + f"\n\n_Claus · {date.today().isoformat()}_"
        )
        tg_send(alert_msg, bot_token)
        state["last_goj_alert_ts"] = now.isoformat()
        log.warning("GOJ alerts sent: %d issue(s)", len(alerts))

    return "\n".join(summary)

# ════════════════════════════════════════════════════════════════════════════════
# RUN MODES
# ════════════════════════════════════════════════════════════════════════════════

def _registry_due(state: Dict) -> bool:
    """True if the registry guardian hasn't run in REGISTRY_CHECK_SECS."""
    last = state.get("last_registry_check")
    if not last:
        return True
    try:
        return (datetime.now() - datetime.fromisoformat(last)).total_seconds() >= REGISTRY_CHECK_SECS
    except Exception:
        return True


async def run_once(bot_token: str) -> None:
    """
    --telegram mode: single snapshot, backward-compatible with the 3×-daily plist.
    Runs all checks once, sends any alerts, sends morning brief if it's time, exits.
    """
    log.info("Claus v2 — snapshot run %s", datetime.now().strftime("%Y-%m-%d %H:%M"))

    state   = load_state()
    results = await run_health_checks()

    # Update stats; send URGENT alerts for services crossing the threshold
    newly_urgent = _update_stats(results, state)
    for svc_name in newly_urgent:
        r  = next((r for r in results if r["name"] == svc_name), {})
        cf = state["service_stats"].get(svc_name, {}).get("consecutive_fail", 0)
        send_failure_alert(svc_name, cf, r.get("error", ""), bot_token)

    # Also alert on first-time failures (single occurrence, not yet URGENT)
    for r in results:
        if not r["up"]:
            cf = state["service_stats"].get(r["name"], {}).get("consecutive_fail", 0)
            if cf == 1:
                # Single failure: send WARNING (not URGENT)
                send_failure_alert(r["name"], cf, r.get("error", ""), bot_token)

    # Morning brief
    if should_send_brief(state):
        await send_morning_brief(results, state, bot_token)

    # GOJ pipeline
    check_goj_pipeline(state, bot_token)

    # Registry guardian (rate-limited)
    if _registry_due(state):
        run_registry_guardian(state, bot_token)

    # File digest
    update_digest_queue(state)
    if should_flush_digest(state):
        send_hourly_digest(state, bot_token)

    save_state(state)
    ups = sum(1 for r in results if r["up"])
    log.info("Snapshot done — %d/%d services UP", ups, len(results))


async def run_loop(bot_token: str) -> None:
    """
    --loop mode: continuous monitoring, never exits.
    Update plist to use KeepAlive + RunAtLoad for 24/7 coverage.
    """
    log.info("Claus v2 — loop mode started")
    tg_send(
        f"🟢 *Claus v2 loop started*\n"
        f"Continuous monitoring active — checking every {LOOP_CHECK_SECS}s.\n"
        f"_Gold Health Systems · {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        bot_token,
    )

    last_reg_check  = 0.0
    last_goj_check  = 0.0

    while True:
        try:
            state   = load_state()
            results = await run_health_checks()

            # Service health
            newly_urgent = _update_stats(results, state)
            for svc_name in newly_urgent:
                r  = next((r for r in results if r["name"] == svc_name), {})
                cf = state["service_stats"].get(svc_name, {}).get("consecutive_fail", 0)
                send_failure_alert(svc_name, cf, r.get("error", ""), bot_token)

            # Morning brief
            if should_send_brief(state):
                await send_morning_brief(results, state, bot_token)

            now_mono = time.monotonic()

            # GOJ pipeline (every 30 min)
            if now_mono - last_goj_check >= 1800:
                check_goj_pipeline(state, bot_token)
                last_goj_check = now_mono

            # Registry (every 10 min)
            if now_mono - last_reg_check >= REGISTRY_CHECK_SECS:
                run_registry_guardian(state, bot_token)
                last_reg_check = now_mono

            # Hourly digest
            update_digest_queue(state)
            if should_flush_digest(state):
                send_hourly_digest(state, bot_token)

            # PAE callback polling
            process_pae_callbacks(state, bot_token)

            save_state(state)

        except Exception as exc:
            log.error("Loop iteration error: %s", exc, exc_info=True)

        await asyncio.sleep(LOOP_CHECK_SECS)


def print_status() -> None:
    """--status mode: pretty-print current state to stdout. No Telegram needed."""
    state = load_state()
    bar   = "═" * 62

    print(bar)
    print("  CLAUS v2 — GHS System Status")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(bar)
    print()

    # Service stats
    stats = state.get("service_stats", {})
    if not stats:
        print("  No service data yet — run with --telegram first.")
    else:
        print("  SERVICE STATS (from saved state in CC_claus_state.json)")
        print(f"  {'NAME':<24} {'UPTIME':>8}  {'FAILS':>7}  LAST")
        print(f"  {'-'*24} {'-'*8}  {'-'*7}  ----")
        for svc in SERVICES:
            name  = svc["name"]
            s     = stats.get(name, {})
            total = s.get("total", 0)
            up    = s.get("up", 0)
            cf    = s.get("consecutive_fail", 0)
            last  = "✅ UP" if s.get("last_up") else "❌ DOWN"
            pct   = f"{up / total * 100:.1f}%" if total > 0 else "n/a"
            print(f"  {name:<24} {pct:>8}  {cf:>7}  {last}")

    print()
    print(f"  Last brief:       {state.get('last_brief_date') or 'never'}")
    print(f"  Last reg check:   {state.get('last_registry_check') or 'never'}")
    print(f"  Last digest:      {state.get('last_digest_ts') or 'never'}")
    print(f"  Digest queue:     {len(state.get('digest_queue', []))} file(s) pending")

    pae_q = state.get("pae_queue", [])
    if pae_q:
        print()
        print("  PAE QUEUE:")
        for p in pae_q:
            status = p.get("status", "pending").upper()
            print(f"    [{status:<8}] {p['id']} — {p['title'][:48]}")

    print()
    print(bar)

# ════════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════════

def main() -> None:
    args = set(sys.argv[1:])

    if "--status" in args:
        print_status()
        return

    if "--help" in args or "-h" in args:
        print(__doc__)
        return

    bot_token = get_bot_token()
    if not bot_token:
        log.error(
            "No Hermes bot token found. "
            "Set $HERMES_BOT_TOKEN or add to %s or %s",
            HERMES_ENV, TG_CONFIG_JSON,
        )
        print_status()
        sys.exit(1)

    if "--brief" in args:
        async def _brief() -> None:
            state   = load_state()
            results = await run_health_checks()
            _update_stats(results, state)
            await send_morning_brief(results, state, bot_token)
            save_state(state)
        asyncio.run(_brief())

    elif "--loop" in args:
        asyncio.run(run_loop(bot_token))

    else:
        # Default / --telegram: single snapshot (backward-compatible with plist)
        asyncio.run(run_once(bot_token))


if __name__ == "__main__":
    main()
