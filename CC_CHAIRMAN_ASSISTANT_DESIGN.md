# Chairman Assistant — Design
**2026-06-25 · Kato's personal voice+SMS assistant. Decisions locked below.**

## Decision (Kato, 2026-06-25)
- **Separate lanes.** Rexxie stays the local-only/encrypted/zero-GOJ private confidant — UNCHANGED.
  Victoria stays the GOJ client agent — UNCHANGED. Build a NEW "Chairman Assistant."
- **De-identified to cloud by default.** The cloud agent never receives raw GOJ PHI or
  Rexxie private content unless Kato explicitly authorizes that send, per-action.

## Three lanes (never cross)
| Lane | What | Cloud? | Data |
|------|------|--------|------|
| Victoria-GOJ | client attendance calls/SMS | Retell cloud | GOJ PHI (de-id'd outbound) |
| **Chairman Assistant (NEW)** | Kato's personal voice+SMS | Retell cloud | de-identified by default |
| Rexxie | private confidant | LOCAL only | Kato-only, encrypted, never cloud |

## Chairman Assistant — capabilities
- Bilingual (RU/EN), natural voice (11labs multilingual), takes messages.
- **Call results to Kato** after each Victoria run → de-identified by default (counts + initials);
  full names only via secure local delivery (see below) on explicit request.
- **Staff timesheets for payroll** → NEVER spoken/texted through the cloud agent. The voice/SMS
  agent triggers a LOCAL action that generates the timesheet and delivers it via a secure channel
  (email/local dashboard/encrypted Telegram), then says "sent to your email."
- **Ask-a-question Q&A** (ops, schedule, status).
- **Bridge to Rexxie:** can notify/relay TO Rexxie's local lane, but Rexxie's private content
  never flows back out to the cloud agent.

## Enforcement: the de-id gate (reuses this session's work)
Every payload bound for the cloud agent passes through `akc_tokenizer.py` (Gate 1) /
`DeidentificationEngine` (Presidio, repaired 2026-06-25). If it still contains PHI/PII after
tokenization → it does NOT go to the cloud agent; it goes via secure local delivery instead.

## Auth (sender-number is spoofable)
- Chairman mode triggers on Kato's number, BUT privileged actions (timesheets, data pulls,
  commands) require a **PIN/confirmation** — a spoofed text can't pull payroll or client data.

## Architecture
```
Inbound SMS/voice → Retell (number TBD, custom_sms_enabled)
   → webhook handler (local, via Cloudflare tunnel)
      → role router: Kato# → chairman mode (PIN for privileged) | else → client mode
         → de-id gate (Gate 1) for anything cloud-bound
         → sensitive data → SECURE LOCAL DELIVERY (email/dashboard/Telegram), not cloud
         → reply via Retell SMS / voice
```
Handler is local code (mine to write). Retell agent + number + SMS enablement get packaged as a
`.command` (harness blocks an agent from creating live cloud agents/numbers).

## Kato's number (provided 2026-06-26)
- **`+1-347-587-9913`** = Kato's personal cell. The assistant CALLS and TEXTS Kato here.
  Texts/calls FROM this number → **chairman mode** (subordinate behavior), gated by PIN for
  privileged actions (timesheets, data pulls). Already his contact in CC_imessage_cascade.py,
  ghl_data/contacts.json, CC_victoria_report.html.

## OPEN — still needed from Kato to build
1. ~~Kato's SMS phone number~~ → **+1-347-587-9913** (done).
2. **Dedicated number for the Chairman Assistant?** (recommended — keep it off Victoria's public GOJ number) — provision a new Retell number, or reuse one?
3. **Staff timesheet source** — `employees` table? Carecenta export? spreadsheet? (where payroll hours live)
4. **Secure-delivery channel** for sensitive data — email to Kato? local dashboard? encrypted Telegram (@goldhealth_rexxie_bot)?
5. A **name** for the Chairman Assistant (not "Rexxie" — that's the private lane).

## Build order (once inputs land)
1. Local handler skeleton: role router + de-id gate + secure-delivery + PIN. (no cloud — buildable now)
2. Provision/enable the Retell agent + number + SMS (packaged .command).
3. Wire call-results-to-Kato (hooks Victoria's run) + fallback SMS.
4. Timesheet action (local generate + secure deliver).
5. Two-way conversational LLM (chairman + client modes).
