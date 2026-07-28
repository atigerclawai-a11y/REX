# Session Handoff — May 31, 2026

**Purpose:** Full continuity document for the next Claude/AI session. Read this before touching any Hermes, SOUL.md, or MEMORY.md work.

---

## 1. What We Started With

- **SOUL.md was at v4** with 3 confirmed factual errors:
  - Wrong model strings (deepseek-chat instead of deepseek-v4-pro; wrong Anthropic fallback)
  - Three-tier architecture presented as current reality (it isn't — Hermes IS the Claus vision realized; no separate tiers)
- **Missing from v4:** full agent roster, intelligence architecture, 14 rules, OG 33 mechanics, voice/video stack, hardware nodes, Claus history
- **MEMORY.md** had stale model strings matching the same v4 errors

---

## 2. The Self-Test Process (4 Rounds + Round 5)

Self-tests were conducted by sending structured questions to `@Hermes_Cloud_May_bot` via Telegram.

**What she got right:**
- Identity (who she is, her purpose)
- Operational rules for GOJ (LARRY exclusion, schedule cadence)

**What she got wrong:**
- Fallback chain (reported deepseek-chat as primary; wrong Anthropic model string)
- Hard rules — specifically LARRY exclusion from routes (inconsistent recall)
- Docker misconception (believed she ran inside Docker; she does not)

**Key discovery:**
- Her SOUL.md was **NOT in her pre-loaded context**. She was finding everything via filesystem search at query time. This means SOUL.md installs directly into the profile's memories directory and must be correct — she has no other authoritative source.

---

## 3. Files Read This Session

| File | What It Revealed |
|------|-----------------|
| `CC_SOUL_DRAFT_v4.md` | Starting point — 3 factual errors, missing sections |
| `BRAIN/MASTER.md` | Current system state as of May 30; agent overview |
| `BRAIN/Hermes.md` | Hermes gateway config, fallback chain, MCP servers |
| `BRAIN/Claus.md` | Claus was the concept before Hermes; Hermes IS Claus realized |
| `BRAIN/Jarvis.md` | Jarvis agent role within REX |
| `BRAIN/TransitionAgent.md` | Current transition state |
| `agent_registry.json` | Full agent roster |
| `rex_planner.py` | Intelligence architecture — planning layer |
| `rex_user_model.py` | User modeling layer |
| `rex_reflection.py` | Reflection/self-evaluation layer |
| `rex_human_behavior.py` | Behavioral modeling |
| `rex_coordinator.py` | Agent coordination layer |
| `BUILD_DECISION_HISTORY.md` | April 7–16 build decisions |
| `MASTER_BUILD_LEDGER.md` | Full build ledger |
| `MASTER_SYSTEM_WORKING_LOG.md` | System working log |
| `REX_PHASE16_STATUS.md` | Phase 16 status |
| `DEVELOPER_HANDOFF.md` | Developer handoff context |
| `/Volumes/cartoons/` (Cline backups) | Multiple SOUL.md locations; full provider list from hermes config.yaml; `GOJ_Master_Architecture.docx` exists; LM Studio currently running 4 models |

---

## 4. What Kato Confirmed Directly (Source of Truth)

These came from Kato directly — override anything found in files:

| Item | Confirmed Value |
|------|----------------|
| Primary model | `deepseek-v4-pro` (NOT deepseek-chat — BRAIN vault was wrong) |
| Fallback chain | `claude-sonnet-4-6` → `gemini-2.0-flash` |
| Contacts | Victoria AND Masha both have phone numbers (Hermes got this wrong) |
| Victoria voice | `11labs-Lily` (placeholder pending RU/EN test) |
| Masha voice | `11labs-Billy` (placeholder pending RU/EN test) |
| Adam voice | ElevenLabs ID `pNInz6obpgDQGcFmaJgB` — NO "Willow" voice |
| Local model | `qwen3.5:9b` is primary local model, hosted in LM Studio (MLX), NOT Ollama |
| LM Studio models (4) | qwen3.5-9b, nvidia-nemotron-3-nano-30b, gemma-3-4b, nomic-embed-text-v1.5 |
| MCP servers (11) | filesystem, fireflies, gdrive, github, instagram, n8n, notebooklm-bridge, obsidian, retell, sqlite, telegram |
| Video stack | ComfyUI/Flux Dev (key confirmed), Seedance, Manim, Kanban Video Orchestrator, ASCII video |
| Hermes Sidecar | Retired |
| Claus history | Claus was the concept BEFORE Hermes. Hermes IS the Claus vision realized. |
| OG 33 mechanics | All models participate by default. Chairman-only global override. Per-session: Kato can use 3–4 models, narrow each round, swap models — this is a core feature. |
| Hardware | Mac Mini M4 24GB (current primary); Alienware 32GB (home, planned IRONWALL node); Office Mac 16GB (planned work gateway) |
| Business contexts (4 planned) | goj, sports_bar, web_design, social_media |
| TOTP security | RFC example value still present — needs fixing |
| Railway DB | Not synced to local auth_tracker.db — known regression |
| BookKeeper | Leaves today (May 31). QuickBooks files incoming. |

---

## 5. Files Created/Modified This Session

| File | Status | Notes |
|------|--------|-------|
| `~/Desktop/REX/CC_SOUL_DRAFT_v5.md` | **CREATED** | Full v5 with all corrections. **NOT YET INSTALLED.** |
| `~/Desktop/REX/CC_MEMORY_DRAFT.md` | **UPDATED** | Fixed 3 stale model strings. |
| `~/Desktop/REX/CC_HERMES_SELFTEST_PROMPT.md` | Created (previous session) | Ready to use for Round 6+ |
| `~/Desktop/REX/CC_fix_yaml_and_restart.command` | Created (previous session) | Fixes config.yaml line 18 syntax error. **Not yet run.** |

---

## 6. What's Still Pending

**Active / In Progress:**
- Round 6 self-test questions (in progress at session end)

**Unread — high priority:**
- `GOJ_Master_Architecture.docx` on `/Volumes/cartoons/` — not yet read
- `GOJ_Per_Agent_Rules_v1.1.docx` on `/Volumes/cartoons/` — not yet read

**Open questions — unanswered:**
- Obsidian MCP — what does Hermes actually use it for?
- Fireflies — what meetings? What's the integration point?
- NotebookLM bridge — purpose and current usage?
- Palace databases (`palace_main.db`, `palace_cloud.db`) — what is Palace?

**Security / Bugs:**
- TOTP rotation — RFC example value still in place (security fix needed)
- Disclosure tier auth gate — currently advisory only. Any Telegram user can request sensitive data. Needs enforcement.
- `rex_memory.db` and `rex_user_model.db` are 0KB — memory system broken, never recalled
- `config.yaml` line 18 syntax error still present (`CC_fix_yaml_and_restart.command` ready but not run)

**Incoming work:**
- QuickBooks export from bookkeeper — Rexxie financial layer build pending

---

## 7. Install Sequence (When Ready)

Do these in order. Do not skip the YAML fix — the gateway won't start clean without it.

```bash
# 1. Fix YAML syntax error first
~/Desktop/REX/CC_fix_yaml_and_restart.command

# 2. Install SOUL.md to cloud profile
cp ~/Desktop/REX/CC_SOUL_DRAFT_v5.md ~/.hermes/profiles/cloud/memories/SOUL.md

# 3. Install MEMORY.md
cp ~/Desktop/REX/CC_MEMORY_DRAFT.md ~/.hermes/profiles/cloud/memories/MEMORY.md

# 4. Restart gateway (clean restart — always include pkill)
launchctl unload ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist
pkill -f "hermes_cli.main.*gateway"
sleep 8
launchctl load ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist

# 5. Verify with self-test
# Paste CC_HERMES_SELFTEST_PROMPT.md into @Hermes_Cloud_May_bot
# She should now answer fallback chain and LARRY rule correctly from pre-loaded context
```

---

*Generated: May 31, 2026. Next session should start by re-reading this file and checking for the QuickBooks files and the /Volumes/cartoons/ docx files before resuming.*
