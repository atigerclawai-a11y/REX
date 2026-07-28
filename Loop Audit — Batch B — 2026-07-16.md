# Loop Audit — Batch B — 2026-07-16

Scored 10 agent cron jobs against the 10-point Loop Engineering checklist (10 sections × 0-2 pts, max 20).
Levels: L0=0-4, L1=5-9, L2=10-15, L3=16-20.

## Compact Score Table

| # | Job ID | Name | Runs | §1 | §2 | §3 | §4 | §5 | §6 | §7 | §8 | §9 | §10 | Score | Level |
|---|--------|------|------|----|----|----|----|----|----|----|----|----|-----|-------|-------|
| 1 | 6e3093 | n8n Daily Full Backup 3am | 16 | 1 | 1 | 0 | 0 | 0 | 0 | 2 | 0 | 1 | 1 | **6** | L1 |
| 2 | ea5978 | n8n Hourly Snapshot | 352 | 1 | 1 | 0 | 0 | 0 | 0 | 2 | 0 | 1 | 1 | **6** | L1 |
| 3 | 839aed | GOJ Dashboard Daily Refresh 6am | 14 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 1 | **5** | L1 |
| 4 | 415583 | Session Learning Loop | 12 | 2 | 1 | 2 | 1 | 2 | 1 | 2 | 0 | 2 | 1 | **14** | L2 |
| 5 | bd5546 | Memory Injector Obsidian→Memory | 112 | 2 | 1 | 2 | 1 | 2 | 0 | 2 | 0 | 1 | 1 | **12** | L2 |
| 6 | 4b6cb5 | Claude Safety Net auto-dump | 103 | 2 | 2 | 0 | 0 | 1 | 1 | 1 | 0 | 1 | 1 | **9** | L1 |
| 7 | e9e118 | Wiki Health Report lint & update | 50 | 2 | 2 | 0 | 0 | 1 | 1 | 1 | 0 | 1 | 1 | **9** | L1 |
| 8 | e33f00 | Wiki Daily Digest Telegram push | 10 | 2 | 2 | 0 | 0 | 0 | 1 | 1 | 0 | 0 | 1 | **7** | L1 |
| 9 | 9a843d | Night Shift Progress Worker | 17 | 2 | 2 | 2 | 0 | 2 | 0 | 2 | 1 | 2 | 2 | **15** | L2 |
| 10 | b5f44b | Night Shift Digest 6am Summary | 5 | 2 | 2 | 2 | 0 | 1 | 1 | 1 | 0 | 0 | 2 | **11** | L2 |

**Summary:** L0=0 | L1=5 | L2=4 | L3=0 | Avg score: 9.4/20

---

## Per-Job Detail

### 1. 6e3093 — n8n Daily Full Backup (3am) [L1 · 6/20]
**Gaps:** No skills loaded, no maker/checker, no state, no escalation triggers, no token budget, no verification that backup is valid.
**🔴 Anti-pattern: AI on deterministic task** — full LLM agent runs a single shell command (`python3 n8n_backup_agent.py backup`). This is a shell script wrapped in prose.
**Failure modes:** Token burn (daily LLM call for a one-liner), no backup integrity verification.

### 2. ea5978 — n8n Hourly Snapshot [L1 · 6/20]
**Gaps:** Same as #1 — identical anti-patterns, identical score.
**🔴 Anti-pattern: AI on deterministic task** — 352 hourly LLM invocations to run `python3 n8n_backup_agent.py snapshot "hourly"`. Massive token waste.
**Failure modes:** Token burn (352× hourly LLM calls for a deterministic snapshot script), no escalation on failure.

### 3. 839aed — GOJ Dashboard Daily Refresh (6am) [L1 · 5/20]
**Gaps:** No skills loaded (goj-governing-docs, goj-operations not used), no maker/checker, no state, no escalation, no budget.
**🔴 Anti-pattern: AI on deterministic task** — entire prompt is a multi-step shell script: Drive sync → file lifecycle → dashboard restart → report. Zero AI reasoning needed.
**🔴 Anti-pattern: Auto-action without allowlist** — auto-starts dashboard server if down. No verification that the restart was needed or successful.
**Failure modes:** Token burn, dashboard restart masking underlying issues, no goj-governing-docs loaded.

### 4. 415583 — Session Learning Loop [L2 · 14/20]
**Gaps:** No token budget (§8=0), same agent does audit + learning + building (§4 partial), no escalation triggers.
**Strengths:** Well-structured 5-phase procedure, 3 relevant skills loaded, full state cycle (reads/writes vault + memory), comprehensive observability.
**Anti-patterns:** Same agent verifies itself (Phase 3 audit within same run), no attempt cap.
**Failure modes:** Token burn (no budget on complex multi-phase run), comprehension debt spiral (reads own previous audit output).

### 5. bd5546 — Memory Injector [L2 · 12/20]
**Gaps:** No token budget (§8=0), no human handoff/escalation (§6=0), verification is self-check (§4 partial).
**Strengths:** Single clear goal, well-defined 4-step procedure, correct skills loaded (obsidian + knowledge-bootstrap), full state management cycle.
**Anti-patterns:** Same agent verifies its own memory writes, no attempt cap.
**Failure modes:** Token burn, state drift if memory writes fail silently (no alert on memory tool failure).

### 6. 4b6cb5 — Claude Safety Net [L1 · 9/20]
**Gaps:** No skills loaded (§3=0 — claude-session-obsidian-dump skill exists), no verifier, no token budget, no structured logging.
**Strengths:** Clear purpose with silence rule (early exit on SAFE/CLEAN = §2=2), Telegram notification on detection, writes recovery dump to vault.
**Anti-patterns:** No skills for a skill-defined domain, no attempt cap.
**Failure modes:** False negatives (misses lost work in edge-case files), false positive Telegram noise.

### 7. e9e118 — Wiki Health Report [L1 · 9/20]
**Gaps:** No skills loaded (§3=0 — wiki-lint skill exists), no verifier, no token budget.
**Strengths:** Silence rule (HEALTHY = no message = §2=2), contradiction-first prioritization in Telegram message, writes full report regardless.
**Anti-patterns:** No skills for a skill-defined domain, AI parsing deterministic script output.
**Failure modes:** Token burn, notification fatigue if lint accumulates minor issues.

### 8. e33f00 — Wiki Daily Digest Telegram [L1 · 7/20]
**Gaps:** No skills (§3=0), no state (§5=0), no token budget (§8=0), no observability log (§9=0).
**Strengths:** Clear purpose, silence rule on HEALTHY, prioritized output format (contradictions first, under 400 chars).
**Failure modes:** Token burn (AI formatting deterministic script output), no run log — can't tell if digest was ever sent.

### 9. 9a843d — Night Shift Progress Worker [L2 · 15/20]
**Gaps:** No maker/checker (§4=0), no escalation (§6=0), token budget is implicit only (§8 partial).
**Strengths:** Best-scored job in batch. Clear guardrails ("no production changes, no service restarts, no PHI"), correct skills (night-shift + obsidian), full state cycle, "ONE concrete action" scope limit, explicit early-exit ("nothing actionable, exit silent").
**Anti-patterns:** Same agent verifies itself, no attempt cap.
**Failure modes:** Token burn (no explicit budget), stale-objective loop (retrying same blocked objective endlessly).

### 10. b5f44b — Night Shift Digest 6am Summary [L2 · 11/20]
**Gaps:** No maker/checker (§4=0), no token budget (§8=0), no observability log (§9=0), only 5 runs — still in burn-in.
**Strengths:** Clear purpose, correct skills loaded, silence-rule on no activity, read-only operation, phone-readable format.
**Failure modes:** Token burn, stale digest (no night shift activity = silent, but no log to confirm it ran).

---

## Anti-Pattern Summary

| # | Anti-Pattern | Affected Jobs |
|---|-------------|---------------|
| 1 | **AI on deterministic task** | 6e3093, ea5978, 839aed, 4b6cb5, e9e118, e33f00 (6/10) |
| 2 | **No attempt cap / budget** | ALL 10 (0/10 have token budgets or iteration limits) |
| 3 | **Skills not loaded for skill-defined domains** | 4b6cb5 (claude-session-obsidian-dump exists), e9e118 (wiki-lint exists), e33f00 (wiki-lint exists), 839aed (goj-governing-docs exists) |
| 4 | **Same agent verifies itself** | 415583, bd5546, 9a843d (3/10) |
| 5 | **Auto-action without allowlist** | 839aed (auto-restarts dashboard), 4b6cb5 (auto-writes to vault) |
| 6 | **No run log** | e33f00, b5f44b (2/10) |

---

## Failure Mode Risk Assessment

| Failure Mode | Risk | Jobs Affected |
|-------------|------|---------------|
| Token Burn | **HIGH** | 6e3093, ea5978 (352 hourly LLM calls!), 839aed, e33f00 |
| Verifier Theater | **MED** | 415583, bd5546 (self-verification) |
| Escalation Failure | **MED** | 6e3093, ea5978, 839aed, bd5546, 9a843d (no escalation triggers) |
| Notification Fatigue | **LOW** | e9e118, e33f00 (mitigated by silence rules) |
| Comprehension Debt Spiral | **LOW** | 415583 (reads own previous audits) |
| Stale Objective Blocking | **MED** | 9a843d (could retry same blocked objective forever) |

---

## Remediation Priority

1. **CRITICAL: Convert deterministic script-runners to no_agent** — Jobs 1, 2, 3 are shell scripts wrapped in AI prose. Set `no_agent=true` and replace prompt with the actual script. Saves 352+ hourly LLM calls/month for n8n snapshots alone.

2. **HIGH: Add token budgets and iteration limits to all 10 jobs** — None have cost controls. Session Learning Loop (415583) is especially vulnerable — 5-phase procedure with unlimited iterations.

3. **HIGH: Load skills for skill-defined jobs** — 4b6cb5 should load `claude-session-obsidian-dump`. e9e118 and e33f00 should load `wiki-lint`. 839aed should load `goj-governing-docs`.

4. **MED: Add escalation triggers to Jobs 1-3, 5, 9** — Jobs that can fail silently need notification paths. Backup failures, memory inject failures, and Night Shift errors should alert Kato.

5. **LOW: Add run logs to e33f00 and b5f44b** — Digest jobs with silence rules need observability to confirm they actually ran.
