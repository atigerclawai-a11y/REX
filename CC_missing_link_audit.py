#!/usr/bin/env python3
"""
CC_missing_link_audit.py — Tiger Claw / REX / Hermes / GOJ "missing-link" deep diagnosis.

Reusable, READ-ONLY auditor that finds EVERY broken connection across the stack so the
owner can tie everything together. Hermes is the top priority.

Audits six categories, each finding emitted as:
    {what, where, status, how_to_fix}

  1. GATEWAYS/TUNNELS  — cloudflared ingress -> local upstream (TCP) + public URL (HTTP)
  2. API KEYS          — hermes-hub/api_keys.json, REX /api/keys/status, env files
  3. AUTH/PASSWORDS    — hub auth.json users/roles, pin.json, setup/fail-open modes
  4. LOCAL SERVICES    — launchctl jobs (hermes/rex/goj/tigerclaw) with non-zero exit
  5. HERMES DEEP-DIVE  — why :8787 is 502, where the WebUI/API went, exact repoint
  6. STALE REFERENCES  — configs/scripts pointing at ports/files that do not exist

Usage:
    python3 CC_missing_link_audit.py            # human report grouped by category
    python3 CC_missing_link_audit.py --json     # machine-readable JSON

STRICTLY READ-ONLY. This script never restarts services, edits configs, or modifies builds.
Only the caller writes the report .md; this script just prints.

Stdlib only. If a Drive/Gmail token check is wanted, run under ~/.rex-venv/bin/python3
(google libs) — the token check degrades gracefully when those libs are absent.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

HOME = Path.home()

# --- Status vocabulary -------------------------------------------------------
OK = "OK"
BROKEN = "BROKEN"
MISSING = "MISSING"
STALE = "STALE"
WARN = "WARN"
INFO = "INFO"

# --- HTTP / TCP probe settings ----------------------------------------------
TCP_TIMEOUT = 2.0
HTTP_TIMEOUT = 6.0

CATEGORIES = [
    "HERMES",  # deep-dive first — owner's #1 priority
    "GATEWAYS",
    "API_KEYS",
    "AUTH",
    "SERVICES",
    "STALE",
]

# Providers Kato cares about for integration that we explicitly flag if missing.
WANTED_INTEGRATIONS = ["perplexity", "poe", "typingmind"]

# Canonical provider list to report CONFIGURED vs MISSING.
PROVIDERS = [
    "anthropic", "openai", "deepseek", "perplexity", "poe", "retell",
    "twilio", "elevenlabs", "google", "xai", "openrouter", "huggingface",
    "typingmind",
]

# Map provider -> env var names that indicate a real (non-comment) key.
PROVIDER_ENV = {
    "anthropic": ["ANTHROPIC_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "perplexity": ["PERPLEXITY_API_KEY"],
    "poe": ["POE_API_KEY", "POE_TOKEN"],
    "retell": ["RETELL_API_KEY"],
    "twilio": ["TWILIO_AUTH_TOKEN", "TWILIO_ACCOUNT_SID"],
    "elevenlabs": ["ELEVENLABS_API_KEY"],
    "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "xai": ["XAI_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "huggingface": ["HF_TOKEN", "HUGGINGFACE_API_KEY", "HUGGINGFACEHUB_API_TOKEN"],
    "typingmind": ["TYPINGMIND_API_KEY", "TYPINGMIND_TOKEN"],
}


# =============================================================================
# Helpers
# =============================================================================
def finding(what: str, where: str, status: str, how_to_fix: str) -> dict[str, str]:
    return {"what": what, "where": where, "status": status, "how_to_fix": how_to_fix}


def tcp_alive(host: str, port: int, timeout: float = TCP_TIMEOUT, retries: int = 1) -> bool:
    """TCP connect probe with one retry — avoids false-negative flapping under load."""
    for attempt in range(retries + 1):
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            if attempt < retries:
                continue
            return False
    return False


def http_probe(url: str, timeout: float = HTTP_TIMEOUT) -> tuple[int, str]:
    """Return (http_status_code, note). code 0 == no response / connection failure."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": "CC-missing-link-audit/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.status, ""
    except urllib.error.HTTPError as e:
        return e.code, ""
    except urllib.error.URLError as e:
        return 0, str(getattr(e, "reason", e))
    except (TimeoutError, socket.timeout):
        return 0, "timeout"
    except Exception as e:  # noqa: BLE001 - defensive: report, never crash audit
        return 0, type(e).__name__


def http_get_json(url: str, timeout: float = HTTP_TIMEOUT) -> Any | None:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": "CC-missing-link-audit/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return json.loads(resp.read().decode())
    except Exception:  # noqa: BLE001
        return None


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(errors="replace")
    except Exception:  # noqa: BLE001
        return None


def read_json(path: Path) -> Any | None:
    txt = read_text(path)
    if txt is None:
        return None
    try:
        return json.loads(txt)
    except Exception:  # noqa: BLE001
        return None


def parse_env_keys(path: Path) -> set[str]:
    """Return the set of env var NAMES that are actually assigned (uncommented, non-empty)."""
    txt = read_text(path)
    if txt is None:
        return set()
    names: set[str] = set()
    for raw in txt.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
        if not m:
            continue
        name, val = m.group(1), m.group(2).strip().strip('"').strip("'")
        if val and val.lower() not in {"changeme", "your_key_here", "todo", "xxx"}:
            names.add(name)
    return names


def listening_ports() -> dict[int, str]:
    """Map of listening TCP port -> short owner string, via lsof. Empty on failure."""
    out: dict[int, str] = {}
    try:
        res = subprocess.run(
            ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"],
            capture_output=True, text=True, timeout=15,
        )
    except Exception:  # noqa: BLE001
        return out
    for line in res.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 9:
            continue
        name = parts[0]
        addr = parts[8]
        m = re.search(r":(\d+)$", addr)
        if m:
            out.setdefault(int(m.group(1)), name)
    return out


def launchctl_list() -> list[tuple[str, str, str]]:
    """Return [(pid, exit_status, label)] for jobs in the target namespaces."""
    try:
        res = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=15)
    except Exception:  # noqa: BLE001
        return []
    rows: list[tuple[str, str, str]] = []
    prefixes = ("com.hermes", "ai.hermes", "com.goj", "com.rex", "com.tigerclaw", "ai.openwebui")
    for line in res.stdout.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 3:
            parts = line.split()
        if len(parts) < 3:
            continue
        pid, status, label = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if label.startswith(prefixes):
            rows.append((pid, status, label))
    return rows


def plist_program(label: str) -> list[str]:
    """Best-effort ProgramArguments for a launchd label, via PlistBuddy."""
    candidates = [
        HOME / "Library" / "LaunchAgents" / f"{label}.plist",
    ]
    for p in candidates:
        if not p.exists():
            continue
        try:
            res = subprocess.run(
                ["/usr/libexec/PlistBuddy", "-c", "Print ProgramArguments", str(p)],
                capture_output=True, text=True, timeout=10,
            )
        except Exception:  # noqa: BLE001
            return []
        args = [ln.strip() for ln in res.stdout.splitlines() if ln.strip() not in ("Array {", "}")]
        return args
    return []


# =============================================================================
# Cloudflared ingress parsing
# =============================================================================
def parse_ingress(path: Path) -> list[dict[str, str]]:
    """Minimal YAML ingress parser (stdlib only). Returns [{hostname, path, service}]."""
    txt = read_text(path)
    if txt is None:
        return []
    rules: list[dict[str, str]] = []
    cur: dict[str, str] = {}
    in_ingress = False
    for raw in txt.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        if re.match(r"^ingress\s*:", stripped):
            in_ingress = True
            continue
        if not in_ingress:
            continue
        # New rule item begins with "- "
        if stripped.startswith("- "):
            if cur:
                rules.append(cur)
            cur = {}
            stripped = stripped[2:].strip()
            if not stripped:
                continue
        m = re.match(r"^(hostname|service|path)\s*:\s*(.+)$", stripped)
        if m:
            cur[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    if cur:
        rules.append(cur)
    return rules


def service_to_hostport(service: str) -> tuple[str, int | None, str]:
    """Parse 'http://127.0.0.1:8787' -> (host, port, kind). kind in {http,status,other}."""
    if service.startswith("http_status:"):
        return ("", None, "status")
    m = re.match(r"^https?://([^:/]+)(?::(\d+))?", service)
    if m:
        host = m.group(1)
        port = int(m.group(2)) if m.group(2) else (443 if service.startswith("https") else 80)
        return (host, port, "http")
    return (service, None, "other")


# =============================================================================
# Category 1 + 5: GATEWAYS / TUNNELS  (and Hermes deep-dive draws from this)
# =============================================================================
def audit_gateways(ctx: dict) -> list[dict]:
    out: list[dict] = []
    cfg_paths = [
        HOME / ".cloudflared" / "config.yml",
        HOME / ".cloudflared" / "hermestigerclaw.yml",
    ]
    listen = ctx["listening"]

    # Collect routes deduped across BOTH configs. Same hostname+path+service in both
    # files is ONE logical route (reported once), but we record which files contain it
    # so the fix can say "edit BOTH configs" — the two cloudflared instances load
    # different files (config.yml vs hermestigerclaw.yml).
    route_files: dict[tuple[str, str, str], list[str]] = {}
    route_order: list[tuple[str, str, str]] = []
    for cfg in cfg_paths:
        if not cfg.exists():
            out.append(finding(
                what=f"cloudflared config {cfg.name}",
                where=str(cfg),
                status=MISSING,
                how_to_fix=f"Expected tunnel config not found at {cfg}. If retired, remove "
                           f"references; otherwise restore it.",
            ))
            continue
        for r in parse_ingress(cfg):
            host = r.get("hostname")
            service = r.get("service", "")
            if not host or not service:
                continue
            path_suffix = r.get("path", "")
            rkey = (host, path_suffix, service)
            if rkey not in route_files:
                route_files[rkey] = []
                route_order.append(rkey)
            route_files[rkey].append(cfg.name)

    if True:
        for (host, path_suffix, service) in route_order:
            in_files = route_files[(host, path_suffix, service)]

            up_host, up_port, kind = service_to_hostport(service)
            if kind == "status":
                continue  # http_status:404 catch-all is intentional

            files_str = " & ".join(in_files)
            where = (f"{files_str} :: {host}{(' path=' + path_suffix) if path_suffix else ''} "
                     f"-> {service}")

            # Probe local upstream (TCP).
            upstream_alive = None
            if up_port is not None and up_host in ("127.0.0.1", "localhost", "::1"):
                upstream_alive = tcp_alive("127.0.0.1", up_port)
                ctx.setdefault("upstream_probe", {})[up_port] = upstream_alive

            # Probe public URL.
            public_url = f"https://{host}{path_suffix or ''}"
            code, note = http_probe(public_url)
            ctx.setdefault("public_probe", {})[host] = (code, note)

            # Decide status.
            if upstream_alive is False:
                owner = ""
                fix = (
                    f"Local upstream :{up_port} is DEAD (nothing listening). Either start the "
                    f"service that should bind :{up_port}, or repoint this ingress to a live port. "
                )
                # Tailored guidance for the known Hermes case.
                if up_port == 8787:
                    fix = (
                        "DEAD upstream :8787 (Hermes WebUI). Nothing listens here and NO launchd "
                        "job binds 8787 — it was a manually-started Python WebUI (see "
                        "~/hermes-webui/.env.local HERMES_WEBUI_PORT) / docker container that died. "
                        "FIX (fastest): repoint hermes+desktop ingress to a LIVE chat UI — "
                        "LibreChat :3080 (running) or Open WebUI :3000 — then "
                        "`cloudflared tunnel ... ingress validate` + reload. ALT: revive the WebUI "
                        "(~/hermes-webui) so it binds :8787, then leave ingress as-is."
                    )
                out.append(finding(
                    what=f"Tunnel route {host} -> dead upstream :{up_port}",
                    where=where,
                    status=BROKEN,
                    how_to_fix=fix,
                ))
                continue

            # Upstream alive (or remote) — judge by HTTP code.
            if code in (502, 503, 530, 0):
                detail = f"HTTP {code}" + (f" ({note})" if note else "")
                fix = (
                    f"Public probe returned {detail}. Upstream "
                    f"{'is alive on :' + str(up_port) if upstream_alive else 'is remote/' + service}; "
                    f"likely the app rejects '/' or needs a path/host header. Verify the service "
                    f"answers locally (`curl -I http://127.0.0.1:{up_port}/`), and confirm "
                    f"cloudflared is running and the DNS CNAME for {host} points at the tunnel."
                )
                if code == 0:
                    fix = (
                        f"No HTTP response from {public_url} ({note or 'connection failed'}). "
                        f"Check: (a) DNS record for {host} exists and CNAMEs to the tunnel, "
                        f"(b) cloudflared tunnel is running, (c) this hostname is present in the "
                        f"ACTIVE ingress config."
                    )
                out.append(finding(
                    what=f"Tunnel route {host} unhealthy",
                    where=where,
                    status=BROKEN if code in (502, 530, 0) else WARN,
                    how_to_fix=fix,
                ))
            else:
                out.append(finding(
                    what=f"Tunnel route {host} -> :{up_port if up_port else service}",
                    where=where,
                    status=OK,
                    how_to_fix=f"Healthy (upstream alive, public HTTP {code}). No action.",
                ))
    return out


# =============================================================================
# Category 5: HERMES DEEP-DIVE
# =============================================================================
def audit_hermes(ctx: dict) -> list[dict]:
    out: list[dict] = []
    listen = ctx["listening"]

    p8787 = 8787 in listen
    p3002 = 3002 in listen
    p8088 = 8088 in listen
    p8642 = 8642 in listen
    p65001 = 65001 in listen
    p3080 = 3080 in listen
    p3000 = 3000 in listen

    # 1) The headline: hermes/desktop -> :8787 502.
    code_hermes = ctx.get("public_probe", {}).get("hermes.hermestigerclaw.com", (None, ""))[0]
    out.append(finding(
        what="hermes.hermestigerclaw.com + desktop.hermestigerclaw.com are 502 (Hermes WebUI down)",
        where="~/.cloudflared/config.yml + hermestigerclaw.yml :: both -> http://127.0.0.1:8787",
        status=BROKEN if not p8787 else WARN,
        how_to_fix=(
            "ROOT CAUSE: nothing listens on :8787 and NO launchd job binds it. The Hermes WebUI on "
            ":8787 was a manually-started Python app (~/hermes-webui, HERMES_WEBUI_PORT in "
            ".env.local) / Docker container that exited and was never restarted, so cloudflared "
            "returns 502. The LIVE Hermes processes are MESSAGING gateways, not the browser chat UI: "
            "local gateway on :8088 + :65001 (ai.hermes.gateway) and cloud gateway on :3002 "
            "(ai.hermes.gateway-cloud) — both answer /health 200 but 404 on '/'. "
            "EXACT FIX (recommended, fastest, zero new services): edit BOTH cloudflared configs so "
            "hermes.hermestigerclaw.com AND desktop.hermestigerclaw.com point at a LIVE chat UI — "
            "LibreChat 'http://127.0.0.1:3080' (running 31h) is the best match; Open WebUI "
            "'http://127.0.0.1:3000' is the alternate. Then run "
            "`cloudflared tunnel ingress validate` and reload the tunnel (brief blip). "
            "ALTERNATIVE (keep the dedicated WebUI): bring ~/hermes-webui back up so it binds :8787 "
            "(it has a Dockerfile + .venv + HERMES_WEBUI_PYTHON) and create a launchd job so it "
            "survives reboot — currently it is unmanaged, which is why it keeps disappearing."
        ),
    ))

    # 2) The Hermes REST/OpenAI API the adapters call (:8642) is dead.
    out.append(finding(
        what="Hermes REST API :8642 is DOWN (breaks WhatsApp/zeroclaw bridge + any /v1/chat client)",
        where="~/.hermes/bin/zeroclaw-adapter (HERMES_URL=http://127.0.0.1:8642/v1/chat/completions)",
        status=BROKEN if not p8642 else OK,
        how_to_fix=(
            "The zeroclaw-adapter (and any OpenAI-compatible client) POST to "
            "http://127.0.0.1:8642/v1/chat/completions, but nothing listens on :8642. The gateway's "
            "API server is governed by API_SERVER_ENABLED / API_SERVER_HOST / API_SERVER_PORT in "
            "~/.hermes/.env — confirm API_SERVER_PORT matches what the adapter expects (8642) and "
            "that API_SERVER_ENABLED=true, then restart ai.hermes.gateway. The gateway currently "
            "exposes only :8088 and :65001; if the REST API is meant to be :65001, repoint the "
            "adapter's HERMES_URL to :65001 instead. This is WHY the WhatsApp path is dead end-to-end."
        ),
    ))

    # 3) zeroclaw-adapter websocket handshake errors.
    out.append(finding(
        what="com.hermes.zeroclaw-adapter logs websocket InvalidMessage / EOF handshake errors",
        where="~/.hermes/logs/zeroclaw-adapter.error.log (adapter listens ws on :18789)",
        status=WARN,
        how_to_fix=(
            "The adapter's websocket server on :18789 is up, but it receives non-websocket / "
            "truncated connections ('did not receive a valid HTTP request', EOF on handshake) — "
            "typically health-check probes or the kapso-whatsapp bridge connecting with the wrong "
            "URL/protocol. These are noisy but non-fatal. Real fix is upstream: once :8642 (Hermes "
            "REST API) is alive, the adapter can actually serve responses; until then every WhatsApp "
            "turn 500s. Point com.hermes.kapso-whatsapp at ws://127.0.0.1:18789 and silence "
            "bare-TCP health probes against that port."
        ),
    ))

    # 4) Signal adapter can't reach signal-cli (gateway log churn).
    if 8085 not in listen:
        out.append(finding(
            what="Hermes gateway: Signal adapter cannot reach signal-cli at :8085 (retry loop)",
            where="~/.hermes/logs/gateway.log (gateway.platforms.signal)",
            status=WARN,
            how_to_fix=(
                "signal-cli daemon on :8085 is not running, so the local gateway logs a reconnect "
                "loop every few minutes. Either start the signal-cli HTTP daemon on :8085, or disable "
                "the Signal platform in ~/.hermes/.env (SIGNAL_HTTP_URL/SIGNAL_ACCOUNT) if Signal is "
                "not in use. Cosmetic for chat, but it floods the gateway log and wastes cycles."
            ),
        ))

    # 5) Inventory line so the fix is unambiguous about what IS alive.
    out.append(finding(
        what="Hermes live-port inventory (for the repoint decision)",
        where="lsof TCP LISTEN snapshot",
        status=INFO,
        how_to_fix=(
            f":8787 WebUI={'UP' if p8787 else 'DOWN'} | "
            f":3002 cloud-gw={'UP' if p3002 else 'DOWN'} | "
            f":8088 local-gw={'UP' if p8088 else 'DOWN'} | "
            f":65001 local-gw-alt={'UP' if p65001 else 'DOWN'} | "
            f":8642 REST-API={'UP' if p8642 else 'DOWN'} | "
            f":3080 LibreChat={'UP' if p3080 else 'DOWN'} | "
            f":3000 OpenWebUI={'UP' if p3000 else 'DOWN'}. "
            "Repoint hermes/desktop -> :3080 (LibreChat) for an immediate working chat UI."
        ),
    ))
    return out


# =============================================================================
# Category 2: API KEYS
# =============================================================================
def audit_api_keys(ctx: dict) -> list[dict]:
    out: list[dict] = []

    # Authoritative live source: REX backend /api/keys/status.
    rex_status = http_get_json("http://127.0.0.1:8000/api/keys/status")
    rex_providers: dict[str, bool] = {}
    if isinstance(rex_status, dict) and isinstance(rex_status.get("providers"), dict):
        rex_providers = {k.lower(): bool(v) for k, v in rex_status["providers"].items()}
        out.append(finding(
            what="REX backend /api/keys/status reachable",
            where="http://127.0.0.1:8000/api/keys/status",
            status=OK,
            how_to_fix=f"Reported: {json.dumps(rex_providers)}",
        ))
    else:
        out.append(finding(
            what="REX backend /api/keys/status unreachable",
            where="http://127.0.0.1:8000/api/keys/status",
            status=WARN,
            how_to_fix="REX backend (:8000) not answering the key-status endpoint; relying on env "
                       "files + api_keys.json. Confirm com.rex.backend is up.",
        ))

    # api_keys.json (hub).
    ak_path = HOME / "hermes-hub" / "api_keys.json"
    ak = read_json(ak_path)
    if ak is None:
        out.append(finding(
            what="hermes-hub/api_keys.json missing or unparseable",
            where=str(ak_path),
            status=MISSING,
            how_to_fix="Hub key store not readable. The hub UI key panel will be empty.",
        ))

    # Collect env-derived configured providers across all env files.
    env_files = [
        HOME / ".hermes" / ".env",
        HOME / "Desktop" / "REX" / ".env",
    ]
    env_names: set[str] = set()
    for ef in env_files:
        env_names |= parse_env_keys(ef)

    def provider_configured(provider: str) -> tuple[bool, str]:
        # 1) REX status wins when it knows the provider.
        if provider in rex_providers:
            src = "REX /api/keys/status"
            if rex_providers[provider]:
                return True, src
            # REX says false — but env might still have it (different consumer).
        # 2) env var presence.
        for var in PROVIDER_ENV.get(provider, []):
            if var in env_names:
                return True, f"env ({var})"
        # 3) REX explicit false with no env => missing.
        if provider in rex_providers and not rex_providers[provider]:
            return False, "REX says missing + no env key"
        return False, "no key found"

    for prov in PROVIDERS:
        ok, src = provider_configured(prov)
        is_wanted = prov in WANTED_INTEGRATIONS
        if ok:
            out.append(finding(
                what=f"API key: {prov}",
                where=src,
                status=OK,
                how_to_fix=f"CONFIGURED via {src}. No action.",
            ))
        else:
            fix = (
                f"No key for {prov}. Add the key to ~/.hermes/.env "
                f"({'/'.join(PROVIDER_ENV.get(prov, ['<VAR>']))}) and/or hermes-hub/api_keys.json, "
                f"then restart the consuming service."
            )
            if is_wanted:
                fix = (
                    f"[KATO WANTS THIS] {prov} integration has NO key. "
                    + fix
                    + (" Poe uses an API key from poe.com/api_key (POE_API_KEY)."
                       if prov == "poe" else "")
                    + (" TypingMind is a frontend that needs YOUR provider keys (it has no key of "
                       "its own) — point it at the live Hermes/REX endpoint or paste your Anthropic/"
                       "OpenAI keys into TypingMind directly; set TYPINGMIND_API_KEY only if you run "
                       "TypingMind's hosted sync."
                       if prov == "typingmind" else "")
                )
            out.append(finding(
                what=f"API key: {prov}" + (" (WANTED INTEGRATION)" if is_wanted else ""),
                where="env files + api_keys.json + REX status",
                status=MISSING,
                how_to_fix=fix,
            ))
    return out


# =============================================================================
# Category 3: AUTH / PASSWORDS
# =============================================================================
def audit_auth(ctx: dict) -> list[dict]:
    out: list[dict] = []
    hub = HOME / "hermes-hub"

    auth = read_json(hub / "auth.json")
    if auth is None:
        out.append(finding(
            what="hub auth.json missing/unparseable",
            where=str(hub / "auth.json"),
            status=MISSING,
            how_to_fix="Hub (:9000) auth store not readable — login likely broken or fail-open. "
                       "Restore auth.json with hashed users.",
        ))
    else:
        users = auth.get("users", {}) if isinstance(auth, dict) else {}
        if not users:
            out.append(finding(
                what="hub auth.json has NO users",
                where=str(hub / "auth.json"),
                status=BROKEN,
                how_to_fix="No users defined — hub may be in fail-open/setup mode. Create at least "
                           "an admin via ~/hermes-hub/reset_password.py.",
            ))
        for uname, u in users.items():
            if not isinstance(u, dict):
                continue
            has_hash = bool(u.get("password_hash"))
            has_salt = bool(u.get("salt"))
            perms = u.get("permissions", [])
            wildcard = perms == ["*"] or "*" in (perms or [])
            expires = u.get("expires_at")
            if not has_hash:
                out.append(finding(
                    what=f"hub user '{uname}' has no password_hash",
                    where=str(hub / "auth.json"),
                    status=BROKEN,
                    how_to_fix=f"User '{uname}' lacks a password hash (fail-open risk). Reset via "
                               f"reset_password.py or remove the user.",
                ))
            elif not has_salt:
                out.append(finding(
                    what=f"hub user '{uname}' has hash but no salt",
                    where=str(hub / "auth.json"),
                    status=WARN,
                    how_to_fix=f"User '{uname}' hash without salt — weaker. Re-hash with a per-user "
                               f"salt via reset_password.py.",
                ))
            else:
                note = f"role={u.get('role')} perms={perms}"
                if expires:
                    note += f" expires_at={expires}"
                out.append(finding(
                    what=f"hub user '{uname}' credential set",
                    where=str(hub / "auth.json"),
                    status=OK if not wildcard else INFO,
                    how_to_fix=(f"{note}. OK." if not wildcard else
                                f"{note}. Wildcard '*' = full admin; confirm this is intended and "
                                f"the password is strong."),
                ))

    # pin.json presence.
    pin = hub / "pin.json"
    out.append(finding(
        what="hub pin.json",
        where=str(pin),
        status=OK if pin.exists() else WARN,
        how_to_fix=("Present (PIN lock configured)." if pin.exists()
                    else "No pin.json — PIN second factor not set. Add one if PIN gating is wanted."),
    ))

    # HUD gate (:27223) — known fail-closed Basic auth per the masterlist.
    hud_code = ctx.get("public_probe", {}).get("hud.hermestigerclaw.com", (None, ""))[0]
    if hud_code is not None:
        out.append(finding(
            what="HUD gate hud.hermestigerclaw.com (:27223)",
            where="~/.cloudflared :: hud -> 127.0.0.1:27223",
            status=OK if hud_code in (200, 401, 403, 503) else WARN,
            how_to_fix=(f"Public HTTP {hud_code}. 401/403 = gate working (fail-closed Basic auth as "
                        f"designed). If 200 with no prompt, the gate is OPEN — set the site password "
                        f"via ~/hermes-hub set-site-password and confirm fail-closed."),
        ))
    return out


# =============================================================================
# Category 4: LOCAL SERVICES
# =============================================================================
def audit_services(ctx: dict) -> list[dict]:
    out: list[dict] = []
    rows = launchctl_list()
    if not rows:
        out.append(finding(
            what="launchctl list returned no target jobs",
            where="launchctl list",
            status=WARN,
            how_to_fix="Could not enumerate launchd jobs (permissions or empty). Re-run in the "
                       "user's GUI session.",
        ))
        return out

    # Known characterizations for the noted failures.
    known: dict[str, str] = {
        "ai.hermes.watchdog": (
            "exit 127 = command not found: ProgramArguments runs "
            "/Users/mainsobhelper/.hermes/bin/hermes-watchdog which DOES NOT EXIST. Either restore "
            "the watchdog script or unload+remove this job (`launchctl bootout`)."
        ),
        "com.hermes.backup": (
            "exit 127 = /Users/mainsobhelper/.hermes/bin/hermes-backup MISSING. Restore the backup "
            "script or remove the job."
        ),
        "com.hermes.docker-guardian": (
            "exit 127 = /Users/mainsobhelper/.hermes/bin/docker-guardian MISSING. Restore or remove."
        ),
        "com.hermes.memory-archive-daily": (
            "exit 127 = /Users/mainsobhelper/.hermes/bin/memory-archive MISSING. Restore the "
            "memory-archive script or remove this job (memory-archive-monthly may share it)."
        ),
        "com.hermes.claus-watchman": (
            "exit 2 = /Users/mainsobhelper/.hermes/bin/claus_watchman.py MISSING (Phase-16 Claus "
            "agent watchman). Restore the script or remove the job."
        ),
        "com.hermes.python-resign": (
            "exit 2 = /Users/mainsobhelper/.hermes-cloud/scripts/python_resign_after_brew.py MISSING. "
            "This re-signs Python after a brew upgrade; restore it or remove the job."
        ),
        "com.hermes.kapso-whatsapp": (
            "exit 1 = /Users/mainsobhelper/.local/bin/kapso-whatsapp-bridge runs but fails — it "
            "depends on the Hermes REST API (:8642) which is DOWN, and on the zeroclaw-adapter ws "
            "(:18789). Fix :8642 first (see HERMES section), then this should connect."
        ),
        "com.hermes.zeroclaw-adapter": (
            "Running (PID present) but logs websocket handshake errors — see HERMES section. "
            "Non-fatal; real fix is bringing up the Hermes REST API on :8642."
        ),
        "com.goj.tigerclaw-backup": (
            "exit 127 = the backup script path in the plist does not exist. Inspect "
            "~/Library/LaunchAgents/com.goj.tigerclaw-backup.plist ProgramArguments and restore the "
            "target or remove the job."
        ),
    }

    for pid, status, label in sorted(rows, key=lambda r: r[2]):
        try:
            code = int(status)
        except ValueError:
            code = None
        running = pid not in ("-", "0") and pid.isdigit()

        # 1) RUNNING jobs (live PID) are healthy regardless of the LAST-exit column.
        #    launchctl shows the *previous* exit status; a long-running daemon that was
        #    last restarted shows e.g. -15 (SIGTERM) but is fine right now.
        if running:
            note = ""
            if code is not None and code != 0:
                note = (f" (last_exit={status}; that's the PRIOR exit — typically a restart/SIGTERM "
                        f"artifact, not a current failure)")
            # zeroclaw-adapter is running but worth a pointer to the HERMES section.
            extra = known.get(label, "")
            out.append(finding(
                what=f"launchd job {label}",
                where=f"pid={pid} last_exit={status}",
                status=OK,
                how_to_fix=(f"Running (PID {pid}).{note} No action." + (f" Note: {extra}" if extra else "")),
            ))
            continue

        # Determine whether the job's target script even exists (drives severity).
        args = plist_program(label)
        target = next((a for a in args if a.startswith("/") and not a.endswith("python3")
                       and "venv/bin/python" not in a and "/bin/bash" not in a),
                      args[-1] if args else "")
        tgt_missing = bool(target) and target.startswith("/") and not Path(target).exists()

        # 2) NOT running. Classify by exit code.
        #    code 0  → clean (scheduled one-shot idle between runs, or stopped cleanly).
        #    code <0 → terminated by signal (-15=SIGTERM). On a stopped job this is almost
        #              always a restart/boot artifact, NOT a crash — unless target is missing.
        #    code >0 → genuine non-zero failure on last run.
        if tgt_missing:
            fix = known.get(label) or (
                f"The plist runs {target}, which does NOT exist — orphaned job. Restore the file, "
                f"or `launchctl bootout gui/$UID/{label}` + remove the plist so it stops trying on "
                f"every load."
            )
            out.append(finding(
                what=f"launchd job {label} — orphaned (target script missing)",
                where=f"~/Library/LaunchAgents/{label}.plist (pid={pid}, last_exit={status}, target={target})",
                status=MISSING,
                how_to_fix=fix,
            ))
            continue

        if code is None or code == 0:
            out.append(finding(
                what=f"launchd job {label}",
                where=f"pid={pid} last_exit={status}",
                status=OK,
                how_to_fix="Clean last exit (idle scheduled job or cleanly stopped). No action.",
            ))
            continue

        if code < 0:
            # Signal-terminated but not currently running and target exists → restart artifact.
            out.append(finding(
                what=f"launchd job {label} stopped via signal (exit {status})",
                where=f"~/Library/LaunchAgents/{label}.plist (pid={pid})",
                status=WARN,
                how_to_fix=(known.get(label) or
                            f"Last terminated by signal ({status}, e.g. -15=SIGTERM) and not currently "
                            f"running. Usually a restart/boot artifact. If it should be running, "
                            f"reload it; if KeepAlive is set it may already be flapping — check its "
                            f"StandardErrorPath log."),
            ))
            continue

        # code > 0 → real failure.
        fix = known.get(label) or (
            f"exit {status}: job failed on last run. Inspect its StandardErrorPath log and "
            f"ProgramArguments ({' '.join(args) if args else 'unknown'}); fix the underlying script "
            f"or dependency. (Note: one-shot scheduled jobs may show a stale non-zero exit between "
            f"runs — confirm against the log before acting.)"
        )
        out.append(finding(
            what=f"launchd job {label} failing (exit {status})",
            where=f"~/Library/LaunchAgents/{label}.plist (pid={pid})",
            status=BROKEN,
            how_to_fix=fix,
        ))
    return out


# =============================================================================
# Category 6: STALE REFERENCES
# =============================================================================
def audit_stale(ctx: dict) -> list[dict]:
    out: list[dict] = []
    listen = ctx["listening"]

    # 6a) cloudflared routes whose local upstream port has nothing listening.
    dead_upstreams = {p: alive for p, alive in ctx.get("upstream_probe", {}).items() if alive is False}
    for port in sorted(dead_upstreams):
        out.append(finding(
            what=f"Stale ingress target :{port} (no listener)",
            where="~/.cloudflared/config.yml / hermestigerclaw.yml",
            status=STALE,
            how_to_fix=(f"One or more ingress hostnames route to 127.0.0.1:{port} but nothing "
                        f"listens there. Repoint to a live port or delete the route."),
        ))

    # 6b) rex-mcp / :8766 specifically (present in ingress, commonly dead).
    if not tcp_alive("127.0.0.1", 8766):
        out.append(finding(
            what="rex-mcp.hermestigerclaw.com -> :8766 (Rex MCP Bridge) has no listener",
            where="~/.cloudflared :: rex-mcp -> http://localhost:8766",
            status=STALE,
            how_to_fix="The Rex MCP Bridge on :8766 is not running. Start the MCP bridge or remove "
                       "the rex-mcp ingress route until it is needed.",
        ))

    # 6c) launchd jobs pointing at non-existent scripts (cross-checked here as 'stale config').
    for pid, status, label in launchctl_list():
        args = plist_program(label)
        for a in args:
            if a.startswith("/Users/") and a.endswith((".py", ".sh")) or (
                a.startswith("/Users/") and "/bin/" in a and not a.endswith("python3")
            ):
                if not Path(a).exists():
                    out.append(finding(
                        what=f"launchd plist references missing file: {a}",
                        where=f"~/Library/LaunchAgents/{label}.plist",
                        status=STALE,
                        how_to_fix=(f"The job {label} runs {a}, which does not exist. Restore the "
                                    f"file or remove/disable the plist so it stops failing on every "
                                    f"load."),
                    ))
                break

    # 6d) cloudflared config divergence (two configs that should agree).
    c1 = parse_ingress(HOME / ".cloudflared" / "config.yml")
    c2 = parse_ingress(HOME / ".cloudflared" / "hermestigerclaw.yml")
    def host_map(rules):
        m = {}
        for r in rules:
            if r.get("hostname") and r.get("service"):
                m.setdefault(r["hostname"], set()).add(r["service"])
        return m
    m1, m2 = host_map(c1), host_map(c2)
    for host in sorted(set(m1) & set(m2)):
        if m1[host] != m2[host]:
            out.append(finding(
                what=f"cloudflared config divergence for {host}",
                where="config.yml vs hermestigerclaw.yml",
                status=WARN,
                how_to_fix=(f"The two tunnel configs route {host} differently "
                            f"(config.yml={sorted(m1[host])} vs hermestigerclaw.yml={sorted(m2[host])}). "
                            f"Determine which file the running cloudflared actually loads and delete "
                            f"or reconcile the other to avoid confusion."),
            ))

    if not out:
        out.append(finding(
            what="No stale references detected",
            where="ingress + launchd cross-check",
            status=OK,
            how_to_fix="All ingress targets and plist script paths resolve. No action.",
        ))
    return out


# =============================================================================
# Optional: Google (Drive/Gmail) token sanity — degrades gracefully
# =============================================================================
def audit_google_tokens(ctx: dict) -> list[dict]:
    out: list[dict] = []
    candidates = [
        HOME / ".hermes" / "google_token.json",
        HOME / ".hermes" / "gmail_token.json",
        HOME / "Desktop" / "REX" / "google_token.json",
        HOME / "hermes-hub" / "google_token.json",
    ]
    found = [p for p in candidates if p.exists()]
    if not found:
        return out  # nothing to say; not every box has these
    for p in found:
        data = read_json(p)
        if not isinstance(data, dict):
            out.append(finding(
                what=f"Google token {p.name} unreadable",
                where=str(p),
                status=WARN,
                how_to_fix="Token file is not valid JSON — re-run the OAuth flow to regenerate.",
            ))
            continue
        has_refresh = bool(data.get("refresh_token"))
        expiry = data.get("expiry") or data.get("token_expiry")
        out.append(finding(
            what=f"Google token {p.name}",
            where=str(p),
            status=OK if has_refresh else WARN,
            how_to_fix=(f"refresh_token present (expiry={expiry}); auto-refresh OK." if has_refresh
                        else "No refresh_token — token will expire and not auto-renew. Re-run OAuth "
                             "with offline access."),
        ))
    return out


# =============================================================================
# Orchestration
# =============================================================================
def run_audit() -> dict[str, list[dict]]:
    ctx: dict = {}
    ctx["listening"] = listening_ports()
    # GATEWAYS must run before HERMES/AUTH/STALE so probe caches are populated.
    gateways = audit_gateways(ctx)
    hermes = audit_hermes(ctx)
    api_keys = audit_api_keys(ctx)
    auth = audit_auth(ctx)
    services = audit_services(ctx)
    stale = audit_stale(ctx)
    google = audit_google_tokens(ctx)

    results = {
        "HERMES": hermes,
        "GATEWAYS": gateways,
        "API_KEYS": api_keys,
        "AUTH": auth,
        "SERVICES": services,
        "STALE": stale,
    }
    if google:
        results["GOOGLE_TOKENS"] = google
    return results


def counts(results: dict[str, list[dict]]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for cat, items in results.items():
        c: dict[str, int] = {}
        for it in items:
            c[it["status"]] = c.get(it["status"], 0) + 1
        summary[cat] = c
    return summary


CAT_TITLES = {
    "HERMES": "HERMES DEEP-DIVE (owner priority #1)",
    "GATEWAYS": "GATEWAYS / TUNNELS",
    "API_KEYS": "API KEYS",
    "AUTH": "AUTH / PASSWORDS",
    "SERVICES": "LOCAL SERVICES (launchd)",
    "STALE": "STALE REFERENCES",
    "GOOGLE_TOKENS": "GOOGLE TOKENS (Drive/Gmail)",
}

ORDER = ["HERMES", "GATEWAYS", "API_KEYS", "AUTH", "SERVICES", "STALE", "GOOGLE_TOKENS"]


def human_report(results: dict[str, list[dict]]) -> str:
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("CC MISSING-LINK AUDIT  —  Tiger Claw / REX / Hermes / GOJ")
    lines.append("READ-ONLY diagnosis. Hermes section first (owner priority).")
    lines.append("=" * 78)

    summ = counts(results)
    lines.append("\nSUMMARY (findings per category):")
    for cat in ORDER:
        if cat not in results:
            continue
        c = summ[cat]
        flag = c.get(BROKEN, 0) + c.get(MISSING, 0)
        lines.append(f"  {CAT_TITLES[cat]:42s} "
                     f"BROKEN/MISSING={flag:2d}  WARN={c.get(WARN,0):2d}  "
                     f"STALE={c.get(STALE,0):2d}  OK={c.get(OK,0):2d}")

    for cat in ORDER:
        if cat not in results:
            continue
        lines.append("\n" + "-" * 78)
        lines.append(f"## {CAT_TITLES[cat]}")
        lines.append("-" * 78)
        # Sort: BROKEN, MISSING, STALE, WARN, INFO, OK
        rank = {BROKEN: 0, MISSING: 1, STALE: 2, WARN: 3, INFO: 4, OK: 5}
        for it in sorted(results[cat], key=lambda x: rank.get(x["status"], 9)):
            lines.append(f"\n[{it['status']}] {it['what']}")
            lines.append(f"    where : {it['where']}")
            lines.append(f"    fix   : {it['how_to_fix']}")
    lines.append("\n" + "=" * 78)
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Tiger Claw/REX/Hermes/GOJ missing-link auditor (read-only)")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args()

    results = run_audit()
    if args.json:
        print(json.dumps({"summary": counts(results), "findings": results}, indent=2))
    else:
        print(human_report(results))
    # Exit non-zero if anything is broken/missing, so it can gate CI/cron if desired.
    flagged = sum(
        1 for items in results.values() for it in items if it["status"] in (BROKEN, MISSING)
    )
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
