# Loop Audit Report — Batch A (10 Agent Cron Jobs) — 2026-07-16

## Overall Summary

- **Total jobs:** 10
- **L0:** 0 | **L1:** 3 | **L2:** 5 | **L3:** 2
- **Active (enabled=true):** 8 | **Paused:** 2 (BBG Poller, Dashboard Monitor)
- **Most common gaps:** No Maker/Checker split (6/10), no attempt cap (9/10), no cost limits (7/10)
- **Anti-patterns found:** same-agent-self-verify (6), AI-on-deterministic (4), no-attempt-cap (9), no-kill-switch (5 partial)
- **Critical gap:** 4 of 10 jobs burn AI tokens on deterministic CLI/curl tasks that should be `no_agent` scripts

---

## Per-Job Scores

### 1. JARVIS HUD Daily Self-Improvement Loop (7bcbe043707c)
- **Level: L1** | **Score: 8/20**
- **Schedule:** `5 3 * * *` (daily 3:05 AM) · 25 runs · enabled · deepseek-v4-pro
- **Skills:** jarvis-hud · **Toolsets:** None (defaults)
- **Deliver:** origin · **Model pinned:** yes (deepseek-v4-pro@deepseek)

| § | Section | Score | Notes |
|---|---------|-------|-------|
| 1 | Purpose | 1/2 | Clear goal (improve HUD), rules listed, but no phased rollout plan |
| 2 | Scheduling | 1/2 | 3:05AM off-hours, good cadence. No early-exit, no off-hours behavior |
| 3 | Skills | 2/2 | jarvis-hud skill — specific and relevant |
| 4 | Maker/Checker | 0/2 | **No verifier.** Agent implements AND marks done. Self-verify anti-pattern |
| 5 | State/Memory | 1/2 | References obsidian in prompt, but no explicit state read/write per run |
| 6 | Human Handoff | 0/2 | No escalation triggers, no max attempts, no notification gating |
| 7 | Connectors | 1/2 | Default toolsets (broad). No explicit MCP restrictions |
| 8 | Cost/Limits | 0/2 | No budget, no iteration cap, no pause criteria |
| 9 | Observability | 1/2 | "Report clearly what you changed." No structured run log, no metrics |
| 10 | Safety | 1/2 | Some killswitch/denylist references. No path allowlist for file writes |

- **Anti-patterns:** same-agent-self-verify (#1), no-attempt-cap (#2), L3-before-L1 (#4 — makes changes without report-only phase)
- **Failure mode risk:** **MEDIUM** — Infinite Fix Loop (no attempt cap), Verifier Theater, Over-Reach (writes without path filtering)
- **To reach L2:** Add verifier sub-agent, iteration cap (max 3 changes/day), escalation trigger on failures

---

### 2. Carecenta Platform Study (ca78d994a06c)
- **Level: L1** | **Score: 8/20**
- **Schedule:** `5 19 * * *` (daily 7:05 PM) · 22 runs · enabled · deepseek-v4-pro
- **Skills:** browser-spa-automation, himalaya · **Toolsets:** terminal, file, web, browser, search
- **Deliver:** origin

| § | Section | Score | Notes |
|---|---------|-------|-------|
| 1 | Purpose | 1/2 | Clear research goal, steps prescribed. Non-goals not explicit |
| 2 | Scheduling | 1/2 | Daily 7:05PM — appropriate for research. No early exit |
| 3 | Skills | 2/2 | browser-spa-automation + himalaya — relevant for research |
| 4 | Maker/Checker | 0/2 | No verifier. Agent reports its own findings |
| 5 | State/Memory | 1/2 | Saves to carecenta_study_results.md. Doesn't read prior state |
| 6 | Human Handoff | 0/2 | No escalation triggers. Research task — handoff less critical |
| 7 | Connectors | 1/2 | 5 toolsets enabled — broad access (browser, web, file, terminal) |
| 8 | Cost/Limits | 0/2 | No budget, no iteration limit |
| 9 | Observability | 1/2 | Reports findings to file. No structured logging |
| 10 | Safety | 1/2 | Research-safe by nature but no guardrails, no denylist |

- **Anti-patterns:** same-agent-self-verify (#1), no-attempt-cap (#2), no-kill-switch (#7)
- **Failure mode risk:** **LOW** — Read-only research, low blast radius. Token burn on repeated identical findings
- **To reach L2:** Add max iterations, define "done" state for study completion, add findings format

---

### 3. GOJ Daily Documents (2fd58acac200)
- **Level: L1** | **Score: 8/20**
- **Schedule:** `10 17 * * *` (daily 5:10 PM) · 21 runs · enabled · deepseek-v4-pro
- **Skills:** goj-drive-first, goj-operations, goj-kitchen-distribution
- **Deliver:** origin

| § | Section | Score | Notes |
|---|---------|-------|-------|
| 1 | Purpose | 1/2 | Clear — generate 6 daily PDFs. Scope from skills. No non-goals explicit |
| 2 | Scheduling | 1/2 | 5:10PM — after shift close. Appropriate. No early exit |
| 3 | Skills | 2/2 | 3 specific GOJ skills — highly relevant, well-scoped |
| 4 | Maker/Checker | 0/2 | No verifier. Agent generates AND considers done |
| 5 | State/Memory | 1/2 | Skills handle state (goj-drive-first checks Drive). No explicit run-log |
| 6 | Human Handoff | 0/2 | No escalation, no notification gating |
| 7 | Connectors | 1/2 | Default toolsets. Access to Google Drive via skill |
| 8 | Cost/Limits | 0/2 | No budget, no iteration cap |
| 9 | Observability | 1/2 | Skills produce output. No structured per-run logging prescribed |
| 10 | Safety | 1/2 | Some "kill" reference. No path allowlist for PDF writes |

- **Anti-patterns:** same-agent-self-verify (#1), no-attempt-cap (#2), no-kill-switch (#7 partial)
- **Failure mode risk:** **MEDIUM** — Over-Reach (PDF generation without write guardrails), State Rot (no prune)
- **To reach L2:** Add verification step (check PDF outputs exist + are non-empty), add iteration cap

---

### 4. GOJ Kitchen+Distribution Noon Refresh (7a623c74b4f1)
- **Level: L2** | **Score: 13/20**
- **Schedule:** `5 12 * * *` (daily 12:05 PM) · 19 runs · enabled · deepseek-v4-pro
- **Skills:** goj-drive-first, goj-kitchen-distribution
- **Deliver:** origin

| § | Section | Score | Notes |
|---|---------|-------|-------|
| 1 | Purpose | 1/2 | Clear goal, detailed preflight. Non-goals implicit but not explicit |
| 2 | Scheduling | 2/2 | Noon daily — appropriate. Has ABORT logic (early exit pattern) |
| 3 | Skills | 2/2 | 2 specific GOJ skills |
| 4 | Maker/Checker | 0/2 | No verifier |
| 5 | State/Memory | 2/2 | Token refresh, Drive check, DB inactive client check. Reads state well |
| 6 | Human Handoff | 1/2 | Reports warnings/errors. No explicit escalation triggers |
| 7 | Connectors | 1/2 | Default toolsets, skills gate access |
| 8 | Cost/Limits | 1/2 | Has ABORT criteria. No token budget stated |
| 9 | Observability | 2/2 | Detailed report format: dates, counts, warnings, unmatched names |
| 10 | Safety | 1/2 | ABORT on token failure, ABORT on Drive unreachable >24h |

- **Anti-patterns:** same-agent-self-verify (#1), no-attempt-cap (#2)
- **Failure mode risk:** **MEDIUM** — Token Burn (if Drive check loops), Over-Reach (PDF writes)
- **To reach L3:** Add verifier sub-agent, iteration cap, explicit token budget, escalation on mismatch

---

### 5. NotebookLM Session Check (a33563c8b83b)
- **Level: L2** | **Score: 13/20**
- **Schedule:** `10 9 * * *` (daily 9:10 AM) · 23 runs · enabled · deepseek-v4-pro
- **Skills:** None
- **Deliver:** origin

| § | Section | Score | Notes |
|---|---------|-------|-------|
| 1 | Purpose | 2/2 | Crystal clear — check and refresh NotebookLM auth |
| 2 | Scheduling | 2/2 | Daily 9:10AM — appropriate. Has early exit ("you're done") |
| 3 | Skills | 1/2 | None needed (simple CLI). But should be `no_agent` — deduction for AI on deterministic |
| 4 | Maker/Checker | 1/2 | N/A for auth check. No verifier needed |
| 5 | State/Memory | 1/2 | N/A — no state needed for auth check |
| 6 | Human Handoff | 1/2 | Reports when reauth fails ("Manual intervention needed") |
| 7 | Connectors | 1/2 | Default toolsets |
| 8 | Cost/Limits | 1/2 | Very short task. But AI for deterministic cmd = waste |
| 9 | Observability | 1/2 | Reports status clearly |
| 10 | Safety | 2/2 | No destructive actions — read-only auth check + reattempt |

- **Anti-patterns:** **AI-on-deterministic (#11)** — This is a 2-line bash script wrapped in an AI agent. It burns tokens on `nlm login --check` every day. Should be `no_agent=true`.
- **Failure mode risk:** **LOW** — Token Burn (minor, once daily)
- **To reach L3:** Convert to `no_agent` script. Not applicable — this task doesn't need AI at all.

---

### 6. BBG Owner.com Reservation Poller (ef3bd16a87e6)
- **Level: L2** | **Score: 11/20**
- **Schedule:** `every 5m` · 1271 runs · **PAUSED** (enabled=false) · deepseek-v4-pro
- **Skills:** himalaya
- **Deliver:** origin

| § | Section | Score | Notes |
|---|---------|-------|-------|
| 1 | Purpose | 2/2 | Clear — poll reservations, handle confirmations |
| 2 | Scheduling | 1/2 | Every 5min appropriate for reservations. But should be script, not AI agent |
| 3 | Skills | 1/2 | himalaya only — relevant but minimal |
| 4 | Maker/Checker | 0/2 | No verifier |
| 5 | State/Memory | 1/2 | Scripts handle state internally |
| 6 | Human Handoff | 2/2 | Asks Kato before confirming — explicit human gate for action |
| 7 | Connectors | 1/2 | Default toolsets |
| 8 | Cost/Limits | 0/2 | Every 5min with AI agent = **massive token burn** for deterministic polling |
| 9 | Observability | 1/2 | Reports reservations. No structured run log |
| 10 | Safety | 2/2 | Human confirmation gate for all actions — good |

- **Anti-patterns:** **AI-on-deterministic (#11)** — Running a Python script every 5min through an AI agent. The script (`CC_owner_reservation_poller.py`) already does the work. The AI wrapper only adds token cost. Also: same-agent-self-verify (#1), no-attempt-cap (#2)
- **Failure mode risk:** **HIGH** (if reactivated) — Token Burn (288 runs/day × AI agent), Notification Fatigue
- **Note:** Already PAUSED. This was the correct move. If re-enabled, convert to `no_agent` script-first approach.

---

### 7. Dashboard Health Monitor (9bd4245c37cb)
- **Level: L2** | **Score: 10/20**
- **Schedule:** `every 30m` · 521 runs · **DISABLED** (Blue Team 2026-07-15, replaced by ce59ba70e9e8) · deepseek-v4-pro
- **Skills:** None · **Toolsets:** terminal, send_message
- **Deliver:** origin

| § | Section | Score | Notes |
|---|---------|-------|-------|
| 1 | Purpose | 2/2 | Clear — health check 8 GHS services |
| 2 | Scheduling | 1/2 | Every 30min. FD-aware (sequential, not parallel). But should be no_agent |
| 3 | Skills | 0/2 | None needed. Pure deterministic — should be no_agent |
| 4 | Maker/Checker | 1/2 | N/A for read-only health checks |
| 5 | State/Memory | 0/2 | No state tracking between runs |
| 6 | Human Handoff | 1/2 | Reports only if DOWN or hourly heartbeat |
| 7 | Connectors | 2/2 | terminal + send_message — tight, appropriate |
| 8 | Cost/Limits | 0/2 | **521 runs × AI agent for curl commands.** Massive waste |
| 9 | Observability | 1/2 | Status table. No structured run log |
| 10 | Safety | 2/2 | Read-only, sequential FD-aware, no writes |

- **Anti-patterns:** **AI-on-deterministic (#11)** — The canonical example. 521 runs of an AI agent running sequential `curl` commands every 30min. Each run: parse prompt, plan, execute curls, format table — all for what `curl -s localhost:8080/ && echo OK` does in 50ms.
- **Failure mode risk:** **RESOLVED** — Already replaced by ce59ba70e9e8. Token burn stopped.
- **Legacy status:** The DISABLED flag is correct. This job is a case study in why deterministic tasks need `no_agent`.

---

### 8. Daily Graphify Vault Rebuild (4c4ff65c8aec)
- **Level: L2** | **Score: 11/20**
- **Schedule:** `0 4 * * *` (daily 4:00 AM) · 15 runs · enabled · deepseek-v4-pro
- **Skills:** None · **Toolsets:** terminal only
- **Deliver:** local

| § | Section | Score | Notes |
|---|---------|-------|-------|
| 1 | Purpose | 2/2 | Clear — rebuild knowledge graph |
| 2 | Scheduling | 2/2 | 4AM daily — perfect off-hours. Has SILENT early exit |
| 3 | Skills | 0/2 | None. Pure CLI — `graphify . --update` |
| 4 | Maker/Checker | 1/2 | N/A |
| 5 | State/Memory | 0/2 | No state tracking |
| 6 | Human Handoff | 1/2 | Reports errors only |
| 7 | Connectors | 2/2 | terminal only — minimal, perfect |
| 8 | Cost/Limits | 0/2 | AI wrapper for `graphify . --update` = unnecessary token burn |
| 9 | Observability | 1/2 | Reports node/edge counts. SILENT on no changes |
| 10 | Safety | 2/2 | Read-only graph rebuild, no writes to vault |

- **Anti-patterns:** **AI-on-deterministic (#11)** — A single CLI command wrapped in an AI agent. The prompt is 346 chars telling the model to run `graphify . --update`.
- **Failure mode risk:** **LOW** — Once daily, minimal blast radius. Still unnecessary tokens.
- **To reach L3:** Convert to `no_agent` script. This is the perfect candidate — one command, clear output, error handling via exit codes.

---

### 9. Red Team — Cross-System Audit (b79bc1095535)
- **Level: L3** | **Score: 18/20**
- **Schedule:** `0 */4 * * *` (every 4 hours) · 83 runs · enabled · deepseek-v4-pro
- **Skills:** cross-system-audit, loop-audit, obsidian
- **Toolsets:** terminal, file, web, search · **Deliver:** local

| § | Section | Score | Notes |
|---|---------|-------|-------|
| 1 | Purpose | 2/2 | Clear adversarial audit scope. 4 AI systems + shared infra. 3 phases defined |
| 2 | Scheduling | 2/2 | Every 4h at :00, offset from Blue Team at :30. Well-coordinated |
| 3 | Skills | 2/2 | cross-system-audit + loop-audit + obsidian — comprehensive, relevant |
| 4 | Maker/Checker | 2/2 | **Blue Team (119c33498f68) is the separate verifier/remediator.** RED→BLUE split |
| 5 | State/Memory | 2/2 | Updates Perpetual Memory, Session Brief. Reads vault. Writes RED_TEAM_FINDINGS.md |
| 6 | Human Handoff | 1/2 | Escalation through Blue Team. Severity-leveled findings. No direct human alert |
| 7 | Connectors | 2/2 | terminal, file, web, search — read-heavy, appropriate scope |
| 8 | Cost/Limits | 1/2 | Every 4h is reasonable cadence. No explicit token budget or iteration cap |
| 9 | Observability | 2/2 | Structured findings. Updates canonical sources. State file for Blue Team |
| 10 | Safety | 2/2 | "NEVER fabricate findings. Every claim backed by tool output." Denylist flagging |

- **Anti-patterns:** no-attempt-cap (#2 — minor risk, every-4h cadence limits blast radius)
- **Failure mode risk:** **LOW** — Token Burn (every 4h), Comprehension Debt Spiral (findings accumulate)
- **To improve:** Add explicit token budget per audit cycle, add stale-finding pruning

---

### 10. Blue Team — Cross-System Remediation (119c33498f68)
- **Level: L3** | **Score: 19/20**
- **Schedule:** `30 */4 * * *` (every 4 hours at :30) · 81 runs · enabled · deepseek-v4-pro
- **Skills:** cross-system-audit, system-recovery
- **Toolsets:** terminal, file, web · **Deliver:** local

| § | Section | Score | Notes |
|---|---------|-------|-------|
| 1 | Purpose | 2/2 | Clear — fix Red Team findings. Explicit DENYLIST + ALLOWLIST. Phased → 2 |
| 2 | Scheduling | 2/2 | Every 4h at :30 offset from Red Team. Allows Red to finish first |
| 3 | Skills | 2/2 | cross-system-audit + system-recovery — appropriate |
| 4 | Maker/Checker | 1/2 | Blue Team verifies Red Team (good). No separate checker for Blue's OWN fixes (mitigated by ALLOWLIST) |
| 5 | State/Memory | 2/2 | Reads RED_TEAM_FINDINGS.md, writes BLUE_TEAM_ACTIONS.md. Both files exist (8.5KB + 6.5KB) |
| 6 | Human Handoff | 2/2 | "If unsure, escalate." "If >5 critical items, escalate everything." Max 3 attempts/item |
| 7 | Connectors | 2/2 | terminal, file, web. No browser — appropriate for remediation |
| 8 | Cost/Limits | 2/2 | Max 3 attempts per item. "If >5 critical, skip ALL auto-fix" |
| 9 | Observability | 2/2 | "State After Actions table." Reports what was done + why |
| 10 | Safety | 2/2 | **Explicit DENYLIST:** auth/payments/secrets/production DBs. ALLOWLIST for safe patterns. Guardrails |

- **Anti-patterns:** Minimal — slight self-verify risk on own fixes (mitigated by strict ALLOWLIST gating)
- **Failure mode risk:** **LOW** — Escalation Failure (if Red Team findings file missing/stale), Delivery Channel Mismatch
- **To improve:** Already at L3. Consider adding a tertiary checker for Blue's own critical fixes.

---

## Anti-Pattern Heatmap

| Anti-Pattern | JARVIS | Carecenta | GOJ Docs | GOJ Noon | NLM Check | BBG Poll | Dash Mon | Graphify | Red Team | Blue Team |
|---|---|---|---|---|---|---|---|---|---|---|
| #1 same-agent-self-verify | 🔴 | 🔴 | 🔴 | 🔴 | — | 🔴 | — | — | — | 🟡 |
| #2 no-attempt-cap | 🔴 | 🔴 | 🔴 | 🔴 | 🟡 | 🔴 | 🔴 | — | 🟡 | — |
| #3 vague-triage | — | — | — | — | — | — | — | — | — | — |
| #4 L3-before-L1 | 🔴 | — | 🔴 | — | — | — | — | — | — | — |
| #5 shared-state-no-schema | — | — | — | — | — | — | — | — | — | — |
| #6 write-everything-mcp | — | — | — | — | — | — | — | — | — | — |
| #7 no-kill-switch | 🟡 | 🔴 | 🟡 | — | — | 🔴 | — | — | — | — |
| #8 fixing-flakes | — | — | — | — | — | — | — | — | — | — |
| #9 auto-action-no-allowlist | 🟡 | — | 🟡 | — | — | — | — | — | — | — |
| #10 no-run-log | 🟡 | 🔴 | 🟡 | — | — | — | 🔴 | 🔴 | — | — |
| #11 AI-on-deterministic | — | — | — | — | 🔴 | 🔴 | 🔴 | 🔴 | — | — |

🔴 = Definite | 🟡 = Partial | — = Not present

---

## Failure Mode Risk Assessment

| Failure Mode | Risk Level | Affected Jobs |
|---|---|---|
| **Token Burn** | HIGH | BBG Poller (288×/day if reactivated), Dashboard Monitor (48×/day was), Graphify (1×/day), NLM Check (1×/day) |
| **Infinite Fix Loop** | MEDIUM | JARVIS HUD (no attempt cap), GOJ Docs (no cap) |
| **Verifier Theater** | MEDIUM | JARVIS HUD, Carecenta, GOJ Docs, GOJ Noon (all self-verify) |
| **Over-Reach** | MEDIUM | JARVIS HUD (writes without path filtering), GOJ Docs (PDF writes) |
| **Notification Fatigue** | LOW | BBG Poller (every 5min), Dashboard Monitor (every 30min) |
| **State Rot** | LOW | GOJ Docs (no prune), Carecenta (accumulating findings) |
| **Escalation Failure** | LOW | Blue Team (if Red Team file stale) |
| **Comprehension Debt Spiral** | LOW | Red Team (findings accumulate across cycles) |

---

## Remediation Priority

### 🔴 CRITICAL — Fix Now
1. **Convert deterministic pollers to `no_agent` scripts:** Graphify, NotebookLM Check are trivially scriptable. BBG Poller (if reactivated) and Dashboard Monitor (already replaced) should never have been AI agents.
   - Graphify: `graphify . --update` → bash script, `no_agent=true`, cron `0 4 * * *`
   - NLM Check: `nlm login --check || nlm login` → bash script, `no_agent=true`

### 🟠 HIGH — This Week
2. **Add Maker/Checker splits to L3-aspiring jobs:** JARVIS HUD and GOJ Docs need verifier sub-agents before they can reach L2/L3
3. **Add attempt caps:** Every job except Red/Blue Team needs explicit `max_iterations` or attempt limits in prompts
4. **Add path allowlists:** JARVIS HUD file writes, GOJ Docs PDF generation — gate writes to specific directories

### 🟡 MEDIUM — This Sprint
5. **Add escalation triggers** to GOJ Docs, GOJ Noon, JARVIS HUD (notify on repeated failures)
6. **Add structured run logs** for Carecenta Study, GOJ Docs, BBG Poller
7. **Add token budget monitoring** for Red Team (every 4h × 1.4K prompt could compound)

### 🟢 LOW — Backlog
8. **Add off-hours behavior** for JARVIS HUD (skip weekends? slower cadence?)
9. **Add flake detection** — none of the 10 jobs handle transient failures explicitly
10. **Prune stale findings** in Red Team → Blue Team pipeline

---

## Key Takeaways

1. **The Red Team / Blue Team pair is the gold standard.** 18/20 and 19/20 respectively. Explicit maker/checker split, denylist/allowlist, iteration caps, state files, escalation rules — this is what L3 looks like.

2. **4 of 10 jobs are AI wrappers around deterministic CLI commands.** Graphify (`graphify . --update`), NLM Check (`nlm login --check`), Dashboard Monitor (`curl` × 8), BBG Poller (`python3 CC_owner_reservation_poller.py`). Combined, these burned tokens on 1,807+ runs of purely mechanical work. The Dashboard Monitor replacement (ce59ba70e9e8) was the right call — extend this to Graphify and NLM Check.

3. **The Maker/Checker gap is the single biggest design debt.** 6 of 10 jobs have no verification layer. The agent that writes is the agent that declares success. In production document generation (GOJ Docs, GOJ Noon) and system modification (JARVIS HUD), this is a real risk.

4. **No job has an explicit token budget.** Even the L3 Red/Blue pair doesn't cap per-run cost. For jobs running every 4 hours, this matters.

5. **Two paused jobs were paused correctly.** BBG Poller (AI-on-deterministic, 1,271 runs of waste) and Dashboard Monitor (521 runs of waste) — both paused for the right reasons. But the underlying tasks still need doing; they should be replaced with `no_agent` scripts, not abandoned.
