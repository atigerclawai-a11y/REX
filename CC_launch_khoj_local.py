#!/usr/bin/env python3
"""
CC_launch_khoj_local.py — launch Khoj with a SANITIZED environment.
Guarantee: no cloud API keys reach the Khoj process. Only local vars allowed.
Usage: python3 CC_launch_khoj_local.py  (stays in foreground; run via launchd)
"""
import os
import subprocess
import sys
from pathlib import Path

# Whitelist of env var NAMES allowed through (values from a clean build below).
# Cloud-key names are asserted ABSENT — any match is fatal.
ALLOWED = {
    "PATH": "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
    "HOME": str(Path.home()),
    "LANG": "en_US.UTF-8",
    "KHOJ_ADMIN_EMAIL": "kato@local.home",
    # KHOJ_ADMIN_PASSWORD set below (not inline in a shared constant)
    "OPENAI_API_KEY": "ollama",
    "OPENAI_BASE_URL": "http://localhost:11435/v1/",
}

# Cloud-key NAMES to assert ABSENT. NOTE: OPENAI_API_KEY is intentionally
# NOT in this set — the whitelist carries OPENAI_API_KEY=ollama as Khoj's
# LOCAL placeholder (points at the office tunnel). The original pyc listed it
# here, which made the launcher always-fatal (latent bug — Khoj was actually
# launched by the gateway, never through this launcher). The verified env
# check (ps eww | grep ANTHROPIC|OPENROUTER|DEEPSEEK|N8N_) confirms the real
# blacklist. Repaired 2026-08-04 during pyc recovery.
CLOUD_KEYS = ("ANTHROPIC", "OPENROUTER", "DEEPSEEK", "N8N_", "AZURE", "GEMINI", "GOOGLE_API")


def main():
    env = dict(ALLOWED)
    env["KHOJ_ADMIN_PASSWORD"] = "rexxie-local-pa-2026"  # local-only PA password (encrypted USB vault holds the real ones)

    # Fatal if any cloud-key name is present in the whitelist
    leaked = [k for k in env if any(tag in k.upper() for tag in CLOUD_KEYS)]
    if leaked:
        print(f"FATAL: cloud keys leaked into whitelist: {leaked}", flush=True)
        sys.exit(1)

    khoj = os.path.expanduser("~/khoj-venv-home/bin/khoj")
    cfg = os.path.expanduser("~/khoj/khoj_config.yml")
    if not os.path.exists(khoj) or not os.path.exists(cfg):
        print(f"FATAL: khoj ({khoj}) or config ({cfg}) missing", flush=True)
        sys.exit(1)

    print(f"[{len(env)}] launching Khoj with sanitized env (zero cloud keys)", flush=True)
    os.execve(khoj, [khoj, "--config-file", cfg, "--anonymous-mode"], env)


if __name__ == "__main__":
    main()
