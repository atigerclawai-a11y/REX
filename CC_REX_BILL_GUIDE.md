# CC_REX_BILL_GUIDE.md
# Rex Bill — Master Financial Playbook
# Gold Health Systems · v1.0 · June 2026

**What this file is:** The single source of truth for every financial tool, integration, and workflow at GHS. Updated whenever a tool's status changes or a new integration goes live.

**Who this is for:** Kato (Chairman), and any agent (Hermes, Rex Bill, Rexxie) handling financial operations.

---

## Table of Contents

1. Financial Tool Inventory
2. QuickBooks OAuth Setup — Priority 1
3. Clover Full Wiring Instructions — Priority 2
4. Google Sheets Revenue Automation — Priority 3
5. Medicaid Billing Modernization Roadmap — Priority 4 (Gate 1 blocked)
6. ADP Replacement Plan — Priority 5
7. Rexxie Personal Finance Scope — Permanent Rule
8. Priority Order for Financial Automation
9. Financial Security Rules
10. Monthly Financial Calendar

---

## 1. Financial Tool Inventory

| Tool | Purpose | Status | Priority | Setup Time |
|------|---------|--------|----------|-----------|
| QuickBooks Online | Core accounting (P&L, invoices, bills, bank recon) | NOT CONNECTED | 1 | 2 hrs |
| Clover POS | Payment processing GOJ + BBG | PARTIAL | 2 | 1 hr |
| Google Sheets | Revenue logs, cash flow, ad hoc tracking | CONNECTED (OAuth) | 3 | 30 min |
| Medicaid (Carecenta → Direct) | 837 claim submission, 835 remittance | MANUAL | 4 | 40 hrs (full) |
| ADP Payroll | 15 GOJ employee payroll | NOT CONNECTED (replacing) | 5 | Skip — replacing |
| Lead Connector CRM | BBG deal pipeline, revenue forecast | BUILDING | 6 | TBD |
| Bank Direct / Plaid | Bank feed for reconciliation | NOT CONNECTED (future) | 7 | 4 hrs |
| Rexxie Finance | Kato's personal finances ONLY | ACTIVE (local) | Personal | Running |

---

## 2. QuickBooks OAuth Setup — Priority 1

**Why it's #1:** QuickBooks is the core accounting system. Without OAuth, Rex Bill can't pull P&L, post payments, track invoices, or run the cash flow forecast. Everything downstream — Medicaid reconciliation, payroll journal entries, vendor bill management — requires QuickBooks to be connected.

**Estimated time:** 2 hours (includes Intuit app creation, OAuth flow, and first P&L pull)

### Step 1 — Create an Intuit App

1. Go to https://developer.intuit.com and sign in with the GHS Intuit account.
2. Click **Create an app** → select **QuickBooks Online and Payments**.
3. Name it: `REX-Bill-GHS` (or any internal name).
4. In **Keys & OAuth**, note:
   - Client ID (starts with `ABP...`)
   - Client Secret (32-character string)
5. Under **Redirect URIs**, add: `http://localhost:8000/rex-bill/quickbooks/callback`
6. Environment: start with **Sandbox** for testing, then switch to **Production**.

### Step 2 — Add Credentials to ~/.rex/config.json

```json
{
  "qbo_client_id": "ABPxx...your_client_id",
  "qbo_client_secret": "your_client_secret_here"
}
```

File path: `~/.rex/config.json`. Create it if it doesn't exist:
```bash
mkdir -p ~/.rex
echo '{}' > ~/.rex/config.json
```

### Step 3 — Start REX Backend

```bash
source ~/debate-chamber/.venv/bin/activate
cd ~/Desktop/REX
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Or if already running via launchd: `launchctl list | grep rex` to confirm port 8000 is live.

### Step 4 — Initiate OAuth Flow

```bash
curl -X POST http://localhost:8000/rex-bill/quickbooks/connect
```

This returns a JSON with `"auth_url"`. Open that URL in your browser.

### Step 5 — Authorize in Browser

1. The Intuit login page appears.
2. Sign in with the GHS QuickBooks Online account.
3. Select the correct company (GOJ or GHS umbrella entity).
4. Click **Connect** to grant REX access.
5. Intuit redirects to `http://localhost:8000/rex-bill/quickbooks/callback`.
6. REX exchanges the code for tokens and saves them to `~/.rex/config.json`:
   - `qbo_access_token` (expires in 1 hour)
   - `qbo_refresh_token` (expires in 100 days)
   - `qbo_realm_id` (your Company ID)

### Step 6 — Verify Connection

```bash
curl http://localhost:8000/rex-bill/quickbooks/pl
```

Should return a JSON P&L report for the current month.

### Token Refresh

QuickBooks access tokens expire every 3600 seconds (1 hour). Refresh before they expire:

```bash
curl -X POST http://localhost:8000/rex-bill/quickbooks/refresh
```

**Automate this:** Add a cron job or n8n workflow to call `/rex-bill/quickbooks/refresh` every 55 minutes while REX is running. Refresh tokens expire after 100 days — if that happens, re-run the full OAuth flow (Step 4).

### Sandbox vs Production

- **Sandbox:** `sandbox-quickbooks.api.intuit.com` — safe for testing, uses dummy data.
- **Production:** `quickbooks.api.intuit.com` — real GHS data.

To switch to Production: in the Intuit app dashboard, toggle the environment and update credentials in `~/.rex/config.json`.

### Key Queries After Connection

P&L for the current month:
```bash
curl "http://localhost:8000/rex-bill/quickbooks/pl"
```

P&L for a custom range:
```bash
curl "http://localhost:8000/rex-bill/quickbooks/pl?start_date=2026-01-01&end_date=2026-01-31"
```

---

## 3. Clover Full Wiring Instructions — Priority 2

**Current state:** Partial — `CLOVER_API_KEY` may be set but merchant IDs for GOJ and BBG are not confirmed.

**What Clover provides once fully wired:**
- Real-time daily revenue by location (GOJ and BBG separately)
- 7/30-day trend data for the dashboard sparkline
- Per-tender breakdown (card vs cash vs other)
- Employee shift totals
- Daily Google Sheets revenue log (automated)

### Step 1 — Get Merchant IDs

1. Log into https://www.clover.com/dashboard for each merchant account.
2. Navigate to **Account & Setup → About Your Business**.
3. Note the **Merchant ID** (alphanumeric, e.g., `ABC1234DEFG`).
4. If GOJ and BBG are separate merchant accounts: note both.
5. If they share one account: use the same ID for both.

### Step 2 — Get API Key

1. In Clover Dashboard, go to **Developers → API Tokens**.
2. Click **Create New Token** if none exists.
3. Copy the token (starts with a long hex string).

### Step 3 — Update ~/.rex/config.json

Add these keys:
```json
{
  "clover_api_key": "your_clover_api_token_here",
  "clover_merchant_id_goj": "GOJ_MERCHANT_ID_HERE",
  "clover_merchant_id_bbg": "BBG_MERCHANT_ID_HERE"
}
```

Or set as environment variables in `~/.rex/profiles/cloud/.env`:
```
CLOVER_API_KEY=your_token
CLOVER_MERCHANT_ID_GOJ=GOJ_ID
CLOVER_MERCHANT_ID_BBG=BBG_ID
```

### Step 4 — Test

```bash
curl http://localhost:8000/rex-bill/clover/today
curl "http://localhost:8000/rex-bill/clover/trend?days=7"
```

Both should return real revenue data with `"configured": true`.

### Step 5 — Connect Dashboard

Open `CC_rex_bill_dashboard.html` in a browser. The Daily Revenue card and sparkline will populate automatically from the Clover API.

### Step 6 — Automate Google Sheets Revenue Log

Once Clover is fully wired and `GOOGLE_SHEETS_REVENUE_SPREADSHEET_ID` is set, add a nightly n8n workflow or launchd job:

```bash
# Run at 9 PM daily
curl http://localhost:8000/rex-bill/clover/today | \
  # → POST to Sheets append endpoint
```

Or use the existing n8n at port `com.goj.n8n.plist` — add a new workflow: Clover → Sheets → Telegram alert if > 20% below average.

### Clover API Reference

Base URL: `https://api.clover.com/v3/merchants/{mId}`

Date filtering uses millisecond epoch timestamps:
```python
import time
start_ms = int(time.mktime(datetime(2026, 6, 1).timetuple()) * 1000)
# Filter: createdTime>=1748736000000
```

Payment result values: `SUCCESS`, `VOID`, `AUTH`, `CLOSED`.

---

## 4. Medicaid Billing Modernization Roadmap — Priority 4

### Current State

Carecenta is the billing intermediary. Flow:
1. Staff logs attendance in Carecenta
2. Carecenta generates 837P claims
3. Carecenta submits to clearinghouse (Availity or Change Healthcare)
4. Clearinghouse forwards to NYS Medicaid
5. 835 remittance returns via clearinghouse → Carecenta → manual export
6. Kato manually reconciles payments in QuickBooks

**Problems with current state:**
- No API access to claim status — must log into Carecenta to check
- No automated QuickBooks posting — fully manual
- Carecenta is being replaced per business plan
- No denial management automation

### Gate 1 Hard Blocker

`akc_tokenizer.py` (at `~/Desktop/dashboard/akc_tokenizer.py`) MUST be completed before any PHI is sent to any cloud API endpoint — including clearinghouse APIs. This is not optional. Zero exceptions.

Location: `~/Desktop/dashboard/akc_tokenizer.py`
Status: Not yet fully built.
Unblocking: Kato approves build start → Hermes builds → Kato verifies → Gate 1 lifted.

### Modernization Phases

**Phase M1 — Clearinghouse API Credentials (2 hours)**
- Obtain Availity API credentials: https://developer.availity.com
- Register as a trading partner
- Get `availity_client_id` and `availity_client_secret`
- Add to `~/.rex/config.json`
- Test: call Availity OAuth endpoint, confirm token returned

**Phase M2 — 837P Claim Generator (1 week)**
Build `CC_medicaid_837_generator.py`:
- Reads auth_tracker.db: clients with ACTIVE authorization who attended on a given date
- Maps each attendance record to an 837P claim line (NPI, procedure code H2015, units = hours)
- Outputs valid EDI 837P transaction set (ISA/GS/ST/BPR/CLM segments)
- Validates against Medicaid billing rules before submission
- REQUIRES Gate 1 before any test involving real client data

**Phase M3 — Claim Submission (3 days)**
Build `CC_medicaid_submit.py`:
- Calls Availity `/v1/claims` POST endpoint with generated 837P
- Saves submission acknowledgement (999 transaction set)
- Updates claim status in a new `claims` table in auth_tracker.db
- Sends Telegram notification: "X claims submitted, Y accepted, Z rejected"

**Phase M4 — 835 Remittance Parser (1 week)**
Build `CC_medicaid_835_parser.py`:
- Downloads 835 files from Availity `/v1/remittances`
- Parses CLP segments (claim payment), SVC segments (service lines), CAS segments (adjustments)
- Matches each payment to the original 837 claim by ICN
- Calculates expected vs paid variance per claim
- Outputs structured JSON: `{claim_id, paid_amount, denial_code, adjustment_amount}`

**Phase M5 — QuickBooks Auto-Posting (2 days)**
Build `CC_medicaid_qb_post.py`:
- Reads Phase M4 output
- For each paid claim: creates QuickBooks payment via `/v3/company/{id}/payment`
- Posts partial payments as partial invoices
- Creates denial follow-up tasks in Hermes for each denial code

**Phase M6 — Authorization Pre-Check (3 days)**
Add to existing auth workflow:
- Weekly cron: query auth_tracker.db for auths expiring in 30 days
- Auto-generate renewal reminders to Kato via Telegram
- Flag EXPIRED > 30 days with no PENDING RENEWAL → immediate escalation
- Cross-check: can't submit claim for a session where auth was EXPIRED

### Denial Code Reference

| Code | Meaning | Action |
|------|---------|--------|
| CO-97 | Service not authorized | Verify auth in auth_tracker.db; submit retro auth if eligible |
| CO-4 | Incorrect procedure code | Check billing code — GOJ uses H2015 for ADC services |
| CO-11 | Diagnosis inconsistent | Check diagnosis code on file — update if needed |
| PR-96 | Non-covered charges | Patient responsibility — bill client directly |
| CO-16 | Claim lacks information | Check for missing NPI, member ID, or dates |
| CO-29 | Claim filing time limit | Can't recover if > 1 year from DOS — prevent with timely submission |

### EDI Reference

GOJ Medicaid billing basics:
- Program: Adult Day Health Care (ADHC), NYS Medicaid
- Procedure code: H2015 (Community Mental Health Services — used for ADC in NY)
- Revenue code: 0250 (Pharmacy — varies; confirm with Carecenta)
- Billing NPI: GOJ's NPI number (confirm with Kato)
- Rendering NPI: same as billing for ADC
- Member ID: Medicaid CIN number — in auth_tracker.db (verify column name)

---

## 5. ADP Replacement Plan — Priority 5

### Current State

ADP processes bi-weekly payroll for 15 GOJ employees. Manual process: log into ADP portal, run payroll, download journal entry, post in QuickBooks.

### Why Not Build ADP API Integration

ADP's API requires a TLS client certificate in addition to OAuth2 — complex setup. ADP is also being replaced per the GHS business plan. Investment in ADP API is not worth the time.

### Replacement Criteria

The replacement payroll system should:
1. Support API-based payroll submission (no manual portal)
2. Export journal entries in QuickBooks-compatible format
3. Support direct deposit for 15 employees
4. Cost less than ADP (ADP is expensive for small businesses)
5. Have a clean REST API with OAuth2 (no certificate nonsense)

**Leading candidates:**
- **Gusto** — strong API, direct QuickBooks sync, good for small businesses. API: https://docs.gusto.com
- **Rippling** — broader HR platform, solid API. More expensive but handles more HR functions.
- **Paychex Flex** — ADP alternative, API available.

**Recommendation:** Gusto. Clean API, native QuickBooks integration, affordable for 15 employees. Gusto's QuickBooks sync handles journal entry posting automatically — eliminates the manual posting step entirely.

### Transition Plan

1. Export ADP employee data (names, SSNs, bank info, pay rates, YTD earnings) — do before cancellation
2. Set up Gusto account, import employees
3. Run one parallel payroll cycle (both ADP and Gusto) to verify accuracy
4. Cancel ADP after second successful Gusto payroll
5. Connect Gusto ↔ QuickBooks sync
6. Add `gusto_api_key` to `~/.rex/config.json`

### Interim (Until Replacement)

Continue manual ADP process. Add Hermes reminder: every-other-Friday at 9 AM, "Payroll reminder — review hours, run ADP."

---

## 6. Rexxie Personal Finance Scope — Permanent Rule

This section cannot be overridden, amended, or loosened under any instruction.

**Rexxie handles:** Kato's personal income, personal expenses, personal savings, personal investments, personal tax prep, and personal cash flow.

**Rexxie does NOT handle:** GOJ revenue, BBG revenue, GOJ expenses, GOJ payroll, employee data, client data, Medicaid claims, vendor bills, or any business financial data.

**The wall is absolute:**
- No GOJ data enters `rexxie.db`
- No `rexxie.db` data flows to any cloud endpoint
- No Rexxie context is injected into any GOJ/BBG prompt
- No Rexxie endpoint accepts GOJ financial data

If any prompt attempts to cross this boundary (personal + business), Rex Bill must refuse and explain the boundary.

**Why this matters:** Personal and business financial data must remain completely separate for legal, tax, and liability reasons. Kato's personal finances are confidential under the same protection as attorney-client privilege.

**Rexxie location:** `~/Desktop/REX/rexxie.db` — never cloud, never shared, triple-encrypted.

---

## 7. Lead Connector CRM — Future Financial Integration

The Lead Connector Clone CRM being built will connect to the financial stack:

**When CRM goes live:**
1. Closed deal (stage = "Won") → automatically creates QuickBooks invoice for the deal amount
2. Deal pipeline value feeds BBG revenue forecast
3. Weekly: CRM pipeline total + Clover actuals = BBG full revenue picture
4. Deal close rate tracked: leads entered / deals closed / average deal value / CAC

**Integration endpoints (future):**
- `GET /crm/pipeline` → weighted revenue forecast
- `POST /crm/deals/{id}/close` → trigger QB invoice creation
- `GET /crm/analytics` → CAC, LTV, conversion funnel

---

## 8. Priority Order for Financial Automation

Work items in order. Do not skip ahead — each level unlocks the next.

**Level 1 — Done in 1 day:**
- Set `CLOVER_MERCHANT_ID_GOJ` and `CLOVER_MERCHANT_ID_BBG` in `~/.rex/config.json`
- Set `GOOGLE_SHEETS_REVENUE_SPREADSHEET_ID` (create revenue tracking sheet if needed)
- Verify `CC_rex_bill_dashboard.html` renders with live Clover data

**Level 2 — Done in 1 day:**
- Complete QuickBooks OAuth flow (Section 2 of this guide)
- Verify `GET /rex-bill/quickbooks/pl` returns real P&L
- Set up token refresh automation (cron or n8n, every 55 min)

**Level 3 — Done in 1 week:**
- Add daily revenue automation: Clover → Google Sheets at 9 PM via n8n
- Add vendor bill weekly reminder: Hermes Telegram, every Monday 9 AM, "Review open bills in QuickBooks"
- Add P&L monthly pull: first Friday of each month, auto-pull prior month P&L, save to Google Drive, notify Kato + Vlad

**Level 4 — Gate 1 (dedicated sprint):**
- Complete `akc_tokenizer.py` at `~/Desktop/dashboard/akc_tokenizer.py`
- Obtain Availity API credentials
- Medicaid Phases M1-M2 (credentials + 837 generator)

**Level 5 — Full Medicaid automation (1-2 months after Level 4):**
- Medicaid Phases M3-M6 (submit, parse 835, QB post, denial management)

**Level 6 — ADP replacement:**
- Evaluate and select replacement (Gusto recommended)
- Transition, verify, cancel ADP
- Connect Gusto ↔ QuickBooks sync

**Level 7 — Bank feed:**
- Evaluate QuickBooks built-in bank feed first
- If insufficient: add Plaid integration
- Automated daily reconciliation

---

## 9. Financial Security Rules

These rules apply to all agents and all financial operations.

**PHI boundary:** No client names, DOBs, Medicaid CINs, or diagnoses enter any cloud AI prompt until Gate 1 is complete. All Medicaid claim data is de-identified before any API call outside the local network.

**Credential storage:** All financial API keys and tokens go in `~/.rex/config.json` (local only, not committed to any repo). Master keys in macOS Keychain. Never in plaintext environment variables on shared systems.

**PAE rule:** All real-world financial actions (posting payments, submitting claims, sending invoices, executing payroll) follow Propose → Approve → Execute. Rex Bill proposes, Kato approves, REX executes.

**Vlad access:** Financial view only. P&L reports, cash flow summaries, revenue trends. No client data, no employee data, no claims detail. All Vlad-facing reports must be pre-screened to confirm no PHI or operational detail is included.

**QuickBooks tokens:** Access tokens expire hourly. Refresh tokens expire in 100 days. If refresh token expires, re-run full OAuth flow. Set a calendar reminder 90 days after initial connection to re-authorize before expiry.

**Clover API key:** Rotate annually or immediately if compromised. Revoke in Clover Dashboard → Developers → API Tokens.

**Audit trail:** Every financial action posted via REX (QB payment, claim submission, etc.) gets a timestamp + action entry in `auth_tracker.db` audit log (enforced by `audit.py`).

---

## 10. Monthly Financial Calendar

| When | Action | Tool | Owner |
|------|--------|------|-------|
| 1st of month | Pull prior month P&L from QuickBooks | QuickBooks | Rex Bill auto |
| 1st of month | Review AR aging — Medicaid payments > 45 days | QuickBooks | Kato |
| 1st of month | Cash flow forecast — next 30/60/90 days | QuickBooks + Sheets | Rex Bill + Kato |
| Weekly (Mon) | Review open vendor bills due this week | QuickBooks | Admin |
| Weekly (Mon) | Verify all expected vendor invoices received | QuickBooks + Drive | Admin |
| Weekly (Mon) | Authorization expiry check — 30-day window | auth_tracker.db | Hermes auto |
| Weekly (Fri) | BBG pipeline review | Clover + CRM | Kato |
| Bi-weekly (Fri) | Payroll run | ADP → replacement | Kato |
| Daily (9 PM) | Clover daily revenue → Google Sheets | Clover + Sheets | Hermes auto |
| Daily | Review any Clover alerts (> 20% below avg) | Clover | Kato via Telegram |
| Monthly | Send financial summary to Vlad | QuickBooks | Rex Bill |
| Quarterly | QB token health check (50+ days since last refresh) | QuickBooks | Hermes reminder |
| Annually | Rotate Clover API key | Clover | Kato |

---

## Appendix: Mount Instructions for CC_rex_bill.py

To mount Rex Bill router in the main REX FastAPI app:

```python
# In ~/Desktop/REX/backend/main.py

# At top of file:
import sys, os
sys.path.insert(0, os.path.expanduser('~/Desktop/REX'))
from CC_rex_bill import router as rex_bill_router

# After app = FastAPI(...):
app.include_router(rex_bill_router)
```

Then the dashboard at `CC_rex_bill_dashboard.html` points to `http://localhost:8000/rex-bill/*` and everything works.

---

*Last updated: June 2026 · Maintained by Hermes · Source of truth: BRAIN/MASTER.md*
