# Documentation Agent README
## Gold Health Systems — How to Keep the Master Log Current
## Version 1.0 · June 4, 2026

---

## Purpose

This file tells any AI agent or human how to maintain the GHS documentation system. The three living documents (`CC_MASTER_BUILD_LOG.md`, `CC_PHASE_STATUS.md`, and this file) form the operational memory of the entire GHS build. Every future agent that joins this system should read these documents first.

---

## The Document Hierarchy

```
BRAIN/MASTER.md                   ← Kato maintains. Source of truth for FACTS.
       ↓
CLAUDE.md                         ← Agent behavioral rules. Governs all sessions.
       ↓
CC_MASTER_BUILD_LOG.md            ← Complete system state. Synthesized from all sources.
       ↓
CC_PHASE_STATUS.md                ← Phase-focused view. Quick lookup for build progress.
       ↓
CC_DOCUMENTATION_AGENT_README.md  ← This file. How to maintain the above.
```

**CC_HERMES_KNOWLEDGE.md** is the historical reference — comprehensive but becomes stale. When it contradicts `CC_MASTER_BUILD_LOG.md`, trust the build log (it is newer and more specific).

---

## When to Update

**Update `CC_MASTER_BUILD_LOG.md` when any of the following happen:**

1. **A phase changes status** — from PLANNED to IN PROGRESS, IN PROGRESS to COMPLETE, or a regression is introduced or resolved.
2. **A critical open item is resolved** — remove from OPEN ITEMS or change its status.
3. **A new service is added or removed** from the active stack.
4. **A build session produces CC_ files** — add them to ALL BUILD ARTIFACTS.
5. **A key decision is made** — add to KEY DECISIONS LOG with date and who approved.
6. **A known issue is discovered or fixed** — update KNOWN ISSUES table.
7. **At the end of any session** where substantive work was done — summarize in TODAY'S CHANGES section.
8. **Agent roster changes** — new agent created, existing agent breaks or is decommissioned.
9. **Security posture changes** — new encryption applied, vulnerability found or patched.
10. **Phase 13-V checkpoint passes** — mark all phases as unblocked.

**Update `CC_PHASE_STATUS.md` when:**
- Any phase moves to a new status.
- A phase regression is discovered or fixed.
- Phase 13-V checklist items are verified.
- A new phase is scoped out (even if not started).

---

## Format Conventions

### Status Icons (use consistently)
- `✅` — Complete, running, healthy
- `⚠️` — Active but with a known issue or regression
- `❌` — Broken, not running, failed
- `🔒` — Locked (no changes without explicit reason)
- `🔄` — In progress
- `⛔` — Blocked by a dependency or gate
- `📋` — Planned, not yet started

### Phase Status Values (CC_PHASE_STATUS.md)
Use exactly these phrases in the Status column:
- `🔒 LOCKED / ✅ COMPLETE`
- `🔒 LOCKED / ⚠️ REGRESSION`
- `🔒 LOCKED / ⚠️ PARTIAL`
- `🔒 LOCKED / ⚠️ DISABLED`
- `🔄 IN PROGRESS`
- `🔄 FILES BUILT`
- `⛔ BLOCKED`
- `📋 PLANNED`
- `✅ COMPLETE / RUNNING`
- `❌ NOT RUNNING`
- `⛔ CHECKPOINT — NOT PASSED`
- `⛔ CHECKPOINT — PASSED`

### Date Format
Always use `June 4, 2026` format (not 2026-06-04) in prose. ISO format `2026-06-04` is fine in file headers.

### File References
Always use the full `~/Desktop/REX/` or `~/.hermes/` style paths. Never relative paths. This makes it unambiguous which machine and location is meant.

### Priority Labels in OPEN ITEMS
- `🔴 Critical` — blocks operations, HIPAA risk, security gap, or data loss risk
- `🟡 High Priority` — significant dysfunction, multiple users affected
- `🟢 Active Building` — in-progress work, someone is working on it
- `⚪ Planned` — identified, scoped, no active work yet

---

## How Phase Status Changes

A phase changes from PLANNED → IN PROGRESS when:
- Kato says "build it" / "do it" / "just do it" (PAE approved)
- OR a file is created that belongs to that phase

A phase changes from IN PROGRESS → COMPLETE when:
- All planned components are built AND tested
- For Phases 1–13: Kato locked it explicitly in CLAUDE.md

A phase is marked REGRESSION when:
- A component that was working no longer works as designed
- A known bug is confirmed, not just suspected

A phase is marked COMPLETE despite regressions when:
- The regression is in a sub-component (not the whole phase)
- The regression is tracked in OPEN ITEMS
- The core functionality remains intact

**Phase 13-V is special.** It is a GATE, not a build phase. When all 9 steps pass:
1. Update Phase 13-V row in CC_PHASE_STATUS.md → `⛔ CHECKPOINT — PASSED`
2. Update Phase 14 and 15 → remove "Blocked by Phase 13-V" from blocking issues
3. Add a TODAY'S CHANGES entry in CC_MASTER_BUILD_LOG.md noting the gate passed

---

## TODAY'S CHANGES Section — How to Write It

The `TODAY'S CHANGES` section in CC_MASTER_BUILD_LOG.md should be the FIRST thing a new session reads to understand what happened recently. Format:

```markdown
## TODAY'S CHANGES (Month D, YYYY)

### Changes Made
**1. Title of Change (~time if known)**
- Problem: What was wrong or what was requested
- Fix/Build: What was done
- Script/File: What file was created or modified
- Result: ✅ Success / ⚠️ Partial / ❌ Failed

### Files Created Today
| File | Path | Status |
| ... | ... | ... |

### Currently Building
- Item 1 — brief description
- Item 2 — brief description

### Pending Actions (PAE-blocked)
| Action | File | What it does |
| ... | ... | ... |
```

When starting a new day's changes, archive the previous day's section by moving it to the bottom of the file under `## CHANGE HISTORY` (or simply overwrite with the new date — the change log in CC_hermes_change_log_2026.md has the full history).

---

## Agent Handoff Protocol

When one session ends and another begins, the receiving agent should:

1. **Read CLAUDE.md first** — behavioral rules and system identity.
2. **Read CC_MASTER_BUILD_LOG.md `## TODAY'S CHANGES`** — what happened last session.
3. **Read CC_MASTER_BUILD_LOG.md `## OPEN ITEMS BY PRIORITY`** — what needs attention now.
4. **Check service health** before touching anything:
   ```bash
   curl -s http://localhost:8000/health
   curl -s http://localhost:3002/health
   launchctl list | grep -E "hermes|rex|goj"
   ```
5. **Read `~/Documents/goj files/GOJ_WORKING_DOC.md`** if doing GOJ work.
6. **Update the build log** at session end with any changes made.

**What NOT to do at handoff:**
- Do not assume services are running — always check.
- Do not assume config files are unchanged — `hermes-workspace` can modify them silently (see June 4 incident).
- Do not start Phase 14+ work without confirming Phase 13-V passed.
- Do not touch `~/.hermes/profiles/cloud/memories/SOUL.md` or `MEMORY.md` without PIN — they are `chflags uchg` locked.

---

## Maintaining the Build Artifacts Table

In `CC_MASTER_BUILD_LOG.md`, the `## ALL CC_ BUILD ARTIFACTS` section tracks every `CC_` prefixed file. When you create a new `CC_` file:

1. Add it to the appropriate subsection (Documentation, Scripts, or by phase).
2. Columns: File name | Purpose | Status (one of: ✅ Active, ✅ Run, ⚠️ NOT YET RUN, ✅ Archive, ✅ Built (not active), 📋 Planning).
3. If the file is a one-time script that has been run successfully, mark it `✅ Run [date]`.
4. If it's awaiting Kato approval, mark it `⚠️ AWAITING APPROVAL`.

---

## Source Priority (When Documents Conflict)

If two documents give different information, trust them in this order:

1. **Kato's direct statement** (most recent wins over older) — overrides everything
2. **CC_MASTER_BUILD_LOG.md** — synthesized, newer, verified
3. **CLAUDE.md** — behavioral rules (may be slightly behind MASTER.md)
4. **CC_HERMES_KNOWLEDGE.md** — comprehensive but updated less frequently
5. **CC_SESSION_HANDOFF_*.md** — point-in-time snapshot from that date
6. **Other CC_ files** — situation-specific, may be stale

When you find a conflict, update CC_MASTER_BUILD_LOG.md with the correct fact and note which source you verified against.

---

## Security Rules for Documentation

These rules apply to this document and all files it governs:

- **New files get `CC_` prefix** — no exceptions for files created in this system.
- **Share files via `attachments[]` only** — `computer://` links break iOS.
- **No PHI to cloud** — never paste client names, SSNs, DOBs, or medical data into any cloud-reaching document.
- **Never permanently delete** — quarantine only (`*.QUARANTINE_YYYY_MM_DD`).
- **Never touch SOUL.md / MEMORY.md** — these are `chflags uchg` PIN-locked. Any changes go through the derivation chain: MASTER.md → CLAUDE.md → SOUL.md → restart Hermes.
- **Never write `Larry`** on any transport or driver list — in any context, any format, any instruction.
- **Gate 1 rule:** `akc_tokenizer.py` must be fully built before ANY PHI routes to cloud AI. Not built yet = complete hard block. This overrides all other considerations.

---

## Quick Reference: Most Common Update Scenarios

| Scenario | Files to update | Section to update |
|---------|-----------------|-------------------|
| A phase finishes | CC_PHASE_STATUS.md, CC_MASTER_BUILD_LOG.md | Phase row, Active Stack if service changes |
| A service goes down | CC_MASTER_BUILD_LOG.md | Active Stack, Open Items (if blocking) |
| A CC_ script is created | CC_MASTER_BUILD_LOG.md | TODAY'S CHANGES > Files Created, ALL BUILD ARTIFACTS |
| A critical bug found | CC_MASTER_BUILD_LOG.md | OPEN ITEMS 🔴, KNOWN ISSUES, PHASE status if relevant |
| A bug is fixed | CC_MASTER_BUILD_LOG.md, CC_PHASE_STATUS.md | Update OPEN ITEMS status, remove from regressions |
| Phase 13-V passes | CC_PHASE_STATUS.md, CC_MASTER_BUILD_LOG.md | 13-V row, unblock Phase 14/15 rows |
| New agent created | CC_MASTER_BUILD_LOG.md | AGENT ROSTER |
| New database added | CC_MASTER_BUILD_LOG.md | DATA SOURCES |
| New key decision made | CC_MASTER_BUILD_LOG.md | KEY DECISIONS LOG |
| Security posture changes | CC_MASTER_BUILD_LOG.md | SECURITY STATUS table |
| SOUL.md / MEMORY.md reinstalled | CC_MASTER_BUILD_LOG.md | TODAY'S CHANGES, note version installed |
| Session ends | CC_MASTER_BUILD_LOG.md | TODAY'S CHANGES with summary |

---

## Obsidian Sync Note

These files live at `~/Desktop/REX/` and should be copied to the BRAIN vault after any significant update:

```bash
# Sync to BRAIN vault
cp ~/Desktop/REX/CC_MASTER_BUILD_LOG.md ~/Desktop/Gold_Health_Systems/BRAIN/CC_MASTER_BUILD_LOG.md
cp ~/Desktop/REX/CC_PHASE_STATUS.md ~/Desktop/Gold_Health_Systems/BRAIN/CC_PHASE_STATUS.md
cp ~/Desktop/REX/CC_DOCUMENTATION_AGENT_README.md ~/Desktop/Gold_Health_Systems/BRAIN/CC_DOCUMENTATION_AGENT_README.md
```

The BRAIN vault (`~/Desktop/Gold_Health_Systems/BRAIN/`) is the primary Obsidian vault and is where `MASTER.md` lives. Keeping these files there means they're accessible from Obsidian and to any agent reading the BRAIN directory.

---

*Documentation Agent README · Gold Health Systems · v1.0 · June 4, 2026*
*This file should itself be updated when documentation conventions change.*
