# CC_attendance_bot — Setup & Operations Guide
## Garden of Joy Attendance Bot
### Last updated: June 2026

---

## What this does

Incoming WhatsApp message → **fuzzy-match client → atomic 7-cascade → reply in group chat**

Staff types: `Berta Sivak won't be in tomorrow`
Bot replies:
```
✅ CASCADE COMPLETE — Berta Sivak — 6/5/2026 (Thu)
Reason: Not specified | Logged by: Maria

Updated:
📅 Calendar — removed
📋 Attendance — marked absent
🚐 Driver list — flagged (PDF regenerated at 3:15 PM)
🍽 Kitchen list — -1 portion flagged
📦 Distribution — removed
📝 Sign-in sheet — marked absent
🥗 Menu — marked absent

Time: 8:42 AM | Sent by: Maria
Reply UNDO Berta Sivak to reverse. (ref #47)
```

---

## Part 1: Environment Variables

Add to `~/.hermes/profiles/cloud/.env` (or wherever REX loads its env):

```bash
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_WHATSAPP_NUMBER=+14155238886   # Your Twilio WhatsApp number (sandbox or production)
```

Restart REX after setting:
```bash
launchctl unload ~/Library/LaunchAgents/com.rex.backend.plist
launchctl load  ~/Library/LaunchAgents/com.rex.backend.plist
```

---

## Part 2: Mount router in main.py

Add these 3 lines to `~/Desktop/REX/backend/main.py`:

**Import** (near the top, after existing imports ~line 82):
```python
from .CC_attendance_bot import attendance_router
```

**Mount** (inside the `lifespan` function, after the other `app.include_router` calls, ~line 163):
```python
app.include_router(attendance_router, prefix="/attendance-bot")
app.include_router(attendance_router, prefix="/api/attendance-bot")   # optional alias
logger.info("✅ Attendance Bot mounted at /attendance-bot")
```

**Verify** after restart:
```bash
curl http://localhost:8000/attendance-bot/today
```

---

## Part 3: Install dependencies

```bash
pip install rapidfuzz dateparser twilio --break-system-packages
```

Verify:
```bash
python3 -c "import rapidfuzz, dateparser, twilio; print('all ok')"
```

---

## Part 4: Twilio WhatsApp — Sandbox (Testing)

1. Sign up at https://www.twilio.com
2. Go to **Messaging → Try it out → Send a WhatsApp message**
3. Note your sandbox number (usually `+14155238886`)
4. Set `TWILIO_WHATSAPP_NUMBER=+14155238886` in your env
5. Each staff member who tests must join the sandbox:
   - Send `join <sandbox-word>` to the sandbox number from their WhatsApp
6. Set webhook in Twilio console:
   - **Sandbox configuration → When a message comes in:**
   - URL: `https://your-cloudflare-tunnel.trycloudflare.com/attendance-bot/webhook`
   - Method: `POST`

Your Cloudflare tunnel URL is in `~/.cloudflared/hermestigerclaw.yml`.

---

## Part 5: Twilio WhatsApp — Production

1. Apply for a WhatsApp Business number in Twilio console:
   - **Messaging → Senders → WhatsApp senders → Request access**
   - Requires: business name, website, Facebook Business Manager ID
   - Approval: 1–5 business days from Meta
2. Once approved, set:
   ```bash
   TWILIO_WHATSAPP_NUMBER=+1XXXXXXXXXX   # your approved production number
   ```
3. Update webhook URL in Twilio production settings:
   - **Phone Numbers → Manage → Active Numbers → your number → Messaging**
   - Webhook: `https://your-cloudflare-tunnel.trycloudflare.com/attendance-bot/webhook`
4. Add the GOJ WhatsApp number to each of the 3 staff groups (see Part 7)

---

## Part 6: Test with /manual (no WhatsApp needed)

Test the full cascade without any Twilio setup:

```bash
# Basic absence
curl -s -X POST http://localhost:8000/attendance-bot/manual \
  -H 'Content-Type: application/json' \
  -d '{"message": "Berta Sivak won'\''t be in tomorrow", "sender_name": "Kato"}'

# Specific date
curl -s -X POST http://localhost:8000/attendance-bot/manual \
  -H 'Content-Type: application/json' \
  -d '{"message": "Ivanova is sick on Friday", "sender_name": "Staff"}'

# Partial name (last name only)
curl -s -X POST http://localhost:8000/attendance-bot/manual \
  -H 'Content-Type: application/json' \
  -d '{"message": "Sivak won'\''t be here Monday", "sender_name": "Test"}'

# UNDO
curl -s -X POST http://localhost:8000/attendance-bot/manual \
  -H 'Content-Type: application/json' \
  -d '{"message": "UNDO Berta Sivak", "sender_name": "Kato"}'

# View today's log
curl http://localhost:8000/attendance-bot/today | python3 -m json.tool

# View audit log
curl http://localhost:8000/attendance-bot/audit | python3 -m json.tool

# Undo by log_id
curl -s -X POST "http://localhost:8000/attendance-bot/undo/47?reason=test"
```

---

## Part 7: Group Chat Setup — Adding the WhatsApp Number

Once you have the production number:

1. Open WhatsApp on your phone
2. Go to each of the 3 GOJ staff groups:
   - **Group 1**: [name of group 1]
   - **Group 2**: [name of group 2]  
   - **Group 3**: [name of group 3]
3. Tap the group name → **Add members** → paste the GOJ WhatsApp bot number
4. The bot will now receive all messages in those groups
5. It only responds to absence-pattern messages — all other messages are ignored

---

## Part 8: iMessage Bridge (Fallback — 3 existing groups)

While the WhatsApp migration is underway, use this AppleScript bridge to forward
iMessage group messages to the bot endpoint.

**Option A: Run manually from Terminal**
```bash
# Save as ~/Desktop/REX/imessage_bridge_test.sh
curl -s -X POST http://localhost:8000/attendance-bot/imessage \
  -H 'Content-Type: application/json' \
  -d "{\"message\": \"$1\", \"sender_name\": \"$2\", \"group_name\": \"GOJ Staff\"}"
```
Usage: `./imessage_bridge_test.sh "Berta Sivak not coming Tuesday" "Maria"`

**Option B: AppleScript monitor (advanced)**

Save as `~/Desktop/REX/CC_imessage_monitor.scpt`:
```applescript
-- Run periodically via launchd or manually
-- Reads the last 10 messages from the GOJ Staff iMessage group
-- and posts any absence-pattern ones to the attendance bot

set groupName to "GOJ Staff"  -- change to exact group name

tell application "Messages"
    set targetChat to missing value
    repeat with aChat in chats
        if name of aChat is groupName then
            set targetChat to aChat
            exit repeat
        end if
    end repeat
    
    if targetChat is missing value then return "Group not found"
    
    -- Get recent messages (AppleScript Messages access is limited — this is a stub)
    -- Full implementation requires macOS Messages database access
    -- See: ~/Desktop/REX/CC_imessage_reader.py for SQLite-based approach
end tell
```

**Option C: Messages SQLite direct (recommended for automation)**

macOS stores iMessages at `~/Library/Messages/chat.db`. A background script
can poll this DB and POST to the attendance bot endpoint.

```bash
# Grant Full Disk Access to Terminal in:
# System Settings → Privacy & Security → Full Disk Access → Terminal ✅

# Then run: ~/Desktop/REX/CC_imessage_poller.py (not yet built — see ticket)
```

> **Priority**: Get WhatsApp production number approved. iMessage bridge is a
> fallback only and requires Full Disk Access grant.

---

## Part 9: Staff Training Guide

### What messages work

The bot listens for **absence reports** — messages that tell it someone won't be at GOJ.

**✅ These work:**

| Message | What the bot hears |
|---|---|
| `Berta Sivak won't be in tomorrow` | Berta Sivak, tomorrow, no reason |
| `Sivak is sick today` | Sivak (fuzzy match), today, Medical |
| `Maria Ivanova not coming Monday` | Maria Ivanova, next Monday |
| `Mrs. Sivak absent Friday` | Berta Sivak, this Friday |
| `Berta calling in sick` | Berta Sivak, tomorrow, Medical |
| `Petrov won't make it June 10` | Petrov, June 10 |
| `Ivanova hospital tomorrow` | Ivanova, tomorrow, Medical |
| `UNDO Berta Sivak` | Reverses her last cascade |

**❌ These don't work (bot ignores them):**

| Message | Why |
|---|---|
| `Good morning everyone!` | No absence trigger words |
| `What's the menu today?` | No absence trigger words |
| `Call Berta` | No absence trigger words |
| `B.S. out tomorrow` | Initials — below match threshold (use full name) |

### Rules of thumb

1. **Always say a name** — first + last is best, last name alone usually works
2. **Say why if you know** — "sick", "hospital", "vacation" gets logged automatically
3. **Tomorrow is the default** — if you don't say a date, tomorrow is assumed
4. **UNDO works** — type `UNDO [full name]` to reverse the last cascade for that client
5. **The bot only responds to the group** — other messages are silently ignored

### What happens after you send

Within ~5 seconds you'll see the `✅ CASCADE COMPLETE` confirmation in the group.
If you see `❌`, read the message — it'll tell you exactly what's wrong.

### Who to contact

If the bot stops responding: **Kato** (Telegram: @Hermes_Cloud_May_bot or SMS)

---

## Part 10: Monitoring & Logs

```bash
# Live bot log
tail -f ~/.hermes/profiles/cloud/logs/gateway.log | grep attendance_bot

# REX log
tail -f ~/Desktop/REX/logs/rex.log

# Bot audit via API
curl http://localhost:8000/attendance-bot/audit | python3 -m json.tool

# Today's absences
curl http://localhost:8000/attendance-bot/today | python3 -m json.tool

# Refresh client cache after adding clients to DB
curl -X POST http://localhost:8000/attendance-bot/refresh-clients
```

---

## Part 11: Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Bot doesn't respond at all | Twilio webhook not set or wrong URL | Check Twilio console → Sandbox settings |
| "Couldn't identify the client" | Name not fuzzy-matching | Use full name; check if client is active in DB |
| "Multiple clients found" | Two clients with similar names | Bot will list options; resend with full name |
| Cascade partial (some steps fail) | Table doesn't exist yet (optional tables) | Bot will still log; optional tables are no-ops |
| UNDO not working | No successful cascade for that client | Check audit log for the log_id |
| `ModuleNotFoundError: rapidfuzz` | Dependencies not installed | `pip install rapidfuzz dateparser twilio --break-system-packages` |
| Twilio 403 / signature error | Webhook URL mismatch | Ensure URL in Twilio matches your live Cloudflare URL exactly |
