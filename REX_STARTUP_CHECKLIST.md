# REX — What To Do Right Now
**For: Kato (Chairman)**
**Date: April 3, 2026**

Do these steps in order. Each takes under 2 minutes.

---

## STEP 1 — Install All Auto-Start Agents (One-Time)
This makes REX, Rexxie, and all backups start automatically every time the Mac boots.

Open Terminal and run:
```bash
chmod +x ~/Desktop/REX/install-all-agents.command
~/Desktop/REX/install-all-agents.command
```

You should see 14 green checkmarks. After this, everything starts on login automatically.

**Verify it worked:**
```bash
launchctl list | grep -E "rex|goj"
```
You should see all 14 agents listed.

---

## STEP 2 — Start REX + Dashboard Right Now
```bash
# Terminal window 1 — REX backend
cd ~/Desktop/REX && source .venv/bin/activate && python rex_app.py

# Terminal window 2 — GOJ Dashboard
cd ~/Documents/goj\ files/dashboard && source .venv/bin/activate && python3 app.py
```

Then open:
- **GOJ Dashboard:** http://localhost:8080 (login: KChairman / ghs2026!)
- **REX Chat App:** http://localhost:8000

---

## STEP 3 — Add Missing Tokens to .env
Open Terminal:
```bash
open ~/Documents/goj\ files/.env
```

Add these lines (if not already there):
```
TELEGRAM_TOKEN=8657319466:AAGqWut7BHTTNIEYJvnXIDlNSDCOiML7tic
PAPERLESS_URL=http://100.99.86.60:8000
PAPERLESS_TOKEN=<get from Paperless UI — Settings → API Token>
```

**Why:** Without TELEGRAM_TOKEN (Rexxie Gold Health bot), the transport alerts and evening reports won't send to your Telegram. Without PAPERLESS_TOKEN, document retrieval won't work.

---

## STEP 4 — Get the Paperless API Token
1. Open http://100.99.86.60:8000 on your Mac (must be on same WiFi as work Mac, or Tailscale)
2. Log in to Paperless
3. Go to: **Settings → API Token**
4. Copy the token
5. Paste it into `.env` as `PAPERLESS_TOKEN=...`

---

## STEP 5 — Clean Up One File
```bash
rm ~/Documents/goj\ files/dashboard/goj_dashboard.db
```
This file is 0 bytes and was causing confusion. The real database is `auth_tracker.db`.

---

## STEP 6 — Delete Stale Routes File
```bash
rm ~/Documents/goj\ files/dashboard/GOJ_Master_Routes_v2.json
```
The app only uses `GOJ_Master_Routes.json` (v1). The v2 file had different counts and format — keeping it causes confusion.

---

## STEP 7 — Verify Backup Is Working
Run the backup manually to confirm it works:
```bash
~/Desktop/REX/rex-backup.command
```

You should see a green success message and a new folder in `~/Desktop/REX_Backups/`.

After this, the backup runs automatically at **4:30 AM every day** (and encrypted backup at 2:00 AM).

---

## STEP 8 — Set Up Paperless Tunnel (Optional but Recommended)
This lets you access Paperless from anywhere through goldhealthsys.com:
```bash
~/Desktop/REX/setup-paperless-tunnel.command
```
Run once. It installs a LaunchAgent that keeps the tunnel running.

---

## STEP 9 — When You're Ready to Go Live
When ready to push the GOJ Dashboard public:
```bash
cd ~/Documents/goj\ files/dashboard && bash DEPLOY.sh
```
This pushes to Railway (https://respectful-intuition-production-0acf.up.railway.app).

---

## How Memory Works (REX + Rexxie)

**REX memory** (staff-facing dashboard widget):
- Stored in: `auth_tracker.db` → `rex_memory` table (auto-created on first chat)
- To save: type `remember: [something]` in the REX chat widget on any dashboard
- REX injects it into every conversation automatically
- Staff-accessible memories are role-filtered (chairman sees all, staff see operational only)

**REX app memory** (the desktop app on port 8000):
- Stored in: `~/.rex/journeys.db` (created automatically when REX starts)
- AES-256-GCM encrypted at rest
- Same commands: `remember:` / `forget:` / `what do you remember?`

**Rexxie memory** (your personal bot):
- Stored in: `~/Desktop/REX/rexxie.db` (triple-encrypted, Kato-only)
- Separate from REX — staff cannot access any of it
- Telegram: just talk to Rexxie normally, she remembers everything

---

## Daily Health Check (30 seconds)

Run this every morning:
```bash
# Check everything is running
curl -s http://localhost:8080/health | python3 -m json.tool
curl -s http://localhost:8000/health | python3 -m json.tool

# Check last backup
cat ~/Desktop/REX/.last_backup

# Check any error logs
tail -20 ~/Desktop/REX/logs/backup_stderr.log
```

---

## If Something Breaks

**REX widget not responding in dashboard:**
```bash
# Is REX backend running?
curl http://localhost:8000/health
# If not: cd ~/Desktop/REX && source .venv/bin/activate && python rex_app.py
```

**Agents stopped (after Mac crash/reboot):**
```bash
~/Desktop/REX/install-all-agents.command
```

**Memory feels empty (REX forgot things):**
- The memory DB is encrypted and tied to your machine key
- If journeys.db is missing: start REX normally — it creates a fresh one
- Re-seed from the training docs: `cd ~/Desktop/REX && source .venv/bin/activate && python seed_rex_memory.py`

**Dashboard won't start:**
```bash
cd ~/Documents/goj\ files/dashboard
pip3 install -r requirements.txt --break-system-packages
python3 app.py
```

**Rexxie not responding on Telegram:**
```bash
# Check if bot is running
launchctl list | grep rexxie
# If missing: ~/Desktop/REX/install-all-agents.command
# Test manually: cd ~/Desktop/REX && source .venv/bin/activate && python rex_rexxie_telegram_bot.py
```
