# CC_KNOWLEDGE_STATE_May31_2026.md
**What Was Understood — Full Brain Dump**
Generated: May 31, 2026
Author: Claude (Cowork session)
Purpose: Kato reads this to verify nothing was misunderstood. Not a handoff doc. Not marketing. A technical record.

---

## 1. Who Kato Is and What GHS Is

Kato's full name is Alejandro. He is the operator of Gold Health Systems. His Mac username is `mainsobhelper`. His email is `atigerclawai@gmail.com`. His Telegram user ID is `5587703834`. He must never be called Allen. Allen Khiger is a former GOJ employee — a completely different person. The confusion would be wrong and should never happen.

Gold Health Systems (GHS) is the parent company. Garden of Joy (GOJ) is a subsidiary — an adult day care facility in Brooklyn, NY serving approximately 425 clients. GOJ is HIPAA-covered. All GOJ data is protected health information.

Boardwalk Beer Garden (BBG) is a second GHS business — a restaurant and events venue in Brighton Beach. It uses Clover POS. It is distinct from GOJ in data handling, staffing, and operational context.

Four business contexts are planned for the system: `goj`, `sports_bar`, `web_design`, and `social_media`. Only GOJ is fully operational today.

Vlad is a business partner. He is granted a delegated financial view — not full system access.

Larry is permanently excluded from all transport and driver route lists. This is a hard rule with no exceptions, no overrides, and no circumstance under which it changes.

---

## 2. What Hermes Is (and What She Isn't)

Hermes is a Python AI gateway, version 0.15.1, running as a macOS LaunchAgent on the Mac Mini M4 (24GB RAM, `mainsobhelper`). It is not a Docker container. Hermes itself is a native process managed by launchd.

The primary Hermes bot facing Kato is `@Hermes_Cloud_May_bot`, running on the cloud profile at port 3002, managed by `ai.hermes.gateway-cloud.plist`.

There are two distinct Hermes installations on the machine. The first is `~/.hermes/`, which is the main gateway installation containing profiles: `cloud`, `builder`, `sage`, `scribe`, `trader`, and `hermie-local`. The second is `~/.hermes-cloud/`, which contains the BBG social pipeline and multi-model profiles. These are separate directory trees. The GOJ Dashboard lives under `~/.hermes-cloud/home/goj-pipeline/datarex/app.py` — not under `~/.hermes/`.

Hermes is the realized form of Kato's original "Claus" concept. Claus was an AI system Kato designed before Hermes existed. Hermes is what Claus became. Phase 18 of the build plan is completing that Claus vision inside Hermes.

SOUL.md exists in at least 7 locations across the filesystem. The canonical cloud profile SOUL.md is at `~/.hermes/profiles/cloud/memories/SOUL.md`.

Hermes's pre-loaded context (what she knows before any file search) contains basic identity and some behavioral rules. It does not contain the full intelligence architecture, the fallback model chain, or system-level hard rules. During the self-test session, Hermes was actively searching `~/Desktop/REX/` in real time to answer architecture questions — she was not recalling these from pre-loaded memory.

Open WebUI (port 3000) does run in Docker. That is the Docker container. Hermes is not it.

---

## 3. The Full Model Routing Stack

The primary model is `deepseek-v4-pro`, routed directly to `https://api.deepseek.com/v1`. This is a direct API connection using Kato's DeepSeek subscription, confirmed on May 31. OpenRouter must never be used for DeepSeek — doing so routes through OpenRouter's credits rather than the direct subscription and would be an error.

Fallback 1 is `claude-sonnet-4-6` via Anthropic directly.
Fallback 2 is `gemini-2.0-flash` via Google directly.
High-stakes routing uses `claude-opus-4-6` via Anthropic.

All providers currently available to the system: DeepSeek (direct), Anthropic, Google, xAI (models: `grok-4.3`, `grok-4.20-reasoning`, `grok-3-mini`), Perplexity (`sonar-pro`), OpenAI (`gpt-4o`, `gpt-4o-mini`, `o1`, `o3-mini`), Mistral (`mistral-large`), Groq (`qwen3-32b`, `llama-3.3-70b`). OpenRouter is available as a router for other providers, but explicitly not for DeepSeek.

Local inference runs on two engines. Ollama at port 11434 with `qwen3:14b` as default and `llama3.1:8b` available. LM Studio at port 1234 with `qwen3.5-9b` as the primary local MLX model; also available: `nvidia-nemotron-3-nano-30b`, `gemma-3-4b`, and `nomic-embed-text-v1.5` for embeddings.

API keys confirmed present in `.env`: DeepSeek, Anthropic, OpenRouter. Other keys are likely stored in macOS Keychain or system environment — their presence in `.env` is unconfirmed.

OG 33 is the multi-model deliberation council. All 33 models participate by default. The Chairman can override this globally or per session. GOJ client data never enters OG 33 prompts — this is a hard rule.

---

## 4. Full Stack — All Services and Ports

**Hermes cloud gateway** — port 3002, LaunchAgent `ai.hermes.gateway-cloud.plist`. Currently running.

**Hermes local gateway** — port 3001, LaunchAgent `ai.hermes.gateway.plist`. Currently broken — crashes on start. Root cause is not yet identified.

**TigerClaw API** — port 27226. Houses modules M01 through M24 within a 34-module framework. This is the daily operations backbone — attendance, menus, routes, billing, scheduling. Currently running.

**REX FastAPI (Nemobot)** — port 8000, public URL `rex.hermestigerclaw.com`. LiteLLM router to all cloud and local models.

**GOJ Dashboard (Flask / DataRex)** — port 8080. LIVE application at `~/.hermes-cloud/home/goj-pipeline/datarex/app.py`. Restarted via `com.goj.datarex.plist`. There is a second, separate dashboard app at `~/Documents/goj files/dashboard/app.py` — it is NOT running and NOT the live system. These two are entirely separate codebases and must never be confused.

**Open WebUI** — port 3000, `ui.hermestigerclaw.com`. Runs in Docker.

**LibreChat** — port 3080, `chat.hermestigerclaw.com`. Runs in Docker.

**Hermes AI Hub** — port 3003, `workspace.hermestigerclaw.com`. Runs in Docker.

**Hermes Kanban** — port 9119.

**Hermes Portal / Landing page** — port 3847, `hermestigerclaw.com`.

**Phone Unlock** — port 8765.

**Kapso WhatsApp** — port 18789.

**Ollama** — port 11434.

**LM Studio** — port 1234.

**Cloudflare tunnel** — manages `*.hermestigerclaw.com` and `goldhealthsys.com`.

---

## 5. All Agents — What They Are and Their Real Status

**Nemobot** is REX FastAPI at port 8000. It is a LiteLLM router that dispatches to all cloud and local models. It is running.

**Rexxie** is Kato's personal-facing and GOJ-facing bot, `@goldhealth_rexxie_bot`. She operates with one Telegram token across four conceptual lanes that cannot run simultaneously: Lane 1 is GOJ ops, Lane 2 is private/personal (local inference only — never cloud, never divulges contents), Lane 3 is employee-facing, Lane 4 is admin. She is running. The zombie plist `com.hermes.rexxie-bot` must remain disabled — it competes for her token and crashes immediately.

**Claus (Phase 18)** is not a separate agent but the name of a vision. Hermes is Claus realized. `com.hermes.claus-watchman.plist` is a monitor process associated with this phase.

**Jarvis (Phase 19)** is a planned real-time HUD that reads from TigerClaw at port 27226. Its plists exist but are not currently running. Getting Jarvis running is a critical open item.

**TransitionAgent** is the highest-priority active build item. Its plist (`com.goj.transition-agent.plist`) was loaded on May 28 and is running. However, the Google Drive monitoring hook has not been built. The urgency is real: the bookkeeper left today, May 31, creating a two-week window before institutional knowledge is lost. The Google Drive hook must be built immediately.

**Victoria (Viktoriya)** is a Retell AI voice agent handling GOJ M12 appointment confirmation calls. Her voice is 11labs-Lily (placeholder, pending bilingual test). She has a phone number assigned. Transfers route to 347-587-9913.

**Masha** is a Retell AI voice agent with a BBG persona. Her voice is 11labs-Billy (placeholder, pending bilingual test). She also has a phone number assigned.

**OG 33** is the multi-model deliberation council. It is both dashboard-integrated and available as a standalone portal. GOJ data never enters its prompts.

**Red Team** (`rex_red_team.py`) is an adversarial probe runner. It runs a 60% random sample of probes and reports results to Rexxie via Telegram.

**Blue Team** (`rex_blue_team.py`) audits Red Team output against a 40+ attack taxonomy. It auto-generates new probes and is self-evolving.

**CLS v3** (Continuous Learning System, Phase 9) has two tiers. Tier A performs automatic pattern learning with no writes to stable memory. Tier B handles informational learning requiring Chairman approval before persistence. Both tiers are disabled when `GAUNTLET_ENV` is active.

**Hermes Sidecar** is retired. It was a locally-built Cline bridge to Hermes. It has been replaced by the main Rexxie bot and should not be referenced as active.

**WebRex (Phase 17)** is a planned web and IT operations agent. It has not been built.

---

## 6. Intelligence Architecture (The Growth Loop)

The full growth loop has 9 steps:

1. Signal detection — incoming message is classified
2. Memory retrieval — relevant stored context is pulled
3. User model build — session profile is assembled
4. Policy check — request is validated against permissions and rules
5. Plan — response strategy is determined
6. Respond — output is generated
7. Log exchange — conversation turn is recorded
8. Update user model — new information is persisted
9. Periodic reflection — meta-analysis runs every 20 exchanges

**Key modules:**

`rex_planner.py` is the Planner. It handles 19 IntentTypes through a pipeline: Classify → Plan → Validate → Enrich → Route → Audit.

`rex_user_model.py` manages the UserModel with 4 memory tiers: Session (wiped at session end), Short-term (21-day window), Long-term (stable facts), and Reflection (meta-patterns). Tracks 8 categories of information per user.

`rex_reflection.py` is the Reflection Engine. It monitors 5 growth signals and runs every 20 exchanges, writing findings to Tier 4 memory.

`rex_human_behavior.py` strips AI-typical filler phrases from all Rexxie responses before delivery.

The Policy Enforcer currently running in production is `rex_policy_enforcer.py` — a single-layer enforcer. `rex_unified_enforcer.py` is a planned 2-layer replacement (858 lines, Phase 16) that has not been activated.

`rex_coordinator.py` is the Build Coordinator. It reads `master_list.json` and uses fuzzy matching to connect incoming ideas to existing components.

The Contamination Scanner, Regression Auditor, and Forward Impact Auditor are not code modules. They are prompt-based, human-in-the-loop AI-assisted audit processes. Their prompts live in `local_only_terminal_prompts_handbook.md`.

---

## 7. Security Architecture

HIPAA de-identification uses the Presidio library on all outbound data.

Message encryption uses AES-256-GCM for Rexxie messages. The vault uses SQLCipher via `rex_sqlcipher_vault.py` with ChaCha20 streaming for large blobs.

Master keys are stored in macOS Keychain under identifiers `rex-sovereign` and `rexxie-2fa-secret`.

The Master Session Unlock (MSU) accepts CHAIRMAN codes and 1234 codes. It uses HMAC-SHA256. **The TOTP secret is currently set to the RFC example value `JBSWY3DPEHPK3PXP`.** This means the MSU provides zero real security until that secret is rotated. This is a known open issue.

RBAC is implemented in `rex_permissions.py` with four tiers: chairman, admin, staff, restricted.

The PHI firewall has 5 layers: tokenizer (Gate 1), classifier, context strip, output scan, and audit log.

`akc_tokenizer.py` is Gate 1 of that firewall. It currently exists only as a skeleton and must be fully built before any PHI-containing requests are routed to cloud models.

`auth_tracker.db`, the primary operational database, is not yet encrypted with SQLCipher. This is the top HIPAA compliance gap.

The disclosure tier currently has no authentication gate. Any Telegram user can request sensitive data. This is a known security gap.

`rexxie.db` is completely isolated from the GOJ operational database. No client data can leak into it. This isolation is intentional and correct.

---

## 8. MCPs Connected (11 Active)

The 11 MCPs currently connected are: `filesystem`, `fireflies`, `gdrive`, `github`, `instagram`, `n8n`, `notebooklm-bridge`, `obsidian`, `retell`, `sqlite`, `telegram`.

Fireflies requires a key that may not be confirmed as active. Its use case is unknown and needs Kato input.

---

## 9. Voice and Video Stack

**Retell AI** hosts two active voice agents. Victoria uses voice `11labs-Lily` (placeholder). Masha uses voice `11labs-Billy` (placeholder). Both are pending a Russian/English bilingual test before going to production use.

**ElevenLabs** — the voice ID confirmed in config is `pNInz6obpgDQGcFmaJgB`, which is the Adam voice (deep American male). There is no voice called "Willow" in this system. The ElevenLabs API key status is unconfirmed — likely in Keychain.

The default TTS fallback is Microsoft Edge, which is free.

**Video stack** includes: ComfyUI/Flux Dev (a `COMFY_CLOUD_API_KEY` is confirmed in `.env`), Seedance (ByteDance), Manim for programmatic animation, a Kanban Video Orchestrator, and ASCII video output. The primary use case for video generation is the BBG social media content pipeline.

**n8n** is a live workflow automation platform with an MCP connected. It handles M11 Telegram delivery workflows.

---

## 10. Data Architecture

The primary operational database is `~/Documents/goj files/dashboard/auth_tracker.db`. It is SQLite. It is not encrypted. All GOJ operational data lives here.

`~/Desktop/REX/rexxie.db` (164KB) is Rexxie's personal memory database. It is completely isolated from GOJ data — no client records, no PHI.

`~/Desktop/REX/rexxie_memory.db` (60KB) is a distinct database from `rexxie.db`. Its specific role differs from the personal store.

`rex_memory.db` is 0KB and broken. The memory steward call path has a regression — memory is not being written or read.

`rex_user_model.db` is 0KB and broken. The user model is never being persisted. This is a one-line fix in `backend/memory.py` but it has not been applied.

`palace_main.db` (144KB) and `palace_cloud.db` (24KB) were found on the external drive. Their purpose has not yet been documented and needs Kato input.

The Railway database is a separate instance from the local `auth_tracker.db`. They are not synced. This is a known regression.

**Dashboard table inventory:**
- `clients` — approximately 426 rows, primary key `id`
- `authorization` — status values: ACTIVE, EXPIRED, PENDING RENEWAL. `service_end_date` is the expiry field.
- `menus` — PDF registry with columns: `filename`, `path`, `date`, `week_start`. The `week_start` column was patched via SQL in April 2026 (previously nullable, causing bugs).
- `client_menus` — 1,661+ rows. Per-client, per-day menu selections. Column is `main` (not `main_dish`). Stores OCR confidence scores.
- `employees` — 15 staff rows with medical and in-service compliance tracking
- `pending_schedule_changes` — schedule modifications awaiting confirmation

---

## 11. Hardware and Planned Topology

The Mac Mini M4 with 24GB RAM, username `mainsobhelper`, is the current primary machine. All production services run here.

The Alienware PC (32GB RAM, home) is the planned primary inference workhorse. It is designated the IRONWALL node. It is not yet integrated.

The Office Mac (16GB) is planned as a work gateway for clock-in/out and local work functions. It is not yet set up. When it is set up, it must receive zero GOJ data, no financials, and no shared drive access. This is a hard air-gap rule.

The external drive is mounted at `/Volumes/cartoons/`. It is the target for nightly Hermes backups — 2:00 AM, 7-day rolling retention.

---

## 12. Current Critical Open Items (In Priority Order)

1. **config.yaml line 18 syntax error** — the `system_prompt` field is not loading due to a YAML syntax error. `CC_fix_yaml_and_restart.command` exists and is ready to run. This is blocking Hermes from loading her full identity context.

2. **TransitionAgent Google Drive monitoring hook not built** — the bookkeeper left today (May 31). The two-week window to capture institutional knowledge before it's gone has started. The hook must be built now.

3. **rex_memory.db + rex_user_model.db both 0KB** — Rexxie has no persistent memory and no user model being written. Every session starts cold. This is a one-line fix in `backend/memory.py` that has not been applied.

4. **Disclosure tier has no auth gate** — any Telegram user can request sensitive data. This must be gated before any external users interact with the system.

5. **TOTP secret is the RFC example value** — MSU authentication provides zero real security in its current state. The secret must be rotated.

6. **Jarvis (Phase 19) plists not running** — the real-time HUD is not active.

7. **akc_tokenizer.py Gate 1 is skeleton only** — the PHI firewall's first gate is not functional. Cloud routing should not carry PHI until this is built.

8. **Zombie plist com.hermes.rexxie-bot must stay disabled** — it is currently disabled. It must never be re-enabled. It competes for Rexxie's token.

9. **Local gateway port 3001 crashes on start** — root cause not yet investigated.

10. **auth_tracker.db not SQLCipher encrypted** — top HIPAA infrastructure gap.

11. **Railway DB not synced to local** — creates data inconsistency between environments.

12. **28 unresolved OCR flags in goj_menu_flags_queue.json** — low-confidence menu entries that have not been reviewed or corrected.

---

## 13. Build Pipeline — What's Locked vs. Pending

Phases 1 through 13 are locked. This is the foundation through CommandCenter UI. Nothing in this range should be reopened or refactored without an explicit reason.

Phase 14 is MultiContext_Ventures — implementing the 4 business contexts (GOJ, sports_bar, web_design, social_media).

Phase 15 is AgentForge.

Phase 16 is Claus/Manager-General completion — includes activating `rex_unified_enforcer.py`.

Phase 17 is WebRex_Topology.

The Phase 13-V verification sprint must complete before any Packet B work (Phase 14 and beyond) begins. No Packet B work starts until 13-V is cleared.

The QuickBooks export is coming from the bookkeeper who left today. The Rexxie financial layer (Plaid integration + receipt OCR) is the next major build item once the export is received.

---

## 14. Files Built or Modified This Session

**CC_SOUL_DRAFT_v5.md** was created this session — 283 lines. It is a proposed SOUL.md revision for the cloud profile. It has not been installed. It sits in the working directory awaiting Kato's review and approval before any installation step.

**CC_MEMORY_DRAFT.md** was updated this session — 3 stale model version strings were corrected to reflect current model names.

**CC_SESSION_HANDOFF_May31_2026.md** was created this session as the session continuation companion document.

**CC_HERMES_SELFTEST_PROMPT.md** was created in a previous session. It is ready for use as a structured self-test prompt for Hermes.

**CC_fix_yaml_and_restart.command** was created in a previous session. It is ready to run and will fix the line 18 YAML syntax error and restart the cloud gateway.

---

## 15. What's Still Unknown / Needs Kato Input

**Obsidian MCP** — which vault is connected, and what does Hermes do with it? Is this personal notes, project documentation, or operational reference material?

**Fireflies** — what meetings are being transcribed? What is the intended use case? Is the API key active?

**NotebookLM bridge** — what content is being fed into it? What is Hermes expected to do with NotebookLM output?

**Palace database** — `palace_main.db` and `palace_cloud.db` were found on the external drive. What is Palace? Is it an active system or a legacy artifact?

**GOJ_Master_Architecture.docx and GOJ_Per_Agent_Rules_v1.1.docx** — both files exist on the external drive. They have not been read in this session. They may contain architecture decisions or agent rules that conflict with or extend what is documented here.

**Full paid subscription list** — the confirmed subscriptions are DeepSeek (direct), Anthropic, OpenRouter, ElevenLabs (unconfirmed key), Retell, ComfyUI Cloud. The complete list beyond these is not documented.

**Stripe account status** — required for the Rexxie financial layer. Not confirmed as set up.

**Alienware integration timeline** — when is it expected to come online, and which services will migrate to it?

---

*This document reflects what was understood as of the end of the May 31, 2026 Cowork session. Items marked as unknown or needing input are genuinely open — they are not hedging, they are actual gaps. Kato should correct any statement here that is wrong before using this as a reference.*
