# GHS × Taskmaster Integration Plan (v1)

**Scope:** Add Taskmaster AI as a non-intrusive planner layer over the locked GHS/REX stack without derailing 13-V validation.
**Machine:** Mac Mini M-series, 24GB, FileVault on. Aurora R8 remains secondary worker only.
**Stack (locked for 13-V):** Ollama @ `localhost:11434` · Ops/planning: `qwen3.5:9b` · Cline coder: `qwen2.5-coder:7b` · LM Studio @ `localhost:1234`.

Execute top-to-bottom. Do not skip phases. Every phase has an explicit exit gate.

---

## Phase 0 — Pre-13-V Freeze Verification

**Goal:** Prove the 13-V lane is stable *before* introducing anything new.

Run each check. Record result (pass/fail) in your 13-V evidence log.

1. **Ollama health**
   ```bash
   curl -s http://localhost:11434/api/tags | jq '.models[].name'
   ```
   Expect `qwen3.5:9b` and `qwen2.5-coder:7b` present.
2. **LM Studio health**
   ```bash
   curl -s http://localhost:1234/v1/models | jq '.data[].id'
   ```
   Expect the endpoint to respond (even if idle).
3. **Cline model pin**
   In VS Code → Cline settings → confirm model = `qwen2.5-coder:7b`, base URL = Ollama.
4. **FileVault on**
   ```bash
   fdesetup status
   ```
   Expect `FileVault is On.`
5. **Memory baseline** (record, don't just glance)
   ```bash
   vm_stat; top -l 1 -n 0 | head -10
   ```
   Log free/wired/compressed numbers. This is your baseline to compare against later.
6. **Git working tree clean on GHS project**
   ```bash
   cd <GHS_PROJECT_ROOT>
   git status
   git rev-parse HEAD
   ```
   Record commit SHA as the 13-V anchor.

**Exit gate:** Every check above is recorded with a pass mark. If any fails, stop — fix before proceeding.

---

## Phase 1 — Branch & Environment Prep

**Goal:** Isolate Taskmaster introduction on a dedicated branch so `main` (or whatever your 13-V branch is) is untouched.

```bash
cd <GHS_PROJECT_ROOT>
git checkout -b feature/taskmaster-planner-layer
```

Create (but do not commit yet) a `.taskmaster/` directory:
```bash
mkdir -p .taskmaster
```

Add ignores so no secrets or state leak:
```bash
cat >> .gitignore <<'EOF'

# Taskmaster local state
.taskmaster/state/
.taskmaster/cache/
.taskmaster/*.log
EOF
```

**Exit gate:** On a new branch, `.taskmaster/` exists empty, `.gitignore` updated, working tree clean except for the ignore diff.

---

## Phase 2 — Minimal `.taskmaster/config.json` (Drop-in)

**Goal:** A planner-only config pinned to the locked stack. No multi-agent, no auto-execution, no research-mode cloud calls.

Save this as `.taskmaster/config.json`:

```json
{
  "models": {
    "main": {
      "provider": "ollama",
      "modelId": "qwen3.5:9b",
      "baseURL": "http://localhost:11434/api",
      "maxTokens": 8192,
      "temperature": 0.2
    },
    "fallback": {
      "provider": "ollama",
      "modelId": "qwen3.5:9b",
      "baseURL": "http://localhost:11434/api",
      "maxTokens": 4096,
      "temperature": 0.2
    },
    "research": {
      "provider": "ollama",
      "modelId": "qwen3.5:9b",
      "baseURL": "http://localhost:11434/api",
      "maxTokens": 8192,
      "temperature": 0.3
    }
  },
  "global": {
    "projectName": "GHS",
    "logLevel": "info",
    "debug": false,
    "defaultSubtasks": 3,
    "defaultPriority": "medium",
    "ollamaBaseURL": "http://localhost:11434/api",
    "telemetry": false,
    "autoExecute": false,
    "parallelAgents": false,
    "kanbanMode": false
  },
  "integrations": {
    "cline": {
      "enabled": true,
      "profile": "cline",
      "coderModelId": "qwen2.5-coder:7b",
      "handoffMode": "manual"
    }
  },
  "phaseGates": {
    "enforceReviewBeforeExecute": true,
    "requireEvidenceArtifact": true,
    "blockOnMissingRexRexxieSeparation": true
  }
}
```

Notes, pinned on purpose:
- All three model slots point at `qwen3.5:9b`. No cloud research model. No data leaves the machine.
- `autoExecute: false`, `parallelAgents: false`, `kanbanMode: false` — matches your one-task-at-a-time rule and keeps memory pressure off the 24GB budget.
- `integrations.cline.handoffMode: "manual"` — Taskmaster produces tasks; you paste them into Cline. No automated handoff until post-13-V.
- `phaseGates.*` block execution if evidence/rules are missing — these are hooks your custom rules will lean on.

**Exit gate:** File saved, `jq . .taskmaster/config.json` parses clean.

---

## Phase 3 — Custom-Rules Scaffold (Taskmaster rulebook for GHS)

**Goal:** Give Taskmaster a rulebook it bakes into every task/PRD breakdown so it cannot accidentally violate your Phase guidelines.

Save this as `.taskmaster/rules/ghs-rules.md`. Fill the bracketed `[PASTE …]` blocks from your locked GHS Phase guidelines — the scaffold below is structured so a careful paste is enough, no rewriting.

```markdown
# GHS Phase & Governance Rules (bound to Taskmaster)

## 1. Operating envelope (non-negotiable during 13-V)
- Primary planning model: qwen3.5:9b (Ollama, localhost:11434).
- Cline execution model: qwen2.5-coder:7b. No other coder model may be proposed.
- No cloud calls. No telemetry. No parallel agents. No auto-execute.
- All secrets stay on Mac Mini. Aurora R8 is batch/inference only; never a governance node.

## 2. Phase gates
[PASTE: verbatim phase list from GHS Phase guidelines — e.g. P0 Discovery, P1 Design, P2 Build, P3 Validate, P4 Release. Keep the original names so traceability stays intact.]

Rule: every task MUST declare `phase:` in its metadata. Tasks without a phase are rejected.
Rule: a task in phase N may not depend on an unclosed task in phase N+1.

## 3. Traceability
- Every task references at least one upstream artifact (PRD section, spec ID, or ticket).
- Every task declares the evidence artifact it will produce on completion (log, diff, screenshot, test result).
- Evidence artifacts are stored under `evidence/<phase>/<task-id>/`.

## 4. Review requirements
[PASTE: the review requirements excerpt from GHS — reviewer roles, minimum reviewers per phase, sign-off format.]

Rule: tasks cannot be marked `done` until the declared reviewer signs off in the task's evidence folder.

## 5. Rex vs Rexxie separation
[PASTE: your current Rex vs Rexxie boundary definition — which surfaces each owns, which data each may read/write, which cannot cross.]

Rule: any task that touches both surfaces must be split into two tasks with an explicit handoff artifact between them. Taskmaster must refuse to emit a single task that crosses the boundary.

## 6. 13-V validation lane
- During 13-V, no task may modify: model IDs, Ollama/LM Studio ports, Cline profile, or this rules file.
- Tasks that would modify the above are allowed only on a branch whose name contains `post-13v/`.

## 7. One-task-at-a-time execution
- Taskmaster may generate plans of any depth.
- Cline receives exactly one leaf task per session.
- The operator (you) confirms phase, reviewer, and evidence target before handoff.
```

Reference this from your config by adding (inside `.taskmaster/config.json` → `global`):
```json
"rulesFile": ".taskmaster/rules/ghs-rules.md"
```
(Add that key if Taskmaster's current schema supports it on your installed version; otherwise Taskmaster picks up `.taskmaster/rules/*.md` automatically.)

**Exit gate:** Every `[PASTE …]` block replaced with real content from your GHS guidelines. No placeholders remaining.

---

## Phase 4 — Install & Init Protocol (exact commands)

Do not run these until Phases 0–3 are green.

```bash
# 1. Install global (user scope, no sudo)
npm install -g task-master-ai

# 2. From the GHS project root, on the feature branch:
cd <GHS_PROJECT_ROOT>
git status   # must be clean or show only the .taskmaster/ scaffold + .gitignore

# 3. Initialize against the existing config
task-master-ai init --non-interactive \
  --provider ollama \
  --base-url http://localhost:11434 \
  --model qwen3.5:9b \
  --profile cline \
  --config .taskmaster/config.json
```

If `--non-interactive` is not supported in your installed version, run `task-master-ai init` and answer:
- Provider: **Ollama**
- Base URL: `http://localhost:11434`
- Model: `qwen3.5:9b`
- Profile: **cline**
- Custom rules: point to `.taskmaster/rules/ghs-rules.md`

Sanity check:
```bash
task-master-ai doctor     # or: task-master-ai status
```
Expect: provider=ollama, model=qwen3.5:9b, profile=cline, rulesFile resolved.

**Exit gate:** `doctor`/`status` is all-green. No warnings about cloud providers, telemetry, or missing rules.

---

## Phase 5 — Usage Protocol (one task at a time)

For every task you plan to execute during 13-V:

1. Generate plan
   ```bash
   task-master-ai plan --input <prd-or-ticket> --phase <P#>
   ```
2. Review the emitted task list *by hand* against `ghs-rules.md`. Reject any task that:
   - crosses the Rex/Rexxie boundary,
   - lacks a phase label,
   - lacks an evidence target,
   - proposes a model/port change during 13-V.
3. Pick exactly one leaf task. Copy its full text to Cline.
4. Cline executes with `qwen2.5-coder:7b`. You review the diff.
5. Save evidence to `evidence/<phase>/<task-id>/`.
6. Mark task done in Taskmaster with reviewer sign-off.
7. Commit:
   ```bash
   git add evidence/ <changed-files>
   git commit -m "P<#>/<task-id>: <short desc> (evidence attached)"
   ```
8. Repeat from (3) until plan is exhausted or phase gate is reached.

Hard rules during 13-V:
- No parallel Cline sessions.
- No second model loaded alongside 9b + 7b (would spike memory).
- No editing `.taskmaster/rules/ghs-rules.md`.

---

## Phase 6 — 13-V Evidence Capture

For 13-V credibility, capture these per task:

- `evidence/<phase>/<task-id>/prompt.txt` — exact Cline prompt used.
- `evidence/<phase>/<task-id>/diff.patch` — `git diff` of the change.
- `evidence/<phase>/<task-id>/review.md` — reviewer name, date, findings, sign-off.
- `evidence/<phase>/<task-id>/mem.txt` — `vm_stat` snapshot before/after the Cline run.
- `evidence/<phase>/<task-id>/result.txt` — test output or verification artifact.

At phase close, run:
```bash
find evidence/<phase> -type f | sort > evidence/<phase>/MANIFEST.txt
shasum -a 256 $(find evidence/<phase> -type f ! -name MANIFEST.txt) \
  > evidence/<phase>/CHECKSUMS.txt
```
That gives 13-V a deterministic fingerprint per phase.

---

## Phase 7 — Post-13-V Optimization Gates (Proposal B)

Only after 13-V evidence is locked and signed off:

1. **Benchmark lane** (separate branch, never during 13-V):
   ```bash
   git checkout -b post-13v/benchmark-qwen-variants
   ```
   Compare, holding the same task set from a closed phase:
   - `qwen3.5:9b` (baseline)
   - `qwen3:8b` (lighter)
   - `qwen3:14b` (only if peak memory pressure on 9b stayed green/yellow)
   Record tokens/sec, peak RSS, task success rate.
2. **Fallback model:** evaluate `gemma3:4b` strictly as a fallback when memory pressure hits red.
3. **Decision record:** write `docs/adr/ADR-0xx-primary-model.md` before changing `.taskmaster/config.json`.
4. **Re-run 13-V delta evidence** for any field you touched in the locked config.
5. **Cross-machine:** Aurora R8 may take batch inference jobs only after the trust boundary doc is merged. No shared secrets, no shared tokens, signed artifacts only.

---

## Phase 8 — Rollback

If anything goes sideways at any phase:
```bash
git checkout <13v-anchor-sha>      # the SHA you recorded in Phase 0
npm uninstall -g task-master-ai    # optional; config alone is inert if unused
```
The 13-V lane is untouched because every Taskmaster change lives on `feature/taskmaster-planner-layer` or `post-13v/*`.

---

## Risk register (aligned with your proposal)

| Action | Risk | Mitigation |
|---|---|---|
| Model swap before 13-V | 7/10 | Forbidden by rule 6 of ghs-rules.md; enforced via `blockOnMissingRexRexxieSeparation` + branch-name gate |
| Taskmaster planner, one-task-at-a-time | 2–3/10 | Manual review of every emitted task; `autoExecute:false` in config |
| Parallel agents / Kanban | High on 24GB | `parallelAgents:false`, `kanbanMode:false` in config |
| Cross-machine secret leak | Medium | Aurora R8 stays inference-only; explicit trust boundary doc required before any handshake |

---

## What's still pending from you

1. Paste the real content into the 4 `[PASTE …]` blocks in `.taskmaster/rules/ghs-rules.md` (phase list, review requirements, Rex/Rexxie boundary).
2. Confirm your `<GHS_PROJECT_ROOT>` path and the 13-V branch name.
3. Confirm whether your installed `task-master-ai` version supports `--non-interactive` (affects Phase 4 exact command).

Once those three are in, this plan is executable top-to-bottom in one sitting without touching the 13-V lane.
