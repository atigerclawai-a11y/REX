# Chairman Assistant — Deploy Runbook
**2026-06-26 · Take the built SMS handler live + add voice.**

## Built & tested (no wiring needed)
- `CC_chairman_assistant.py` — SMS handler. Kato-only (347-587-9913 → chairman mode; others →
  "private line"), PIN for sensitive actions, de-identified to the cloud LLM (Gate 1), command
  shortcuts (`help`, `results`), Claude fallback for free-form. Verified via CLI.
- `CC_chairman_notify.py` + `CC_install_chairman_notify.command` — daily de-id call summary → SMS to Kato.

## Decision locked
Dedicated line for the assistant (NOT Kato's 347 cell, NOT Masha's 877). Local **646/718**.

---

## STEP 1 — Set the PIN (you)
Add to `~/.hermes/.env`:  `CHAIRMAN_PIN=<a number only you know>`
(Gates timesheets / data pulls — a spoofed text can't pull data without it.)

## STEP 2 — Get a dedicated 646/718 number
Provision a Twilio number (SMS handler is a Twilio Messaging webhook):
- Twilio Console → Phone Numbers → Buy a number (area 646 or 718, SMS+Voice).
- Or via API with your Twilio creds. Note the number — call it `ASSISTANT_NUMBER`.

## STEP 3 — Run the SMS handler as a service + expose it
1. Run it under launchd (port 8110):
```bash
PLIST=~/Library/LaunchAgents/com.goj.chairman-assistant.plist
cat > "$PLIST" <<XML
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
 <key>Label</key><string>com.goj.chairman-assistant</string>
 <key>ProgramArguments</key><array>
   <string>$HOME/Desktop/REX/.venv/bin/python3</string>
   <string>$HOME/Desktop/REX/CC_chairman_assistant.py</string><string>--serve</string></array>
 <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
 <key>StandardOutPath</key><string>$HOME/Desktop/REX/logs/chairman_assistant.log</string>
 <key>StandardErrorPath</key><string>$HOME/Desktop/REX/logs/chairman_assistant.err</string>
</dict></plist>
XML
launchctl bootstrap gui/$(id -u) "$PLIST"
```
2. Expose :8110 publicly via your existing **Cloudflare tunnel** (`~/.cloudflared/hermestigerclaw.yml`) —
   add an ingress rule mapping a hostname (e.g. `chairman.tigerclaw...`) → `http://127.0.0.1:8110`,
   then restart the tunnel. Note the public URL → `WEBHOOK_URL`.

## STEP 4 — Point the number's SMS webhook at the handler
Twilio Console → your `ASSISTANT_NUMBER` → Messaging → "A message comes in" →
Webhook (HTTP POST) → `WEBHOOK_URL`. Save.
Test: text the number "results" from your phone → you should get the de-id GOJ summary.

## STEP 5 (voice) — add a Retell chairman voice agent
For "call it for answers": create a Retell agent (chairman persona, bilingual, gpt-4.1),
bind `ASSISTANT_NUMBER` to it (inbound+outbound). Mirror `CC_upgrade_masha.command` to build it.
For voice→data actions (results/timesheets), give it a custom function pointing at the handler.
(Build this as a follow-up once the SMS half is confirmed live.)

---

## OPEN inputs (to finish)
1. `CHAIRMAN_PIN` (Step 1).
2. `ASSISTANT_NUMBER` (Step 2) — 646/718.
3. Cloudflare tunnel hostname for :8110 (Step 3).
4. **Staff timesheet source** — `employees` table? Carecenta export? spreadsheet? (for the PIN-gated timesheets action; currently stubbed).
5. A name for the assistant (not "Rexxie").

## Security posture (already enforced in code)
- Kato-only; others get "private line."  • PIN before sensitive actions.
- GOJ data de-identified before any cloud LLM (Gate 1 / Presidio).  • Rexxie's private lane untouched.
