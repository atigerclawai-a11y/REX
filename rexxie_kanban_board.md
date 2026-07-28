# Rexxie Kanban Board — 2026-07-14 05:05

## 🔴 CRITICAL

| ID | Task | Status | Assigned | Notes |
|---|---|---|---|---|
| `red-blue/001` | Move 4 API keys from config.yaml to .env | ⬜ Todo | Hermes | 5 min. Anthropic/DeepSeek/Gemini/MiniMax keys |
| `red-blue/002` | Audit :8092 + :8778 — identify services, close if dead | ⬜ Todo | Hermes | Two unknown Python services on LAN |
| `red-blue/005` | Fix missing claude-to-wiki-dump.sh cron error | ⬜ Todo | Hermes | 1 of 34 crons broken |
| `social/001` | Connect BBG Facebook Page to Meta App 4214631288789941 | ⬜ Todo | Kato | Blocker for Instagram publishing |

## 🟠 HIGH

| ID | Task | Status | Assigned | Notes |
|---|---|---|---|---|
| `red-blue/003` | Add auth to REX API :8000 + GOJ :8080 | ⬜ Todo | Hermes | Unprotected localhost endpoints |
| `red-blue/004` | Bind Ollama proxy :11436 to localhost | ⬜ Todo | Hermes | 5 min fix |
| `build/001` | Build Alienware as headless GPU server | ⬜ Todo | Kato | Guide emailed. Frees Mac RAM. |

## 🟡 MEDIUM

| ID | Task | Status | Assigned | Notes |
|---|---|---|---|---|
| `ram/001` | Monitor swap — target <4GB | 🔄 In Progress | System | Was 9.2GB, now 6.3GB. Docker kill helped. |
| `rexxie/001` | Rexxie via `/model custom:office:` | ✅ Done | Hermes | Working. Telegram bot dead (polling conflict). |

## 🟢 DONE

| ID | Task | Status | Notes |
|---|---|---|---|
| `ram/002` | Kill Docker Desktop | ✅ Done | Freed 4GB |
| `ram/003` | Close Chrome | ✅ Done | Freed ~200MB |
| `ram/004` | Close TigerClaw | ✅ Done | Freed ~200MB |
| `audit/001` | Full red/blue audit 02:30 | ✅ Done | Report: security/red-team/findings/2026-07-14.md |
| `audit/002` | Full red/blue audit 05:00 (kanban-initiated) | ✅ Done | Report: security/red-team/findings/2026-07-14-0500.md |
| `rexxie/002` | Wire office Mac models to Hermes | ✅ Done | `/model custom:office:rexxie-qwen3:latest` |
| `config/001` | Override rexxie context to 65K | ✅ Done | Fixed Hermes 64K requirement |
