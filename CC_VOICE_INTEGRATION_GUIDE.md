# CC_VOICE_INTEGRATION_GUIDE.md
# Voice Agent Integration — Victoria (GOJ) & Masha (BBG)
# Gold Health Systems · v1.0 · June 2026

---

## ⚠️ CURRENT STATUS: BOTH AGENTS ARE DEAD

| Agent    | Business | Status          | Blocker                    |
|----------|----------|-----------------|----------------------------|
| Victoria | GOJ      | ❌ INACTIVE     | Retell API key expired     |
| Masha    | BBG      | ❌ INACTIVE     | Retell API key expired     |

**One action unblocks both:** Renew the Retell AI subscription at https://retell.ai
and generate a new API key. Both agents share the same Retell account.

---

## Reactivation Checklist

### Step 1 — Renew Retell Subscription
1. Go to https://retell.ai → log in to the Gold Health Systems account
2. Navigate to Billing → renew the subscription
3. Go to API Keys → create a new API key (or rotate the existing one)
4. Copy the new key — it starts with `key_...`

### Step 2 — Update the API Key
Update in two places:

**In `~/.rex/config.json`:**
```json
{
  "RETELL_API_KEY": "key_..."
}
```

**In your shell environment** (add to `~/.zshrc` or set in launchd plist):
```bash
export RETELL_API_KEY="key_..."
```

For the Masha service (port 8100), set the same key in its launchd plist
`EnvironmentVariables` dict.

### Step 3 — Confirm Agent IDs in Retell Dashboard
1. Log into Retell dashboard → Agents
2. Locate **Victoria** → copy the agent ID (format: `agent_...`)
3. Locate **Masha** → copy the agent ID
4. Set environment variables:

```bash
export VICTORIA_AGENT_ID="agent_..."
export MASHA_AGENT_ID="agent_..."
```

Or add to `~/.rex/config.json`:
```json
{
  "VICTORIA_AGENT_ID": "agent_...",
  "MASHA_AGENT_ID":    "agent_..."
}
```

### Step 4 — Confirm Phone Numbers
1. In Retell dashboard → Phone Numbers
2. Confirm which number is assigned to Victoria (GOJ) and which to Masha (BBG)
3. Update in environment or config:

```bash
export VICTORIA_FROM_PHONE="+1XXXXXXXXXX"   # GOJ phone
export MASHA_FROM_PHONE="+1XXXXXXXXXX"       # BBG phone
```

In `CC_victoria_goj_integration.py` and `CC_masha_bbg_integration.py`,
these are read from env with `os.getenv(...)`.

### Step 5 — Mount Victoria in REX main.py
Add these two lines to `~/Desktop/REX/backend/main.py` inside the lifespan
startup block (around line 148, alongside the other router mounts):

```python
try:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from CC_victoria_goj_integration import victoria_router
    app.include_router(victoria_router, prefix="/victoria")
    logger.info("✅ Victoria (GOJ voice agent) mounted at /victoria")
except Exception as _vic_err:
    logger.warning(f"⚠️ Victoria router not loaded: {_vic_err}")
```

Victoria endpoints will then be live at:
- `GET  http://localhost:8000/victoria/status`
- `POST http://localhost:8000/victoria/call/auth-reminder`
- `POST http://localhost:8000/victoria/call/run-daily-reminders`
- `POST http://localhost:8000/victoria/call/auth-expired-notify`
- `POST http://localhost:8000/victoria/call/driver-noshow`
- `POST http://localhost:8000/victoria/webhook/inbound`

### Step 6 — Start Masha as a Separate Service
Masha is a standalone FastAPI app (BBG is separate from GOJ — no shared DB).

**Dev mode:**
```bash
source ~/debate-chamber/.venv/bin/activate
cd ~/Desktop/REX
uvicorn CC_masha_bbg_integration:app --host 0.0.0.0 --port 8100 --reload
```

**Production — create launchd plist** at
`~/Library/LaunchAgents/com.bbg.masha.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.bbg.masha</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/mainsobhelper/.rex-venv/bin/uvicorn</string>
        <string>CC_masha_bbg_integration:app</string>
        <string>--host</string><string>0.0.0.0</string>
        <string>--port</string><string>8100</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/mainsobhelper/Desktop/REX</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>RETELL_API_KEY</key><string>key_...</string>
        <key>MASHA_AGENT_ID</key><string>agent_...</string>
        <key>MASHA_FROM_PHONE</key><string>+1XXXXXXXXXX</string>
    </dict>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key>
    <string>/Users/mainsobhelper/Desktop/REX/logs/masha.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/mainsobhelper/Desktop/REX/logs/masha.err</string>
</dict>
</plist>
```

Load it:
```bash
launchctl load ~/Library/LaunchAgents/com.bbg.masha.plist
```

Masha endpoints will be live at:
- `GET  http://localhost:8100/health`
- `GET  http://localhost:8100/masha/status`
- `GET  http://localhost:8100/masha/reservations`
- `POST http://localhost:8100/masha/reservations`
- `POST http://localhost:8100/masha/call/event-promo`
- `POST http://localhost:8100/masha/webhook/inbound`
- `POST http://localhost:8100/masha/webhook/instagram-dm`

### Step 7 — Configure Retell Webhooks
In the Retell dashboard, for each agent, set the webhook URL:

| Agent    | Webhook URL                                        |
|----------|----------------------------------------------------|
| Victoria | `https://<cloudflare-tunnel>/victoria/webhook/inbound` |
| Masha    | `https://<cloudflare-tunnel>/masha/webhook/inbound`    |

The Cloudflare tunnel (`hermestigerclaw.yml`) already routes external HTTPS to
the local stack. If Masha runs on port 8100, add a route in the tunnel config
or proxy through nginx.

### Step 8 — Configure n8n Triggers

**Victoria daily reminders (10:00 AM):**
- n8n Schedule trigger → `POST http://localhost:8000/victoria/call/run-daily-reminders`

**Victoria driver no-show check (7:45 AM):**
- n8n Schedule trigger → check driver route status → if not started,
  `POST http://localhost:8000/victoria/call/driver-noshow`
  with body `{"driver_name": "...", "backup_driver_phone": "+1...", "backup_driver_name": "..."}`

**Instagram DM bridge (Masha):**
- n8n Instagram trigger → extract `sender_id` + `message_text` →
  `POST http://localhost:8100/masha/webhook/instagram-dm`

---

## ElevenLabs Voice Assignments

Both agents use ElevenLabs voices configured inside the Retell agent settings
(not in these Python files). The ElevenLabs API key is separate from Retell.

| Agent    | Voice Character                          | ElevenLabs Voice ID          |
|----------|------------------------------------------|------------------------------|
| Victoria | Formal, warm, female EN-US               | ⚠️ Pull from ElevenLabs account |
| Masha    | Friendly, slightly playful, female EN-US | ⚠️ Pull from ElevenLabs account |

**To find/assign voice IDs:**
1. Log into https://elevenlabs.io
2. Voice Library → note the voice ID for each character
3. In Retell dashboard → Agent settings → Voice → select ElevenLabs → paste ID
4. Test with a sample phrase before going live

Recommended ElevenLabs voices to audition for Victoria: Rachel, Domi, or Bella
(professional, clear diction, warm). For Masha: Freya or Serena (friendly, 
conversational energy).

---

## Testing Checklist

### Victoria (GOJ)
- [ ] `GET http://localhost:8000/victoria/status` — returns `retell_configured: true`
- [ ] `POST /victoria/call/auth-reminder` with `{"client_id": <test_id>}` — call fires
- [ ] `POST /victoria/call/run-daily-reminders` — lists expiring clients + queues calls
- [ ] `POST /victoria/webhook/inbound` with mock Retell payload — event logged in victoria_call_log
- [ ] Sick-day: simulate inbound call with `custom_data.sick_day_reported = true` — attendance_log updated + Telegram fires
- [ ] `POST /victoria/call/driver-noshow` with mock body — backup driver call queued
- [ ] `GET /victoria/status` after calls — recent_calls populated

**Manual DB check:**
```bash
sqlite3 ~/Documents/goj\ files/dashboard/auth_tracker.db \
  "SELECT * FROM victoria_call_log ORDER BY id DESC LIMIT 10;"
```

### Masha (BBG)
- [ ] `GET http://localhost:8100/health` — `{"status": "ok"}`
- [ ] `GET /masha/status` — returns `retell_configured: true`
- [ ] `POST /masha/reservations` with test data — written to CC_bbg_reservations.json
- [ ] `GET /masha/reservations` — returns today's reservations
- [ ] `POST /masha/webhook/inbound` with mock Retell `call_ended` + reservation data — auto-created in JSON
- [ ] `POST /masha/webhook/instagram-dm` with reservation intent — logged in reservations JSON
- [ ] `POST /masha/call/event-promo` with `vip_phones: ["+1TESTNUM"]` — promo call queued

**Manual reservations check:**
```bash
cat ~/Desktop/REX/CC_bbg_reservations.json | python3 -m json.tool
```

---

## HIPAA Note — Victoria / GOJ

Victoria handles PHI (client full names, attendance status, authorization expiry
dates). Before going live with Victoria on GOJ calls, the following are required:

1. **Retell BAA** — Retell AI must have a signed Business Associate Agreement
   with Gold Health Systems. Request this from Retell's compliance/sales team.
   Do not process real client calls without a BAA in place.

2. **ElevenLabs BAA** — If ElevenLabs processes the voice synthesis for live
   client calls, a BAA with ElevenLabs is also required.

3. **Call logging** — All Victoria calls are logged to `victoria_call_log` in
   `auth_tracker.db`. This table must be included in the auth_tracker.db
   encryption plan (SQLCipher — currently an open item per CLAUDE.md).

4. **Transcript storage** — Retell can store call transcripts. Review Retell's
   data retention policy and disable cloud transcript storage if needed until
   PHI handling is confirmed compliant.

5. **Gate 1 (akc_tokenizer.py)** — Per CLAUDE.md, this gate blocks all cloud
   PHI routing until fully built. Victoria's outbound metadata (client name +
   expiry date) constitutes PHI and flows to Retell's cloud infrastructure.
   Confirm Gate 1 status with Kato before enabling live calls.

**Masha / BBG does not handle PHI.** Beer garden reservations (name, phone,
party size) are not covered under HIPAA. Standard data hygiene applies.

---

## Architecture Summary

```
GOJ Stack (port 8000 — REX FastAPI)
  └── /victoria  ← CC_victoria_goj_integration.py (router)
        ├── reads auth_tracker.db  ← expiring/expired clients
        ├── calls Retell API       ← outbound calls
        ├── receives Retell webhook ← inbound call events
        └── fires Telegram alerts  ← via rex_notify_config.json

BBG Stack (port 8100 — standalone FastAPI)
  └── /masha  ← CC_masha_bbg_integration.py (app)
        ├── reads/writes CC_bbg_reservations.json
        ├── calls Retell API       ← outbound calls
        ├── receives Retell webhook ← inbound call events
        └── receives Instagram DMs ← via n8n bridge

Shared dependency: Retell AI account (one key, two agents)
⚠️ BLOCKED: key expired — one renewal unblocks both
```

---

## Files Created

| File | Location | Purpose |
|------|----------|---------|
| `CC_victoria_goj_integration.py` | `~/Desktop/REX/` | Victoria FastAPI router |
| `CC_masha_bbg_integration.py` | `~/Desktop/REX/` | Masha standalone FastAPI app |
| `CC_VOICE_INTEGRATION_GUIDE.md` | `~/Desktop/REX/` | This document |
| `CC_bbg_reservations.json` | `~/Desktop/REX/` | Auto-created on first reservation |
| `CC_bbg_vip_list.json` | `~/Desktop/REX/` | Create manually for event promos |

**VIP list format (`CC_bbg_vip_list.json`):**
```json
[
  {"phone": "+1XXXXXXXXXX", "name": "Jane Doe"},
  {"phone": "+1XXXXXXXXXX", "name": "John Smith"}
]
```
