# Rexxie — Build Knowledge (2026-06-25 → 06-30 build)
> Loaded as Rexxie's context + stored in her encrypted memory. This is the full record of
> what Kato and the assistant built together. Local-only. Kato-only.
> Last updated 2026-06-30.

## Who's who (agents & lanes — kept SEPARATE)
- **Rexxie** = Kato's PRIVATE personal assistant. Local-only, encrypted (`rexxie.db`, triple-encrypted /
  Argon2). Talks to Kato over **Signal (end-to-end encrypted)**, brain = **local LLM**
  **`llama3.2:3b`** via Ollama (switched from mistral-hermie, which was ~48s/reply; llama3.2:3b
  replies in ~13s). Override with env `REXXIE_MODEL`. Perpetual memory. **Never cloud. Zero GOJ PHI.**
- **Victoria** = GOJ (Garden of Joy adult day care) client attendance caller. Retell cloud agent
  `agent_26e3746829ae6e174f4a012bbd` ("Victoria-GOJ"), number **646-760-3781**, voice cartesia-Elena.
  Handles client PHI → de-identified on anything outbound. (Deprecated twin: `agent_8a3265…` v2.)
- **Masha** = BBG (Boardwalk Beer Garden) receptionist. Retell agent `agent_305ba9…`, number
  **+1-877-768-2887** (Twilio, Kato-owned, being imported to Retell), background sound coffee-shop.
- **Numbers:** Victoria=646-760-3781 · Masha=877-768-2887 · Kato's cell=347-587-9913.

## Architecture decisions (Kato, this build)
- Rexxie, Victoria, Masha are **separate** builds, each own number + voice + memory.
- Rexxie is the **private** one: Signal + local brain + local memory, so it can call/text Kato
  without breaking "never cloud." Classic Rexxie privacy preserved.
- GOJ client PHI is **de-identified before any cloud** (Gate 1 / Presidio) and **never** enters
  Rexxie's memory raw.
- **Rexxie and the Chairman Assistant are BOTH built and SEPARATE** (the earlier "fold into one"
  idea was reversed): **Rexxie** = private, Signal, local brain, local memory. **Chairman Assistant**
  (`CC_chairman_assistant.py`) = Kato-only **SMS** line via Twilio, de-identifies through Gate 1/
  Presidio before any cloud LLM, PIN-gates sensitive actions. Different transport, different brain,
  same owner. Rexxie never touches GOJ PHI; the Chairman line only ever sends de-identified counts.

## What got fixed/built this session (GOJ OCR pipeline)
- **3 critical bugs** in `CC_signin_ocr.py`: (C1) header-skip phrases + removed 2 bad footer→client
  mappings; (C2) `write_to_db` is now an UPSERT on a partial unique index `idx_cs_unique
  (client_id,date,shift) WHERE deleted=0`; (C3) never writes NULL-client_id rows.
- **DB cleaned**: `client_signatures` purged 181,613 → 1,349 live (103k NULL + 77k dup soft-deleted),
  audit-logged. Script `CC_signin_db_purge.py`. Root cause: improve-loop reprocessing samples w/o dedup.
- **4-engine consensus** wired: Tesseract + Claude Vision (3×) + Paperless + Google Drive OCR, weighted
  vote. Vision/Drive send PHI to cloud → enabled by explicit Chairman override of Gate 1.
- **Daily OCR Telegram summary** (`CC_signin_ocr_report.py`) wired into the scan watcher.
- Match threshold raised 0.45 → 0.58 (env `REX_MATCH_THRESHOLD`).

## Security — red team / blue team (2 passes)
- **Presidio was silently broken** (`Pattern(flags=…)` crash) → de-id ran on regex that missed NAMES.
  Fixed (`(?i)` inline). THEN found the deeper cause: the live backend's **serving venv
  (`~/Desktop/REX/.venv`) lacked presidio/spacy** (`.rex-venv` is a DECOY; the uvicorn shebang points
  to the real `.venv`). Installed presidio + `en_core_web_lg` there; `/api/health` now reports
  `deid_engine: Presidio`. **Real venv = `~/Desktop/REX/.venv`.**
- **Fail-closed PHI gate** added to `backend/main.py`: secure-mode cloud chat 503s if de-id degraded.
- Closed PHI-leak paths: no client names to Telegram/logs, basename-only source_pdf, HTML-escape,
  PDF page cap, atomic learning-store write, IMAP watcher hardening (magic-byte, path-traversal,
  sender re-verify, whole-word subject routing).
- `akc_tokenizer.py` (Gate 1) v1 built at `~/Desktop/dashboard/` — text-only de-id gate, fail-closed.
- **Still open (Kato):** rotate exposed secrets (Anthropic/Telegram/Paperless/etc.); auth_tracker.db
  unencrypted; dashboard localhost-auth bypass; TOTP is the RFC example secret.

## Memory audit (corrected wrong facts — these were WRONG in old memory)
- Google OAuth token serves Gmail AND **full Drive** (5 scopes); IMAP is an extra path, not separate.
  **Gmail = IMAP only (App Password), never OAuth** (per CLAUDE.md). Drive = OAuth.
- Dashboard runs from `~/Documents/goj files/dashboard/` (gunicorn datarex.app:app :8080 + app.py :8090);
  the old `~/.hermes-cloud/…/datarex/app.py` path is GONE.
- 6 cited cron IDs are DEAD; real automation = launchd + Hermes cron (6) + n8n (6).
- `goj_proprietary.db` real copy = `~/Documents/goj files/proprietary/` (the REX-root one is a 0-byte stub).
- MiniMax key present (not "lost"); rex_memory.db 28KB (not 0); rexxie-bot plist already deleted.

## Staged `.command` files (Kato runs these — harness blocks the agent from live changes)
- `CC_upgrade_victoria.command` — Victoria: bilingual + natural voice + coffee-shop background + prompt.
- `CC_upgrade_masha.command` — Masha: full BBG brain + bilingual + natural + gpt-4.1.
- `CC_fix_victoria_routing.command` — point 646 number at canonical Victoria 26e3.
- `CC_bind_masha_number.command` / `CC_import` — bind Masha's 877 once imported to Retell.
- `CC_BBG_NUMBER_UNTANGLE.md` — separate Masha from Victoria's number.
- `CC_install_owner_poller.command` — BBG owner.com reservation polling (5-min).
- `CC_chairman_notify.py` (+ installer) — daily de-id call summary → SMS to Kato 347.
- `CC_check_877_voice_conflict.command` — verified 877 is SMS-only, safe to import (just demo webhooks).

## Assistant-stack hardening + go-live (2026-06-30, red team → blue team)
Surgical security pass on both private agents. Baseline never broke (backend `/api/health` stayed
`ok`/Presidio, `rexxie.db` intact). Pre-pass snapshot: `CC_session_snapshots/20260627_024133`.
- **Rexxie (`CC_rexxie_signal.py`)** — CRITICAL: sender auth was suffix-match (a foreign number ending
  in Kato's digits could impersonate him) → fixed to exact full-E.164 on `sourceNumber`. CRITICAL:
  added reply-loop guard (only `dataMessage`, skip own number, ordered dedup by timestamp, backoff).
  HIGH: removed Kato's phone from the system prompt; LLM endpoint now hard-refuses at import unless
  localhost + rejects cloud model names — this is what lets this very knowledge file stay COMPLETE
  (it physically can't leave the Mac). Memory recall now uses `RexxieMemory.get_recent(n)`.
- **Chairman Assistant (`CC_chairman_assistant.py`)** — CRITICAL: Twilio webhook now validates
  `X-Twilio-Signature` **fail-closed**; PIN prompt bound to sender + 5-min expiry + 3-strike→15-min
  lockout. HIGH: session file atomic `0o600`; Gate-1 PHI-block vs import error split so PHI never
  leaks on a swallowed exception.

## How to go live — ONE command + what only Kato can do
- **`CC_bringup_assistants.command`** — idempotent orchestrator: ensures Ollama+`llama3.2:3b`,
  smoke-tests both brains locally, starts every ready service, prints a checklist for the rest.
- Persistent services (launchd, KeepAlive): `CC_install_rexxie_signal.command` (Signal brain),
  `CC_install_chairman_assistant.command` (SMS webhook :8110, fail-closed), `CC_install_chairman_notify.command`
  (daily 3 PM de-id SMS summary). `CC_install_hermes_memory.command` installs this archive's sibling
  (`CC_HERMES_KNOWLEDGE.md`) into the uchg-locked `MEMORY.md` (backs up + pauses for confirm).
- **Only Kato can finish:** (1) link Rexxie to Signal — `signal-cli link -n "Rexxie"`, scan QR in
  phone → Linked Devices; (2) set in `~/.hermes/.env`: `CHAIRMAN_PIN`, `TWILIO_AUTH_TOKEN`,
  `CHAIRMAN_WEBHOOK_URL` (public tunnel URL); (3) Twilio console → point the number's Messaging
  webhook at `CHAIRMAN_WEBHOOK_URL` → :8110. Then re-run the one command → "fully live."
- **Still open (Kato, security):** rotate exposed secrets; `auth_tracker.db` unencrypted (SQLCipher
  pending); TOTP is the RFC example secret; install this file into the locked `MEMORY.md` needs his PIN.

## Personal-assistant intent (Rexxie)
Kato wants Rexxie to learn + remember everything about his world (perpetual memory), reachable by
encrypted Signal text (voice later via a local pipeline). She should know this entire build and keep
learning. Private, local, his alone.
