# REX + GOJ — Claude Session Context
**Read this at the start of every session.**
Last updated: 2026-04-03

---

## Who Is Kato (The Chairman)
- Founder & Chairman — Garden of Joy (GOJ) Adult Day Care, Brooklyn NY
- Address: 3152 Brighton 6 St, Brooklyn NY 11235
- Email: atigerclawai@gmail.com
- Mac username: `mainsobhelper`
- REX is his AI operations system. Rexxie is his personal Telegram bot. GOJ Dashboard is the staff-facing web app.

---

## STARTUP — What Must Be Running (Check First)

Every session, confirm these are live before doing any work:

| Process | Start Command | Health Check |
|---|---|---|
| **GOJ Dashboard** | `cd ~/Documents/goj\ files/dashboard && python3 app.py` | http://localhost:8080 |
| **REX Backend** | `cd ~/Desktop/REX && source .venv/bin/activate && python rex_app.py` | http://localhost:8000 |
| **Rexxie Telegram Bot** | Auto-started by `com.rex.rexxie-bot.plist` LaunchAgent | Telegram: message Rexxie |
| **Ollama (local AI)** | Auto-started by Ollama.app or `ollama serve` | `ollama list` |

**To start everything at once (after login):**
```bash
# 1. Start REX (opens tray icon + backend on port 8000)
cd ~/Desktop/REX && source .venv/bin/activate && python rex_app.py &

# 2. Start GOJ Dashboard (port 8080)
cd ~/Documents/goj\ files/dashboard && source .venv/bin/activate && python3 app.py &

# 3. Open both in browser
open http://localhost:8000
open http://localhost:8080
```

**If LaunchAgents are not installed yet (first time or after Mac reinstall):**
```bash
chmod +x ~/Desktop/REX/install-all-agents.command
~/Desktop/REX/install-all-agents.command
```
This installs all 14 agents — REX auto-starts on every login after this.

---

## Key Paths (All Absolute)

| What | Path |
|---|---|
| REX folder | `~/Desktop/REX/` |
| GOJ dashboard folder | `~/Documents/goj files/dashboard/` |
| GOJ templates (HTML) | `~/Documents/goj files/dashboard/templates/` |
| GOJ database | `~/Documents/goj files/dashboard/auth_tracker.db` |
| GOJ `.env` | `~/Documents/goj files/.env` |
| REX memory DB | `~/.rex/journeys.db` (auto-created when REX starts) |
| REX config | `~/.rex/config.json` |
| REX logs | `~/Desktop/REX/logs/` |
| REX backups | `~/Desktop/REX_Backups/` (daily rsync, 14-day rolling) |
| GOJ data backups | `~/Desktop/REX_GOJ_Backups/` (twice daily) |
| LaunchAgents installed | `~/Library/LaunchAgents/` |
| LaunchAgent plists | `~/Desktop/REX/launchd/` |
| REX venv | `~/Desktop/REX/.venv/` |

---

## Cowork Workspace Mounts
- REX folder → `/sessions/.../mnt/REX`
- GOJ dashboard → `/sessions/.../mnt/dashboard`
- GOJ templates → `/sessions/.../mnt/templates`
- Other folders: use `request_cowork_directory` tool

---

## GOJ Dashboard — Current State (as of 2026-04-03)

- Theme: **Arena Night** — VGK Black (#111111) × GHS Gold (#C9A84C) × Teal
- Flask app: `app.py`, port **8080**
- Database: `auth_tracker.db` (~1MB, 28 tables) — source of truth (R1)
- **Live counts:** 426 total clients (401 active, 25 inactive), 375 ACTIVE auths, 919 route assignments
- Auth status: 375 ACTIVE · 16 EXPIRED · 16 PENDING RENEWAL
- **Users:** `chairman` (chairman), `vlad` (vlad), `frontdesk` (frontdesk), `mykhailo` (kitchen)
- Chairman login: `KChairman` / `ghs2026!`
- Railway deploy URL: https://respectful-intuition-production-0acf.up.railway.app
- Tailscale IP: 100.98.90.26 · Local IP: 192.168.1.249
- **Routes JSON:** `GOJ_Master_Routes.json` is canonical (keys: M1, M2, F1, F2, T1, T2, TH1, TH2, W1, W2, Su). `GOJ_Master_Routes_v2.json` deleted (was stale).

### All 38 Dashboard Templates (finalized)
**Dashboards:** `dashboard_chairman.html` · `dashboard_vlad.html` · `dashboard_frontdesk.html` · `dashboard_driver.html` · `dashboard_kitchen.html`
**Client/Auth:** `client_list.html` · `client_detail.html` · `client_profile.html` · `auth_list.html` · `auth_detail.html` · `auth_add.html` · `auth_manual_entry.html`
**Attendance:** `attendance.html` · `attendance_calendar.html` · `attendance_log.html` · `attendance_client_report.html`
**Routes/Sign-in:** `routes.html` · `routes_signin.html` · `driver_schedule.html` · `driver_day_view.html` · `signin_upload.html` · `transportation_master.html`
**Billing:** `billing_dashboard.html` · `billing_add_claim.html` · `billing_add_payment.html` · `billing_reports.html` · `billing_pin_gate.html`
**Admin:** `system_users.html` · `system_status.html` · `admin_templates.html` · `audit_hub.html` · `change_password.html` · `login.html`
**Content:** `menus.html` · `docs_section.html`
**REX:** `rex_log.html` · `rex_memory.html`
**Shared:** `_nav.html` (nav bar) · `master.html` (base layout)
**PDF generator:** `gen_blank_templates.py` (regenerates the 4 PDF templates)

### GOJ Templates — Full Registry
**Registry file (REX reads this for every template request):** `~/Desktop/REX/GOJ_Templates_Registry.json`
All templates are stored in BOTH locations: `~/Desktop/REX/` and `~/Documents/goj files/dashboard/documents/templates/`

| File | Purpose | When to Send |
|---|---|---|
| `GOJ_Weekly_Menu_Form.pdf` | 2-page Russian weekly meal form — clients check food items per day | On request; clients fill out at facility |
| `TEMPLATE_signin.pdf` | Daily client sign-in/attendance sheet | Generated & sent at **3 PM** for next day |
| `TEMPLATE_driver.pdf` | Driver pickup/dropoff route list | Generated & sent at **3 PM** for next day |
| `TEMPLATE_kitchen.pdf` | Kitchen staff meal prep quantities | Generated & sent at **10 AM** for next day |
| `TEMPLATE_distribution.pdf` | Meal distribution list per client | Generated & sent at **10 AM** for next day |

**Generator:** `~/Documents/goj files/dashboard/generate_tomorrow.py`
- Modes: `signin` | `drivers` | `kitchen` | `distribution` | `all`
- Output: `~/Documents/goj files/output_docs/`
- Example: `python3 generate_tomorrow.py --day tomorrow --mode all --send`

**Menu timing rule:** Client menus are submitted ONE WEEK IN ADVANCE. When looking for this week's orders, search Gmail 6–14 days back. Scans come from goj3152.scans@gmail.com to atigerclawai@gmail.com.

**Automated daily schedule (all via Rexxie/Telegram):**
| Time | What's sent |
|---|---|
| 7:30 AM | Morning report: today's expected clients + menu status |
| 10:00 AM | Kitchen sheet + distribution sheet for NEXT day |
| 3:00 PM | Sign-in sheet + driver list for NEXT day |
| 9:00 PM | Drop-off attendance confirmation |

---

## REX Backend (OpenClaw) — Current State

- FastAPI + uvicorn on `http://127.0.0.1:8000`
- Default model: `ollama/llama3` (local-first, HIPAA-safe)
- Secure Mode: ON by default
- **Memory:** `~/.rex/journeys.db` — auto-created when REX starts. AES-256-GCM encrypted.
  - In-chat: type `remember: [fact]` to save · `forget: [topic]` to remove · `what do you remember?` to list
  - Memory is injected into every conversation automatically
- Encryption: triple-layer ChairmanVault
- React frontend: built (`frontend/dist/`) — served at port 8000
- REX widget in GOJ Dashboard calls `/api/rex/chat` on port 8000

## Rexxie — Personal Bot (Kato Only)

- Database: `~/Desktop/REX/rexxie.db` — triple-encrypted, completely separate from REX
- Telegram bot token: `rex_rexxie_telegram_config.json`
- Owner-locked: only Kato's Telegram chat_id can interact
- LaunchAgent: `com.rex.rexxie-bot.plist` (KeepAlive — auto-restarts if crashed)
- **Rexxie is EXCLUSIVELY Kato's** — not shared with staff, not rolled out to others during the current phase

---

## Multi-User REX Architecture (Rollout Plan)

**Core rule: REX instances NEVER share data with each other. Complete isolation.**

| User | REX Instance | Status | Notes |
|---|---|---|---|
| Kato (Chairman) | Personal REX + Rexxie | ✅ Live | Full access, triple-encrypted, Rexxie Telegram bot |
| Vlad | Vlad's own REX | 🔜 Planned | Separate instance, separate memory, separate DB — no access to Kato's data |
| Front desk / Staff | Staff REX (future) | 🔜 Rolling out | Limited scope, no cross-contamination with chairman or Vlad data |

**Isolation rules (enforce in every session):**
1. Kato's `~/.rex/journeys.db` is his alone — never seed Vlad's memories into it, never mix
2. Vlad's REX will have its own separate memory DB at a different path (TBD when built)
3. Rexxie (`rexxie.db`) is chairman-only forever — staff do not get Rexxie access
4. GOJ Dashboard REX widget (`/api/rex/chat`) is the staff-facing REX — scope-limited, no personal data
5. When building Vlad's REX: clone the architecture, new credentials, new DB, new Telegram bot token if needed
6. No REX instance should ever be able to query or learn from another instance's memory

---

## All 14 Launch Agents

Install/reinstall with: `~/Desktop/REX/install-all-agents.command`
Source plists: `~/Desktop/REX/launchd/`
Installed to: `~/Library/LaunchAgents/`

### Always-On (KeepAlive)
| Plist | What it does |
|---|---|
| `com.rex.backend.plist` | REX FastAPI on port 8000 — auto-restarts |
| `com.rex.rexxie-bot.plist` | Rexxie Telegram bot — Kato only, auto-restarts |
| `com.rex.queue-processor.plist` | AI training queue — every 15 min |
| `com.rex.email-pdf-watcher.plist` | Watches inbox for auth PDFs — every 10 min |
| `com.rex.reminders.plist` | Reminders daemon — every 5 min |

### Scheduled Backups
| Plist | Time | What it does |
|---|---|---|
| `com.rex.daily-backup.plist` | **4:30 AM** | Full REX → `REX_Backups/`, keeps 14 days |
| `com.rex.encrypted-backup.plist` | **2:00 AM** | Encrypted vault backup |

### Evening Reports
| Plist | Time | What it does |
|---|---|---|
| `com.rex.evening-report.plist` | **9:00 PM** | GOJ ops summary → Telegram |
| `com.rex.nextday-preview.plist` | **9:30 PM** | Tomorrow's routes + clients |

### Training & Curriculum
| Plist | Schedule | What it does |
|---|---|---|
| `com.goj.rexcurriculum.plist` | Mon–Fri 8 AM | REX daily class + quiz |
| `com.goj.rexxiedaily.plist` | Daily | Rexxie daily lesson → Kato |
| `com.goj.saturdayreview.plist` | Saturday | Weekly review + grade |
| `com.goj.menuaudit.plist` | Daily | Menu audit |
| `com.goj.scanprocessor.plist` | Daily | GOJ scan processor |

---

## Backup System

**Layer 1 — 4:30 AM daily (LaunchAgent):**
```
Script:   ~/Desktop/REX/rex-backup.command
Output:   ~/Desktop/REX_Backups/REX_YYYY-MM-DD_HH-MM/
Keeps:    14 most recent snapshots
Verify:   cat ~/Desktop/REX/.last_backup
```

**Layer 2 — 6 AM + 6 PM (Cowork scheduled):**
```
Script:   ~/Desktop/REX/rex-backup-goj.command
Output:   ~/Desktop/REX_GOJ_Backups/GOJ_YYYY-MM-DD_HH-MM/
Covers:   uploads/, auth docs, Gmail cache, Drive sync manifest
```

**Layer 3 — 2:00 AM (LaunchAgent, encrypted):**
```
Script:   ~/Desktop/REX/rex_encrypted_backup.sh
Output:   ~/Desktop/REX/rex_vault.enc (triple-encrypted)
```

**To check backup health:**
```bash
cat ~/Desktop/REX/.last_backup
ls ~/Desktop/REX_Backups/ | tail -5
ls ~/Desktop/REX_GOJ_Backups/ | tail -5
```

---

## ⚠️ Pending One-Time Setup (Must Do on Mac)

**1. Install LaunchAgents (auto-start everything):**
```bash
chmod +x ~/Desktop/REX/install-all-agents.command
~/Desktop/REX/install-all-agents.command
```

**2. Add missing tokens to `~/Documents/goj files/.env`:**
```
TELEGRAM_TOKEN=8657319466:AAGqWut7BHTTNIEYJvnXIDlNSDCOiML7tic
PAPERLESS_TOKEN=<get from Paperless → Settings → API Token>
PAPERLESS_URL=http://100.99.86.60:8000
```

**3. Set up Paperless Cloudflare Tunnel:**
```bash
~/Desktop/REX/setup-paperless-tunnel.command
```

**4. Set up dashboard Cloudflare Tunnel (goldhealthsys.com → port 8080):**
```bash
~/Desktop/REX/setup_cloudflare_tunnel.sh
```

**5. Clean up 0-byte file:**
```bash
rm ~/Documents/goj\ files/dashboard/goj_dashboard.db
```

---

## Cowork Scheduled Tasks
| Task | Schedule |
|---|---|
| `goj-transport-alert` | 3:04 PM daily |
| `rex-security-audit` | 8 AM every 2 days |
| `daily-menu-delivery` | 9:40 AM Mon–Fri |
| `afternoon-ops-report` | 3:38 PM Mon–Fri |
| `rex-friday-synthesis` | 5:02 AM Friday |
| `session-audit-check-in` | Every 12 hours |
| `rex-daily-backup` | 3:01 AM daily |
| `rex-goj-backup` | 6 AM + 6 PM daily |
| AI training (5 AIs) | Mon–Fri 5 AM |

---

## 14 Architecture Rules (Non-Negotiable)

R1 — Database is the ONLY source of truth. JSON = render/export only.
R2 — Audit trail on every write. Actor, timestamp, old → new value. Append-only.
R3 — Tenant isolation. Every record carries tenant_id. No cross-tenant queries.
R4 — Idempotency. Same input twice never creates duplicates.
R5 — Human review gates. Every AI extraction requires Chairman approval before billing.
R6 — Soft delete only. Never hard delete. Archive with deleted_by, deleted_at, reason.
R7 — Job standards. Every job: inputs, outputs, logging, exit codes, retry logic.
R8 — Chairman authority. All permission changes require Chairman approval.
R9 — Staging required. No billing changes hit production without staging test first.
R10 — Encrypted backups. Off-machine, tested restore, before billing goes live.
R11 — Private repo. All code in private repo under AKC Managing.
R12 — NDAs first. Every contractor signs NDA + IP assignment before seeing code.
R13 — EVV native. EVV-compatible export on all attendance sign-in paths.
R14 — Incident auto-alert. Every incident auto-alerts Chairman and checks DOH flag.

**PROPOSE → APPROVE → EXECUTE. No exceptions. No silent changes.**

---

## HIPAA Encryption Status (Audited 2026-04-04)

| Component | Status | Notes |
|---|---|---|
| **auth_tracker.db** (GOJ, 426 clients) | 🔴 NOT ENCRYPTED | Plain SQLite. TOP PRIORITY — needs SQLCipher. PHI fully exposed at file level. |
| **auth_tracker.db — audit trail** | ✅ Fixed (2026-04-04) | `audit_log` table created. `_audit()` in app.py was silently failing (column mismatch) — now fixed, writes to audit_log. |
| **rex_journeys.db** (~/.rex/) | ✅ AES-256-GCM | Field-level encryption. Key in macOS Keychain via keyring. |
| **rexxie.db** (~/Desktop/REX/) | ⚠️ Partial | Triple field-encryption (AES-GCM→ChaCha20→AES-GCM). SQLite file structure visible. Key in Keychain. Content protected. |
| **rex_vault.enc** | ✅ AES-256-GCM | PBKDF2-SHA256 600k iterations. Passphrase in macOS Keychain. |
| **uploads/** | ✅ Empty | No PHI files present as of audit. Monitor ongoing. |
| **Paperless-NGX (100.99.86.60)** | ⚠️ Unverified | Separate machine — cannot confirm disk encryption. Manual check required. |
| **Daily backup (REX_Backups/)** | ⚠️ Unencrypted | rsync plaintext copy. Does NOT include auth_tracker.db (GOJ data) but does include code/secrets. |
| **Encrypted backup (rex_encrypted_backup.sh)** | ✅ AES-256-CBC | Key in Keychain. Targets /Volumes/cartoons — only runs when external drive connected. |
| **GOJ backup (REX_GOJ_Backups/)** | 🔴 MISSING | Directory does not exist. GOJ client data has no dedicated backup. |
| **.env file (goj files/)** | ⚠️ Plaintext keys | Contains PAPERLESS_TOKEN, PAPERLESS_API_TOKEN, PAPERLESS_URL. File perms 600. |
| **Key storage** | ✅ macOS Keychain | rex_vault, storage.py, rexxie, backup script all use Keychain. JWT secret is file-based (~/.rex/auth/jwt_secret.key). |

### 🔴 TOP PRIORITY Manual Actions for Kato
1. **Encrypt auth_tracker.db with SQLCipher** — 426 client PHI records in plaintext (names, DOB, address, phone, member IDs). This is the most critical HIPAA gap.
2. **Create REX_GOJ_Backups/** — `rex-backup-goj.command` targets it but the folder doesn't exist.
3. **Verify Paperless-NGX disk encryption** — SSH to 100.99.86.60 and confirm FileVault or LUKS is on.
4. **Move Paperless tokens from .env to rex_vault** — run `python3 rex_vault.py add`.
5. **Keep "cartoons" external drive connected** — encrypted backup (Layer 3) only works when it's mounted.
6. **Move JWT secret to Keychain** — `~/.rex/auth/jwt_secret.key` is a key on disk; store it via `security add-generic-password` instead.

---

## Operational Notes
- Telegram alerts are blocked in Cowork automated sessions → fall back to Gmail drafts automatically (this is normal)
- GOJ database = only source of truth. Never spreadsheets or localStorage.
- HIPAA-sensitive ops → Secure Mode (de-identification before any cloud AI)
- Paperless-NGX: `100.99.86.60:8000` (16GB work Mac on Tailscale)
- GOJ public site: goldhealthsys.com (Cloudflare Pages — pending Cloudflare tunnel)
