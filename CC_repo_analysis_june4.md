# 10 Repos — GHS Applicability Analysis
**Date:** June 4, 2026  
**Analyst:** Claude (Hermes session)

---

## Priority Tier 1 — Act on These Now

### 1. hermes-agent (NousResearch)
**Repo:** github.com/NousResearch/hermes-agent  
**What it is:** Self-evolving AI agent that extracts skills from every conversation and gets smarter with use.  
**GHS fit:** CRITICAL. The skills-extraction architecture is exactly the evolution path for Hermes. Currently Hermes learns via manual SOUL.md/MEMORY.md updates — this would automate that loop. Skills extracted from GOJ conversations (schedule changes, auth workflows, kitchen runs) could become permanent Hermes capabilities. Study before planning Phase 14+.  
**Action:** Deep-dive. Evaluate skill extraction mechanism for integration into Hermes v0.16.

---

### 2. MemPalace (github.com/MemPalace/mempalace)
**What it is:** Near-perfect LongMemEval score AI memory system, co-built by Milla Jovovich.  
**GHS fit:** HIGH. REX's `rex_memory.db` is underbuilt. MemPalace's architecture handles exactly the kind of long-context retention needed for 425-client GOJ tracking — remembering client preferences, auth history, care notes across sessions. LongMemEval performance suggests it handles the kind of multi-turn, multi-entity recall GOJ requires.  
**Action:** Read architecture. Candidate to replace or sit under RexMemory. Especially relevant for Rexxie's cross-session continuity.

---

### 3. SuperClaude Framework (github.com/SuperClaude-Org)
**What it is:** Complete Claude Code methodology — personas, commands, prompts, workflows.  
**GHS fit:** HIGH. Hermes already has a persona system (SOUL.md + role tiers). SuperClaude's persona framework could directly upgrade it. The commands/workflows could map to Hermes toolsets. Most valuable: the prompting patterns for agentic consistency under long sessions.  
**Action:** Extract persona and command patterns. Fold best practices into SOUL.md and MEMORY.md during next Hermes config update.

---

## Priority Tier 2 — Schedule for Next Sprint

### 4. awesome-claude-code (github.com/hesreallyhim/awesome-claude-code)
**What it is:** Canonical Claude Code playbook — hooks, slash commands, tool use, MCP patterns.  
**GHS fit:** MEDIUM-HIGH. Hermes runs on Claude Code under the hood. Better hooks = better PostToolUse automation (auto-format, type check, lint). Better MCP patterns = cleaner tool integrations. Several hook patterns could replace ad-hoc `.command` scripts.  
**Action:** Mine for hook configurations. Add best patterns to `~/.hermes/profiles/cloud/config.yaml` toolsets.

### 5. autoresearch (github.com/karpathy/autoresearch)
**What it is:** Karpathy's research automation framework.  
**GHS fit:** MEDIUM. Already installed at `~/Documents/autoresearch`. Has never been wired into Hermes. The framework automates multi-step research tasks — useful for competitive analysis, regulatory research (Medicaid auth rules), vendor evaluation.  
**Action:** Wire a Hermes toolset pointing at autoresearch. Define trigger: "research [topic]" → autoresearch pipeline → summary to Kato via Telegram.

### 6. andrej-karpathy-skills (github.com/forrestchang/...)
**What it is:** Single markdown file distilling Karpathy's AI coding wisdom (109K+ stars).  
**GHS fit:** MEDIUM. Not operational code — it's a reference. High signal-to-noise ratio on prompting, agent behavior, and knowing when NOT to use AI. Worth reading once and extracting 3–5 principles into CLAUDE.md or MEMORY.md.  
**Action:** Read once. Extract principles. Done.

---

## Priority Tier 3 — Reference, No Immediate Action

### 7. AI-Agents-for-Beginners (Microsoft, github.com/microsoft/ai-agents-for-beginners)
**What it is:** 12-lesson course on building AI agents.  
**GHS fit:** LOW-MEDIUM. More educational than operational. Could inform architecture decisions for Phase 14+ multi-agent coordination. Not urgent — Hermes architecture is already past "beginner" level.  
**Action:** Bookmark. Review before Phase 14 planning.

### 8. awesome-llm-apps (github.com/Shubhamsaboo/awesome-llm-apps, 106K stars)
**What it is:** Comprehensive collection of working LLM applications.  
**GHS fit:** LOW-MEDIUM. Pattern library. Useful when building new GOJ features to check if someone has already solved a similar problem. Not a priority until new feature work begins.  
**Action:** Bookmark. Reference when scoping new GOJ features.

### 9. mattpocock/skills (github.com/mattpocock/skills)
**What it is:** TypeScript wizard's daily coding workflow — planning, TDD, architecture, git guardrails.  
**GHS fit:** LOW. GHS stack is Python (FastAPI, Flask, SQLite). The TDD and planning discipline is solid but TypeScript-specific patterns don't translate directly. Architectural principles (planning before coding, git guardrails) are already in CLAUDE.md.  
**Action:** Skip unless GHS adds a TypeScript frontend.

### 10. qlib (Microsoft, github.com/microsoft/qlib)
**What it is:** Full quantitative investment platform — the brain of a hedge fund analyst.  
**GHS fit:** LOW for current GHS. Tiger Claw API exists but is positioned as a health/ops tool, not a quant platform. If GHS ever expands into financial analysis (BBG Social has potential), revisit.  
**Action:** No action now. File under "if GHS expands to financial services."

---

## Summary Table

| Repo | Priority | Action |
|------|----------|--------|
| hermes-agent (NousResearch) | 🔴 High | Deep-dive for Hermes v0.16 skills extraction |
| MemPalace | 🔴 High | Evaluate for RexMemory replacement/enhancement |
| SuperClaude Framework | 🔴 High | Extract persona/prompt patterns → SOUL.md |
| awesome-claude-code | 🟡 Medium | Hook patterns → Hermes config |
| autoresearch | 🟡 Medium | Wire into Hermes toolset |
| andrej-karpathy-skills | 🟡 Medium | Read once, extract 3-5 principles |
| AI-Agents-for-Beginners | 🟢 Low | Review before Phase 14 planning |
| awesome-llm-apps | 🟢 Low | Reference library |
| mattpocock/skills | 🟢 Low | Skip unless TypeScript frontend |
| qlib | 🟢 Low | Skip unless GHS expands to finance |

---

## One-Line Bottom Line

The three repos that move the needle for GHS right now are **hermes-agent** (auto-skill extraction = Hermes evolves itself), **MemPalace** (proper long-term memory = GOJ clients remembered across sessions), and **SuperClaude** (prompt engineering upgrades = sharper agent behavior). Everything else is useful eventually but not urgent.
