# PAE Assessment Pack — 2026-06-08

## TL;DR (3 bullets)
- **Three items are low-risk, high-payoff and should go first:** PAE-5 (Tiger Claw API is already alive and serving real data — just confirm + activate), PAE-D (disclosure tier gate — security-critical, scoped, no infra rework), PAE-H (hermes-dreaming plugin install — declared safe, one-command install).
- **PAE-4 (AKC tokenizer) is the gating item for everything PHI-touching.** The v2 file is ready (560 lines, all 18 HIPAA Safe Harbor identifiers) but isn't wired into the PHI pipeline yet. Until this lands, PAE-R (Railway) cannot legally proceed because OG33/voice/documents pages depend on it.
- **PAE-7 (bot 401s) is a misread.** The 401s aren't API-key failures; they're 40 hits from one Signal UUID hammering the gateway as a non-authorized user. It's an access-list nuisance, not a system fault. Add the user or block the platform — no auth rotation needed.

## Per-PAE item

### PAE-4 — AKC tokenizer wire-in
- Doc(s) read: `CC_CLAUDECODE_HANDOFF_june8.md`, `CC_akc_tokenizer_v2.py` head
- Current state: `CC_akc_tokenizer_v2.py` exists at 560 lines, claims full Safe Harbor (18 identifiers). NOT imported anywhere in the live PHI pipeline. Skeleton at `~/Desktop/dashboard/akc_tokenizer.py` is what's currently being called.
- Scope to complete: Replace skeleton import path; add Gate 1 hard-block on outbound calls in REX `/api/cowork-relay`, the Hermes cloud gateway's outbound serializer, and any OG33/voice path that touches client text.
- Risk if executed now: LOW for the swap itself (file is self-contained). MEDIUM if rollout misses a code path — silent PHI leak.
- Preconditions: None from Kato. Needs a code search for every existing tokenizer import before the swap.
- My recommendation: **PROCEED** — but as the gating prerequisite for PAE-R, not a standalone.

### PAE-5 — Tiger Claw API :27226 verify + activate
- Probe result: `/health/full` HTTP 200, `/stats` HTTP 200, `/agents` HTTP 200
- Endpoints alive: All three. Returns real data — Hermes 0.15.0, GOJ attendance 423, 11 active agents, 202 skills, 10 MCP servers.
- Current state: It's already running. "Activate" appears to mean "stop treating it as pending and wire HUD/Jarvis consumers to it."
- Risk: Very LOW — read-only stats API, no auth surface.
- Recommendation: **PROCEED** — fastest win on the board. Verify launchd plist exists (`CC_jarvis_startup.command`) and add it to KeepAlive if not already.

### PAE-6 — Phase 16 business isolation enforcer swap
- File on disk: `~/Desktop/REX/core/business_isolation.py` (317 lines)
- Current state: File exists; "swap" implies replacing an earlier enforcer. Did not deep-read because it's a Phase 16 architectural change and the user wants assessment only.
- Risk if executed now: MEDIUM-HIGH — isolation enforcers typically gate cross-business data (GOJ ↔ BBG ↔ Rexxie). A bad swap leaks one tenant's data into another or causes legit calls to fail closed.
- Preconditions: A diff between old and new enforcer; a test plan covering all three businesses; a rollback path.
- Recommendation: **WAIT** — don't bundle with the quick wins. Schedule it alongside PAE-4 since both touch isolation boundaries.

### PAE-7 — Bot 401 errors in Hermes gateway
- Log evidence: 40 hits in `~/.hermes-cloud/logs/errors.log` over 5–6 June, all from a single Signal user UUID `02aa25ac-6fa8-4ece-ae48-ce5ec2adff94 (J)`. Pattern: `gateway.run: Unauthorized user: <uuid> (J) on signal`. Zero hits in `~/.hermes/profiles/cloud/logs/gateway.error.log` (those errors are unrelated — DeepSeek tool failures and Telegram fallback IP retries).
- Likely cause: Real human ("J") on Signal repeatedly trying to talk to the bot without being whitelisted. Not a credential failure, not a system bug.
- Recommendation: **KILL** as written. Reframe as either (a) add J to the allowlist if they're legit, or (b) ignore — the gateway is correctly refusing. No "fix" needed.

### PAE-8 — Agent Forge (13 agents)
- File on disk: `~/Desktop/REX/backend/rex_agent_forge.py` (385 lines)
- Current state: Not read. The :27226 `/agents` probe shows 11 agents already online — Agent Forge presumably defines the canonical 13 and would replace the current 11.
- Risk: MEDIUM — adds 2+ new agents to a topology already running. Could overlap with existing personas (REX, REXXIE, Victoria, Masha, Hermes Cloud, etc.) and confuse routing.
- Preconditions: Kato should review the 13-agent roster against the running 11 before activation.
- Recommendation: **WAIT** — needs Kato's persona-list decision first. Not urgent.

### PAE-T — TOTP rotation
- Why fenced: Current secret is the RFC example `JBSWY3DPEHPK3PXP` — publicly documented. Rotating without Kato updating his authenticator app first locks him out.
- Steps Kato should take to unblock:
  1. Open authenticator app, prepare to remove the current "Tiger Claw" entry.
  2. Confirm via Telegram that he's at his desk, not running GOJ ops.
  3. Then approve the rotation — Claude generates new secret, prints provisioning URI as QR-able, Kato scans, verifies new code works, removes the old entry.
- Recommendation: **PROCEED** the next time Kato is at his desk and not in the middle of GOJ ops. 5-minute job.

### PAE-R — Railway 18-page build
- Spec doc size: ~18KB / 357 lines (`CC_CLAUDE_RAILWAY_BUILD.md`)
- Pages covered: 18 (dashboard with knowledge graph, modules, clients, employees, schedule, billing, kitchen, transport, security, agents, bbg, design, tools, documents, og33, vault, voice, settings)
- Dependencies: PAE-4 (AKC tokenizer) is non-negotiable — `/og33`, `/voice`, `/documents` all touch PHI. Mac Mini Hub API bridge needs to exist. Existing 4,983-line `~/Desktop/REX/CC_railway_deploy/index.html` (v2 single-file) should be archived not extended.
- Estimated scope: Large — 18 routes, real-time WebSocket to Mac Mini, Three.js + Chart.js + D3 knowledge graph. Multi-week build.
- Decisions Kato needs to make (the 4 from GAP_ANALYSIS):
  1. **Master build or split** — one repo or 18 separate pages?
  2. **DropTop integration** — Tauri tray vs standalone Swift menu bar?
  3. **Antigravity integration** — MCP, API, or CLI bridge?
  4. **Change management workflow** — Telegram → fix → deploy → verify; and Railway preview branches for major changes?
- Recommendation: **WAIT** — biggest payoff but highest cost. Don't start until PAE-4 lands. Propose phased build (dashboard + modules + agents first; PHI-touching pages last) once tokenizer is live.

### PAE-A — Alienware 32GB integration
- Doc(s) read: `CC_alienware_integration_plan.md` (75 lines)
- Current state: Plan only — Tailscale mesh, Ollama on RTX 2070, role as "IRONWALL" security/GPU worker node. Pop!_OS Linux box, 32GB RAM, 8GB VRAM.
- Risk: LOW for steps 1–4 (install Tailscale, SSH, Ollama). MEDIUM for step 6 (point Hermes at it as a secondary inference endpoint — could cause routing surprises).
- Preconditions: Physical access to the Aurora, Tailscale auth key from admin console, ssh-copy-id from Mac Mini.
- Recommendation: **PROCEED** in stages — install + smoke test Ollama first, leave Hermes routing change for after. Independent of PAE-R timing.

### PAE-H — hermes-dreaming plugin install
- Doc(s) read: Supplemental section of `CC_CLAUDECODE_HANDOFF_june8.md`
- Current state: One command: `hermes plugins install asimons81/hermes-dreaming --enable` + gateway restart.
- Risk: LOW — declared "should be safe" by Hermes. Gateway restart is the only operational impact (~10s downtime).
- Recommendation: **PROCEED** alongside PAE-5. Same operational window.

### PAE-I — iMessage watcher build
- Doc(s) read: Section 6 of `CC_CLAUDE_AUDIT_OUTPUT.md`
- Current state: NOT YET BUILT. Architecture: iPad physically connected to Mac Mini, watcher reads through that iPad bridge. Monitors 3 GOJ group chats. Required for the 7-System Schedule Change Cascade to catch sick calls / day swaps that happen on iMessage.
- Risk: MEDIUM — touches iMessage internals which are fragile across macOS updates. Group chat names need Kato input.
- Preconditions: Kato names the 3 specific group chats and confirms the iPad is paired and accessible.
- Recommendation: **WAIT** — fence stays. Real GOJ feature value but needs Kato input + careful implementation. Not blocking anything else.

### PAE-D — Disclosure tier gate on Telegram bots
- Current state: Per supplemental notes, "any Telegram user currently gets sensitive data" from the bots. No tier check.
- Risk if executed: LOW for the gate itself (adds a check before bot replies). HIGH if NOT executed — this is a live data leak.
- Preconditions: Define the tier ladder (public / staff / chairman) and which Telegram user IDs sit at which tier.
- Recommendation: **PROCEED** — security-critical. Build the tier check, default everyone to "public" (no sensitive data), explicitly elevate Kato + named staff.

## Recommendation — what Kato should green-light first
1. **PAE-5** — Tiger Claw API verify + activate. Already serving 200s. Wire HUD consumers. ~30 min.
2. **PAE-D** — Disclosure tier gate. Closes an active data-leak surface. ~1–2 hr.
3. **PAE-H** — hermes-dreaming install. One command + restart. ~10 min.
4. **PAE-4** — AKC tokenizer wire-in. Gating prerequisite for Railway. ~2–3 hr.
5. **PAE-T** — TOTP rotation. Schedule for next desk-time window. ~5 min.

After those: PAE-A (Alienware staged install), then PAE-6 + PAE-8 (need Kato design input), then PAE-R (the big build), then PAE-I.

## Items I'd recommend killing (overtaken by other work)
- **PAE-7** — Not a real issue. Reframe as allowlist decision for one Signal user, or close as won't-fix.
