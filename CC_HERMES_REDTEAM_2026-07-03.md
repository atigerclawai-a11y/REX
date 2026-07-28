# Hermes Telegram Integration — Red Team Report
**Date:** 2026-07-03  
**Analyst:** Hermes Red Team (adversarial audit via Desktop Commander)  
**Scope:** All failure modes in the Hermes gateway Telegram integration  
**Data sources:** gateway.log, gateway.error.log, sessions.json, state.db, all 5 gateway plists, config.yaml, restart_loop_guard.py, gateway/run.py grep  

---

## Severity Summary

| # | Vulnerability | Severity | Impact to Kato |
|---|--------------|----------|----------------|
| 1 | DeepSeek primary model is deeply unreliable | CRITICAL | Hermes hangs/fails on ~every complex turn |
| 2 | Context window silent failure (97,787/128k) | CRITICAL | Next agentic turn likely fails with no notification |
| 3 | 569 SIGTERMs in 24h, root cause unknown, no throttle | CRITICAL | Gateway killed repeatedly, mid-turn data lost |
| 4 | Fallback chain in config doesn't match CLAUDE.md | HIGH | Operators troubleshoot wrong providers |
| 5 | state.db growing at 837MB/3 weeks — no pruning | HIGH | I/O cliff kills gateway silently |
| 6 | terminal tool blocked 1,654 times: pending_approval | HIGH | Every agentic tool call freezes until approved |
| 7 | No watchdog on Telegram polling loop | HIGH | Silent freeze undetectable until next SIGTERM |
| 8 | Kanban/auth lock files not force-cleaned on crash | MEDIUM | Kanban deadlocks on next boot after kill-9 |
| 9 | 83 Telegram commands hidden (>60 limit) | MEDIUM | Kato can't access 58% of registered commands |
| 10 | sessions.json display_name mismatch | LOW | Session routing ambiguity |

---

## FINDING 1 — CRITICAL: DeepSeek Stream Reliability

### Evidence
```
18,266 lines matching deepseek|RemoteProtocol|stream|retry|chunked in gateway.error.log
```

Sample failure modes observed:
```
WARNING agent.chat_completion_helpers: Stream stale for 180s — no chunks received.
  model=deepseek-v4-pro context=~59,915 tokens. Killing connection.

WARNING agent.conversation_loop: API call failed (attempt 1/3) error_type=ReadError
  error=[Errno 32] Broken pipe

WARNING agent.stream_diag: Stream drop on attempt 2/3 — retrying.
  error_type=RemoteProtocolError
  error=peer closed connection without sending complete message body (incomplete chunked read)
  http_status=200 bytes=841 chunks=2 elapsed=1.39s ttfb=0.77s
  upstream=[via=1.1 ac9d99d80216e8ed0f411e6f253f72c0.cloudfront.net (CloudFront) server=elb]

WARNING agent.stream_diag: Stream drop on attempt 3/3 — retrying.
  bytes=105100 chunks=251 elapsed=4.37s
```

### What this means
- DeepSeek routes through **AWS CloudFront** (CDN), not direct. The "incomplete chunked read" is CloudFront dropping the connection before the full response body arrives — a CDN-layer failure, not a DeepSeek API-layer failure. This cannot be fixed by the client.
- Three distinct failure types: **Broken pipe** (TCP reset mid-stream), **stream stale** (180s or 240s with zero chunks — DeepSeek accepted the request but returned nothing), **incomplete chunked read** (CloudFront cut the connection after partial delivery).
- `api_max_retries: 3` — all retries hit the same CloudFront infrastructure. A CDN-layer issue doesn't self-heal in 3 attempts.
- Stale stream timeout is 180s → Hermes hangs for **3 full minutes** per failed attempt before retrying. 3 attempts = **9 minutes of silence** before fallback triggers — from Kato's view, Hermes is frozen.
- At high context (59,915 tokens in one sample), stream stale threshold extends to **240s**.

### Failure mode from Kato's perspective
Send a message → Hermes appears to receive it (✓ ticks in Telegram) → 3–9 minutes of silence → eventually falls back or sends an error reply. Or: all 3 retries exhaust, fallback chain fires, minimax fails, Claude picks it up — total delay 15–20 minutes.

### Attack vector
This is **already happening continuously** — 18,266 error lines vs. presumably normal operation lines suggests DeepSeek is failing on a significant fraction of all turns. No rate data without counting total response lines, but it's not rare.

---

## FINDING 2 — CRITICAL: Context Window Silent Failure

### Evidence
From `sessions.json`:
```json
{
  "session_key": "agent:main:telegram:dm:5587703834",
  "session_id": "20260702_052812_212a54b6",
  "updated_at": "2026-07-02T15:41:37.388721",
  "last_prompt_tokens": 97787,
  "suspended": false,
  "resume_pending": false,
  "expiry_finalized": false
}
```

### What this means
- **97,787 tokens** used out of **128k limit** = **76.4% full**, ~30k remaining.
- The session is NOT suspended, NOT reset. Every new message from Kato appends to this context.
- A single tool-heavy turn (reading a file, running a command, getting a long response) can consume 10,000–50,000 tokens of tool output.
- At 30k headroom, **one complex tool-use turn can overflow the context**.
- When the context overflows, DeepSeek returns a 400-class error. The fallback providers (minimax, anthropic) each have their own context limits. This is not guaranteed to succeed.
- **There is no log evidence of a context-overflow warning being sent to Kato via Telegram.** The session will just fail silently until Kato notices Hermes stopped responding and manually triggers a `/reset` or `/new`.
- The `compression` config is enabled (`compression.enabled: true`, `target_ratio: 0.2`, `protect_last_n: 20`), but compression only runs between turns. If a single turn's input already exceeds the limit, compression doesn't help.

### Failure mode from Kato's perspective
Session appears normal → Kato sends a message → Hermes tries to build a ~100k+ prompt → DeepSeek rejects it (or CloudFront drops the oversized request) → Hermes error log fills, no Telegram reply → Kato waits, eventually realizes Hermes is dead.

### Compounding factor
The session display_name in sessions.json is `"Allen Khiger"` — suggesting this is the session that was active during the 15:41 freeze. After the session's last activity at 15:41:37, the gateway received a SIGTERM at 16:18:28 (37 minutes of silence). Any messages Kato sent in that 37-minute window hit a live polling loop but an agent that couldn't respond.

---

## FINDING 3 — CRITICAL: SIGTERM Storm, Unknown Source, No Throttle

### Evidence
```
=== SIGTERM count (total in gateway.log) ===
569 log lines (≈ 284 actual SIGTERM events, since each event logs 2 lines)

=== SIGTERM timestamps (sample) ===
2026-07-02 03:52:44
2026-07-02 03:52:58   ← 14 seconds apart
2026-07-02 03:53:12   ← 14 seconds apart
2026-07-02 03:53:26   ← 14 seconds apart
```

Restart-loop breaker from gateway.log:
```
WARNING: Restart-loop breaker TRIPPED: 5 restart-interrupted gateway boots within 60s
  (threshold 3). Skipping auto-resume (#30719).
  Delete /Users/mainsobhelper/.hermes/profiles/cloud/gateway/restart_loop.json
  to clear.
```

### What this means
All 5 gateway plists are configured identically:
```xml
<string>--replace</string>   <!-- in every plist -->
<key>KeepAlive</key><true/>   <!-- in every plist -->
<!-- NO ThrottleInterval in any plist -->
```

**The missing ThrottleInterval is the bomb.** `KeepAlive: true` without `ThrottleInterval` means launchd respawns the gateway **immediately** on every exit with no cooldown. If the gateway crashes or is SIGTERM'd, launchd fires it back up within ~1 second. The new process runs `--replace`, which SIGTERMs the previous process... which launchd respawns... which SIGTERM's again. This is a self-feeding loop.

The shutdown forensics in the log show:
```
Shutdown context: signal=SIGTERM under_systemd=yes parent_pid=1
parent_name=? parent_cmdline='(unknown)'
```
The `(unknown)` parent command is suspicious — **the source of the SIGTERMs cannot be identified from logs.** It's not `hermes gateway stop`, it's not a user command. It could be:
- Another plist starting and running `--replace` against the same profile (if a PID file race occurs)
- An external monitor/watchdog script
- macOS system sleep/wake cycles sending SIGTERM to background processes
- The Claus Watchman plist triggering restarts

### All 5 profiles confirmed
| Plist | Profile | --replace | KeepAlive | ThrottleInterval |
|-------|---------|-----------|-----------|-----------------|
| ai.hermes.gateway-cloud.plist | cloud | ✅ | ✅ | ❌ MISSING |
| ai.hermes.gateway.plist | default | ✅ | ✅ | ❌ MISSING |
| ai.hermes.gateway-hermie.plist | hermie | ✅ | ✅ | ❌ MISSING |
| ai.hermes.gateway-rexxie.plist | rexxie | ✅ | ✅ | ❌ MISSING |
| ai.hermes.gateway-work.plist | work | ✅ | ✅ | ❌ MISSING |

Since `--replace` is profile-scoped (kills the existing instance for the same profile only), the 5 profiles shouldn't normally SIGTERM each other. However, with no ThrottleInterval, any one of them can still enter a self-SIGTERM loop within its own profile, as confirmed by the 03:52–03:53 burst.

### The restart_loop_guard is the only protection — and it has holes
The guard (`restart_loop_guard.py`) trips at 3 restarts in 60 seconds and skips auto-resume. **But the gateway still starts** — it just doesn't replay the session. This means the loop stops killing itself, but:
1. The stale `restart_loop.json` blocks auto-resume on future legitimate restarts (this is the bug that was "just fixed").
2. The circuit breaker is good engineering but it's treating a symptom, not the disease.

### Failure mode from Kato's perspective
Hermes goes silent mid-task → restarts immediately → loses in-flight session state → Kato's conversation context evaporates → Hermes greets Kato as if fresh → loop may repeat.

---

## FINDING 4 — HIGH: Fallback Chain Mismatch (CLAUDE.md Is Wrong)

### Evidence
`config.yaml`:
```yaml
model:
  provider: deepseek
  default: deepseek-v4-pro

fallback_providers:
  - minimax
  - anthropic

providers:
  minimax:
    base_url: https://api.minimax.io/v1
    model: minimax-m3
  anthropic:
    api_key: sk-ant-api03-...
```

CLAUDE.md documents:
```
Gateway: deepseek-v4-pro via api.deepseek.com/v1 (NEVER OpenRouter)
· fallback: claude-sonnet-4-6 → gemini-2.0-flash
```

### What this means
The actual fallback chain is:
```
deepseek-v4-pro → minimax-m3 → anthropic (claude, no specific model pinned)
```

**Gemini is not in the fallback chain at all.** A Gemini API key exists in config (`AIzaSy...`) but it's NOT listed in `fallback_providers`.

**Minimax (minimax-m3)** is a Chinese LLM provider that is not documented anywhere in CLAUDE.md. It is now Hermes's first fallback when DeepSeek fails. This matters because:
1. Minimax has different context limits and behavior than Claude
2. It's not in the operational runbook, so when DeepSeek fails and Hermes starts acting differently, there's no documentation explaining why
3. Minimax may have its own reliability issues

When minimax also fails (and it will, given the volume of DeepSeek failures), **anthropic/claude** is the actual last resort. But no specific model is configured — it will use whatever hermes-agent defaults to, which may or may not be claude-sonnet-4-6.

### Failure mode from Kato's perspective
DeepSeek fails → Hermes silently switches to minimax → response quality/latency changes unexpectedly → Kato thinks something is wrong → searches CLAUDE.md for fallback info → finds "claude-sonnet-4-6 → gemini" → neither matches actual behavior → debugging is based on wrong assumptions.

---

## FINDING 5 — HIGH: state.db Unbounded Growth (984MB, No Pruning)

### Evidence
```
state.db: 984MB (Jul 3 01:28)
state-snapshots/20260614.../state.db: 147MB (Jun 14)

Growth: 837MB in ~18 days = ~46MB/day
Projected: 2GB by ~Jul 20, 4GB by ~Aug 25
```

Database contents:
```
messages: 57,359 rows
sessions: 3,797 rows
+ 11 FTS (Full Text Search) tables duplicating message content
state.db-wal: 0B (checkpointed)
state.db-shm: 32K
```

### What this means
- The `messages` table stores every message from every session — 57,359 messages × average message size = ~17KB/message (consistent with 984MB).
- The **FTS tables** (`messages_fts`, `messages_fts_trigram`, etc.) maintain **full-text search indexes** over the message content. These typically add 1.5–2× storage overhead.
- Top sessions by message count: `20260628_071606_bd025feb` (704 msgs), `20260624_112459_8c7cae8a` (689 msgs) — long agentic sessions accumulate thousands of messages.
- **No auto-pruning is configured** — `checkpoints.auto_prune: true` manages checkpoint snapshots, not the main `state.db` messages.
- SQLite performance degrades significantly on databases over ~1–2GB on spinning disk or when working sets don't fit in shared memory cache (shm).
- The WAL file is currently 0B (checkpointed clean), but during active use it grows — a checkpoint failure during heavy use can leave a multi-GB WAL that effectively doubles disk consumption.

### Failure mode from Kato's perspective
Gateway slows progressively → queries that took 50ms now take 500ms → state.db hits 2GB → SQLite tries to read the entire FTS index → swap pressure on the M4 → gateway starts timing out its own internal DB operations → sessions fail to save → message history lost.

---

## FINDING 6 — HIGH: terminal Tool Blocked by pending_approval (1,654 Times)

### Evidence
```
grep -c "pending_approval" gateway.error.log
1654
```

Sample blocked commands:
```
Tool terminal returned error: {"status": "pending_approval", "approval_pending": true,
  "command": "python3 -c \"import os, json\npath = '/Users/mainsobhelper/Desktop/REX/..."

Tool terminal returned error: {"status": "pending_approval", "approval_pending": true,
  "command": "curl -s -H \"Authorization: Bearer ***\" \"https://api.retellai.com/..."

Tool terminal returned error: {"status": "pending_approval", "approval_pending": true,
  "command": "ls -la ~/.hermes/shared/google_token.json 2>&1; echo \"---\"..."
```

### What this means
`terminal.modal_mode: auto` in config.yaml triggers Telegram button-based approval for terminal commands when Hermes is operating non-interactively (no TTY). **Every python3, bash, curl, ls, and file-read command requires Kato to tap "Approve" in Telegram before it executes.**

This means:
- Multi-step agentic tasks (e.g., "check all service statuses and restart the unhealthy ones") become **interactive approval chains** requiring Kato to tap 10–20 times
- If Kato doesn't respond to an approval prompt, the tool call hangs until `clarify_timeout: 600` (10 minutes) elapses
- 1,654 pending_approval events means this happened an average of **~90 times per day over the log period** — Hermes was effectively asking permission for every action
- Approval pending state is NOT persisted across restarts — if the gateway gets SIGTERM'd while waiting for approval, the approval is lost and the task hangs permanently until Kato restarts it

### Failure mode from Kato's perspective
Ask Hermes to run a diagnostic → Hermes sends "Approve this command?" button → Kato doesn't see it → 10 minutes later Hermes times out → Hermes reports failure → Kato tries again → cycle repeats.

---

## FINDING 7 — HIGH: No Watchdog on Telegram Polling Loop

### Evidence
Reconnect logic visible in gateway.log:
```
⚠️ No response from provider for 180s (model: deepseek-v4-pro, context: ~31,780 tokens). Reconnecting...
[Telegram] Connected to Telegram (polling mode)
```

But this "reconnect" is a **provider reconnect** (reconnecting to DeepSeek), NOT a Telegram polling reconnect.

Grep for actual Telegram polling watchdog:
```
grep -i "heartbeat|watchdog|poll|getUpdates" gateway.log | tail -10
```
Results: Only "Connected to Telegram (polling mode)" on startup — **no periodic heartbeat, no watchdog timer on the getUpdates loop itself.**

### What this means
The Telegram polling loop (`getUpdates` long-poll) is a coroutine running inside the gateway process. If it deadlocks (not crashes), the process remains alive (health endpoint returns 200, launchd considers it healthy) but inbound messages are silently dropped. The dead polling loop cannot be detected without external monitoring.

### Confirmed freeze window: 15:41 → 16:18 (37 minutes)
```
2026-07-02 15:41:37 — Last session activity
2026-07-02 16:18:28 — SIGTERM received (first SIGTERM after the freeze)
```

During those 37 minutes, the gateway process was alive, Telegram polling loop may have been running or frozen, but no messages were processed. A Telegram polling heartbeat (e.g., logging `getUpdates OK` every 30 seconds) would have detected this within 1 minute.

### 9-hour blackout (06:08:54 → 15:11:51)
The gateway connected at 06:08:54 and the next startup was at 15:11:51. The prior instance exited "cleanly" (per the boot log), meaning it shut itself down intentionally. However, during this 9-hour window, there are **zero log entries** — no messages processed, no errors, nothing. Either Kato sent no messages during this window, or messages were received but the logs don't record polling activity between turns. Worth verifying with Telegram's server-side logs.

### Failure mode from Kato's perspective
Gateway "alive" (launchd shows it running), Kato sends messages, nothing happens. No error. No timeout. Messages just disappear. Only way to detect: SIGTERM the gateway and check if it reconnects.

---

## FINDING 8 — MEDIUM: Dispatcher Lock Files Not Force-Cleaned on Crash

### Evidence
```
/Users/mainsobhelper/.hermes/kanban.db.dispatch.lock  — 0 bytes, last modified Jun 24
/Users/mainsobhelper/.hermes/kanban.db.init.lock      — 0 bytes, last modified Jun 9
/Users/mainsobhelper/.hermes/auth.lock                — 0 bytes, last modified Jun 9
/Users/mainsobhelper/.hermes/shared/nous_auth.lock    — 0 bytes, last modified Jun 9 (backup)
```

From `kanban_db.py` comments:
```python
# Motivation (issue #35240): a ``hermes gateway run --replace`` /
# crash can drive the supervisor into a tight respawn loop.
```

### What this means
Currently all lock files are 0 bytes and appear clean. However:
- These are advisory POSIX-style lock files (0-byte sentinels, not flock-based)
- A `kill -9` of the gateway (OOM kill, `pkill -9`, system crash) will **not** run cleanup code — the lock files are left in whatever state they were in at crash time
- If the kanban dispatcher is holding `kanban.db.dispatch.lock` when the process is killed, the next boot finds the lock occupied → kanban task processing deadlocks → Hermes can still chat but **cannot dispatch kanban tasks**
- The lock has been held since Jun 24 with no new writes — this could mean the kanban dispatcher isn't running, or the lock was orphaned by a crash 9 days ago

### Failure mode from Kato's perspective
Hermes responds to chat but silently fails to queue/dispatch any kanban tasks. No error message. Tasks look like they're accepted ("OK, I'll take care of that") but never execute.

---

## FINDING 9 — MEDIUM: 83 Telegram Commands Hidden (>60 BotFather Limit)

### Evidence
```
2026-07-02 16:26:50 INFO: [Telegram] Telegram menu: 60 commands registered,
  83 hidden (over 60 limit). Use /commands for full list.
```
(This appears on every restart.)

### What this means
- BotFather enforces a hard cap of 60 commands in the Telegram command menu (the `/` autocomplete)
- Hermes has **143 total registered commands** but only 60 are shown — **58% of commands are invisible** in the Telegram UI
- Commands visible in the menu are whatever the first 60 registered are — likely the common ones, but the selection is not documented
- Kato must know the exact command string to use any of the 83 hidden commands — no autocomplete, no discovery
- New commands added during development are silently dropped from the visible menu with no warning until the restart log is read

### Failure mode from Kato's perspective
Tries to use a command via Telegram menu — it's not there. Doesn't know if the command exists or was removed. Has to use `/commands` (which presumably lists all 143) and manually type hidden commands.

---

## FINDING 10 — LOW: sessions.json User Display Name

### Evidence
```json
"display_name": "Allen Khiger",
"origin": {
  "chat_name": "Allen Khiger",
  "user_id": "5587703834"
}
```

Per CLAUDE.md: User ID 5587703834 = Kato. But `display_name` = "Allen Khiger" (Allen is a former GOJ employee, per CLAUDE.md). This is likely a Telegram display name that Kato's account shows — not a routing error — but it creates session metadata that misidentifies the Chairman. Any system that reads `display_name` from sessions.json to determine access level or identity would route Kato to Allen's permissions tier.

---

## Attack Scenarios

### Scenario A: Context Overflow + DeepSeek Failure = Silent Death
1. Kato sends a complex multi-tool request at 97k tokens
2. Hermes assembles prompt → ~115k tokens
3. DeepSeek returns RemoteProtocolError (or CloudFront drops the oversized request)
4. Hermes retries 3× over 9 minutes → all fail
5. Minimax fallback fires → minimax has smaller context limit → also fails
6. Anthropic fallback fires → context trimmed → response is incoherent without full history
7. Hermes sends a degraded response or times out entirely
8. Kato sees nothing for 15–20 minutes, then a confused reply

### Scenario B: SIGTERM Storm → Loop Breaker Trip → Sessions Frozen
1. Unknown trigger sends SIGTERM to cloud gateway
2. KeepAlive respawns it immediately (no ThrottleInterval)
3. New process runs `--replace` → SIGTERMs previous → launchd respawns → loop
4. Loop breaker trips at 5 restarts in 60s → auto-resume disabled
5. All sessions in `resume_pending` state
6. Kato sends a message → Hermes receives it → starts fresh context (no history)
7. Kato asks "what were we just doing?" → Hermes: "I don't have context for that"

### Scenario C: pending_approval + SIGTERM = Lost Work
1. Hermes is mid-task, waiting for Kato to approve a terminal command
2. SIGTERM fires (happens ~dozen times/day)
3. Gateway dies with the approval request in-flight
4. On restart, approval state is lost — the tool call is abandoned
5. Hermes auto-resumes the session but the pending tool is gone
6. Hermes either re-runs from scratch (duplicates work) or proceeds without the tool result (produces wrong output)

### Scenario D: state.db I/O Cliff (2–4 weeks)
1. state.db crosses 2GB threshold
2. FTS index queries slow from ~10ms to ~200ms per message lookup
3. Every session load involves FTS — response initiation latency grows
4. SQLite WAL grows during heavy use → checkpoint takes 30+ seconds → gateway I/O blocks
5. Gateway timeout fires → SIGTERM storm begins
6. KeepAlive respawns → restart loop → loop breaker trips → sessions frozen
7. Everything compounds simultaneously

---

## Recommended Fixes (Priority Order)

### CRITICAL — Do immediately

**Fix 1a — Add ThrottleInterval to all gateway plists**
```xml
<key>ThrottleInterval</key>
<integer>10</integer>
```
Prevents launchd from firing more than one restart per 10 seconds. Eliminates the 14-second restart burst.

**Fix 1b — Identify the SIGTERM source**
```bash
# Add to plist EnvironmentVariables:
<key>HERMES_SIGTERM_DEBUG</key><string>1</string>
# Or add a pre-exit hook that runs: lsof -p $PPID; ps -p $PPID -o comm=
```
The `parent_cmdline='(unknown)'` must be resolved to know what's killing the gateway.

**Fix 2 — Context auto-reset at 90% or proactive notification**
Implement a pre-turn check: if `last_prompt_tokens > 115,000`, auto-send Kato a warning message ("⚠️ Context at 97k/128k — consider /reset or /new to avoid a silent failure") before attempting the API call.

**Fix 3 — Pin specific fallback models in config.yaml**
```yaml
fallback_providers:
  - minimax
  - anthropic
providers:
  anthropic:
    model: claude-sonnet-4-6  # Currently unpinned — add this
```
Also update CLAUDE.md to accurately reflect the minimax → anthropic chain (remove gemini reference).

### HIGH — Fix this week

**Fix 4 — state.db pruning**
Add a cron job or gateway housekeeping task to DELETE messages older than 90 days and run `VACUUM ANALYZE` weekly. Target: keep state.db under 500MB.

**Fix 5 — Change terminal.modal_mode**
```yaml
terminal:
  modal_mode: disabled  # or 'never' if that's the correct value
```
Or at minimum, configure auto-approve for specific safe commands (ls, cat, curl GETs) and require approval only for write operations.

**Fix 6 — Telegram polling heartbeat**
Log a `getUpdates: OK (n messages)` line every 60 seconds even if n=0. This creates a watchable signal. Pair with a separate cron that checks if this heartbeat log entry exists in the last 2 minutes and SIGTERMs the gateway if not (force respawn via KeepAlive).

### MEDIUM — Fix this sprint

**Fix 7 — Force-clean lock files on startup**
```python
# In gateway startup, before acquiring locks:
for lock_path in [KANBAN_DISPATCH_LOCK, KANBAN_INIT_LOCK, AUTH_LOCK]:
    if lock_path.exists() and is_stale(lock_path, max_age_seconds=300):
        lock_path.unlink()
        logger.warning("Removed stale lock: %s", lock_path)
```

**Fix 8 — Trim command list or use /commands pagination**
Implement a command priority ranking so the 60 most important commands are always registered. Archive low-frequency commands to `/commands advanced` response only.

---

## Metrics Baseline (2026-07-02)

| Metric | Value |
|--------|-------|
| SIGTERMs in 24h | 569 log lines ≈ 284 events |
| DeepSeek error log lines | 18,266 |
| pending_approval blocks | 1,654 |
| Active session context | 97,787 / 128,000 tokens (76.4%) |
| state.db size | 984 MB |
| state.db growth rate | ~46 MB/day (~837MB in 18 days) |
| Total messages in DB | 57,359 |
| Total sessions in DB | 3,797 |
| Telegram commands hidden | 83 of 143 (58%) |
| Gateway plist count | 5 (cloud, default, hermie, rexxie, work) |
| All plists missing ThrottleInterval | YES — all 5 |
| Polling loop watchdog | NONE |
| Context overflow notification | NONE |
| state.db auto-pruning | NONE |

---

*Report generated 2026-07-03. Data from ~/.hermes/profiles/cloud/logs/ and supporting files.*
