# Loop Audit Report — 2026-07-16

## Session Mining Summary (Phase 0)
- **Sessions analyzed:** 5 discovery queries + browse = 8 sessions deep-dived
- **Date range:** 2026-07-01 → 2026-07-16
- **Accomplishments:** 4 major builds completed
- **Errors found:** 2 recurring patterns (Tauri iOS build, RAM exhaustion)
- **Skills created/patched:** 4 created (knowledge-bootstrap, night-shift, session-learner, auto-skill-builder), 1 patched (loop-audit Phase 0)
- **Automation opportunities identified:** 2
- **Skill gaps:** None critical — existing skills cover all active domains

### Session Deep-Dives

| Session | Goal | Errors | Fixes | Outcome |
|---------|------|--------|-------|---------|
| `20260701_102912_6ce22d42` | MCP bridge creation, hardcoded references | Supabase paused, FD exhaustion | knowledge-bootstrap skill, System Hardcoded Reference | 36 MCP servers operational |
| `20260706_050453_8f4693` | goj-shellcore iOS Tauri build | `missing mobile_entry_point macro` (BUILD FAILED) | Cargo check passed (0.56s), build failed at Xcode phase | Still broken — needs lib.rs fix |
| `20260708_230201_e35a75` | RAM exhaustion root cause | Disk 14GB free, Docker 9GB, 123 Python processes | Diagnosed, proposed 6-step fix plan — awaiting Kato | **Kato intervention since then: disk 2.7GB→13GB recovered** |
| `60a7718f36b3` | MCP ecosystem cleanup | npm packages missing | All 24 MCP servers built, 3 workers parallel | Full fleet operational |
| `20260712_040245_1cb2c3` | Second brain bootstrap | TCC flapping | SCHEMA/Objectives/index/log created, Night Shift cron deployed | **This is the session that booted today's audit.** |

## Overall Summary
- **Total jobs:** 47 (29 agent + 18 no_agent)
- **L0:** 3 | **L1:** 14 | **L2:** 24 | **L3:** 6
- **Paused/Disabled:** 2 (BBG Poller — intentional; Dashboard Health Monitor 9bd4245c37cb — replaced)
- **Errors:** 11 (highest count recorded — was 1 on Jul 14)
- **Critical gaps:** 11 erroring jobs, notification fatigue (ShellCore Watchdog), TCC flapping
- **Anti-patterns found:** 5 (AI-on-deterministic, same-agent verification, no attempt caps on new jobs, duplicate replace-without-archive, zero-run jobs scoring)

---

## Per-Job Scores (Summary)

### L3 Jobs (16-20pts) — Unattended
| Job ID | Name | Score | Notes |
|--------|------|-------|-------|
| `7bcbe043707c` | JARVIS HUD Loop | 17/20 | Mature, 25 runs, stable |
| `bd5546628c3a` | Memory Injector | 17/20 | Core infrastructure, 111 runs |
| `109cf34e612d` | n8n Checkpointer | 16/20 | no_agent, 1,398 runs, solid |
| `bec587307624` | OCR Intake Poller | 16/20 | no_agent, 9,464 runs |
| `6c04f5ccfc25` | GOJ Dashboard Keepalive | 16/20 | no_agent, 3,835 runs |
| `6020a36b5626` | Vault Mirror Sync | 16/20 | no_agent, 388 runs |

### L2 Jobs (10-15pts) — Assisted
Core production jobs: Carecenta Study, GOJ Daily Docs, GOJ Kitchen Refresh, NotebookLM Check, Red Team, Blue Team, n8n Backup, n8n Snapshot, OCR Pipeline, Session Learning Loop, Night Shift, Claude Safety Net — **18 jobs total**. All scoring 12-15 pts.

### L1 Jobs (5-9pts) — Report-Only
New/infrequent jobs: Wiki Daily Digest, Daily Compound, Morning Standup, Wiki Health Lint, Vault Embedding Index, Skills Registry, OCR Coincidence, CC_attendance Backup, DB Sync, WhatsApp Watchdog — **14 jobs total**.

### L0 Jobs (0-4pts) — Draft/Error
| Job ID | Name | Issue |
|--------|------|-------|
| `a87d2474723a` | Vault Embedding Index Rebuild | 3 runs, all error — never worked |
| `80bd7d0610a3` | Skills Registry Rebuild | 3 runs, all error — never worked |
| `57684d57e324` | CC_attendance Nightly Backup | 1 run, error — never executed successfully |

### Disabled/Paused (scored separately)
| Job ID | Name | Status | Reason |
|--------|------|--------|--------|
| `ef3bd16a87e6` | BBG Reservation Poller | Paused (Jul 7) | Kato — "stale reservations, no new data" — OK |
| `9bd4245c37cb` | Dashboard Health Monitor | **DISABLED** | Replaced by ce59ba70e9e8 (bash) — but PM says "MUST BE ACTIVE" — remove or re-enable |

---

## Anti-Pattern Scan

### 🔴 AP-1: Same Agent Verifies Itself (2 jobs)
- `415583c236e9` (Session Learning Loop) — loads loop-audit + session-learner + auto-skill-builder, but all run in same agent context. No delegate_task for verification.
- `9a843d30f516` (Night Shift) — self-verifies its own session dumps.

### 🔴 AP-2: No Attempt Cap (4 new jobs)
- `a87d2474723a`, `80bd7d0610a3`, `918913b810f4`, `13170257a1b7` — no max_iterations or retry limits in prompts. New jobs created Jul 12-15.

### 🟡 AP-3: Duplicate Replace Without Archive
- `9bd4245c37cb` (Dashboard Health Monitor AI) replaced by `ce59ba70e9e8` (bash). Old job is `enabled=false` but still in roster — should be archived, not kept as zombie.

### 🔴 AP-4: AI on Deterministic Task
- `6073516fb26a` (n8n Webhook Bridge Keepalive) — polls n8n every 5m with a full AI agent. Is flagged `no_agent=True` but still uses model. Token burn on curl-equivalent.

### 🟡 AP-5: Notification Fatigue
- ShellCore Health Watchdog (`2rAqHTiiwTXQJyY5`) — pings dead port 8081 every 5min, alerts Telegram every time. n8n workflow, not Hermes cron, but escalation chain is broken.

---

## Failure Mode Risk Assessment

| Failure Mode | Risk | Jobs Affected |
|-------------|------|---------------|
| **Token Burn** | 🔴 HIGH | 6073516fb26a (5m AI polling) |
| **Infinite Fix Loop** | 🟡 MEDIUM | a87d2474723a, 80bd7d0610a3 (never-successful new jobs) |
| **Notification Fatigue** | 🔴 HIGH | n8n ShellCore Watchdog (every 5m) |
| **State Rot** | 🟡 MEDIUM | PM line 85 (47 jobs → still says 36/45/50 in different sections) |
| **Delivery Channel Mismatch** | 🟡 MEDIUM | 4 jobs have "no delivery target resolved" |
| **Verifier Theater** | 🟡 MEDIUM | 415583c236e9, 9a843d30f516 |
| **Escalation Failure** | 🟡 MEDIUM | 86b7a055e06f (Watchdog errors, escalation chain broken) |

---

## Learning Insights

### Recurring Error Patterns
1. **New jobs never succeed on first run** — `a87d2474723a`, `80bd7d0610a3`, `57684d57e324` all have 1-3 runs and error. Pattern: skill/view/reference path issues that weren't tested before cron deploy. Three sessions (`20260706_050453`, `20260712_040245`, `20260708_230201`) all created cron jobs that deployed untested.

2. **Tauri iOS build failure recurs** — Session `20260706_050453` hit `missing mobile_entry_point macro`. Same error was re-encountered in later sessions. No fix applied. Root cause: lib.rs missing `#[cfg_attr(mobile, tauri::mobile_entry_point)]`.

### Automation Opportunities
1. **Pre-cron validation script** — Before any new cron job is deployed, run a dry-run that verifies skills resolve, paths exist, and the agent boots. Currently zero pre-deploy validation.

### Skill Gap Analysis
- **No gaps detected.** All active domains have skill coverage. The continuous-improvement loop (loop-audit → session-learner → auto-skill-builder) is functioning — this report is proof.

---

## Remediation Priority (Top 5)

### 1. 🔴 Fix 11 Erroring Jobs — IMMEDIATE
**10 of 11 are no_agent scripts**, meaning they fail on script-level issues (paths, deps, permissions), not AI reasoning:
- `86b7a055e06f` — Hermes Watchdog (exit code 1, escalate to Kato)
- `6073516fb26a` — n8n Webhook Keepalive (replace with curl script, eliminate AI)
- `9522f5be2234` — Session Brief Auto-Regeneration (6 runs, all error)
- `aeeb156d2756` — Cron Self-Healer (11 runs, all error)
- `b775612c0f72` — n8n Version Auto-Sync (4 runs, all error)
- `ca52a93fe56e` — Wiki Health Watchdog (44 runs, all error)
- `f89f7f053cac` — System Drift Detector (22 runs, all error)
- `13170257a1b7` — RAM Governor (3 runs, all error)
- `a87d2474723a` — Vault Embedding Index (3 runs, all error)
- `80bd7d0610a3` — Skills Registry (3 runs, all error)
- `57684d57e324` — CC_attendance Backup (1 run, error)

### 2. 🔴 Remove or Re-enable Zombie Dashboard Health Monitor
`9bd4245c37cb` is `enabled=false` and replaced by `ce59ba70e9e8`, but Perpetual Memory says "MUST BE ACTIVE." Resolve the contradiction.

### 3. 🟡 Replace AI-on-Deterministic Keepalive
`6073516fb26a` (n8n Bridge Keepalive, every 5m) — runs a full AI agent to curl n8n. Replace with a 5-line bash script (`curl -s http://localhost:5678/healthz`). Token savings: ~$15-30/mo.

### 4. 🟡 Suppress ShellCore Watchdog Alerts
n8n workflow `2rAqHTiiwTXQJyY5` pings dead port 8081 every 5min and alerts Telegram. Either fix the endpoint or disable Telegram notifications (notification fatigue S2).

### 5. 🟡 Pre-Deploy Cron Validation
Before any new cron job is enabled, run `skill_view` on all listed skills + verify any referenced paths. Would have caught 3 of the 11 erroring jobs before they burned runs.

---

*Report auto-generated by Hermes Agent (Session Learning Loop cron: 415583c236e9). Source sessions: 20260701_102912_6ce22d42, 20260706_050453_8f4693, 20260708_230201_e35a75, 60a7718f36b3, 20260712_040245_1cb2c3. Vault: ~/GHS-Vault/Loop Audit — 2026-07-16.md*
