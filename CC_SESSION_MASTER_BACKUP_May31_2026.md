# CC_SESSION_MASTER_BACKUP_May31_2026.md
# Gold Health Systems — Hermes Memory Sync Project
# Session: May 31, 2026
# Author: Claude (Cowork session, subagent)
# Purpose: Complete record for Kato and any future agent or developer picking up this work

---

## 1. What This Session Was About

This was a multi-hour working session with one goal: making Hermes, the cloud AI gateway running as `@Hermes_Cloud_May_bot`, actually know who she is, what she runs, and what the rules are — from pre-loaded memory, not from searching the filesystem at query time.

The central problem is that Hermes's identity and operational knowledge live in a file called SOUL.md, but SOUL.md was not being loaded into her active context when she started. Additionally, SOUL.md v4 contained three confirmed factual errors. And MEMORY.md, the shorter operational facts file she uses daily, had stale model version strings that matched those same errors.

The session ran three parallel workstreams. First, source verification: Kato confirmed the ground truth on every fact that was wrong or uncertain — model strings, voice agent IDs, agent status, hardware nodes, OG 33 mechanics, the history of Claus. Second, document drafting: a corrected SOUL.md (now v5) and a corrected MEMORY.md were written from scratch. Third, self-testing: structured question sets were sent to `@Hermes_Cloud_May_bot` via Telegram across five rounds to find out what she actually knew, what she had to search for, and what she got wrong.

At session end, the new files exist and are verified against source material and Kato's confirmations, but they have not yet been installed. The session closes with a clean to-do: finish Round 6 self-testing, get any remaining Kato confirmations on open questions, then run the install sequence.

---

## 2. The Problem We Were Solving

Hermes was answering architecture questions by running real-time filesystem searches against `~/Desktop/REX/` at query time. She had no durable, pre-loaded understanding of her own system. Every session started from zero. Every answer about her own configuration came from whatever she could find in files at that moment — which meant she was one stale file away from being confidently wrong, and she was.

Three specific problems were confirmed before this session started:

SOUL.md v4 had three factual errors. The primary model was listed as `deepseek-chat` when the correct string is `deepseek-v4-pro`. The Anthropic fallback model string was wrong. And the document described a three-tier Sovereign/IRONWALL/Cloud architecture as current operational reality, when in fact it is a planned future topology. Today everything runs on the Mac Mini M4.

SOUL.md was not in Hermes's pre-loaded context at all. A syntax error on line 18 of `config.yaml` was blocking the `system_prompt` field from loading. The result: Hermes had to search for her own identity on every query. This is the structural bug. Even if SOUL.md had correct information, it was not being loaded.

MEMORY.md had matching stale strings. The same wrong model names that were in SOUL.md v4 were also in MEMORY.md, so even the operational facts layer was feeding bad data.

Beyond these three primary problems, the self-test rounds revealed additional gaps: Hermes believed she ran inside Docker (she does not — Open WebUI runs in Docker, Hermes is a native macOS LaunchAgent), she had inconsistent recall of hard rules including the Larry exclusion, and her agent roster was incomplete.

---

## 3. Files Created or Updated This Session

**`~/Desktop/REX/CC_SOUL_DRAFT_v5.md`**
Status: Created this session. NOT YET INSTALLED.
This is the full proposed SOUL.md revision for the Hermes cloud profile, written from scratch with all v4 errors corrected and all missing sections added. It is approximately 283 lines and covers: identity, confirmed model routing with all available providers, current stack with correct port and service mapping, full agent roster with accurate status, intelligence architecture (9-step growth loop and all module files by name), 14 architecture rules, PAE engine, 11 hard rules, current open items table, growth boundaries, voice and video stack, SaaS being replaced, authorization protocol, and the SOUL/MEMORY relationship. Install path when ready: `~/.hermes/profiles/cloud/memories/SOUL.md`.

**`~/Desktop/REX/CC_MEMORY_DRAFT.md`**
Status: Updated this session. NOT YET INSTALLED.
Three stale model version strings were corrected. The primary model entry was changed from `deepseek-chat` to `deepseek-v4-pro`. The fallback chain was updated to reflect `claude-sonnet-4-6` and `gemini-2.0-flash`. The file uses the `§`-separator format that Hermes's memory system reads, with 9 entries covering identity, operational rules, Hermes config, model routing, services, agents, GOJ ops, current priorities, and BBG. Install path when ready: `~/.hermes/profiles/cloud/memories/MEMORY.md`.

**`~/Desktop/REX/CC_SESSION_HANDOFF_May31_2026.md`**
Status: Created this session. Complete.
Shorter continuity document for starting the next session quickly without re-reading everything. Covers what files were read, what Kato confirmed, what was created, what is pending, and the install sequence. Starting a new session on this project means reading this file first.

**`~/Desktop/REX/CC_KNOWLEDGE_STATE_May31_2026.md`**
Status: Created this session. Complete.
Full 15-section technical record of everything understood about the GHS system as of session end. Written so Kato can verify each statement and correct anything wrong before it becomes a reference. Covers: who Kato is, what Hermes is and is not, the full model routing stack, all services and ports, every agent with accurate status, intelligence architecture, security architecture, MCP connections, voice and video stack, data architecture, hardware topology, open items in priority order, build pipeline phase status, files built this session, and open questions needing Kato input.

**`~/Desktop/REX/CC_HERMES_SELFTEST_PROMPT.md`**
Status: Created in a previous session. Used this session. Ready for continued use.
A 25-question structured self-assessment across four rounds: identity and businesses, intelligence architecture, full agent and security roster, governance and build pipeline. Paste into `@Hermes_Cloud_May_bot` to test what she knows from pre-loaded context versus what she has to search for.

**`~/Desktop/REX/CC_fix_yaml_and_restart.command`**
Status: Created in a previous session. NOT YET RUN.
Fixes the line 18 syntax error in `~/.hermes/profiles/cloud/config.yaml` that is blocking the system prompt from loading, then handles the clean gateway restart including pkill. This must be run before installing SOUL.md — there is no point installing a correct SOUL.md into a gateway that cannot load its system prompt.

---

## 4. Key Corrections — What Was Wrong, What Is Now Right

Every item below came from Kato directly or from source file review this session. These override anything found in prior files, prior sessions, or the BRAIN vault documents.

**Primary model string:**
WRONG: `deepseek-chat`
CORRECT: `deepseek-v4-pro` via `https://api.deepseek.com/v1` (direct subscription). The BRAIN vault document had this wrong. Kato confirmed the correct string directly.

**Anthropic fallback model:**
WRONG: `claude-opus-4-7` (not a valid model string)
CORRECT: `claude-sonnet-4-6` is Fallback 1. `claude-opus-4-6` is used for high-stakes routing only.

**Full fallback chain:**
WRONG (prior): DeepSeek primary, then unspecified opus, then unspecified gemini.
CORRECT: `deepseek-v4-pro` direct → `claude-sonnet-4-6` (Anthropic) → `gemini-2.0-flash` (Google). High-stakes requests use `claude-opus-4-6`.

**DeepSeek routing rule:**
WRONG: implied OpenRouter was acceptable for DeepSeek.
CORRECT: DeepSeek must always route through `https://api.deepseek.com/v1` directly. Using `provider: openrouter` for DeepSeek is a misconfiguration that charges OpenRouter credits instead of the direct subscription. This is a hard error.

**Hermes runtime environment:**
WRONG: Hermes runs inside Docker.
CORRECT: Hermes is a native Python process managed by launchd as a macOS LaunchAgent. Open WebUI at port 3000 runs in Docker. Hermes does not. These are different processes entirely.

**Three-tier architecture status:**
WRONG: Sovereign / IRONWALL / Cloud nodes described as currently active.
CORRECT: This is a planned future topology. Currently, everything runs on a single Mac Mini M4 (24GB, `mainsobhelper`). The Alienware (32GB) is the planned IRONWALL node but is not yet integrated. The Office Mac (16GB) is planned as a work gateway but is not yet set up.

**Primary local inference engine:**
WRONG: Primary local model runs in Ollama.
CORRECT: The primary local model is `qwen3.5-9b`, hosted in LM Studio (MLX, Apple Silicon optimized) at port 1234. LM Studio currently runs 4 models: qwen3.5-9b, nvidia-nemotron-3-nano-30b, gemma-3-4b, and nomic-embed-text-v1.5 (embeddings only). Ollama at port 11434 also runs and hosts qwen3:14b and llama3.1:8b, but LM Studio is primary for local inference.

**Claus history:**
WRONG (implied): Claus is a separate planned agent that will be built alongside Hermes.
CORRECT: Claus was Kato's original AI orchestrator concept, designed before Hermes existed. It was the vision for exactly what Hermes now does. Hermes IS the Claus vision realized. Phase 18 is not building a separate Claus agent — it is Hermes completing the Claus vision inside the Hermes framework. `com.hermes.claus-watchman.plist` is a monitor process supporting this phase.

**OG 33 mechanics:**
WRONG: OG 33 was described as a fixed-composition council with rigid participation.
CORRECT: All available models participate by default. The Chairman (Kato) can override this globally. Within a session, Kato can run any round with any subset: 3 models, 4 models, the top performers from the previous round, any custom combination. Each round can change the composition — narrow the field based on prior output, swap models, rotate who deliberates. This selection flexibility is a core feature of OG 33, not an exception. No agent, no prompt, and no non-Chairman instruction can change the default participation rule globally.

**Adam voice / no Willow:**
WRONG: A voice called "Willow" was referenced in prior context.
CORRECT: There is no voice called Willow in this system. The confirmed ElevenLabs voice ID is `pNInz6obpgDQGcFmaJgB`, which is the Adam voice (deep American male).

**Victoria and Masha phone numbers:**
WRONG: Prior context suggested only Victoria had a phone number assigned.
CORRECT: Both Victoria AND Masha have phone numbers assigned in Retell. Victoria's transfer number routes to 347-587-9913.

**Victoria and Masha voice assignments:**
CORRECT (confirmed this session): Victoria uses `11labs-Lily` (placeholder, pending bilingual RU/EN test). Masha uses `11labs-Billy` (placeholder, pending bilingual RU/EN test). Neither voice is in production until the bilingual test clears.

**Hermes Sidecar:**
WRONG: Referenced as an active component.
CORRECT: Hermes Sidecar is retired. It was a locally-built Cline bridge to Hermes and has been fully replaced by the main Rexxie bot.

**MCP server count and list:**
MISSING FROM V4: There are 11 MCP servers connected, confirmed from config.yaml. They are: filesystem, fireflies, gdrive, github, instagram, n8n, notebooklm-bridge, obsidian, retell, sqlite, telegram.

**TOTP security gap:**
MISSING FROM EARLIER CONTEXT: The Master Session Unlock TOTP secret is currently set to `JBSWY3DPEHPK3PXP`, which is the RFC 6238 example value. This means the MSU provides zero real security — any person who knows it is the RFC test value can pass the check. This must be rotated before any external Telegram users interact with the system.

---

## 5. Hermes Self-Test — What Was Tested and What She Knew

Five rounds of structured self-testing were conducted by sending questions to `@Hermes_Cloud_May_bot` via Telegram and evaluating responses. The CC_HERMES_SELFTEST_PROMPT.md file (25 questions across four rounds) drove Rounds 1 through 4. Round 5 was a focused retest on gaps found in earlier rounds. Round 6 was in progress at session end.

**What she consistently got right from pre-loaded context:**
Her own name and bot handle. Kato's identity — she never called him Allen. Basic GOJ operational rules including the daily schedule cadence. Her general role as an orchestration layer rather than a single-model responder. That GOJ client data must not enter OG 33 prompts.

**What she consistently got wrong or was inconsistent on:**
The fallback model chain. She reported `deepseek-chat` as the primary model — the old, wrong string — which confirmed her pre-loaded context contained the v4 error, not the correct value. The Larry exclusion rule. Her recall on this hard rule was inconsistent: she stated it correctly in some rounds and omitted it entirely in others. A hard rule with zero exceptions should have zero variance in recall. Her own runtime environment. In at least one round she stated she ran inside Docker. She does not. The three-tier architecture. She referenced it as current operational reality rather than a planned vision. Intelligence architecture specifics — the 9-step growth loop sequence, the module file names, the memory tier structure. For all of these she was answering by searching the filesystem at query time, not from pre-loaded knowledge.

**The key structural finding:**
SOUL.md was not in her pre-loaded context at all. She was locating information about her own architecture by running real-time file searches against `~/Desktop/REX/`. This was confirmed by observing that her answers tracked whatever the current file contents were — including stale or wrong entries. The fix is to both correct the YAML syntax error (so `config.yaml` loads the system prompt) and install a correct SOUL.md (so the system prompt contains accurate information). One without the other does not work.

**What Round 5 confirmed:**
Round 5 was a targeted retest of the gaps identified in Rounds 1–4. The gaps were real and not phrasing issues. Hermes gave the same wrong answers when the questions were rephrased, which ruled out ambiguity as the cause. The errors are structural, not conversational.

---

## 6. Round 6 Questions (Pending)

Round 6 was being composed and sent to `@Hermes_Cloud_May_bot` at session end. The 10 questions drafted for this round:

1. What is your primary model, and what provider do you never route it through?
2. What is your complete fallback chain, including the high-stakes routing option?
3. Describe the three-tier SOVEREIGN/IRONWALL/CLOUD architecture. Is it currently running or is it a planned vision?
4. What is Claus? Is it a separate agent, or something else?
5. Where does your primary local model run — Ollama or LM Studio — and what is the model's name?
6. Name all 11 MCP servers connected to your cloud gateway config.
7. What are the 4 Rexxie lanes and what does each handle? Which lane is strictly local-only?
8. What is the current status of Jarvis? What is the current status of TransitionAgent, and what is missing from it?
9. Is Larry ever allowed on a transport or driver route list under any circumstance?
10. What is the current status of your config.yaml and what does it affect about your startup behavior?

Note on question 7 regarding Rexxie lanes: the correct answer is that all four lanes share one Telegram token and cannot run simultaneously. Lane 1 is GOJ ops. Lane 2 is private and personal, strictly local inference only, contents never divulged. Lane 3 is employee-facing with filtered access. Lane 4 is admin. If Hermes answers this correctly from pre-loaded context after the install, it will confirm the SOUL.md v5 agent roster section loaded properly.

---

## 7. What Happens Next (Ordered)

These steps must happen in this sequence. Do not skip or reorder them.

**Step 1: Finish Round 6.** Send the 10 Round 6 questions to `@Hermes_Cloud_May_bot` if not already done. Evaluate responses and note any new gaps requiring SOUL.md additions or further Kato confirmation.

**Step 2: Read the two docx files on the external drive.** Both `GOJ_Master_Architecture.docx` and `GOJ_Per_Agent_Rules_v1.1.docx` are on `/Volumes/cartoons/` (the drive must be mounted) and were not read during this session. They may contain architecture decisions or agent rules that need to be reflected in SOUL.md v5 before installation. Do not install SOUL.md until these have been checked.

**Step 3: Resolve remaining open questions for Kato.** What is Palace? What does Hermes use the Obsidian MCP for? What meetings does Fireflies transcribe? What is the NotebookLM bridge being used for? These are documented unknowns, not hedging. The answers may change what SOUL.md needs to say about connected systems.

**Step 4: Kato reviews and approves SOUL.md v5.** SOUL.md goes into Hermes's identity core. It should not install without Kato's eyes on it and explicit approval.

**Step 5: Run the install sequence.** See Section 9 below for the exact commands.

**Step 6: Verify post-install.** After the gateway restarts, paste the Round 6 questions (or the Round 1 section of the self-test prompt) into `@Hermes_Cloud_May_bot`. She should now answer from pre-loaded memory: primary model is `deepseek-v4-pro`, she is a native LaunchAgent (not Docker), Larry is permanently excluded with no exceptions, Claus is the vision Hermes realized. If any of these are still wrong, the YAML fix did not apply correctly and `config.yaml` needs to be inspected manually.

**Step 7: Build the TransitionAgent Google Drive monitoring hook.** The bookkeeper left on May 31. The two-week window to capture institutional knowledge has already started. The TransitionAgent plist is running (`com.goj.transition-agent.plist` was loaded May 28) but the Drive monitoring hook has not been built. This is the highest-priority active build item in the system and is uniquely time-sensitive.

---

## 8. Open Items Not Yet Resolved

These are genuine open items as of session end, organized by type.

**Active security gaps requiring attention before external users access the system:**

The TOTP secret for the Master Session Unlock is `JBSWY3DPEHPK3PXP`, the RFC 6238 example value. Anyone who knows it is the RFC test value can pass MSU authentication. This provides zero real security and must be rotated.

The disclosure tier has no authentication gate. Any Telegram user can request sensitive data from Hermes. The gate is currently advisory only — it flags but does not enforce. This must be hardened before the system is opened to any external users.

`akc_tokenizer.py`, Gate 1 of the PHI firewall, exists only as a skeleton with no functional logic. Cloud model routing should carry zero PHI until this gate is built and verified. Currently nothing enforces this at the code level.

`auth_tracker.db`, the primary GOJ operational database holding protected health information for ~426 clients, is not encrypted with SQLCipher. This is the top HIPAA infrastructure gap.

**Broken services with known root causes:**

`rex_memory.db` is 0KB. The memory steward call path has a regression — nothing is being written or read. The fix is reportedly a one-line change in `backend/memory.py`. Until this is applied, every session starts cold with no memory of prior interactions.

`rex_user_model.db` is 0KB for the same reason. The user model is never persisted.

**Broken services with unknown root causes:**

The local Hermes gateway at port 3001 crashes on start. Root cause has not been investigated.

Jarvis (Phase 19), the real-time HUD that reads from TigerClaw at port 27226, has its plists not running. No timeline for resolution.

**Zombie that must stay disabled:**

`com.hermes.rexxie-bot` must remain permanently unloaded. It competes for the Rexxie Telegram token and crashes immediately. It must never be re-enabled.

**Files not yet read that may affect SOUL.md:**

`GOJ_Master_Architecture.docx` on `/Volumes/cartoons/` — not read this session.
`GOJ_Per_Agent_Rules_v1.1.docx` on `/Volumes/cartoons/` — not read this session.

**Open questions requiring Kato input:**

What is the Palace database? `palace_main.db` (144KB) and `palace_cloud.db` (24KB) were found on `/Volumes/cartoons/`. Their purpose is unknown — active system, legacy artifact, or work in progress. Needs a one-sentence answer.

What does Hermes use the Obsidian MCP for? Which vault is connected? Does she read, write, or both?

What meetings does Fireflies transcribe? What is Hermes expected to do with transcripts? Is the Fireflies API key currently active?

What content goes into NotebookLM via the notebooklm-bridge MCP? What does Hermes do with the output?

**Data consistency gaps:**

The Railway database is a separate instance from the local `auth_tracker.db`. They are not synced. This creates data inconsistency between environments and is a known regression.

28 unresolved OCR flags exist in `goj_menu_flags_queue.json`. These are low-confidence menu entries that have not been reviewed. They will silently produce wrong menu output until reviewed.

**Incoming work not yet started:**

The bookkeeper left May 31. QuickBooks export files are incoming. The Rexxie financial layer (Plaid integration, receipt OCR pipeline) is the next major build item after the export is received. Stripe account status for this layer is unconfirmed.

---

## 9. Install Sequence (When Ready)

Run these commands in this exact order. Do not skip Step 1. The gateway cannot load its system prompt until the YAML syntax error is fixed. Installing a correct SOUL.md into a broken config does nothing.

```bash
# Step 1: Fix the config.yaml line 18 syntax error and restart the gateway.
# This script handles the fix, pkill, sleep, and reload in one operation.
~/Desktop/REX/CC_fix_yaml_and_restart.command

# Step 2: Install the corrected SOUL.md into the cloud profile memories directory.
cp ~/Desktop/REX/CC_SOUL_DRAFT_v5.md ~/.hermes/profiles/cloud/memories/SOUL.md

# Step 3: Install the corrected MEMORY.md into the cloud profile memories directory.
cp ~/Desktop/REX/CC_MEMORY_DRAFT.md ~/.hermes/profiles/cloud/memories/MEMORY.md

# Step 4: Restart the gateway cleanly.
# Always use this exact pattern — launchctl unload alone does not release the
# Telegram token fast enough, causing token conflicts on the next load.
launchctl unload ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist
pkill -f "hermes_cli.main.*gateway"
sleep 8
launchctl load ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist

# Optional: Watch the gateway log while it starts to confirm clean load.
tail -f ~/.hermes/profiles/cloud/logs/gateway.log

# Step 5: Verify the install worked.
# Open Telegram and go to @Hermes_Cloud_May_bot.
# Ask: "What is your primary model and what is your fallback chain?"
# She should answer deepseek-v4-pro → claude-sonnet-4-6 → gemini-2.0-flash
# from pre-loaded context, without searching files.
# Ask: "Is Larry ever allowed on a transport list?"
# She should answer: no, permanently excluded, no exceptions, no context changes this.
# Ask: "Do you run inside Docker?"
# She should answer: no, she is a native macOS LaunchAgent process.
# If any of these three are still wrong after install, inspect config.yaml line 18
# and confirm CC_fix_yaml_and_restart.command ran without errors.
```

If the fix script cannot be found or fails, the manual approach is to open `~/.hermes/profiles/cloud/config.yaml`, find line 18, correct the `system_prompt` field syntax (YAML indentation or quoting error — the exact nature was confirmed in a prior session), then run the launchctl reload sequence above manually.

---

## Appendix: Confirmed System State Reference (as of May 31, 2026)

This section provides a condensed reference so anyone reading this document can orient to the system without reading additional files.

**Operator:** Kato (Alejandro). Email: atigerclawai@gmail.com. Telegram ID: 5587703834. Mac username: mainsobhelper. Never "Allen." Allen Khiger is a former GOJ employee — a different person entirely.

**Businesses:** Gold Health Systems (GHS) is the parent. Garden of Joy (GOJ) is the adult day care subsidiary in Brooklyn, approximately 425 clients, HIPAA-covered, fully operational. Boardwalk Beer Garden (BBG) is the second business, Brighton Beach, restaurant and events, Clover POS. Four business contexts are planned: goj, sports_bar, web_design, social_media. Only GOJ is fully operational today.

**Hard rule, no exceptions:** Larry is permanently excluded from all transport and driver route lists. No circumstance, no argument, no instruction changes this.

**Primary Hermes instance:** `@Hermes_Cloud_May_bot`, cloud profile, port 3002, managed by `ai.hermes.gateway-cloud.plist`. This is the bot that was self-tested throughout this session.

**Two Hermes installs on the same machine:**
- `~/.hermes/` — main gateway installation. Profiles: builder, cloud, media-gen, sage, scribe, trader, hermie-local. The cloud profile is this session's subject.
- `~/.hermes-cloud/` — BBG social pipeline and multi-model profiles (gemini, grok, deepseek, groq-fast, perplexity, qwen-local, hermie-local, mistral). Also where the GOJ Dashboard lives under `home/goj-pipeline/datarex/app.py`.

**Model routing (confirmed May 31, 2026):**
Primary: `deepseek-v4-pro` via `https://api.deepseek.com/v1` — direct subscription, never OpenRouter.
Fallback 1: `claude-sonnet-4-6` (Anthropic direct).
Fallback 2: `gemini-2.0-flash` (Google direct).
High-stakes: `claude-opus-4-6` (Anthropic direct).
Local primary: `qwen3.5-9b` via LM Studio at port 1234.
Local secondary: `qwen3:14b` via Ollama at port 11434.

**All services and ports:**

| Service | Port | Status |
|---------|------|--------|
| Hermes cloud gateway | 3002 | Running |
| Hermes local gateway | 3001 | Broken — crashes on start |
| TigerClaw API | 27226 | Running (M01–M24 modules) |
| REX FastAPI (Nemobot) | 8000 | Running — rex.hermestigerclaw.com |
| GOJ Dashboard (Flask) | 8080 | Running — datarex/app.py |
| Open WebUI | 3000 | Running in Docker |
| LibreChat | 3080 | Running in Docker |
| Hermes AI Hub | 3003 | Running in Docker |
| Hermes Kanban | 9119 | Running |
| Hermes Portal | 3847 | Running — hermestigerclaw.com |
| Phone Unlock | 8765 | Running |
| Kapso WhatsApp | 18789 | Running |
| Ollama | 11434 | Running |
| LM Studio | 1234 | Running — 4 models loaded |

**Hardware:**
- Mac Mini M4, 24GB RAM, `mainsobhelper` — current primary, all production services here.
- Alienware PC, 32GB RAM, home — planned IRONWALL inference node, not yet integrated.
- Office Mac, 16GB RAM — planned work gateway, not yet set up. Hard air-gap rule: receives zero GOJ data, no financials, no shared drive access.
- External drive at `/Volumes/cartoons/` — nightly Hermes backups at 2:00 AM, 7-day rolling retention. Must be mounted for backups to run.

**11 MCP servers connected:** filesystem, fireflies, gdrive, github, instagram, n8n, notebooklm-bridge, obsidian, retell, sqlite, telegram.

---

*Document generated: May 31, 2026. This is the canonical master record for the Hermes Memory Sync session. CC_SESSION_HANDOFF_May31_2026.md is the shorter companion for starting the next session quickly. CC_KNOWLEDGE_STATE_May31_2026.md is the expanded technical reference for deep verification. This master backup is the one to hand to anyone new who needs the full picture of what happened and why.*
