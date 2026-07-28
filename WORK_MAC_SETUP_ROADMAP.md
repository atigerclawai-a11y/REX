# REX — Work Mac Setup Roadmap
### GOJ Office Machine (MacBook or Mac at GOJ)

---

## What the Work Mac gets vs. the Personal Mac Mini

| Feature | Personal Mac Mini (Home) | Work Mac (GOJ Office) |
|---|---|---|
| REX backend | ✅ Full | ✅ Full |
| GOJ staff dashboard | ✅ Yes | ✅ Yes |
| Rexxie personal mode | ✅ Yes (personal) | ❌ No — work only |
| Credential vault | ✅ Yes (Rexxie) | ❌ No |
| Phone unlock (Face ID) | ✅ Yes | ✅ Yes (optional) |
| Proximity daemon | ✅ Yes | ✅ Optional |
| REX Telegram bot | ✅ Yes | ✅ Same bot, same chairman chat_id |
| Login greeter | ✅ Personal greeting | ✅ Work/GOJ briefing |
| Chairman vault | ✅ Yes | ✅ Same vault (shared) |
| Triple encryption | ✅ All Rexxie data | ✅ GOJ session logs |

The Work Mac runs REX as a pure **GOJ operations AI**. No personal data, no Rexxie,
no personal credentials. Staff can access REX through the dashboard widget.
Only the Chairman gets full access via the `/api/chat` endpoint.

---

## Step 1 — Copy REX to the Work Mac

From your Personal Mac Mini, transfer the REX folder:

```bash
# Option A: USB drive (most secure — no cloud involved)
cp -r ~/Desktop/REX /Volumes/YourUSBDrive/

# Then on the Work Mac:
cp -r /Volumes/YourUSBDrive/REX ~/Desktop/

# Option B: Local network transfer (if both on same WiFi)
# On Personal Mac: System Settings → Sharing → File Sharing → On
# On Work Mac: Finder → Go → Connect to Server → smb://[personal-mac-ip]

# Option C: iCloud / AirDrop (for non-sensitive code files)
# DO NOT use for .db files, key files, or config files with secrets
```

**What to transfer:**
- `~/Desktop/REX/backend/` — all Python backend files
- `~/Desktop/REX/*.py` — all root Python scripts
- `~/Desktop/REX/requirements.txt` — Python dependencies
- **DO NOT transfer:** `.venv/`, `rexxie.db`, `.rexxie_key`, any `*_config.json` files
  (The Work Mac generates its own secrets fresh)

---

## Step 2 — Install Python Dependencies

```bash
cd ~/Desktop/REX

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install all dependencies
pip install -r requirements.txt
```

---

## Step 3 — Configure API Keys (Work Mac)

```bash
# Set your AI provider API key (Anthropic recommended)
# The Work Mac uses REX for GOJ work — Claude API is appropriate here
export ANTHROPIC_API_KEY="your-api-key-here"

# Or set it permanently in your shell profile:
echo 'export ANTHROPIC_API_KEY="your-api-key-here"' >> ~/.zshrc
```

Alternatively, use the REX settings UI after starting the backend:
- Go to `http://localhost:3000/settings` → enter API key in the UI

---

## Step 4 — Run REX Backend

```bash
cd ~/Desktop/REX
source .venv/bin/activate

# Start the backend
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Or install as a background service (recommended):

```bash
# Create LaunchAgent for auto-start on login
cat > ~/Library/LaunchAgents/com.rex.backend.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.rex.backend</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/YOUR_USERNAME/Desktop/REX/.venv/bin/uvicorn</string>
    <string>backend.main:app</string>
    <string>--host</string>
    <string>0.0.0.0</string>
    <string>--port</string>
    <string>8000</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/YOUR_USERNAME/Desktop/REX</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/Users/YOUR_USERNAME/Desktop/REX/logs/rex_backend.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/YOUR_USERNAME/Desktop/REX/logs/rex_backend_err.log</string>
</dict>
</plist>
EOF

# Replace YOUR_USERNAME with your actual username
# Activate it:
launchctl load ~/Library/LaunchAgents/com.rex.backend.plist
```

---

## Step 5 — Register Role Registry (Work Mac)

The Work Mac needs its own role registry. Kato is still Chairman:

```bash
cd ~/Desktop/REX
python backend/rex_role_auth.py --add kato chairman
python backend/rex_role_auth.py --add vlad staff
python backend/rex_role_auth.py --add frontdesk staff
python backend/rex_role_auth.py --list
```

---

## Step 6 — Set Up GOJ Dashboard

The dashboard is a separate frontend (React/Next.js) that connects to the REX backend.
If you have the GOJ dashboard repository:

```bash
cd ~/GOJ-Dashboard   # or wherever the dashboard lives
npm install
npm run dev          # runs at http://localhost:3000
```

REX appears as the floating 🥚 egg widget. Staff can now chat with REX.

---

## Step 7 — Login Greeter (Work Mac)

```bash
python rex_mac_login_greeter.py --setup
# Choose: work (GOJ briefing) or personal (Rexxie greeting)
# Work Mac → choose "work"

python rex_mac_login_greeter.py --install
# → Installs LaunchAgent at ~/Library/LaunchAgents/com.rex.login-greeter.plist

# Test immediately:
python rex_mac_login_greeter.py --greet --mac-type work
```

---

## Step 8 — Phone Unlock (Optional, Recommended)

If you want Face ID → Work Mac unlock:

```bash
python rex_phone_unlock.py --setup
# → Generates a NEW shared secret (separate from home Mac)
# → Follow the iOS Shortcut setup instructions
# → Add a second shortcut on iPhone for the Work Mac
```

In the REX Heartbeat iPhone app, you can configure multiple Mac addresses
by updating the setup screen with the Work Mac's IP.

---

## Step 9 — Proximity Daemon (Optional)

```bash
python rex_proximity_daemon.py --install-launchagent
# Starts automatically, locks Work Mac when you leave
# Same 60s absence + 600s idle dual-condition logic
```

---

## Step 10 — Staff Onboarding

For GOJ staff to use REX:
1. Dashboard is at `http://[WORK-MAC-IP]:3000`
2. They log in with their staff credentials
3. The REX widget appears at bottom-right
4. They can chat naturally — staff firewall enforced automatically
5. No setup needed on staff devices — it's all server-side

---

## Security Differences: Work Mac vs. Personal Mac

**Work Mac does NOT have:**
- Rexxie personal mode (code is present but chairman doesn't activate it at work)
- Credential vault (not needed — GOJ doesn't store personal passwords)
- Personal training data

**Work Mac DOES have:**
- Separate `rex_role_registry.json` (same chairman, same staff)
- Separate `rex_memory.db` (GOJ-specific operational memories)
- Same staff firewall in `sovereign.py`
- Same chairman audit log (`/admin/rex-log`)

**Recommendation:** The Work Mac's `rex_memory.db` should be synced periodically
with the Personal Mac to keep GOJ memories consistent. Do this via USB — not cloud.

---

## Quick Reference — Commands to Run (in order)

```bash
# 1. Copy REX files (USB recommended)
# 2. Install dependencies
pip install -r requirements.txt

# 3. Set API key
export ANTHROPIC_API_KEY="..."

# 4. Register Kato as Chairman
python backend/rex_role_auth.py --add kato chairman

# 5. Start REX backend
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# 6. (Optional) Install as auto-start service
launchctl load ~/Library/LaunchAgents/com.rex.backend.plist

# 7. (Optional) Login greeter
python rex_mac_login_greeter.py --setup && python rex_mac_login_greeter.py --install

# 8. (Optional) Phone unlock
python rex_phone_unlock.py --setup

# 9. (Optional) Proximity daemon
python rex_proximity_daemon.py --install-launchagent

# 10. Test everything
curl http://localhost:8000/api/health
```

---

*Generated by Claude (claude-sonnet-4-6) — REX Sovereign Edition architecture session, March 2026*
