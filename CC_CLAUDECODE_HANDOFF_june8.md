# CLAUDE CODE HANDOFF — Tiger Claw Ecosystem
# Generated: 2026-06-08 — by Hermes (Cowork) for Claude Code CLI
# READ CLAUDE.md FIRST: ~/Desktop/REX/CLAUDE.md
# This document is your single source of truth for what to build next.

---

## IDENTITY & HARD RULES

You are building for Kato (Alejandro), Chairman of Gold Health Systems.
- **Larry** NEVER appears on any transport/driver list. Zero exceptions.
- **DeepSeek** always `provider: deepseek` + `base_url: https://api.deepseek.com/v1`. NEVER OpenRouter.
- New files get `CC_` prefix. Existing files keep their names.
- **PHI never crosses tiers.** `auth_tracker.db` never reaches cloud. Presidio on all outbound.
- **Rexxie** private lane is local-only, never divulges contents.
- **PAE = Propose → Approve → Execute.** Items fenced at bottom — DO NOT touch without Kato's approval.
- Auth everywhere: `tigerclaw2026` / `kato`

---

## SYSTEM STATE RIGHT NOW

All 17 services are UP. Key ports:

| Port | What | Location |
|------|------|----------|
| 8000 | REX FastAPI (7 routers) | ~/Desktop/REX/backend/main.py |
| 8001 | Stats API | ~/Desktop/REX/CC_stats_api.py |
| 8002 | Lead Connector CRM | ~/Desktop/REX/CC_lead_connector_api.py |
| 8080 | GOJ Dashboard (LIVE) | ~/.hermes-cloud/home/goj-pipeline/datarex/app.py |
| 9000 | Tiger Claw Hub | ~/hermes-hub/server.py |
| 27226 | Tiger Claw API | ~/Desktop/REX/ |

**7 routers mounted on REX :8000:**

| Prefix | File | Status |
|--------|------|--------|
| /api/cowork-relay | backend/CC_cowork_relay.py | ✅ LIVE |
| /api/auth | backend/CC_auth_router.py | ✅ LIVE |
| /social | backend/CC_social_media_router.py | ✅ LIVE |
| /rex-bill | CC_rex_bill.py | ✅ LIVE |
| /goj-live | backend/CC_goj_live.py | ✅ LIVE |
| /quickbooks-capture | CC_quickbooks_capture.py | ✅ LIVE |
| /masha | backend/CC_victoria_goj_integration.py | ⚠️ Partial |

**Database:** `~/Documents/goj files/dashboard/auth_tracker.db`
- 430 clients (`clients` table)
- Key columns: `clients(client_id, name, plan_raw, plan_canonical, transportation, shift)`
- Auth: `authorization(auth_id, client_name, service_start_date, service_end_date, status)`
- Attendance: `attendance_log(log_date, day_key, shift, client_name, status)`
- Menus: `menus(menu_date, week_start, original_filename)`, `client_menus(main)` — NOT `main_dish`

**Restart REX after edits:**
```bash
pkill -f "uvicorn backend.main:app.*8000"
sleep 3
cd ~/Desktop/REX && /opt/homebrew/bin/python3.11 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --timeout-keep-alive 5 --no-server-header &
```

---

## WHAT WAS DONE TODAY (June 8) — DO NOT REBUILD

These are complete. Verify before touching:

1. **GOJ Live** — `backend/CC_goj_live.py` (228 lines) + `CC_goj_live.html`. SSE streaming every 15s. URL: `https://rex.hermestigerclaw.com/goj-live/`
2. **TransitionAgent Drive Hook** — `CC_transition_drive_hook.py` (318 lines). Launchd running (com.goj.transition-drive-hook). Polls Drive every 60s.
3. **QuickBooks Capture** — `CC_quickbooks_capture.py` (1,107 lines) + `CC_quickbooks_capture.html`. 188 fields, 43 question groups. URL: `https://rex.hermestigerclaw.com/quickbooks-capture`
4. **/LOOP Daily Examiner** — `CC_loop_examiner.py`. Cron at 9 AM daily. First run June 9.
5. **Instagram token** — recovered, in `~/.hermes-cloud/.env` as `META_IG_ACCESS_TOKEN`. Posted Knicks menu to @boardwalkbeergarden.
6. **Gmail OAuth fix** — `backend/rex_gmail.py` and `backend/rex_menu_scan_watcher.py` both patched to write scopes explicitly and auto-refresh. `CC_gmail_reauth.command` created for one-time re-auth. **Kato must double-click `CC_gmail_reauth.command` to activate — this is still pending.**

---

## BUILD QUEUE — ORDERED BY PRIORITY

Work these top-to-bottom. Each item has: what to do, exact file, exact change, verification.

---

### TASK 1 🔴 — GOJ Live: Fix Attendance Showing Zero

**Problem:** `/goj-live/` attendance card shows 0 because `attendance_log` has no rows for today (Sunday, or early morning). The dashboard looks broken.

**File:** `~/Desktop/REX/backend/CC_goj_live.py`

**Fix:** In the endpoint that queries attendance, fall back to the most recent day with data if today is empty. Find the attendance query (it will look like `WHERE log_date = date('now')`). Replace with logic like:

```python
import sqlite3

DB_PATH = os.path.expanduser("~/Documents/goj files/dashboard/auth_tracker.db")

def get_attendance():
    with sqlite3.connect(DB_PATH) as conn:
        # Try today first
        rows = conn.execute(
            "SELECT COUNT(*) FROM attendance_log WHERE log_date = date('now')"
        ).fetchone()[0]
        
        if rows == 0:
            # Fall back to most recent day with data
            last_date = conn.execute(
                "SELECT MAX(log_date) FROM attendance_log"
            ).fetchone()[0]
            if last_date:
                data = conn.execute(
                    "SELECT status, COUNT(*) FROM attendance_log WHERE log_date = ? GROUP BY status",
                    (last_date,)
                ).fetchall()
                return {"date": last_date, "is_today": False, "data": dict(data)}
            return {"date": None, "is_today": False, "data": {}}
        else:
            data = conn.execute(
                "SELECT status, COUNT(*) FROM attendance_log WHERE log_date = date('now') GROUP BY status"
            ).fetchall()
            return {"date": str(datetime.date.today()), "is_today": True, "data": dict(data)}
```

In the HTML (`CC_goj_live.html`), show the date and a label like "Last recorded: Mon Jun 3" when not today.

**Verify:** Hit `https://rex.hermestigerclaw.com/goj-live/` — attendance card should show a non-zero number with a date label.

---

### TASK 2 🔴 — GOJ Live: Fix the 88-Client Gap

**Problem:** 430 total in `clients` table but only 342 have authorization records (240 active + 35 pending + 67 expired). 88 clients have NO auth rows. Dashboard summary is misleading.

**File:** `~/Desktop/REX/backend/CC_goj_live.py`

**Fix:** Change the client count query to LEFT JOIN against authorization and bucket the 88 as "No Auth":

```sql
SELECT 
    COALESCE(a.status, 'NO AUTH') as status,
    COUNT(*) as count
FROM clients c
LEFT JOIN authorization a ON c.name = a.client_name
GROUP BY COALESCE(a.status, 'NO AUTH')
```

In the dashboard card, show a fourth row: "No Auth: 88" in amber/yellow so it's visible but not alarming.

**Verify:** Client card shows 5 categories: ACTIVE, EXPIRED, PENDING RENEWAL, NO AUTH, and total = 430.

---

### TASK 3 🔴 — Rex Bill Dashboard: Mount the HTML Route

**Problem:** `CC_rex_bill_dashboard.html` exists and has the unified nav but no route serves it. Navigating to `/rex-bill/ui` returns 404.

**File:** `~/Desktop/REX/CC_rex_bill.py`

**Add this route** (find the router definition, add after existing routes):

```python
from fastapi.responses import HTMLResponse
from pathlib import Path

@router.get("/ui", response_class=HTMLResponse)
async def bill_dashboard_ui():
    html_path = Path("~/Desktop/REX/CC_rex_bill_dashboard.html").expanduser()
    return HTMLResponse(html_path.read_text())
```

Restart REX after this change.

**Verify:** `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/rex-bill/ui` returns 200.

---

### TASK 4 🟡 — Social Router: Wire Instagram Auto-Post Execute

**Problem:** Instagram token is in `.env` and the container→poll→publish flow works manually, but the `/social/execute` endpoint only handles Telegram. Instagram auto-posts return `autopost_ready: false`.

**File:** `~/Desktop/REX/backend/CC_social_media_router.py`

**Find** the `execute` endpoint (or wherever posts are dispatched). Add an Instagram branch:

```python
import os
import time
import httpx

IG_TOKEN = os.getenv("META_IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("META_IG_USER_ID", "27923669980556036")
IG_API_BASE = "https://graph.facebook.com/v19.0"

async def post_instagram(image_url: str, caption: str) -> dict:
    """Container → poll → publish flow for Instagram Graph API."""
    async with httpx.AsyncClient() as client:
        # Step 1: Create container
        r = await client.post(
            f"{IG_API_BASE}/{IG_USER_ID}/media",
            params={
                "image_url": image_url,
                "caption": caption,
                "access_token": IG_TOKEN,
            },
        )
        container_id = r.json().get("id")
        if not container_id:
            return {"error": "Container creation failed", "detail": r.text}

        # Step 2: Poll until ready (max 30s)
        for _ in range(10):
            await asyncio.sleep(3)
            status_r = await client.get(
                f"{IG_API_BASE}/{container_id}",
                params={"fields": "status_code", "access_token": IG_TOKEN},
            )
            if status_r.json().get("status_code") == "FINISHED":
                break

        # Step 3: Publish
        pub_r = await client.post(
            f"{IG_API_BASE}/{IG_USER_ID}/media_publish",
            params={"creation_id": container_id, "access_token": IG_TOKEN},
        )
        return pub_r.json()
```

Update the router's execute endpoint to call `post_instagram()` when `platform == "instagram"`.

Also update `.env` to ensure `META_IG_USER_ID=27923669980556036` is set.

**Verify:** POST to `/social/execute` with `{"platform": "instagram", "image_url": "...", "caption": "test"}` returns a media ID without error.

---

### TASK 5 🟡 — Website: Fix the Email Capture Form (goldhealthsys.com)

**Problem:** `FinalCTA.jsx` form never sends data anywhere. `handleSubmit` only calls `setSubmitted(true)`. Every signup is silently lost.

**Path:** `~/Desktop/REX/website/`

**Step 1 — Create Next.js API route:**

Create `~/Desktop/REX/website/app/api/waitlist/route.js`:

```javascript
import { NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

export async function POST(request) {
  try {
    const { email } = await request.json()
    if (!email || !email.includes('@')) {
      return NextResponse.json({ error: 'Invalid email' }, { status: 400 })
    }

    // Append to waitlist file (simple, local, no cloud)
    const filePath = path.join(process.cwd(), 'waitlist.csv')
    const line = `${new Date().toISOString()},${email}\n`
    fs.appendFileSync(filePath, line)

    return NextResponse.json({ ok: true })
  } catch (err) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
```

**Step 2 — Fix FinalCTA.jsx handleSubmit:**

```javascript
const handleSubmit = async (e) => {
  e.preventDefault()
  if (!email.trim()) return
  
  try {
    const res = await fetch('/api/waitlist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.trim() }),
    })
    if (res.ok) {
      setSubmitted(true)
    } else {
      console.error('Waitlist error:', await res.text())
    }
  } catch (err) {
    console.error('Waitlist fetch failed:', err)
  }
}
```

**Step 3 — Redeploy to Railway:**
```bash
cd ~/Desktop/REX/website
# Commit and push, or run railway up if CLI is installed
```

**Verify:** Submit a test email on the live site. Check that `~/Desktop/REX/website/waitlist.csv` (or wherever Railway writes it) has the entry. Note: Railway ephemeral filesystem means a persistent store (Resend API, Airtable, or a DB) is better long-term — flag this to Kato.

---

### TASK 6 🟡 — Website: Fix Dead Footer Links

**Problem:** Every link in Footer.jsx uses `href="#"`. All three columns (Platform, Company, Tech) are non-functional.

**File:** `~/Desktop/REX/website/components/Footer.jsx`

**Replace the three link columns** with real anchor targets:

```javascript
const links = {
  Platform: [
    { label: 'Features',              href: '#features' },
    { label: 'GOJ Dashboard',         href: '#features' },
    { label: 'Rexxie Agent',          href: '#features' },
    { label: 'Document Intelligence', href: '#features' },
    { label: 'REX OS',                href: '#os' },
  ],
  Company: [
    { label: 'The Story',    href: '#about' },
    { label: 'How It Works', href: '#process' },
    { label: 'Early Access', href: '#cta' },
    { label: 'Contact',      href: 'mailto:atigerclawai@gmail.com' },
  ],
  Tech: [
    { label: 'Privacy Policy', href: '#cta' },  // placeholder until real page exists
    { label: 'Terms of Use',   href: '#cta' },  // placeholder
  ],
}
```

In the JSX, map over these instead of the current dead links.

**Also fix copyright:** Change `© {new Date().getFullYear()} REX Intelligence.` to `© {new Date().getFullYear()} Gold Health Systems / REX Intelligence.` — or pick one entity and commit.

**Verify:** Every footer link scrolls to a real section or opens a mailto. No `href="#"` remains in the footer (except temporary Privacy/Terms placeholders, which should be noted as TODO).

---

### TASK 7 🟡 — Website: Add Favicon

**Problem:** `app/layout.jsx` defines no favicon. Browser shows a blank tab icon.

**File:** `~/Desktop/REX/website/app/layout.jsx`

Add to the metadata export:

```javascript
export const metadata = {
  // ... existing fields ...
  icons: {
    icon: '/favicon.ico',
    apple: '/apple-touch-icon.png',
  },
}
```

Then create a simple gold circle favicon. Drop an SVG or PNG at `~/Desktop/REX/website/public/favicon.ico`. Simplest approach:

```bash
# Create a minimal gold SVG favicon
cat > ~/Desktop/REX/website/public/favicon.svg << 'EOF'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <circle cx="16" cy="16" r="15" fill="#D4AF37"/>
  <text x="16" y="22" font-size="18" text-anchor="middle" fill="#0A0A0A" font-family="serif" font-weight="bold">R</text>
</svg>
EOF
```

Update layout.jsx icons to point to `'/favicon.svg'`.

**Verify:** Hard-refresh goldhealthsys.com — browser tab should show a gold "R" icon.

---

### TASK 8 🟡 — Website: Remove Fake Status Pills OR Make Them Live

**Problem:** Footer has "GOJ Live 🟢", "Rexxie Active 🟢", "OS In Dev 🟡" hardcoded. These are always green regardless of actual service health — a false signal.

**Option A (fast, honest):** Remove the green dots. Change "GOJ Live 🟢" to "GOJ Live" with a neutral style. No false signal.

**Option B (correct, 2 hours):** Add a `/api/status` endpoint on the website that pings `hermestigerclaw.com` via Cloudflare tunnel to check service health, and dynamically color the pills based on the response.

`~/Desktop/REX/website/app/api/status/route.js`:
```javascript
import { NextResponse } from 'next/server'

export async function GET() {
  try {
    const r = await fetch('https://rex.hermestigerclaw.com/health', { 
      next: { revalidate: 30 } 
    })
    const goj = r.ok
    return NextResponse.json({ goj_live: goj, rexxie: goj, os: false })
  } catch {
    return NextResponse.json({ goj_live: false, rexxie: false, os: false })
  }
}
```

Then have `Footer.jsx` fetch this on mount with `useEffect`.

**Recommend Option A** unless Kato wants live pills. Either way, the current state (always-green hardcoded) should not remain.

---

### TASK 9 🟢 — CC_stats_api Permanent Plist Install

**Problem:** `CC_stats_api.py` (:8001) is running without a launchd plist. Will die on reboot.

**Create:** `~/Library/LaunchAgents/com.rex.stats-api.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.rex.stats-api</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/python3.11</string>
        <string>/Users/mainsobhelper/Desktop/REX/CC_stats_api.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/mainsobhelper/Desktop/REX/logs/stats_api.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/mainsobhelper/Desktop/REX/logs/stats_api_err.log</string>
    <key>WorkingDirectory</key>
    <string>/Users/mainsobhelper/Desktop/REX</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.rex.stats-api.plist
```

**Verify:** `launchctl list | grep stats-api` shows the service. `curl http://127.0.0.1:8001/health` returns 200.

---

### TASK 10 🟢 — Gmail OAuth Re-Auth (Kato Action Required — Cannot Be Done by Claude Code)

**Status:** `CC_gmail_reauth.command` was created today at `~/Desktop/REX/CC_gmail_reauth.command`. It's ready.

**Action needed:** Kato must double-click this file in Finder. It will:
1. Delete the stale token (`~/.rex_google_token.json`)
2. Open browser → Google OAuth flow
3. Write a new token WITH a `refresh_token` (permanent)
4. Test the connection and log the result

Until this is done, the GOJ pipeline (menu scans, OCR, all 9 daily JSON files) remains broken as of May 28.

**Claude Code should verify the token exists and is valid after Kato runs it:**
```bash
python3 -c "
import json
tok = json.load(open('/Users/mainsobhelper/.rex_google_token.json'))
print('Has refresh_token:', bool(tok.get('refresh_token')))
print('Scopes:', tok.get('scopes'))
"
```

---

## VERIFICATION CHECKLIST — Run After All Tasks

```bash
# Service health
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
curl -s http://127.0.0.1:8001/health
curl -s http://127.0.0.1:8080/health

# Routes working
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/goj-live/
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/rex-bill/ui
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/quickbooks-capture

# GOJ Live data
curl -s http://127.0.0.1:8000/goj-live/api/summary | python3 -m json.tool
# Expect: clients total=430, attendance has a non-zero number and a date label

# Instagram env
python3 -c "
import os; from dotenv import load_dotenv
load_dotenv('/Users/mainsobhelper/.hermes-cloud/.env')
token = os.getenv('META_IG_ACCESS_TOKEN', '')
print('IG token present:', bool(token), '| Length:', len(token))
"

# Website build
cd ~/Desktop/REX/website && npm run build 2>&1 | tail -20
# Expect: no errors, successful build
```

---

## PAE FENCE — DO NOT EXECUTE WITHOUT KATO APPROVAL

These items require PAE (Propose → Approve → Execute). List them back to Kato and wait for "do it":

| ID | What | File |
|----|------|------|
| PAE-4 | Wire Gate 1 AKC tokenizer into PHI pipeline | CC_akc_tokenizer_v2.py |
| PAE-5 | Verify + activate TigerClaw API :27226 | CC_jarvis_startup.command |
| PAE-6 | Phase 16 business isolation enforcer swap | core/business_isolation.py |
| PAE-7 | Fix bot 401 errors in Hermes gateway | Hermes gateway config |
| PAE-8 | Activate Agent Forge (13 agents) | rex_agent_forge.py |
| — | Claus orchestrator plist swap | CC_claus_orchestrator.py |
| — | Unified auth across all subdomains | CC_auth_router.py + hub |
| — | iOS Tauri build for device | ~/hermes-apps/ios/ |

---

## KEY FILE PATHS

| What | Path |
|------|------|
| Governing doc | ~/Desktop/REX/CLAUDE.md |
| REX main app | ~/Desktop/REX/backend/main.py |
| GOJ Live backend | ~/Desktop/REX/backend/CC_goj_live.py |
| GOJ Live HTML | ~/Desktop/REX/CC_goj_live.html |
| Rex Bill router | ~/Desktop/REX/CC_rex_bill.py |
| Rex Bill HTML | ~/Desktop/REX/CC_rex_bill_dashboard.html |
| Social router | ~/Desktop/REX/backend/CC_social_media_router.py |
| QB Capture | ~/Desktop/REX/CC_quickbooks_capture.py |
| /LOOP examiner | ~/Desktop/REX/CC_loop_examiner.py |
| Transition hook | ~/Desktop/REX/CC_transition_drive_hook.py |
| Website | ~/Desktop/REX/website/ |
| Website CTA | ~/Desktop/REX/website/components/FinalCTA.jsx |
| Website Footer | ~/Desktop/REX/website/components/Footer.jsx |
| Website Layout | ~/Desktop/REX/website/app/layout.jsx |
| Database | ~/Documents/goj files/dashboard/auth_tracker.db |
| All API keys | ~/.hermes-cloud/.env |
| Gmail re-auth | ~/Desktop/REX/CC_gmail_reauth.command |
| Hermes memory | ~/.hermes/profiles/cloud/memories/MEMORY.md |
| GOJ working doc | ~/Documents/goj files/GOJ_WORKING_DOC.md |
| Website audit | ~/Desktop/REX/CC_website_audit_june8.md |
| This handoff | ~/Desktop/REX/CC_CLAUDECODE_HANDOFF_june8.md |

---

## SUMMARY — TASK STATUS

| # | Task | Priority | Owner |
|---|------|----------|-------|
| 1 | GOJ Live attendance fallback | 🔴 Urgent | Claude Code |
| 2 | GOJ Live 88-client NO AUTH | 🔴 Urgent | Claude Code |
| 3 | Rex Bill /ui route | 🔴 Urgent | Claude Code |
| 4 | Instagram auto-post execute | 🟡 High | Claude Code |
| 5 | Website email capture (FinalCTA) | 🟡 High | Claude Code |
| 6 | Website footer links | 🟡 High | Claude Code |
| 7 | Website favicon | 🟡 High | Claude Code |
| 8 | Website status pills | 🟡 High | Claude Code |
| 9 | stats-api plist | 🟢 Nice | Claude Code |
| 10 | Gmail re-auth | ⚠️ Manual | **KATO** (double-click CC_gmail_reauth.command) |

PAE items (6+) — DO NOT TOUCH until Kato says "do it."

---

*Compiled June 8, 2026 — Hermes (Cowork) + Claude Code handoff*  
*Source documents: CC_CLAUDE_HANDOFF_june8.md + CC_website_audit_june8.md + today's session*

---

# SUPPLEMENTAL — FROM LAST WEEK'S SESSIONS
# Added: 2026-06-08 (Cowork audit of CC_HERMES_KNOWLEDGE.md + CC_HUB_MASTER_REFERENCE.md + CC_NEXT_STEPS.md)
# Source: June 1–8 session logs, CC_HERMES_KNOWLEDGE.md, CC_hermes_sync_brief.md

These items were NOT in the original 10-task list above. All are real gaps confirmed in the knowledge base.

---

## CRITICAL ONE-LINERS THAT ARE BROKEN RIGHT NOW

### TASK 11 🔴 — Fix rex_memory.db (Rexxie Starts Cold Every Session)

**Problem:** `rex_memory.db` and `rex_user_model.db` are both 0KB — they exist as empty files. This means Rexxie loses all learned context on every restart. She literally forgets everything she's learned about Kato's preferences, patterns, and habits. This is a one-line fix.

**File:** `~/Desktop/REX/backend/memory.py`

**Find** the `RexMemory.__init__` (or database initialization block). The tables are likely never being created because the `CREATE TABLE IF NOT EXISTS` statement is missing or the `connect()` call happens but the schema is never applied. 

Look for something like:
```python
self.conn = sqlite3.connect(self.db_path)
```

It needs to be followed by schema creation:
```python
self.conn = sqlite3.connect(self.db_path)
self.conn.execute("""
    CREATE TABLE IF NOT EXISTS memories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE NOT NULL,
        value TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")
self.conn.commit()
```

Do the same for `rex_user_model.db` (find its initialization path, likely also in `memory.py` or `rex_training.py`).

**Verify:**
```bash
ls -lh ~/Desktop/REX/rex_memory.db ~/Desktop/REX/rex_user_model.db
# Both should be > 0 bytes after REX restart
python3 -c "
import sqlite3
conn = sqlite3.connect('/Users/mainsobhelper/Desktop/REX/rex_memory.db')
print('Tables:', conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall())
"
```

---

### TASK 12 🔴 SECURITY — Rotate the TOTP Secret (Currently Zero Security)

**Problem:** The current TOTP secret is `JBSWY3DPEHPK3PXP` — this is the RFC example value from the TOTP spec documentation. It is publicly known and provides zero security. Anyone who knows about TOTP RFCs can generate valid codes.

**Where it's used:** `~/Desktop/REX/backend/auth.py` or wherever TOTP verification lives. Also likely in `~/hermes-hub/server.py` or `~/.hermes/profiles/cloud/.env`.

**Fix:**
```python
import pyotp
import base64
import os

# Generate a proper secret (do this ONCE, save the result)
new_secret = base64.b32encode(os.urandom(20)).decode('utf-8')
print(new_secret)
# Example output: JFNVSS3TMNQXIZLJNRQXIZLJNR...

# Test it works
totp = pyotp.TOTP(new_secret)
print("Current code:", totp.now())
print("URI for authenticator app:", totp.provisioning_uri("kato@goldhealthsys.com", issuer_name="Tiger Claw"))
```

Steps:
1. Generate new secret with the above
2. Scan the QR provisioning URI into Kato's authenticator app BEFORE removing the old secret
3. Replace `JBSWY3DPEHPK3PXP` in all files where it appears
4. Store new secret in macOS Keychain: `security add-generic-password -s "rex-totp-secret" -a "kato" -w "<NEW_SECRET>"`

**Find all occurrences:**
```bash
grep -r "JBSWY3DPEHPK3PXP" ~/Desktop/REX/ ~/.hermes/ ~/hermes-hub/ 2>/dev/null
```

**⚠️ PAE FENCE:** Confirm with Kato before rotating — he needs to update his authenticator app first or he gets locked out.

---

## INCOMPLETE BUILDS — NEED COMPLETION

### TASK 13 🟡 — Victoria/Masha (Retell AI) — Complete the Integration

**Problem:** `/masha` router exists (`backend/CC_victoria_goj_integration.py`, 37KB, June 8) but is marked ⚠️ Partial. The Retell AI voice agents (Victoria for English, Masha for Russian) were making GOJ M12 Medicaid confirmation calls but went silent. Likely cause: Retell API key expired.

**Check the key first:**
```bash
# Key should be in ~/.hermes/.env or ~/.hermes-cloud/.env
grep -i "retell" ~/.hermes/.env ~/.hermes-cloud/.env 2>/dev/null
```

**Test the key:**
```bash
curl -H "Authorization: Bearer <RETELL_API_KEY>" \
  https://api.retellai.com/list-agents 2>&1 | head -50
# If 401/403 → key expired. Get new key from app.retellai.com
# If 200 → key valid, problem is elsewhere
```

**What CC_victoria_goj_integration.py needs to complete:**
- The webhook endpoint at `/masha/webhook` to receive Retell call events
- The call initiation flow: pull pending M12 clients from auth_tracker.db → trigger Retell call → log result
- A status page showing which clients have been called, outcomes, and pending

**Verify after completion:** POST to `/masha/initiate-test` with a test phone number. Confirm Retell dashboard shows an outbound call attempt.

---

## SERVICE RESTORATION QUEUE (4 Services Currently DOWN)

Per `CC_HUB_MASTER_REFERENCE.md` (June 7 audit), these were confirmed down:

### Restore Portal :3847
```bash
launchctl list | grep portal
launchctl load ~/Library/LaunchAgents/com.hermes.portal.plist
curl http://127.0.0.1:3847/health
```

### Restore LibreChat :3080 (Docker)
```bash
docker ps -a | grep librechat
docker start librechat
# OR if no container exists:
cd ~/Documents/LibreChat && docker-compose up -d
curl http://127.0.0.1:3080/health
```

### Restore Kapso WhatsApp Bridge
```bash
launchctl list | grep kapso
# Currently exiting with code 1 — check logs first:
tail -50 ~/Library/Logs/kapso-whatsapp.log 2>/dev/null || \
  launchctl log show --predicate 'subsystem == "com.hermes.kapso-whatsapp"' --last 1h
launchctl kickstart -k gui/$(id -u)/com.hermes.kapso-whatsapp
```

### Restore Obsidian REST API :27124
Obsidian must be RUNNING (it's a plugin inside the Obsidian app). Then:
```bash
launchctl load ~/Library/LaunchAgents/com.hermes.obsidian-api.plist 2>/dev/null || true
curl -k https://127.0.0.1:27124/vault/ -H "Authorization: Bearer $OBSIDIAN_API_KEY"
```
Without this, the NotebookLM local module, Hermes MCP, and n8n Obsidian sync all break.

---

## INSTALL QUEUE — IMPORTANT TOOLS NOT YET ACTIVE

### Install MemPalace (Tier 1 System — Sitting Dormant)

MemPalace is already configured as an MCP server in `~/.hermes/config.yaml`:
```yaml
- mempalace: python3 -m mempalace.mcp_server
```
But `pip install mempalace` was never run. The databases exist at `/Volumes/cartoons/palace_main.db` and `/Volumes/cartoons/palace_cloud.db` (external drive must be mounted).

```bash
source ~/debate-chamber/.venv/bin/activate
pip install mempalace --break-system-packages
# Verify:
python3 -m mempalace.mcp_server --help
```

### Install hermes-dreaming Plugin (Hermes' Most Important Plugin)

Per the knowledge base, this is rated as Hermes's most important plugin. Not yet installed.
```bash
hermes plugins install asimons81/hermes-dreaming --enable
# Then restart Hermes cloud gateway:
launchctl unload ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist
pkill -f "hermes_cli.main.*gateway" && sleep 8
launchctl load ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist
```

---

## SECURITY HARDENING (Non-PAE items — these are safe to fix)

### Fix Cloud .env Permissions
```bash
# Currently ACL-blocked. Must use sudo:
sudo chmod 600 ~/.hermes/profiles/cloud/.env
ls -la ~/.hermes/profiles/cloud/.env
# Should show: -rw------- (600)
```

### Fix Gatekeeper + Firewall (Low priority but easy)
```bash
# Re-enable macOS Gatekeeper (was disabled for dev):
sudo spctl --master-enable
# Enable Firewall:
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate on
```

### Audit Chain Broken at Entry 1
Per CC_HUB_MASTER_REFERENCE.md, the Hub security audit chain has a hash mismatch at entry 1. This breaks the chain of custody for the audit log.
```bash
# Check audit entries in Hub vault:
curl -s -b /tmp/cookies http://127.0.0.1:9000/api/hub/security/audit | python3 -m json.tool | head -40
# The fix depends on what's in entry 1 — likely need to reset/reseal the chain
```

---

## BUILT FILES NOT IN ORIGINAL HANDOFF — VERIFY STATUS

These files were built June 5-8 and appear on disk. Status unknown — verify they're integrated or flag as dormant:

| File | Size | Built | Integration Status |
|------|------|-------|-------------------|
| `CC_ocr_live_watcher.py` | 14KB | Jun 7 | Unknown — is this replacing `rex_menu_scan_watcher.py`? |
| `CC_employee_clock.html` | 17KB | Jun 7 | Unknown — is this served by any route? |
| `CC_hub_security_sweep.py` | 6KB | Jun 8 | Unknown — is this a cron job? Manual? |
| `CC_victoria_goj_integration.py` | 37KB | Jun 8 | ⚠️ Partial (TASK 13 above) |
| `CC_alienware_integration_plan.md` | — | Jun 7 | Plan only — not yet executed |
| `CC_CLAUDE_RAILWAY_BUILD.md` | — | Jun 7 | **18-PAGE BUILD SPEC** — big next build |
| `CC_CLAUDE_GAP_ANALYSIS.md` | — | Jun 7 | 4 unanswered architecture questions |
| `CC_CLAUDE_AUDIT.md` | — | Jun 7 | Audit prompt — read before building |

**For CC_ocr_live_watcher.py specifically:** Check if this conflicts with `backend/rex_menu_scan_watcher.py`. One of them should be the active watcher. Grep for which one is referenced in main.py:
```bash
grep -n "scan_watcher\|ocr_live" ~/Desktop/REX/backend/main.py
```

---

## THE TIGER CLAW HUB :9000 — FULL CONTEXT MISSING FROM HANDOFF

The original handoff only lists `:9000 Tiger Claw Hub` in the service table. Here's what's actually there and what's broken:

**Hub is at** `~/hermes-hub/server.py` (4,423 lines, FastAPI). PIN: `2563`.

**Key broken items inside the Hub:**
- **Vault**: `GET /api/rexxie/vault/status` returns `{"unlocked": false}` — needs master password. Vault DB exists but empty.
- **`/api/hub/models`**: Returns 404. Endpoint may have moved. Check `server.py` for correct route.
- **NotebookLM PDF support**: Needs `brew install poppler` for PDF extraction to work. Currently falls back to pdftotext which may not be installed.
- **WebRex page** (`/webrex`): Listed in hub pages as "pending".

**Quick Hub auth:**
```bash
curl -s -c /tmp/hub_cookies http://127.0.0.1:9000/api/hub/auth/pin \
  -H "Content-Type: application/json" -d '{"pin":"2563"}'
# Then use -b /tmp/hub_cookies for authenticated requests
curl -s -b /tmp/hub_cookies http://127.0.0.1:9000/api/hub/summary | python3 -m json.tool
```

---

## THE NEXT BIG BUILD — READ THESE FILES

Hermes designed the next major build before the session ended. Claude Code should read these and propose before building:

1. **`~/Desktop/REX/CC_CLAUDE_AUDIT.md`** — Send to Claude Code FIRST. Honest inventory of everything built and what's actually running.

2. **`~/Desktop/REX/CC_CLAUDE_GAP_ANALYSIS.md`** — 4 architecture questions that need answering before the next big build (12-tab command center, DropTop integration, Antigravity integration, change management workflow).

3. **`~/Desktop/REX/CC_CLAUDE_RAILWAY_BUILD.md`** — Full spec for the 18-page Railway app that replaces the current scattered command center. This is the main build Hermes has queued.

The Railway build spec covers 18 pages: `/dashboard`, `/modules`, `/clients`, `/employees`, `/schedule`, `/billing`, `/kitchen`, `/transport`, `/security`, `/agents`, `/bbg`, `/design`, `/tools`, `/documents`, `/og33`, `/vault`, `/voice`, `/settings`.

**Only read and propose — do NOT start building this without Kato saying "do it."** It's a significant build that replaces multiple existing pages.

---

## UPDATED PAE FENCE (additions from last week)

Additions to the PAE fence from last week's sessions:

| ID | What | Note |
|----|------|------|
| PAE-T | Rotate TOTP secret | Kato must update authenticator app first |
| PAE-R | Railway 18-page build | Read CC_CLAUDE_RAILWAY_BUILD.md, propose scope |
| PAE-A | Alienware integration | Read CC_alienware_integration_plan.md first |
| PAE-D | Disclosure tier gate on Telegram bots | Any Telegram user currently gets sensitive data |
| PAE-H | Hermes-dreaming plugin install | Should be safe but confirm w/ Kato |
| PAE-I | iMessage watcher build | Required for 7-System Cascade, uses iPad-Mac Mini |

---

## UPDATED TASK SUMMARY (Tasks 1–13)

| # | Task | Priority | Owner |
|---|------|----------|-------|
| 1 | GOJ Live attendance fallback | 🔴 Urgent | Claude Code |
| 2 | GOJ Live 88-client NO AUTH | 🔴 Urgent | Claude Code |
| 3 | Rex Bill /ui route | 🔴 Urgent | Claude Code |
| 4 | Instagram auto-post execute | 🟡 High | Claude Code |
| 5 | Website email capture | 🟡 High | Claude Code |
| 6 | Website footer links | 🟡 High | Claude Code |
| 7 | Website favicon | 🟡 High | Claude Code |
| 8 | Website status pills | 🟡 High | Claude Code |
| 9 | stats-api plist | 🟢 Nice | Claude Code |
| 10 | Gmail re-auth | ⚠️ Manual | **KATO** |
| 11 | rex_memory.db fix (0KB) | 🔴 Urgent | Claude Code |
| 12 | TOTP rotation | 🔴 Security | **KATO** approves first |
| 13 | Victoria/Masha completion | 🟡 High | Claude Code |
| — | Restore Portal/LibreChat/Kapso/Obsidian | 🟡 High | Claude Code |
| — | MemPalace + hermes-dreaming install | 🟢 Nice | Claude Code |
| — | Hub vault unlock + /api/hub/models fix | 🟡 High | Claude Code |
| — | Security hardening (.env perms, Gatekeeper, Firewall) | 🟡 High | Claude Code |

---

*Supplemental added June 8, 2026 — by Cowork (Claude), cross-referencing CC_HERMES_KNOWLEDGE.md + CC_HUB_MASTER_REFERENCE.md + CC_NEXT_STEPS.md*  
*These items represent gaps from the June 1–8 sprint that were NOT captured in the original 10-task handoff.*
