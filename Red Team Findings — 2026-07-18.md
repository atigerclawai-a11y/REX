# Red Team Findings — 2026-07-18 11:45 EDT

## Critical (needs immediate attention)

- [ ] **🔴 DISK SPACE EMERGENCY — 4.2Gi free (74% root, 100% Data volume)** — OBJ-018 is ACTIVE, not downgraded. PM claimed 13Gi as of Jul 16 Blue Team. Reality: 4.2Gi. `/System/Volumes/Data` at 100% capacity (429Gi/460Gi). Docker daemon may have been killed by disk pressure. Downloads at 29Gi, `.hermes` at 14Gi. **CRITICAL: system operations may fail at any moment.**

- [ ] **🔴 Docker daemon DOWN** — LibreChat :3080 and Paperless :8010 are OFFLINE. Docker app exists but daemon not running. Root cause likely: Docker killed by macOS from disk pressure, or manual shutdown during Kato's disk cleanup. These are production services used by Kato.

- [ ] **🔴 5/10 active n8n workflows have NULL activeVersionId (unchanged since Jul 15)** — GOJ Daily Delivery, GOJ Nightly Handoff, Morning System Report, GOJ Kitchen Correction, GOJ Daily Pack — appear active but CANNOT execute. This was flagged Jul 15 (3 days ago) and remains unfixed.

- [ ] **🔴 n8n API Key ROTATED — Hermes config key is WRONG** — The key in Hermes config returns 401 `unauthorized`. The REAL key in `.claude.json` is different. This affects: n8n Continuous Checkpointer, n8n Hourly Snapshot, n8n Daily Full Backup, n8n Webhook Bridge (all may be silently failing on API calls). Verified via SQLite: 13 workflows, 10 active, 3 inactive.

- [ ] **🔴 34/34 agent cron jobs have ZERO toolset restrictions** — Every single agent job runs with unrestricted tool access. No `toolsets` configured on any job. This is a security gap — a compromised job has full system access.

## Warnings (should fix within 24h)

- [ ] **🟡 Session Brief 28h stale** — Last updated Jul 17 08:41. Auto-regen cron broken. Brief claims 51 total crons (actual 57), 20 no-agent (actual 23), services 11/11 UP (2 DOWN), disk 10Gi (actual 4.2Gi).

- [ ] **🟡 Victoria Sunday GAP** — Caller plist has Weekday 1-6 (Mon-Sat) at 14:00. Missing Sunday. 148 Monday clients get zero Sunday reminder calls. OBJ-014 flagged Jul 15, remains BLOCKED.

- [ ] **🟡 Duplicate cron: Session Learning Loop** — `415583c236e9` (14 runs) + `010f3c9a0df4` (4 runs). Both active, same pipeline.

- [ ] **🟡 RAM Governor at 650 wasted runs** — Script `ram_governor.py` missing from disk. Highest token-burn no-agent job.

- [ ] **🟡 2 never-run crons** — Carecenta Watchdog and Agent Oversight have 0 completed runs.

- [ ] **🟡 11 total error crons** — 5 missing-script, 3 disabled agent, 2 path-mismatch, 1 broken watchdog.

- [ ] **🟡 Perpetual Memory has stale service claims** — PM says LibreChat and Paperless are UP (both DOWN), disk 13Gi (actual 4.2Gi), Agent Loop "DEAD" (partially recovered).

## Info (notable but not urgent)

- [ ] **🔵 JARVIS Agent Loop partially recovered** — Now responds with `ok:true` (was completely dead). Hits 404 on step 1. Hub processes 2 (was 4).

- [ ] **🔵 Office Mac reachable** — 100.99.86.60 ping OK (24ms).

- [ ] **🔵 All Victoria HARD RULES pass** — voice_id=11labs-Kate, temperature=0.3, speed=0.85, language=ru-RU, agent_id correct, webhook :8089=200.

- [ ] **🔵 NotebookLM authenticated** — 2 notebooks, account correct.

- [ ] **🔵 0 delivery errors across all 57 crons** — Delivery infrastructure working.

- [ ] **🔵 Core services UP** — REX :8000, GOJ Dashboard :8080, Open WebUI :3000, Obsidian REST :27125 all OK. Work/Cloud gateways :3022/:3002 healthy.

## System Health Summary

| System | Status | Issues |
|--------|--------|--------|
| Hermes cron | 40/57 healthy (11 error, 6 disabled) | 11 error crons, 2 never-run, 1 duplicate pair |
| n8n | 10 active (5 NULL versionId) | API key rotated, 5 workflows can't execute |
| Docker | DOWN | LibreChat + Paperless offline |
| Obsidian | PM fresh, SB 28h stale | Session Brief auto-regen broken |
| NotebookLM | ✅ Authenticated | 2 notebooks |
| JARVIS Hub | Partially up | Agent loop responds but 404 on step 1 |
| Victoria Voice | ✅ All hard rules pass | Sunday gap only |
| Disk | 🔴 4.2Gi free | EMERGENCY — OBJ-018 actively critical |
| Google Auth | ✅ SA + IMAP present | No OAuth, compliant |

*Canonical copy: ~/.hermes/profiles/work/state/RED_TEAM_FINDINGS.md*
*PM patched: 5 sections updated 2026-07-18 11:45*
*Session Brief: updated 2026-07-18 11:45*
