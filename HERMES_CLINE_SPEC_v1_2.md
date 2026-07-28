# Hermes Sidecar — Cline Build Spec
Version: 1.2 | Date: 2026-04-21 | Authority: Chairman/Kato
Status: FINAL — PHASE 0 REQUIRED BEFORE ANY CODE

---

## WHAT THIS DOCUMENT IS

This is the complete governing build specification for the Hermes local sidecar.
Cline must read this document in full before writing a single line of code.
Every section is authoritative. Nothing in this document is a suggestion.

Hermes is NOT Rexxie. Hermes is a temporary local sidecar/operator running
alongside Rex/Rexxie while that system is being hardened. It is a bridge, not
a replacement. Every architectural decision must preserve future compatibility
with a more sovereign private Rexxie layer.

---

## GOVERNING CONSTRAINTS (non-negotiable — Cline must never violate)

- local-first only — zero cloud routing without documented Chairman override
- privacy-first — no external API calls, no data leaving localhost
- governed rollout — no autonomous actions until explicitly unlocked per phase
- no silent actions — every Hermes action must produce a log entry
- no fake capability claims — if a tool call fails, report failure, never assume success
- no cross-domain contamination — Hermes cannot read/write Rex or Rexxie files
- Chairman-controlled customization — all configurable values in one locked config file
- future-compatible — no architectural choices that block later Rexxie integration
- audit-first — if the audit log write fails, the action aborts; nothing proceeds without a log entry

---

## PHASE 0 — PREFLIGHT (MANUAL, NO CLINE BUILD WORK)

These are Chairman-executed steps. Cline does not write any code until all six
checkpoints are confirmed passed by Chairman.

If Chairman has not confirmed Phase 0 complete: stop and ask before proceeding.

### P0-1: Remove Anthropic API key from Hermes environment
Remove from .env, config files, and any Hermes settings UI.
Not commented out — deleted entirely.
Verify: `grep -r "ANTHROPIC\|sk-ant" <hermes_config_directory>` → zero results.
Pass condition: grep returns zero matches.

### P0-2: Verify 100% local routing
Send one test prompt via Hermes chat.
Confirm it resolves to localhost:11434 only.
Method: check Ollama logs for the incoming request.
Pass condition: Ollama log shows the prompt was received. No outbound connection
to api.anthropic.com or any external host.
If routing cannot be confirmed at the network layer: do not proceed.

### P0-3: Clarify Docker backend
Determine exactly what Docker is running.
If Docker is running Ollama: document the container name and port as a locked parameter.
If Docker is not essential to Hermes: disable it.
Pass condition: Docker role is explicitly documented OR Docker is confirmed disabled.

### P0-4: Confirm sandbox isolation
Hermes must have no write access outside the designated sandbox folder.
Verify in Hermes config: workspace/project path is scoped to sandbox only.
Pass condition: live Rex/Rexxie/GOJ project folder paths do not appear in any
Hermes config, workspace setting, or tool permission scope.

### P0-5: Lock handoff file schema
The handoff file schema defined in this document is approved by Chairman before
Cline builds the writer. No changes to the schema after build begins without
explicit Chairman approval.
Pass condition: Chairman has read and approved the schema section below.

### P0-6: Confirm Hermes Telegram bot token is separate from Rexxie
Two bots must never share a token. Ever.
Pass condition: Hermes bot token is confirmed different from Rexxie bot token.
Compare last 4 characters of each token. They must not match.

---

## HANDOFF FILE SCHEMA (locked — do not alter without Chairman approval)

### File locations
Morning file: ~/Documents/hermes_handoff/YYYY-MM-DD_morning.md
Nightly file:  ~/Documents/hermes_handoff/YYYY-MM-DD_nightly.md

Naming: use ISO date format. Zero-pad month and day.
Example: 2026-04-21_morning.md

Never overwrite an existing file. If the script is re-run on the same day,
append a timestamp suffix: 2026-04-21_morning_143022.md

### Morning file — fixed field order
```
# Morning Handoff — [YYYY-MM-DD]
Generated: [ISO TIMESTAMP]

## System Status
- Ollama (localhost:11434): [UP/DOWN]
- Hermes Telegram gateway: [UP/DOWN/STOPPED]
- [Any other monitored services — add by config only]

## Yesterday Completions
[List of items marked done in previous nightly handoff]
[If no previous nightly file exists: state "No prior nightly file found"]

## Today Open Items
[Priority-ordered list of open items from open_items source file]
[If source file missing: state "Open items file not found at [path]"]

## Overnight Alerts
[Any alerts that fired between nightly and morning run]
[If none: state "No overnight alerts"]

## Notes
[Freeform — Hermes may add operational context here]
```

### Nightly file — fixed field order
```
# Nightly Handoff — [YYYY-MM-DD]
Generated: [ISO TIMESTAMP]

## What Happened Today
[Summary of completed items]
[If nothing to report: state "No completions recorded today"]

## Unresolved Items
[Items still open from today's open items list]

## Tomorrow Flags
[Priority items flagged for tomorrow]

## Email Summary (Phase 3+ only)
[PLACEHOLDER — not active until Phase 3 gate passes]
[Do not populate this section before Phase 3]

## System Alerts
[Any alerts fired today]
[If none: state "No alerts today"]
```

### Open items source file
Path: ~/Documents/hermes_handoff/open_items.json
Format: JSON array of objects with fields: id, priority, item, status, added_date
Status values: open / done / deferred
Hermes reads this file. Hermes never modifies it directly — that is Chairman's file.

---

## MANDATORY AUDIT LOG (applies to every phase — no exceptions)

Every Hermes action must create a structured log entry before the action is
considered complete. If the log write fails, the action is aborted and an error
is reported to Chairman. No action proceeds without a confirmed successful log write.

### Log location (locked)
~/Documents/hermes_handoff/logs/hermes_audit.jsonl

One JSON object per line. Append only. Never overwrite. Never delete entries.

### Required fields — every log entry must contain all of these
```json
{
  "timestamp": "ISO 8601 datetime",
  "phase": "phase identifier — e.g. phase_1, phase_2",
  "trigger_source": "see trigger sources below",
  "requested_action": "what was asked of Hermes",
  "actual_action": "what Hermes actually did — must differ from requested if action was modified",
  "result_status": "see result status values below",
  "success_boolean": true or false,
  "approval_required": true or false,
  "approval_state": "not_required / pending / approved / rejected",
  "tool_used": "name of tool or null if no tool",
  "file_or_message_id": "file path, Telegram message ID, email ID, or null",
  "notes": "any additional context — empty string if none"
}
```

### Trigger sources
- manual_cli
- telegram_inbound
- scheduled_handoff
- email_reader
- alert_rule
- health_check

### Result status values
- success
- denied
- failed
- skipped
- dry_run
- aborted

### Hard rules
1. Hermes must never claim an action succeeded unless a corresponding
   success log entry exists and was written without error.
2. If the audit log write itself fails: abort the action, surface the error to
   Chairman immediately, do not retry silently.
3. The audit log is read-only for all automated processes. Only Chairman may
   manually inspect or archive it.

---

## EMAIL SCOPE SEPARATION (locked — no shared defaults between scopes)

Personal email and work email are logically separate systems. They share no
default rules, no shared priority lists, no shared thresholds, and no shared
approval chains. The only way a rule applies to both scopes is if Chairman
explicitly adds it to both, separately.

### Personal email
- Config key: email_scope_personal
- Activated in Phase 3
- Separate sender priority list
- Separate alert thresholds
- Separate section in nightly handoff file
- Approval loop activated in Phase 4

### Work email (Outlook)
- Config key: email_scope_work
- Disabled by default — value must be "disabled" until Phase 5
- Activated only in Phase 5, after Phase 4 is stable for 14 days
- Separate sender priority list
- Separate alert thresholds
- Separate approval gate — never inherits personal email approvals
- Separate section in nightly handoff file

### Hard rule
No shared default rule-set between personal and work email. If Cline creates
any shared data structure, config key, or rule that applies to both scopes
without explicit Chairman-authored entries for each: that is a violation.

---

## PHASE 1 — MUST DO NOW

Cline may begin Phase 1 only after Chairman confirms all P0 checkpoints passed.

### STEP 1-A: Handoff file writer

Build a Python script: hermes_handoff_writer.py

What it does:
- Pings localhost:11434 to check Ollama status
- Pings Telegram gateway to check status
- Reads open_items.json for current open items
- Reads previous nightly file (if exists) to extract yesterday's completions
- Writes morning and nightly handoff files to ~/Documents/hermes_handoff/
  using the locked schema above
- Writes a log entry to hermes_audit.jsonl for every action taken

Trigger in Phase 1: MANUAL ONLY.
No scheduler, no cron, no launchd until Phase 2 gate passes.
Chairman runs the script by hand: `python3 hermes_handoff_writer.py morning`
or `python3 hermes_handoff_writer.py nightly`

External calls: none. No network calls except localhost port pings.

Error handling:
- If Ollama is down: write "DOWN" in system status, continue
- If open_items.json is missing: write file-not-found notice, continue
- If audit log write fails: print error to terminal, abort file write, exit

Validation checkpoint — Chairman must verify all before Step 1-B:
- [ ] Run script manually: `python3 hermes_handoff_writer.py morning`
- [ ] Confirm file appears in ~/Documents/hermes_handoff/ with correct name
- [ ] Confirm file content matches schema exactly — no missing sections
- [ ] Confirm no external network calls (check Ollama logs — only localhost traffic)
- [ ] Confirm audit log entry written to hermes_audit.jsonl
- [ ] Chairman reads file and confirms content is accurate
All six must pass. If any fail: fix before 1-B.

---

### STEP 1-B: Telegram listener (read-only)

Wire Hermes Telegram bot to receive Chairman questions and respond.

What it does:
- Listens for inbound messages from Chairman's Telegram account only
- Sends message text to local model at localhost:11434/v1
- Returns model response to Chairman via Telegram
- Writes a log entry for every inbound message and every outbound reply

What it does NOT do:
- Does not send any message unless Chairman sent one first
- Does not initiate conversations
- Does not fire on any schedule
- Does not have access to email, files, or project directories

Approved inbound commands in Phase 1:
- Any freeform question → routed to local model
- /ping → Hermes replies with system status (Ollama up/down, gateway up/down)
- /status → same as /ping

No other commands are wired until Phase 2 gate passes.

Error handling:
- If local model is unreachable: reply "Model unavailable — localhost:11434 not responding"
- If reply fails to send: log failure with result_status=failed, do not retry silently

Validation checkpoint — Chairman must verify all before advancing to Phase 2:
- [ ] Send 10 different questions via Telegram
- [ ] Confirm all 10 responses came from localhost:11434 (check Ollama logs for each)
- [ ] Confirm no Telegram message was sent without Chairman sending one first
- [ ] Confirm audit log has an entry for every inbound message and every reply
- [ ] Send /ping and confirm status response is accurate
- [ ] Gateway runs stable for 48 hours with no crashes or missed replies
All six must pass. If any fail: fix before Phase 2.

---

## PHASE 2 — SHOULD DO LATER

Do not start Phase 2 until all Phase 1 validation checkpoints are confirmed passed.

### STEP 2-A: Telegram alert sender (one-way, threshold-based)

Expand Telegram bot to allow Hermes to send pre-approved alert types.

Approved alert types — must be defined in hermes_config.json before build:
- service_down: fires when Ollama or gateway fails health check
- handoff_failed: fires when handoff file writer errors out
- ping_response: fires only in response to /ping command

Hermes never initiates a conversation. It fires alerts only.
Hermes never sends a message type that is not in alert_types_enabled config list.

Dead-man switch: if Hermes sends no heartbeat ping in heartbeat_timeout_hours,
the Telegram gateway stops automatically. Restart is manual.

Schedule: alert rules may run on a schedule in Phase 2. Handoff file writer
may also be scheduled in Phase 2 after gate passes. Define schedule in config —
do not hardcode times.

Validation checkpoint before 2-B:
- [ ] Trigger each alert type manually — confirm exactly one message per trigger
- [ ] Restart gateway — confirm no duplicate alerts re-sent (idempotency)
- [ ] Confirm audit log captures: trigger event, send event, delivery result
- [ ] Run 48 hours — zero duplicate alerts, zero missed alerts
All four must pass.

---

### STEP 2-B: Structured output validation layer (pre-Phase 3 gate)

Before Hermes touches any real email: validate structured output quality
using synthetic test fixtures.

Build a test harness: hermes_email_test.py

Test procedure:
- Create 10 synthetic test emails with known sender, subject, date, body, action items
- Run Hermes against each using the same model and prompt that will be used in Phase 3
- Compare output fields: sender, subject, date, summary, action items
- Log every test case and every field mismatch to hermes_audit.jsonl

Pass condition: 9 of 10 test emails correct on ALL fields with zero hallucinated content.
Hallucination definition: any invented sender name, wrong date, wrong subject,
or action item not present in the original email body.

If fewer than 9/10 pass: stay in Phase 2. Investigate model configuration.
Adjust prompt. Re-run full 10 synthetic tests from scratch. Do not promote to Phase 3.

Preserve synthetic fixtures: save to ~/Documents/hermes_handoff/test_fixtures/
These are permanent reference fixtures for future regression testing.

---

## PHASE 3 — SHOULD DO LATER

Do not start Phase 3 until Phase 2 validation passes AND 2-B synthetic test passes 9/10.

### STEP 3-A: Personal email reader (read-only)

Hermes reads personal email inbox and writes summaries to nightly handoff file.

What it does:
- Reads personal email inbox (read-only API access)
- Generates structured email summary
- Writes summary to "Email Summary" section of nightly handoff file
- Logs every read cycle and every summary write to hermes_audit.jsonl

What it does NOT do:
- Does not send any email
- Does not reply to any email
- Does not archive, delete, label, or modify any email
- Does not access work/Outlook email — that scope is disabled
- Does not write email data anywhere except the nightly handoff summary section

Scope: email_scope_personal only. email_scope_work remains "disabled".

Validation checkpoint before Phase 4:
- [ ] Chairman reviews nightly handoff email summaries every day for 14 days
- [ ] Zero hallucinated emails in 14 days (no invented senders, wrong dates, wrong subjects)
- [ ] Audit log shows a read cycle entry and a summary write entry for every night
- [ ] Chairman explicitly states "Phase 4 gate passed" before Cline does anything further
All four must pass. 14 days is the minimum — no shortcuts.

---

## PHASE 4 — SHOULD DO LATER

Do not start Phase 4 until 14-day Phase 3 validation is complete and Chairman
has explicitly approved "Phase 4 gate passed."

### STEP 4-A: Personal email approval loop

Hermes drafts email replies. Drafts are saved locally. Nothing is sent until
Chairman explicitly approves via Telegram command.

Draft workflow:
1. Hermes reads email and identifies messages that may warrant a reply
2. Hermes drafts a reply and saves it locally with a unique draft-id
3. Hermes sends Chairman a Telegram notification: "Draft ready: [draft-id] — reply /approve [draft-id] or /reject [draft-id]"
4. Chairman reviews draft content (Hermes must include draft text in notification or via /draft [id] command)
5. Chairman sends /approve [draft-id] → Hermes sends the email and logs the send event
   Chairman sends /reject [draft-id] → draft is permanently discarded and logged
6. No action is taken on any draft without an explicit /approve or /reject from Chairman

Hard rules:
- One email at a time — no batch approvals
- No bulk operations of any kind
- No email rules changes
- No archiving
- No labeling
- No deletion
- Send action requires a paired approval log entry — if approval log entry is missing, send is blocked

Audit log entries required for: draft created, notification sent, Chairman command received,
action taken (sent or discarded), send confirmation or send failure.

---

## PHASE 5 — SHOULD DO LATER

Do not start Phase 5 until Phase 4 approval loop has been stable for 14 days.

### STEP 5-A: Outlook work email

Same approval-loop model as Phase 4. No exceptions.

Additional rules specific to work email:
- email_scope_work must be changed from "disabled" to "active" in config by Chairman manually
- Work summaries appear in a separate section of the nightly handoff file — never merged with personal
- Work sender priority list is separate — never inherits personal email priorities
- Work approval gate is separate — a /approve for a personal draft cannot approve a work draft
- No promotion to autonomy at any point

---

## DO NOT DO (at any phase without explicit written Chairman doctrine update)

Cline must not implement any of the following regardless of instruction:

- Autonomous email sending without approval loop
- Email deletion or archiving of any kind
- Silent rule changes to Hermes behavior or config
- Write access to live Rex, Rexxie, or GOJ project folders
- Replacing or simulating Rexxie in any capacity
- Broad live repo authority
- Open WebUI — defer until after Phase 2 is stable; only add if Tauri dashboard
  is genuinely insufficient for Chairman workflow
- Shared Telegram bot token with Rexxie or any other bot
- Cloud model fallback of any kind without Chairman-documented override
- Cron-triggered Telegram sends before Phase 2 gate passes
- Shared config keys, rule-sets, or approval chains between personal and work email
- Any action that does not produce an audit log entry

---

## LOCKED CONFIG FILE

All Chairman-customizable values live in exactly one file.
Path: ~/Documents/hermes_handoff/hermes_config.json

Cline must not hardcode any value that appears in this config.
Cline must not create additional config files.

```json
{
  "model": "qwen3.5:9b",
  "base_url": "http://localhost:11434/v1",
  "handoff_folder": "~/Documents/hermes_handoff/",
  "audit_log_path": "~/Documents/hermes_handoff/logs/hermes_audit.jsonl",
  "open_items_path": "~/Documents/hermes_handoff/open_items.json",
  "test_fixtures_path": "~/Documents/hermes_handoff/test_fixtures/",
  "morning_run_time": "07:30",
  "nightly_run_time": "21:00",
  "telegram_gateway": "stopped",
  "alert_types_enabled": [],
  "heartbeat_timeout_hours": 4,
  "email_scope_personal": "none",
  "email_scope_work": "disabled",
  "cloud_routing_allowed": false,
  "phase_current": "phase_0"
}
```

Immutable rules for Cline:
- cloud_routing_allowed must never be set to true by Cline under any circumstance
- telegram_gateway starts as "stopped" — Chairman changes it to "active" manually
  after Phase 1 validation passes; Cline must not change this value
- alert_types_enabled is an empty array until Phase 2-A is built and validated
- email_scope_work must remain "disabled" until Chairman manually changes it for Phase 5
- phase_current is updated by Cline after each phase gate passes and Chairman approves

---

## RISK REGISTER

| Risk | Score | Trigger | Mitigation |
|------|-------|---------|------------|
| Anthropic key routes prompts to cloud | 9/10 | Key present in Hermes env | P0-1 + P0-2 routing verification |
| Tool/file hallucination | 8/10 | Unverified tool call output | Audit log hard rule — no claimed success without log entry |
| Scope creep from one autonomous exception | 8/10 | "Just this once" send without approval | Hard gate in spec — no exceptions at any phase |
| Drift to live project folder | 7/10 | Cline uses project path for a feature | P0-4 sandbox lock + config path enforcement |
| qwen3.5:9b email hallucination | 7/10 | Structured output failure on real email | 2-B synthetic test gate — 9/10 required before Phase 3 |
| Personal/work email rule contamination | 7/10 | Shared defaults leak between scopes | Email scope separation — hard rule, no shared config keys |
| Docker network exposure | 6/10 | Unknown Docker service exposes port | P0-3 clarification before any build |
| Telegram double-fire on gateway restart | 6/10 | Restart replays undelivered queue | Idempotency test required in 2-A checkpoint |
| Audit log write failure goes silent | 8/10 | Disk full, permissions error | Audit-first constraint — log failure aborts action |

---

## PHASE GATE SUMMARY

| Gate | Condition | Who approves |
|------|-----------|-------------|
| P0 → Phase 1 | All 6 preflight checkpoints confirmed passed | Chairman |
| Phase 1 → Phase 2 | All 6 Phase 1 checkpoints confirmed passed | Chairman |
| Phase 2 → Phase 3 | All Phase 2 checkpoints + 2-B synthetic test 9/10 passed | Chairman |
| Phase 3 → Phase 4 | 14 days clean summaries + zero hallucinations + explicit "Phase 4 gate passed" | Chairman |
| Phase 4 → Phase 5 | Phase 4 approval loop stable for 14 days | Chairman |

Chairman approval is required at every gate.
No gate may be self-certified by Cline or automated.

---

## INSTRUCTION TO CLINE

Read this document completely before doing anything.

Your first action after reading: ask Chairman to confirm Phase 0 status.
Ask explicitly: "Have all 6 Phase 0 preflight checkpoints been completed and confirmed?
Please confirm before I begin any build work."

If Chairman confirms Phase 0 is complete: begin Step 1-A only.
If Chairman has not confirmed Phase 0: stop and wait. Do not write any code.

Build only what the current phase specifies. Do not build ahead.
Do not interpret "should do later" as permission to build now.
Do not add features not listed in this spec without explicit Chairman approval.
When in doubt: ask. Do not assume. Do not proceed silently.

---

END OF SPEC — Version 1.2 — Authority: Chairman/Kato — 2026-04-21
