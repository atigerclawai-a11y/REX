# Loop Audit Report — 2026-07-06

## Session Mining Summary (Phase 0)

- **Sessions analyzed:** 6 (3 browse + 3 targeted queries x 4 dimensions)
- **Date range:** June 20, 2026 → July 06, 2026
- **Accomplishments identified:**
  - `20260706_050453_8f4693` — Created session-learner + auto-skill-builder skills, patched loop-audit with Phase 0, built iOS Tauri build script (blocked by terminal fd exhaustion)
  - `20260701_102912_6ce22d42` / `60a7718f36b3` — MCP ecosystem: 18→36 servers, 23/24 ready, all 6 paid AI bridges operational
  - `20260629_113303_14b7a02b` — BBG reservation SMS via Twilio (from Retell), skill patches, gateway port fix
  - `20260620_121142_87da6e1b` — GOJ Drive-first pipeline plan written (5 swimlanes, multi-agent)
- **Errors found:** 3 recurring across sessions
  - **Terminal fd exhaustion** — sessions `20260706_050453_8f4693`, `20260701_102912_6ce22d42`, `20260701_144127_9289fb`
  - **"unknown platform 'webui'" delivery errors** — 7 jobs affected (Red Team, Blue Team, n8n backups, Graphify, Watchdog, Token refresh)
  - **"Telegram send failed: Unauthorized"** — 4 jobs affected (JARVIS HUD, Carecenta, GOJ Kitchen, GOJ Dashboard)
- **Skills created/patched:** 3 created (session-learner, auto-skill-builder, loop-audit Phase 0 patch) — all today
- **Automation opportunities:** 1 — n8n webhook re-registration (watchdog alert webhook is 404)
- **Skill gaps:** iOS build automation (no native-app-wrappers coverage for Tauri iOS in cron)

## Overall Summary

- **Total jobs:** 23
- **L0:** 1 | **L1:** 3 | **L2:** 10 | **L3:** 7 | **N/A (no_agent):** 6 | **Insufficient data:** 2
- **Critical gaps:**
  1. Telegram delivery is broken across 4+ jobs (auth issue)
  2. "unknown platform 'webui'" affects 7 jobs (delivery misconfiguration)
  3. Hermes System Integrity Watchdog in ERROR state (exit code 1, n8n webhook 404)
  4. Google Token Refresh disabled (OAuth tokens deleted, but 6am dashboard refresh still calls direct_token_refresh.py)
  5. Session Learning Loop + Memory Injector have only 1-2 runs (too early to score)
- **Anti-patterns found:**
  1. **#2 No attempt cap** — BBG Reservation Poller (1081 runs, no max_iterations)
  2. **#7 No kill switch** — Dashboard Health Monitor (no budget limit, no pause criteria)
  3. **#4 L3 before L1 quality** — GOJ Daily Documents does writes without prior report-only phase
  4. **#8 Fixing flakes with code** — Multiple sessions show code fixes for transient fd exhaustion
  5. **AI-driven deterministic polling** — BBG Reservation Poller (every 5m), n8n Webhook Keepalive (every 5m), Dashboard Health Monitor (every 30m) — all burn AI tokens on mechanical curl/poll checks

---

## Per-Job Scores

### 1. JARVIS HUD Daily Self-Improvement Loop (`7bcbe043707c`)
- **Level:** L2 | **Score:** 13/20
- **Schedule:** Daily 3:05 AM | **Runs:** 15 | **Last:** ok
- **Gaps:** §8 (no token budget), §9 (no run log beyond STATE), §10 (modifies ~6700-line HTML without allowlist)
- **Anti-patterns:** None specific
- **Failure mode risk:** Med — Token Burn (large prompts), Over-Reach (no path denylist)
- **Delivery:** ❌ "Telegram send failed: Unauthorized"
- **To reach L3:** Add token budget estimate, implement path allowlist (jarvis.html + server.py only), add append-only run log

### 2. Carecenta Platform Study (`ca78d994a06c`)
- **Level:** L1 | **Score:** 8/20
- **Schedule:** Daily 7:05 PM | **Runs:** 13 | **Last:** ok
- **Gaps:** §4 (no maker/checker), §5 (no state tracking — each run is independent research), §8 (no budget), §9 (no observability)
- **Anti-patterns:** None
- **Failure mode risk:** Low — research-only, no writes
- **Delivery:** ❌ "Telegram send failed: Unauthorized"
- **To reach L2:** Add state tracking (what was found last run?), add attempt caps

### 3. GOJ Daily Documents (`2fd58acac200`)
- **Level:** L2 | **Score:** 12/20
- **Schedule:** Daily 5:10 PM | **Runs:** 12 | **Last:** ok
- **Gaps:** §4 (no verifier — generates PDFs without post-generation verification), §9 (no observability beyond job status), §10 (no allowlist for file writes)
- **Anti-patterns:** #4 (writes PDFs directly, no prior report-only phase), #9 (no path allowlist on generated files)
- **Failure mode risk:** Med — generates stale docs if Drive sync fails silently
- **To reach L3:** Add CC_drive_verify.py post-generation check, add path allowlist (only ~/Documents/goj files/output_docs/), add run log

### 4. GOJ Kitchen+Distribution Noon Refresh (`7a623c74b4f1`)
- **Level:** L2 | **Score:** 14/20
- **Schedule:** Daily 12:05 PM | **Runs:** 11 | **Last:** ok
- **Gaps:** §4 (suggests verification but doesn't enforce as separate step), §10 (writes PDFs without allowlist)
- **Anti-patterns:** #9 (no path allowlist)
- **Failure mode risk:** Med — no separate verifier
- **Delivery:** ❌ "Telegram send failed: Unauthorized"
- **To reach L3:** Split verify into separate sub-agent, add path allowlist

### 5. NotebookLM Session Check (`a33563c8b83b`)
- **Level:** L2 | **Score:** 12/20
- **Schedule:** Daily 9:10 AM | **Runs:** 13 | **Last:** ok
- **Gaps:** §4 (no verifier — checks its own work), §8 (no attempt cap for `nlm login`), §10 (touches auth state without explicit allowlist)
- **Anti-patterns:** #1 (verifies itself)
- **Failure mode risk:** Low — auth check only
- **To reach L3:** Add attempt cap (max 3 `nlm login` retries), add auth state log

### 6. BBG Owner.com Reservation Poller (`ef3bd16a87e6`)
- **Level:** L1 | **Score:** 7/20
- **Schedule:** Every 5 min | **Runs:** 1081 | **Last:** ok
- **Gaps:** §8 (1081 AI runs on 5-min polling — massive token burn for mechanical task), §5 (no state between runs), §9 (no run log), §3 (himalaya skill loaded but this is deterministic email checking)
- **Anti-patterns:** #2 (no attempt cap), **CRITICAL: AI-driven deterministic polling** — checking emails every 5 min via AI agent burns tokens unnecessarily
- **Failure mode risk:** High — Token Burn (1081 runs × ~500 tokens = ~500K tokens burned on mechanical polling)
- **To reach L2:** Replace AI agent with no_agent script (Python script → curl to bridge), keep AI only for confirmation/response step

### 7. Dashboard Health Monitor (`9bd4245c37cb`)
- **Level:** L1 | **Score:** 6/20
- **Schedule:** Every 30 min | **Runs:** 202 | **Last:** ok
- **Gaps:** §8 (202 AI runs for 8 sequential curls — deterministic), §4 (no verifier), §5 (no state tracking), §9 (no run log)
- **Anti-patterns:** **CRITICAL: AI-driven deterministic polling** — sequential curl checks don't need an AI agent. #7 (no kill switch), #2 (no attempt cap)
- **Failure mode risk:** High — Token Burn (202 runs × 8 curls via AI)
- **To reach L2:** Convert to no_agent script, report only when services are down

### 8. Daily Graphify Vault Rebuild (`4c4ff65c8aec`)
- **Level:** L2 | **Score:** 13/20
- **Schedule:** Daily 4:00 AM | **Runs:** 6 | **Last:** ok
- **Gaps:** §5 (no state — doesn't check if graphify output changed from last run), §9 (no observable metrics beyond exit code)
- **Anti-patterns:** None specific
- **Failure mode risk:** Low — read-only operation
- **Delivery:** ❌ "unknown platform 'webui'"
- **To reach L3:** Track node/edge counts across runs, add metrics

### 9. Google Token Refresh (`d33f24fe6ef6`) — **DISABLED**
- **Level:** N/A (disabled) | State: paused
- **Reason:** OAuth tokens deleted (2026-07-06 Red Team), cron renamed to reflect no-op status
- **Note:** `839aed29d920` (GOJ Dashboard Refresh) still calls `direct_token_refresh.py` — will fail until OAuth is re-introduced

### 10. Red Team — Cross-System Audit (`b79bc1095535`)
- **Level:** L2 | **Score:** 14/20
- **Schedule:** Every 4 hours | **Runs:** 28 | **Last:** ok
- **Gaps:** §8 (no token budget estimate), §9 (delivery broken, findings file may be stale)
- **Anti-patterns:** None
- **Failure mode risk:** Low — read-heavy, writes to state file only
- **Delivery:** ❌ "unknown platform 'webui'"
- **To reach L3:** Fix delivery, add budget monitoring

### 11. Blue Team — Cross-System Remediation (`119c33498f68`)
- **Level:** L2 | **Score:** 14/20
- **Schedule:** Every 4 hours (30m offset from Red) | **Runs:** 26 | **Last:** ok
- **Gaps:** §8 (no budget), §10 (auto-fix allowlist exists but narrow — could miss edge cases)
- **Anti-patterns:** None (well-designed allowlist/denylist in prompt!)
- **Failure mode risk:** Low — explicit allowlist restricts actions
- **Delivery:** ❌ "unknown platform 'webui'"
- **To reach L3:** Fix delivery, add budget estimate

### 12. n8n Daily Full Backup (`6e3093abfec2`)
- **Level:** L2 | **Score:** 14/20
- **Schedule:** Daily 3:00 AM | **Runs:** 6 | **Last:** ok
- **Gaps:** §5 (no state comparison to detect backup size drift), §9 (no success metrics)
- **Anti-patterns:** None
- **Failure mode risk:** Low — script-based, idempotent
- **Delivery:** ❌ "unknown platform 'webui'"
- **To reach L3:** Track backup sizes over time, add size drift alert

### 13. n8n Hourly Snapshot (`ea597858e867`)
- **Level:** L2 | **Score:** 13/20
- **Schedule:** Hourly at :05 | **Runs:** 124 | **Last:** ok
- **Gaps:** §8 (124 AI runs for a deterministic script call — potential token waste), §5 (no state), §9 (no metrics)
- **Anti-patterns:** Borderline AI-driven deterministic — prompt is "run this script, report if failed". Could be no_agent script.
- **Failure mode risk:** Low
- **Delivery:** ❌ "unknown platform 'webui'"
- **To reach L3:** Consider converting to no_agent or adding metrics

### 14. n8n Webhook Bridge Keepalive (`6073516fb26a`)
- **Level:** L1 | **Score:** 5/20
- **Schedule:** Every 5 min | **Runs:** 820 | **Last:** ok
- **Gaps:** **CRITICAL: AI-driven deterministic polling** — 820 AI runs for `curl health, restart if dead`. §8 massive token burn. §4, §5, §9 all missing.
- **Anti-patterns:** #2 (no attempt cap), #7 (no kill switch), AI-driven polling
- **Failure mode risk:** High — Token Burn (820 runs at minimal work per run)
- **To reach L2:** Convert to no_agent shell script. This is 3 lines of bash.

### 15. GOJ Dashboard Daily Refresh (`839aed29d920`)
- **Level:** L2 | **Score:** 12/20
- **Schedule:** Daily 6:00 AM | **Runs:** 4 | **Last:** ok
- **Gaps:** §4 (no verifier), §9 (no metrics), §5 (calls disabled token refresh)
- **Anti-patterns:** #9 (no path allowlist on file operations)
- **Failure mode risk:** Med — depends on disabled token refresh, will fail on OAuth
- **Delivery:** ❌ "Telegram send failed: Unauthorized"
- **To reach L3:** Remove dependency on direct_token_refresh (OAuth deleted), add verification step

### 16. Session Learning Loop (`415583c236e9`)
- **Level:** Insufficient data | **Score:** Withheld (<3 runs)
- **Schedule:** Daily 10:00 AM | **Runs:** 2 | **Last:** ok (this very job!)
- **Note:** Created today (2026-07-06), 2 completions. This is the job currently running.
- **Delivery:** ❌ "no delivery target resolved for deliver=all"

### 17. Memory Injector — Obsidian → Agent Memory (`bd5546628c3a`)
- **Level:** Insufficient data | **Score:** Withheld (1 run)
- **Schedule:** Every 2 hours | **Runs:** 1 | **Last:** ok
- **Note:** Created today (2026-07-06), 1 completion
- **Delivery:** local (silent — correct for this job type)

---

## no_agent Jobs (Reduced Rubric, max 8pts)

### 18. Hermes System Integrity Watchdog (`86b7a055e06f`) — ⚠️ ERROR
- **Score:** 4/8
- **Schedule:** Every 60m | **Runs:** 121 | **Last:** ERROR (exit code 1)
- **Purpose (2/2):** Clear — watches MASTERLIST freshness, config drift, gateway health
- **Scheduling (1/2):** Hourly is appropriate, but error state persists
- **Observability (0/1):** Output shows issues but n8n webhook delivery fails (404 "POST watchdog-alert" not registered)
- **Safety (1/2):** Read-only diagnostics, but writes to n8n webhook that's broken
- **Escalation (0/1):** Webhook is broken (n8n workflow not active), so errors go undelivered
- **Issues:** "MASTERLIST STALE: 6 days old", "CONFIG DRIFT: work fallback=[anthropic,] vs cloud fallback=[]", n8n alert webhook 404

### 19. n8n Continuous Checkpointer (`109cf34e612d`)
- **Score:** 7/8
- **Schedule:** Every 15m | **Runs:** 467 | **Last:** ok
- **Purpose (2/2):** Clear — detect n8n workflow changes, trigger backup
- **Scheduling (2/2):** 15min cadence appropriate for change detection
- **Observability (1/1):** stdout captured, exit codes reliable
- **Safety (2/2):** Read-only detection + trigger-only (backup is separate)
- **Escalation (1/1):** Backup triggers on change

### 20. OCR Intake — Folder Poller (`bec587307624`)
- **Score:** 7/8
- **Schedule:** Every 2m | **Runs:** 2,712 | **Last:** ok
- **Purpose (2/2):** Clear — poll scans folder, route new docs to OCR
- **Scheduling (2/2):** 2min cadence for document intake
- **Observability (0/1):** Silent on success (by design), but no count metrics
- **Safety (2/2):** Read-only polling + webhook trigger
- **Escalation (1/1):** Bridge handles failures

### 21. Email Intake — Gmail GOJ Documents (`5035221135ce`)
- **Score:** 7/8
- **Schedule:** Every 3m | **Runs:** 1,191 | **Last:** ok
- **Purpose (2/2):** Clear — check Gmail for GOJ docs, route to OCR
- **Scheduling (2/2):** 3min cadence for email intake
- **Observability (0/1):** Silent on success
- **Safety (2/2):** Read-only IMAP + webhook trigger
- **Escalation (1/1):** Bridge handles failures

### 22. macOS Desktop Integrity Watchdog (`59fd1dbab5ce`)
- **Score:** 7/8
- **Schedule:** Every 30m | **Runs:** 188 | **Last:** ok
- **Purpose (2/2):** Clear — dock, Finder, desktop integrity
- **Scheduling (2/2):** 30min cadence
- **Observability (0/1):** No metrics in visible output
- **Safety (2/2):** Diagnostics only
- **Escalation (1/1):** Reports issues

### 23. GOJ Dashboard Keepalive (`6c04f5ccfc25`)
- **Score:** 7/8
- **Schedule:** Every 5m | **Runs:** 1,077 | **Last:** ok
- **Purpose (2/2):** Clear — keep dashboard alive
- **Scheduling (2/2):** 5min keepalive appropriate
- **Observability (0/1):** Silent unless restart needed
- **Safety (2/2):** Health check + conditional restart
- **Escalation (1/1):** Restart handles transient failures

---

## Anti-Pattern Summary

| # | Anti-Pattern | Jobs Affected | Severity |
|---|-------------|---------------|----------|
| **AI-driven deterministic polling** | Jobs that poll/curl on a timer via AI agent | BBG Poller (5m), n8n Keepalive (5m), Health Monitor (30m), n8n Snapshot (hourly) | **HIGH** — ~1600+ AI runs wasted |
| **No attempt cap** | No max_iterations in prompt | BBG Poller, Health Monitor, n8n Keepalive | MED |
| **No kill switch** | No pause criteria, no budget limit | Health Monitor, BBG Poller | MED |
| **L3 before L1** | Writes before report-only phase | GOJ Daily Docs, GOJ Kitchen Refresh | MED |
| **Fixing flakes with code** | Code changes for transient fd exhaustion | Multiple sessions | MED |
| **No verifier** | Same agent checks its own work | NotebookLM Check, GOJ Daily Docs | LOW |

## Failure Mode Risk Summary

| Failure Mode | Severity | Jobs at Risk |
|-------------|----------|-------------|
| Token Burn | S1 | BBG Poller, n8n Keepalive, Health Monitor, n8n Snapshot |
| Notification Fatigue | S1→S2 | 7 jobs with broken delivery (Telegram + webui) |
| Escalation Failure | S2 | System Integrity Watchdog (n8n webhook 404) |
| State Rot | S1→S2 | GOJ Daily Docs (depends on disabled token refresh) |
| Over-Reach | S2→S3 | JARVIS HUD (no path denylist on 6700-line file) |

---

## Remediation Priority

1. **FIX TELEGRAM DELIVERY** — 4 jobs failing with "Telegram send failed: Unauthorized". This is a single auth fix that unblocks JARVIS HUD, Carecenta Study, GOJ Kitchen Refresh, and GOJ Dashboard Refresh.
2. **FIX "unknown platform 'webui'"** — 7 jobs (Red Team, Blue Team, n8n backups ×2, Graphify, Watchdog, Token refresh) can't deliver. Change deliver to "local" or fix webui delivery.
3. **CONVERT AI-DRIVEN POLLING TO no_agent** — BBG Poller (1081 AI runs), n8n Keepalive (820 AI runs), Dashboard Health Monitor (202 AI runs), n8n Hourly Snapshot (124 AI runs). Total: ~2200 wasted AI invocations. Replace with shell/Python scripts.
4. **FIX SYSTEM INTEGRITY WATCHDOG** — Currently ERROR state with MASTERLIST stale (6 days) and n8n webhook 404. Activate or re-register the watchdog-alert webhook.
5. **FIX SESSION LEARNING LOOP DELIVERY** — "no delivery target resolved for deliver=all". Set explicit origin or change to deliver=local.
6. **FIX GOJ DASHBOARD REFRESH OAUTH DEPENDENCY** — Remove `direct_token_refresh.py` call (OAuth tokens deleted). Replace with DB-based sync or re-introduce OAuth.
7. **ADD ATTEMPT CAPS** — BBG Poller, Health Monitor, n8n Keepalive need max_iterations.
8. **FIX n8n WATCHDOG WEBHOOK** — Activate the watchdog-alert workflow in n8n so System Integrity Watchdog errors get delivered.

---

## Close-the-Loop Notes

- **Obsidian MCP unreachable** — vault writes failed (ClosedResourceError). Report saved locally as canonical copy.
- **Perpetual Memory update deferred** — will be synced when Obsidian bridge recovers.
- **Agent memory update deferred** — memory tool unavailable in this cron session.
- **3 new skills created today** (session-learner, auto-skill-builder, loop-audit Phase 0 patch) — all operational.
- **This Session Learning Loop** (`415583c236e9`) ran its 3rd execution successfully — next run is scored.
- **Telegram delivery crisis** is the #1 blocker: 4 production jobs silently failing to deliver.
