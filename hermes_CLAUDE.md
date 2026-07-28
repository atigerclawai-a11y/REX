# CLAUDE.md — Hermes Build (Kato / GOJ)

This file provides guidance to Claude Code when working with the Hermes AI gateway stack.

---

## What Hermes Is

Hermes is an open-source multi-platform AI gateway. It connects messaging platforms (Telegram, Discord, Slack, etc.) to LLM backends (DeepSeek, Anthropic, Ollama, OpenAI, etc.) and runs scheduled cron jobs that deliver reports via those platforms. On this machine it runs as a macOS LaunchAgent.

---

## Key Paths

| Path | Purpose |
|------|---------|
| `~/.hermes/hermes-agent/` | Hermes source code (Python project, git repo) |
| `~/.hermes/hermes-agent/.venv/` | Python venv — use this for all `pip` and `hermes-agent` calls |
| `~/.hermes/hermes-agent/gateway/` | Core gateway module — platform adapters, config, session |
| `~/.hermes/profiles/cloud/` | Cloud profile home (HERMES_HOME for cloud gateway) |
| `~/.hermes/profiles/cloud/config.yaml` | **Primary gateway config** — this is what `load_gateway_config()` reads |
| `~/.hermes/profiles/cloud/logs/gateway.log` | Cloud gateway stdout/cron output |
| `~/.hermes/profiles/cloud/logs/gateway.error.log` | Cloud gateway stderr |
| `~/.hermes/profiles/cloud/sessions/` | Session transcripts (JSONL + SQLite) |
| `~/.hermes-cloud/config.yaml` | Hermes Workspace config (providers, models, system_prompt) — separate from gateway |
| `~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist` | LaunchAgent for cloud gateway |
| `~/Library/LaunchAgents/com.rex.rexxie-bot.plist` | LaunchAgent for Rexxie (Goldhealth bot) |
| `~/Desktop/REX/rex_rexxie_telegram_bot.py` | Rexxie v3 source |
| `~/Desktop/REX/rex_rexxie_telegram_config.json` | Rexxie + GojAttendance bot token/chat config |
| `~/Desktop/REX/goj_daily_scheduler.py` | GOJ daily automation scheduler |

---

## Architecture

### Config Loading (gateway)

`load_gateway_config()` in `gateway/config.py` merges from four sources in priority order:

1. **Environment variables** — highest priority, always win
2. **`~/.hermes/profiles/cloud/config.yaml`** — primary user config
3. **`~/.hermes/profiles/cloud/gateway.json`** — legacy fallback
4. **Built-in defaults** — lowest priority

Token injection for Telegram: the cloud gateway reads `TELEGRAM_BOT_TOKEN` from its plist `EnvironmentVariables`. The token is also in `~/.hermes/profiles/cloud/config.yaml` under `telegram.token`. If the YAML has a syntax error, the gateway falls back to the plist env var — this is the current failure mode.

### Platform Adapters

Each messaging platform is a `BasePlatformAdapter` subclass in `gateway/platforms/`. The adapter is auto-selected based on which env vars / config keys are present. Telegram uses long-polling (`getUpdates`). Only one process may poll a given bot token at a time — duplicate pollers produce `Conflict: terminated by other getUpdates request` errors.

### Session Storage

Sessions live in `~/.hermes/profiles/cloud/sessions/`:
- `sessions.json` — index of all sessions (platform, chat_id, updated_at)
- `<session_id>.jsonl` — message transcript
- SQLite DB alongside for fast queries

### Cron / Delivery

The gateway has a built-in cron ticker (interval=60s). Cron jobs can deliver to:
- `telegram` → home channel (set via `/sethome`)
- `telegram:<chat_id>` → specific chat
- `local` → file in `~/.hermes/profiles/cloud/cron/output/`

GOJ daily automation uses a separate scheduler (`goj_daily_scheduler.py`) that sends via `rex_rexxie_telegram_config.json` → @GojAttendance_bot.

---

## LaunchAgents in Use

| Label | Plist | What It Runs | Status |
|-------|-------|--------------|--------|
| `ai.hermes.gateway-cloud` | `ai.hermes.gateway-cloud.plist` | Cloud Hermes gateway (DeepSeek / @Hermes_Cloud_May_bot) | Running (PID 75270) |
| `com.rex.rexxie-bot` | `com.rex.rexxie-bot.plist` | Rexxie v3 (rex_rexxie_telegram_bot.py / @goldhealth_rexxie_bot) | Running (PID 56577) |
| `com.hermes.rex-telegram-bot` | `com.hermes.rex-telegram-bot.plist` | Rex Gold bot (rex_telegram_bot.py / @RexOfGold_bot) | Running (PID 14959) |
| `com.hermes.rexxie-bot` | `com.hermes.rexxie-bot.plist` | OLD Rexxie (deprecated, uses debate-chamber venv) | Crashed (exit -9) — should be disabled |
| `ai.hermes.gateway` | `ai.hermes.gateway.plist` | LOCAL Hermes gateway | Crashed (exit 1) |

Manage with:
```bash
launchctl load ~/Library/LaunchAgents/<label>.plist
launchctl unload ~/Library/LaunchAgents/<label>.plist
launchctl list | grep hermes
```

---

## Known Broken Things (as of 2026-05-30)

### 1. YAML Syntax Error — `config.yaml` line 18

**Error:** `while scanning a simple key … could not find expected ':' at line 18, column 1`

**Effect:** Gateway cannot load `config.yaml`. Falls back to `.env`/`gateway.json` values. The `system_prompt`, session reset policy, and streaming config are NOT applied. The gateway still runs using plist env vars (TELEGRAM_BOT_TOKEN etc.) but may be misconfigured.

**Fix:** Run `CC_fix_hermes_cloud_yaml.command` from `~/Desktop/REX/`. It shows lines 14-25 of the file, attempts to auto-fix a bare key on line 18, and restarts the gateway.

Manual fix if needed:
```bash
nano ~/.hermes/profiles/cloud/config.yaml
# Fix line 18: add a colon after the bare key, or delete the line if it's spurious
python3 -c "import yaml; yaml.safe_load(open('~/.hermes/profiles/cloud/config.yaml'))"
```

### 2. Telegram Not Connected — Cloud Gateway

**Error:** `[Telegram] Telegram bot token already in use (PID 74439). Stop the other gateway first.`

**Effect:** Cloud gateway runs but only as `api_server` (localhost:8644). @Hermes_Cloud_May_bot does not respond to Telegram messages.

**Root cause:** When `CC_fix_hermes_cloud_token.command` reloaded the plist, the old gateway process (PID 74439) had not fully died before the new one (75270) started. The new gateway detected the token collision and disabled Telegram.

**Fix:** Restart the cloud gateway after the old process is fully gone:
```bash
launchctl unload ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist
sleep 5
launchctl load ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist
# Verify Telegram connected:
tail -20 ~/.hermes/profiles/cloud/logs/gateway.log | grep -i telegram
```

The restart is included at the end of `CC_fix_hermes_cloud_yaml.command`.

### 3. `com.hermes.rexxie-bot` — Zombie Plist

This is the OLD Rexxie LaunchAgent (debate-chamber venv, deprecated). It crashes immediately (exit -9). It should be disabled to prevent it from restarting and competing for the Rexxie bot token:

```bash
launchctl unload ~/Library/LaunchAgents/com.hermes.rexxie-bot.plist
# Optionally rename so it won't auto-load on next boot:
mv ~/Library/LaunchAgents/com.hermes.rexxie-bot.plist ~/Library/LaunchAgents/com.hermes.rexxie-bot.plist.DISABLED
```

### 4. `ai.hermes.gateway` — Local Gateway Crash (exit 1)

The local (non-cloud) Hermes gateway is crashing. Check its log:
```bash
tail -50 ~/.hermes/logs/gateway.log 2>/dev/null
tail -50 ~/.hermes/logs/gateway.error.log 2>/dev/null
```

---

## Common Commands

```bash
# Check what's running
launchctl list | grep -iE "hermes|rex.*bot|rexxie"

# Tail cloud gateway log
tail -f ~/.hermes/profiles/cloud/logs/gateway.log

# Check gateway config is valid YAML
python3 -c "import yaml; yaml.safe_load(open('$HOME/.hermes/profiles/cloud/config.yaml'))"

# Run hermes CLI manually (cloud profile)
cd ~/.hermes/hermes-agent
HERMES_HOME=~/.hermes/profiles/cloud .venv/bin/hermes-agent gateway status

# Restart cloud gateway
launchctl unload ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist
sleep 5
launchctl load ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist

# Show all active sessions
ls ~/.hermes/profiles/cloud/sessions/*.jsonl 2>/dev/null | wc -l
```

---

## Config Reference — `config.yaml`

Full schema lives in `gateway/config.py`. Key top-level sections:

```yaml
telegram:
  token: <bot_token>          # overridden by TELEGRAM_BOT_TOKEN env var
  allowed_chats: [chat_id1]   # whitelist; omit for all chats
  home_channel: <chat_id>     # default delivery target

session_reset:
  mode: both                  # daily|idle|both|none
  at_hour: 4                  # hour for daily reset
  idle_minutes: 1440          # idle timeout

streaming:
  enabled: false
  transport: edit             # edit|draft|auto

agent:
  max_turns: 90
  system_prompt: "..."

platforms:
  api_server:
    enabled: true
    extra:
      port: 8644              # localhost API server (Open WebUI connects here)
```

---

## Private Confidant / Rexxie

`~/Desktop/Gold_Health_Systems/private_confidant_gold.py` is a **tombstone** — the original bot was merged into `rex_rexxie_telegram_bot.py` (v3.0) in April 2026. DO NOT run it.

Active Rexxie: `rex_rexxie_telegram_bot.py` managed by `com.rex.rexxie-bot.plist`, using `~/Desktop/REX/.venv/`.

---

## Telegram Bot Inventory

| Bot | Token Prefix | LaunchAgent | Config Location |
|-----|-------------|-------------|-----------------|
| @Hermes_Cloud_May_bot | 8648749431 | `ai.hermes.gateway-cloud.plist` | plist EnvironmentVariables |
| @goldhealth_rexxie_bot | 8657319466 | `com.rex.rexxie-bot.plist` | rex_rexxie_telegram_bot.py or .env |
| @RexOfGold_bot | (see rex_telegram_bot.py) | `com.hermes.rex-telegram-bot.plist` | rex_telegram_bot.py |
| @GojAttendance_bot | 8129962350 | goj_daily_scheduler.py | rex_rexxie_telegram_config.json |
| @GOJReceipts_bot | (see receipt_processor/) | CC_start_receipts_bot.command | telegram_bot.py in receipt_processor/ |
