# Hermes Sidecar — Cline Build Spec
Version: 1.0 | Date: 2026-04-21 | Authority: Chairman/Kato
Status: PRE-BUILD REVIEW COMPLETE — PHASE 0 REQUIRED BEFORE ANY CODE

---

## GOVERNING CONSTRAINTS (non-negotiable, Cline must not violate)

- local-first only — zero cloud routing without documented Chairman override
- privacy-first — no external API calls, no data leaving localhost
- governed rollout — no autonomous actions until explicitly unlocked per phase
- no silent actions — every Hermes action must produce a log entry
- no fake capability claims — if a tool call fails, report failure, never assume success
- no cross-domain contamination — Hermes cannot read/write Rex or Rexxie files
- Chairman-controlled customization — all configurable values in one locked config file
- future-compatible — no architectural choices that block later Rexxie integration

---

## PHASE 0 — PREFLIGHT (MANUAL, NO CLINE BUILD WORK)

These are Chairman-executed steps. Cline does not build anything until all six pass.

### P0-1: Remove Anthropic API key from Hermes environment
Remove from .env, config files, and any Hermes settings UI.
Not commented out — deleted.
Verify: grep -r "ANTHROPIC\|sk-ant" in Hermes config directory → zero results.

### P0-2: Verify 100% local routing
Send one test prompt via Hermes.
Confirm it resolves to localhost:11434 only.
Method: check Ollama logs for the request, OR add temporary network logging middleware.
Pass condition: Ollama log shows the prompt. No outbound requests to api.anthropic.com.

### P0-3: Clarify Docker backend
Determine what Docker is running.
If Docker is running Ollama: document it as a locked parameter.
If Docker is not essential: disable it.
Pass condition: Docker role is documented OR Docker is disabled.

### P0-4: Confirm sandbox isolation
Hermes must have no write access outside the sandbox folder.
Verify in Hermes config: workspace/project path is scoped to sandbox only.
Pass condition: live project folder path does not appear in any Hermes config.

### P0-5: Lock handoff file schema
Define before Cline builds the writer. Record in this spec (see Section: Handoff File Schema below).
Pass condition: schema is written down and Chairman has approved it.

### P0-6: Confirm Hermes Telegram bot token is separate from Rexxie
Two bots must never share a token.
Pass condition: Hermes bot token != Rexxie bot token (compare last 4 digits).

---

## SECTION: HANDOFF FILE SCHEMA (locked before Phase 1 build)

### File locations (locked)
Morning file: ~/Documents/hermes_handoff/YYYY-MM-DD_morning.md
Nightly file: ~/Documents/hermes_handoff/YYYY-MM-DD_nightly.md
Never overwritten — if re-run same day, append timestamp suffix.

### Morning file fields (fixed, in order)
```
# Morning Handoff — [DATE]
Generated: [TIMESTAMP]

## System Status
- Ollama (localhost:11434): [UP/DOWN]
- Hermes Telegram gateway: [UP/DOWN]
- Any other monitored services

## Yesterday Completions
[List of items marked done in previous nightly handoff]

## Today Open Items
[Priority-ordered list of open items]

## Overnight Alerts
[Any alerts that fired between nightly and morning run]

## Notes
[Freeform — Hermes may add context here]
```

### Nightly file fields (fixed, in order)
```
# Nightly Handoff — [DATE]
Generated: [TIMESTAMP]

## What Happened Today
[Summary of completed items]

## Unresolved Items
[Items still open]

## Tomorrow Flags
[Priority items for tomorrow]

## Email Summary (Phase 3+)
[Placeholder until Phase 3 is activated]

## System Alerts
[Any alerts fired today]
```

---

## MUST DO NOW — Phase 1 Build

Cline may begin Phase 1 ONLY after all P0 checkpoints pass.

### STEP 1-A: Handoff file writer
Build a Python script that generates morning and nightly handoff files.
Input: static system status checks (port pings) + a local open-items list (simple JSON or txt file).
Output: markdown files saved to ~/Documents/hermes_handoff/ using the locked schema above.
No Telegram. No email. No external calls.

Validation checkpoint before 1-B:
- Run the script manually
- Confirm files appear in correct folder with correct naming
- Confirm content matches schema exactly
- Confirm no external network calls in script
- Chairman reads output and confirms accuracy

### STEP 1-B: Telegram listener (read-only)
Wire Hermes Telegram bot to receive Chairman questions.
Hermes reads the message, processes with local model, returns response.
No autonomous sending. Hermes only replies to Chairman-initiated messages.
No cron triggers.

Validation checkpoint before Phase 2:
- Test 10 questions via Telegram
- Confirm all responses come from localhost:11434 (check Ollama logs)
- Confirm no message is sent unless Chairman sent one first
- Gateway stable for 48 hours with no crashes or missed replies

---

## SHOULD DO LATER — Phase 2 Build

Do not start Phase 2 until Phase 1 validation checkpoints pass.

### STEP 2-A: Telegram alert sender (one-way, threshold-based)
Hermes may send pre-approved alert types only:
- System service down alert
- Handoff file generation failure
- Chairman-triggered test ping (/ping command)
Hermes never initiates a conversation. It fires alerts only.
All alert types must be defined in the locked config file before this step.
Dead-man switch: if Hermes sends no heartbeat in 4 hours, gateway stops.

Validation checkpoint before 2-B:
- Trigger each alert type manually
- Confirm exactly one message fires per trigger (no double-send)
- Confirm gateway restart does not re-send pending alerts (idempotency test)
- 48-hour clean run with no duplicate or missed alerts

### STEP 2-B: Structured output validation layer for email (pre-Phase 3 gate)
Before touching real email: run Hermes against 10 synthetic test emails.
Test fields: sender, subject, date, summary, action items.
Pass condition: 9 of 10 correct on all fields with no hallucinated content.
If it fails: stay in Phase 2, investigate model configuration, retest.
Only promote to Phase 3 after this gate passes.

---

## SHOULD DO LATER — Phase 3 Build

Do not start Phase 3 until Phase 2 validation checkpoints pass AND synthetic email test passes.

### STEP 3-A: Personal email reader (read-only)
Hermes reads personal email inbox.
Generates email summary section in nightly handoff file.
Does NOT send, archive, delete, or modify any email.
Does NOT reply.
Summary written to handoff file only.

Validation checkpoint before Phase 4:
- Chairman reviews nightly handoff email summaries for 14 days
- Zero hallucinated emails (invented senders, wrong subjects, wrong dates) in 14 days
- Chairman explicitly approves "Phase 4 gate passed" before advancing

---

## SHOULD DO LATER — Phase 4 Build

Do not start Phase 4 until 14-day Phase 3 validation passes.

### STEP 4-A: Personal email approval loop
Hermes drafts email replies. Drafts saved locally, NOT sent.
Chairman approves via Telegram command: /approve [draft-id]
Hermes sends ONLY after explicit /approve.
/reject [draft-id] discards draft permanently.
No bulk operations. No rules changes. No archiving. One email at a time.

### STEP 5-A: Outlook work email (Phase 5, after Phase 4 stable for 14 days)
Same approval-loop model as Phase 4.
No exceptions to the approval requirement.

---

## DO NOT DO (at any phase without explicit Chairman doctrine update)

- Autonomous email sending (no approval loop)
- Email deletion or archiving
- Silent rule changes to Hermes behavior
- Write access to live Rex/Rexxie project folder
- Replacing or simulating Rexxie
- Broad live repo authority
- Open WebUI (defer — revisit after Phase 2 is stable, only if Tauri dashboard insufficient)
- Shared Telegram bot token with Rexxie
- Cloud model fallback without Chairman-documented override
- Cron-triggered Telegram sends in Phase 1

---

## LOCKED CONFIG FILE STRUCTURE

All Chairman-customizable values live in one file: ~/Documents/hermes_handoff/hermes_config.json

```json
{
  "model": "qwen3.5:9b",
  "base_url": "http://localhost:11434/v1",
  "handoff_folder": "~/Documents/hermes_handoff/",
  "morning_run_time": "07:30",
  "nightly_run_time": "21:00",
  "telegram_gateway": "stopped",
  "alert_types_enabled": [],
  "email_scope": "none",
  "heartbeat_timeout_hours": 4,
  "cloud_routing_allowed": false
}
```

- cloud_routing_allowed must never be set to true by Cline
- telegram_gateway starts as "stopped" — Chairman changes to "active" manually after Phase 1 validation
- alert_types_enabled is empty until Phase 2-A is built and validated

---

## RISK REGISTER

| Risk | Score | Trigger | Mitigation |
|------|-------|---------|------------|
| Anthropic key routes to cloud | 9/10 | Key present in env | P0-1 + P0-2 |
| Tool/file hallucination | 8/10 | Unverified tool calls | Never trust claimed actions without log verification |
| Scope creep from one exception | 8/10 | "Just this once" autonomous send | Hard gate in spec — no exceptions |
| Drift to live project folder | 7/10 | Cline builds a feature needing project path | P0-4 + locked config |
| Docker network exposure | 6/10 | Unknown Docker services | P0-3 |
| Telegram double-fire on restart | 6/10 | Gateway restart replays queue | Idempotency test in 2-A checkpoint |
| qwen3.5:9b email hallucination | 7/10 | Structured output failure | 2-B synthetic test gate |

---

## PHASE GATE SUMMARY

| Gate | Condition | Who approves |
|------|-----------|-------------|
| P0 → Phase 1 | All 6 preflight checkpoints pass | Chairman |
| Phase 1 → Phase 2 | 10 Telegram test passes + 48-hour stability | Chairman |
| Phase 2 → Phase 3 | Synthetic email test 9/10 + Phase 2 alert stability | Chairman |
| Phase 3 → Phase 4 | 14 clean nightly summaries, zero hallucinations | Chairman explicit "Phase 4 gate passed" |
| Phase 4 → Phase 5 | Phase 4 approval loop stable 14 days | Chairman |

---

END OF SPEC
Cline: do not begin build work until Phase 0 is complete and Chairman confirms all P0 checkpoints passed.
