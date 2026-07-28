"""
CC_rex_bill.py — Rex Bill: Financial Intelligence Layer for Gold Health Systems
FastAPI router — mounts to REX on port 8000 at /rex-bill

Modules:
  A — Financial Tool Knowledge Base (8 tools, fully described)
  B — Workflow Templates (9 pre-built workflows)
  C — Clover POS Integration (live revenue data)

To mount in main.py:
    from CC_rex_bill import router as rex_bill_router
    app.include_router(rex_bill_router)
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pathlib import Path
from pydantic import BaseModel
from typing import Optional
import httpx
import os
import json
import sqlite3
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rex-bill", tags=["Rex Bill — Financial Intelligence"])


# ─────────────────────────────────────────────────────────────────────────────
# MODULE A — FINANCIAL TOOL KNOWLEDGE BASE
# ─────────────────────────────────────────────────────────────────────────────

FINANCIAL_TOOLS: dict = {
    "quickbooks": {
        "name": "QuickBooks Online",
        "purpose": "Core accounting — invoices, bills, P&L, bank reconciliation",
        "api_docs": "https://developer.intuit.com/app/developer/qbo/docs",
        "auth_type": "OAuth2",
        "credentials_location": "~/.rex/config.json (qbo_client_id, qbo_client_secret, qbo_realm_id)",
        "key_endpoints": [
            "GET  /v3/company/{realmId}/query              — SQL-like queries against any entity",
            "GET  /v3/company/{realmId}/invoice            — List invoices",
            "POST /v3/company/{realmId}/invoice            — Create invoice",
            "GET  /v3/company/{realmId}/bill               — List vendor bills",
            "POST /v3/company/{realmId}/bill               — Create vendor bill",
            "GET  /v3/company/{realmId}/payment            — Payment records",
            "POST /v3/company/{realmId}/payment            — Post a payment",
            "GET  /v3/company/{realmId}/report/ProfitAndLoss   — P&L report",
            "GET  /v3/company/{realmId}/report/BalanceSheet    — Balance sheet",
            "GET  /v3/company/{realmId}/report/CashFlow        — Cash flow statement",
            "GET  /v3/company/{realmId}/vendor             — Vendor list",
            "GET  /v3/company/{realmId}/customer           — Customer/client list",
            "GET  /v3/company/{realmId}/account            — Chart of accounts",
            "GET  /v3/company/{realmId}/journalentry       — Journal entries",
        ],
        "ghs_workflows": [
            "Medicaid payment reconciliation — post 835 remittances as payments against invoices",
            "Payroll recording — ADP payroll journal entries, debit payroll expense credit cash",
            "Vendor bills — rent, utilities, food supplies, insurance",
            "Monthly P&L — GOJ + BBG combined or class-separated",
            "Client invoicing — GOJ private pay clients",
            "Bank reconciliation — match QuickBooks bank feed to actual statements",
            "Accounts receivable aging — flag Medicaid payments > 60 days",
            "Cash flow forecast — pull receivables + bills for 30/60/90 day projections",
        ],
        "integration_status": "NOT YET CONNECTED",
        "setup_priority": 1,
        "estimated_setup_time": "2 hours",
        "setup_guide": "See CC_REX_BILL_GUIDE.md — Section 2: QuickBooks OAuth Setup",
        "env_vars": [
            "QBO_CLIENT_ID",
            "QBO_CLIENT_SECRET",
            "QBO_REALM_ID",
            "QBO_ACCESS_TOKEN",
            "QBO_REFRESH_TOKEN",
        ],
        "notes": (
            "OAuth2 — 1-hour access tokens, 100-day refresh tokens. "
            "Realm ID = Company ID, visible in QBO URL after /app/. "
            "Sandbox available at sandbox-quickbooks.api.intuit.com for testing. "
            "Token refresh must be automated — REX should refresh before expiry."
        ),
    },

    "clover": {
        "name": "Clover POS",
        "purpose": "Payment processing at GOJ and BBG — client payments, retail sales",
        "api_docs": "https://docs.clover.com/reference",
        "auth_type": "API Key (Bearer token)",
        "credentials_location": (
            "~/.rex/config.json "
            "(clover_api_key, clover_merchant_id_goj, clover_merchant_id_bbg)"
        ),
        "key_endpoints": [
            "GET /v3/merchants/{mId}/orders              — All orders",
            "GET /v3/merchants/{mId}/payments            — All payments (filterable by date)",
            "GET /v3/merchants/{mId}/employees           — Employee list",
            "GET /v3/merchants/{mId}/shifts              — Employee shifts",
            "GET /v3/merchants/{mId}/inventory/items     — Inventory",
            "GET /v3/merchants/{mId}/cash_events         — Cash drawer events",
            "GET /v3/merchants/{mId}/tender_summaries    — Payment method breakdown",
            "GET /v3/merchants/{mId}                     — Merchant info (name, timezone)",
        ],
        "ghs_workflows": [
            "Daily revenue reconciliation — match Clover batch to bank deposit",
            "Shift reporting — per-employee sales summary",
            "Cash flow tracking — daily cash vs card breakdown",
            "Inventory tracking — BBG product stock levels and low-stock alerts",
            "Revenue trend — 7/30 day Clover revenue for dashboard",
        ],
        "integration_status": "CONNECTED (partial)",
        "setup_priority": 2,
        "estimated_setup_time": "1 hour (partial connection exists)",
        "env_vars": [
            "CLOVER_API_KEY",
            "CLOVER_MERCHANT_ID_GOJ",
            "CLOVER_MERCHANT_ID_BBG",
        ],
        "notes": (
            "Two merchant accounts may exist: one for GOJ, one for BBG. "
            "Confirm merchant IDs in Clover Dashboard → Account & Setup → About Your Business. "
            "API key in Clover Dashboard → Developers → API Tokens. "
            "Date filters use millisecond epoch timestamps."
        ),
    },

    "medicaid_billing": {
        "name": "Medicaid Billing (Carecenta → Direct Clearinghouse)",
        "purpose": "Submit 837P claims, receive 835 remittances for GOJ adult day care services",
        "api_docs": "https://developer.availity.com  |  https://developers.changehealthcare.com",
        "auth_type": "OAuth2 (Availity)  /  API Key (Change Healthcare)",
        "credentials_location": (
            "~/.rex/config.json — availity_client_id, availity_client_secret "
            "(NOT YET SET UP)"
        ),
        "key_endpoints": [
            "POST /v1/claims                                         — Submit 837P batch (Availity)",
            "GET  /v1/claims/{claimId}/status                        — Check claim status",
            "GET  /v1/remittances                                    — Download 835 remittance files",
            "POST /change-healthcare/medicalnetwork/submitclaim/v3  — Submit via CHC",
            "GET  /change-healthcare/medicalnetwork/acknowledgement/v3/{id} — Acknowledgement",
            "GET  /change-healthcare/medicalnetwork/remittance/v3   — 835 via CHC",
        ],
        "ghs_workflows": [
            "Weekly claim submission — 837P for all Medicaid clients who attended that week",
            "Remittance processing — download 835, match to claims, post to QuickBooks",
            "Denial management — flag CO-97 (not authorized), CO-4 (wrong procedure), PR-96 (patient balance)",
            "Authorization cross-reference — verify billed services match auth_tracker.db authorizations",
            "Underpayment detection — flag when payment < expected rate",
        ],
        "integration_status": "MANUAL (Carecenta) — Modernization in progress",
        "setup_priority": 3,
        "estimated_setup_time": "40 hours (full modernization)",
        "current_vendor": "Carecenta",
        "target_vendors": ["Availity", "Change Healthcare"],
        "env_vars": [
            "AVAILITY_CLIENT_ID",
            "AVAILITY_CLIENT_SECRET",
            "CHC_API_KEY",
        ],
        "notes": (
            "GATE 1 BLOCKER: akc_tokenizer.py must be built before any PHI reaches clearinghouse API. "
            "Carecenta currently handles EDI 837 submission and 835 receipt. "
            "Migration plan: Gate 1 → direct 837 generator → clearinghouse API → 835 parser → QB posting. "
            "425 GOJ Medicaid clients. Rate ~$80-120/day/client."
        ),
    },

    "adp": {
        "name": "ADP Payroll",
        "purpose": "Payroll processing for 15 GOJ employees",
        "api_docs": "https://developers.adp.com",
        "auth_type": "OAuth2 with TLS client certificate",
        "credentials_location": "~/.rex/config.json — NOT YET SET UP",
        "key_endpoints": [
            "GET /hr/v2/workers                    — Employee list",
            "GET /payroll/v1/pay-distributions     — Pay distribution data",
            "GET /payroll/v1/pay-statements/{id}  — Pay stub detail",
            "GET /payroll/v1/payroll-instructions  — Payroll run data",
        ],
        "ghs_workflows": [
            "Bi-weekly payroll reconciliation — verify ADP totals match QB entries",
            "Employee record sync → auth_tracker.db employees table (15 rows)",
            "Payroll journal entries → QuickBooks (debit payroll expense, credit cash)",
            "Tax filing reminders — quarterly 941, annual W-2 deadlines",
        ],
        "integration_status": "NOT CONNECTED — Being replaced",
        "setup_priority": 5,
        "estimated_setup_time": "8 hours (complex OAuth with certificates — being replaced anyway)",
        "env_vars": [
            "ADP_CLIENT_ID",
            "ADP_CLIENT_SECRET",
            "ADP_CERT_PATH",
        ],
        "notes": (
            "ADP API requires a TLS client certificate in addition to OAuth2 — complex setup. "
            "Being actively replaced per GHS business plan. "
            "15 current GOJ employees in auth_tracker.db employees table. "
            "Do not invest significant time in ADP API; replacement handles this."
        ),
    },

    "google_sheets": {
        "name": "Google Sheets",
        "purpose": "Financial tracking spreadsheets — revenue logs, expense tracking, ad hoc analysis",
        "api_docs": "https://developers.google.com/sheets/api/reference/rest",
        "auth_type": "OAuth2 (already configured via rex_gmail.py)",
        "credentials_location": (
            "~/.rex_google_token.json (shared token with Gmail + Drive). "
            "Credentials: ~/Desktop/REX/google_credentials.json"
        ),
        "key_endpoints": [
            "GET  /v4/spreadsheets/{spreadsheetId}                     — Spreadsheet metadata",
            "GET  /v4/spreadsheets/{spreadsheetId}/values/{range}      — Read range",
            "PUT  /v4/spreadsheets/{spreadsheetId}/values/{range}      — Write/overwrite range",
            "POST /v4/spreadsheets/{spreadsheetId}/values/{range}:append — Append rows",
            "POST /v4/spreadsheets                                     — Create new spreadsheet",
            "POST /v4/spreadsheets/{spreadsheetId}:batchUpdate         — Formatting, charts",
        ],
        "ghs_workflows": [
            "Daily revenue log — Hermes appends Clover daily totals at 9 PM",
            "Expense tracking — vendor payment log, flagged when category jumps > 15%",
            "Medicaid claim log — submitted vs paid vs denied (until clearinghouse connected)",
            "Budget vs actual — monthly comparison with prior year",
            "Cash flow forecast — 30/60/90 day projections",
        ],
        "integration_status": "CONNECTED (OAuth configured)",
        "setup_priority": 4,
        "estimated_setup_time": "30 minutes (OAuth already done)",
        "env_vars": ["GOOGLE_SHEETS_REVENUE_SPREADSHEET_ID"],
        "notes": (
            "Uses same OAuth token as Gmail and Drive — already live. "
            "Token at ~/.rex_google_token.json. "
            "Credentials at ~/Desktop/REX/google_credentials.json. "
            "Set GOOGLE_SHEETS_REVENUE_SPREADSHEET_ID to the main revenue tracking sheet."
        ),
    },

    "rexxie_finance": {
        "name": "Rexxie — Personal Finance Confidant",
        "purpose": "Kato's PERSONAL financial confidant. Income, spending, savings, tax. ZERO GOJ data.",
        "api_docs": "Internal — ~/Desktop/REX/backend/rex_rexxie.py",
        "auth_type": "Chairman-only, triple-encrypted, local only",
        "credentials_location": "macOS Keychain: rex-sovereign",
        "key_endpoints": [
            "POST /rexxie/chat — Private financial chat (local-only endpoint, never cloud)",
        ],
        "ghs_workflows": [
            "Personal income tracking (NOT GOJ revenue)",
            "Personal expense review and categorization",
            "Personal savings goals",
            "Personal tax prep support",
            "Personal cash flow monitoring",
        ],
        "integration_status": "ACTIVE (local only — private lane)",
        "setup_priority": 0,
        "estimated_setup_time": "Already running",
        "notes": (
            "CRITICAL BOUNDARY: Rexxie finance scope is PERSONAL ONLY. "
            "Zero GOJ data. Zero BBG data. Zero crossover with business financials. "
            "Private lane — local only. rexxie.db never reaches cloud. "
            "AES-256-GCM + SQLCipher vault. Do not mix personal and GOJ/BBG in any Rexxie context."
        ),
    },

    "lead_connector": {
        "name": "Lead Connector Clone (CRM — Being Built)",
        "purpose": "Track deal values, pipeline revenue, client acquisition costs for BBG",
        "api_docs": "Internal — being built",
        "auth_type": "Internal API key (TBD)",
        "credentials_location": "TBD",
        "key_endpoints": [
            "GET  /crm/pipeline           — Revenue pipeline with deal totals",
            "GET  /crm/deals              — All deals with values and stages",
            "GET  /crm/deals/{id}         — Deal details",
            "POST /crm/deals              — Create new deal",
            "PUT  /crm/deals/{id}         — Update deal stage/value",
        ],
        "ghs_workflows": [
            "BBG revenue pipeline — open deals and expected close values",
            "Client acquisition cost analysis — marketing spend vs new client value",
            "Deal close rate tracking — conversion funnel metrics",
            "Revenue forecast — pipeline-weighted projections",
            "Deal-to-invoice bridge — closed deal auto-creates QuickBooks invoice",
        ],
        "integration_status": "BEING BUILT",
        "setup_priority": 6,
        "estimated_setup_time": "TBD — depends on build progress",
        "notes": (
            "CRM being built in parallel with GHS business plan. "
            "Will integrate with QuickBooks: closed deal → QB invoice. "
            "Also feeds Hermes revenue forecasting."
        ),
    },

    "bank_direct": {
        "name": "Direct Bank Feed / Plaid (Future Phase)",
        "purpose": "Real-time bank transaction feed for automated reconciliation",
        "api_docs": "https://plaid.com/docs",
        "auth_type": "API Key + Plaid Link (user-facing OAuth)",
        "credentials_location": "Not yet configured",
        "key_endpoints": [
            "POST /transactions/get   — Get transactions for date range",
            "POST /balance/get        — Account balances",
            "POST /auth/get           — Account + routing numbers",
            "POST /transactions/sync  — Incremental transaction sync (preferred)",
        ],
        "ghs_workflows": [
            "Daily bank reconciliation — match Clover deposits to bank credits",
            "Cash flow monitoring — real-time balance alerts",
            "Payroll debit verification — confirm ADP/payroll ACH cleared",
            "Medicaid payment detection — flag incoming ACH from Medicaid",
        ],
        "integration_status": "NOT CONNECTED — Future phase",
        "setup_priority": 7,
        "estimated_setup_time": "4 hours",
        "env_vars": ["PLAID_CLIENT_ID", "PLAID_SECRET", "PLAID_ACCESS_TOKEN"],
        "notes": (
            "QuickBooks Online has a built-in bank feed connector — evaluate that first. "
            "If QB bank feed covers reconciliation needs, skip Plaid. "
            "Plaid adds value for real-time alerting that QB doesn't provide."
        ),
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# MODULE B — WORKFLOW TEMPLATES
# ─────────────────────────────────────────────────────────────────────────────

WORKFLOWS: list = [
    {
        "id": "medicaid_reconciliation",
        "name": "Medicaid Payment Reconciliation",
        "frequency": "Monthly",
        "tools": ["QuickBooks", "Availity / Change Healthcare clearinghouse"],
        "estimated_time": "2-4 hours manual → 15 min automated",
        "owner": "Kato / Billing",
        "steps": [
            "1.  Log into Availity or Change Healthcare clearinghouse portal",
            "2.  Download all 835 remittance files for the billing period",
            "3.  Open each 835 — locate CLP segments (claim-level payment) and SVC segments (service lines)",
            "4.  Match each CLP to the original 837 claim by ICN or claim reference number",
            "5.  For PAID claims: post payment in QuickBooks against the corresponding client invoice",
            "6.  For DENIED claims: note denial code — CO-97 (not authorized), CO-4 (wrong procedure code), PR-96 (patient responsibility)",
            "7.  Create denial follow-up task in Hermes for each denial code",
            "8.  For PARTIAL payments: post partial amount, note CAS adjustment segment, flag for review",
            "9.  Run QuickBooks P&L → verify Medicaid revenue line matches total posted payments",
            "10. Reconcile with bank statement — confirm ACH deposits match QuickBooks total",
        ],
        "current_status": "Manual — Carecenta submits EDI, payments received via ACH",
        "automation_potential": "High — Steps 2-9 fully automatable once clearinghouse API connected",
        "automation_blockers": [
            "Gate 1 (akc_tokenizer.py) must be completed",
            "QuickBooks OAuth must be connected",
            "Clearinghouse API credentials (Availity or CHC) must be obtained",
        ],
        "notes": "425 GOJ Medicaid clients. Rate approx $80-120/client/day. Monthly Medicaid revenue ~$500K-800K depending on attendance.",
    },
    {
        "id": "daily_revenue_close",
        "name": "Daily Revenue Close",
        "frequency": "Daily (end of business)",
        "tools": ["Clover POS", "QuickBooks"],
        "estimated_time": "15 min manual → 2 min automated",
        "owner": "Operations / Kato",
        "steps": [
            "1. Pull Clover day-end summary — total sales, card vs cash breakdown, tips",
            "2. Verify physical cash drawer count matches Clover expected cash total",
            "3. Compare Clover total to expected based on day's attendance and pricing",
            "4. Post daily sales journal entry in QuickBooks (debit cash/AR, credit revenue)",
            "5. Flag any discrepancy > $50 for follow-up",
            "6. Confirm Clover batch settled (automated at midnight — verify in Clover dashboard)",
            "7. Append row to Google Sheets revenue log: date, GOJ, BBG, payment method breakdown",
        ],
        "current_status": "Manual",
        "automation_potential": "High — Clover API live, QuickBooks connection needed for full automation",
        "automation_blockers": ["QuickBooks OAuth needed for automated QB posting"],
    },
    {
        "id": "payroll_processing",
        "name": "Payroll Processing",
        "frequency": "Bi-weekly",
        "tools": ["ADP (current)", "QuickBooks"],
        "estimated_time": "1 hour",
        "owner": "Kato",
        "steps": [
            "1. Pull attendance hours for all 15 GOJ employees for the pay period",
            "2. Check for overtime (> 40 hrs), PTO, sick days, or pay adjustments",
            "3. Submit payroll run in ADP portal (or replacement system)",
            "4. Download payroll journal entry / summary from ADP",
            "5. Post payroll journal entry in QuickBooks: debit payroll expense accounts, credit payroll liabilities and cash",
            "6. Verify bank ACH debit matches ADP payroll total within $1",
            "7. File employee earnings record and pay stubs",
        ],
        "current_status": "Manual via ADP portal",
        "automation_potential": "Medium — ADP API complex, handled by ADP replacement system",
        "automation_blockers": ["ADP API requires TLS certificate auth", "ADP being replaced"],
    },
    {
        "id": "monthly_pl_review",
        "name": "Monthly P&L Review",
        "frequency": "Monthly (first week)",
        "tools": ["QuickBooks"],
        "estimated_time": "30 min once QuickBooks connected",
        "owner": "Kato + Vlad",
        "steps": [
            "1.  Pull QuickBooks P&L for prior month (date range: first → last day of month)",
            "2.  Review revenue by class: Medicaid vs private pay vs BBG",
            "3.  Review top 10 expense categories — compare month-over-month",
            "4.  Calculate net income and operating margin percentage",
            "5.  Compare to prior month (MoM) and prior year same month (YoY)",
            "6.  Flag any expense category up > 15% MoM without explanation",
            "7.  Flag any revenue down > 10% MoM without explanation",
            "8.  Generate financial summary for Vlad (financial view only — no PHI, no operational detail)",
            "9.  Update Hermes MEMORY.md with key financial metrics for the month",
            "10. Archive P&L PDF to Google Drive",
        ],
        "current_status": "Manual — QuickBooks not yet connected to Rex Bill",
        "automation_potential": "High — QuickBooks P&L API endpoint returns structured data",
        "automation_blockers": ["QuickBooks OAuth must be connected"],
    },
    {
        "id": "vendor_bill_management",
        "name": "Vendor Bill Management",
        "frequency": "Weekly review",
        "tools": ["QuickBooks"],
        "estimated_time": "20 min/week",
        "owner": "Admin / Kato",
        "steps": [
            "1. Pull all open vendor bills in QuickBooks (Accounts Payable aging report)",
            "2. Flag any bills due within 7 days",
            "3. Verify invoices received for all expected recurring services (rent, utilities, food, insurance, laundry)",
            "4. Flag any expected bill not yet received (potential missed invoice)",
            "5. Approve and schedule ACH payments for all approved bills",
            "6. Post payments in QuickBooks against each bill",
            "7. File original vendor invoices in Google Drive under /Vendors/{vendor_name}/{year}/",
        ],
        "current_status": "Manual via QuickBooks portal",
        "automation_potential": "Medium — auto-reminders and aging reports automatable",
        "automation_blockers": ["QuickBooks OAuth must be connected"],
    },
    {
        "id": "authorization_billing_sync",
        "name": "Authorization → Billing Sync",
        "frequency": "Weekly",
        "tools": ["auth_tracker.db", "Medicaid clearinghouse"],
        "estimated_time": "1 hour manual → 5 min automated",
        "owner": "Kato / Billing",
        "steps": [
            "1. Query auth_tracker.db — pull all ACTIVE clients with service_end_date within next 30 days",
            "2. Cross-check attendance records — verify services billed match authorized service types and units",
            "3. Flag clients whose authorization expires before month end — initiate renewal",
            "4. Submit renewal requests for all PENDING RENEWAL clients — confirm submissions",
            "5. Identify any EXPIRED > 30 days with no PENDING RENEWAL — escalate to Kato immediately",
            "6. Generate 837P claim batch for the week's attended sessions",
            "7. Submit batch to clearinghouse",
            "8. Save 999 acknowledgement — confirm all claims accepted",
        ],
        "current_status": "Partially automated — auth_tracker.db has authorization data, EDI is manual",
        "automation_potential": "High — can auto-detect expiring auths and generate billing flags",
        "automation_blockers": [
            "Gate 1 (akc_tokenizer.py) must be built",
            "Clearinghouse API not connected",
        ],
    },
    {
        "id": "google_sheets_revenue_log",
        "name": "Google Sheets Daily Revenue Log",
        "frequency": "Daily (automated at 9 PM)",
        "tools": ["Clover POS", "Google Sheets"],
        "estimated_time": "Fully automated — 0 min manual",
        "owner": "Hermes (automated)",
        "steps": [
            "1. At 9 PM, Hermes calls GET /rex-bill/clover/today",
            "2. Receives GOJ total, BBG total, payment method breakdown",
            "3. Appends row to Google Sheets revenue log: [date, goj_total, bbg_total, card, cash, other]",
            "4. Checks if today's total is > 20% below trailing 30-day average — alerts Kato via Telegram if so",
            "5. On Fridays: generates 7-day summary row and appends to weekly summary tab",
            "6. On 1st of month: generates prior-month totals and appends to monthly tab",
        ],
        "current_status": "Buildable now — Clover partial + Google Sheets OAuth configured",
        "automation_potential": "Full — both APIs available",
        "automation_blockers": [
            "CLOVER_MERCHANT_ID_GOJ and CLOVER_MERCHANT_ID_BBG must be set in ~/.rex/config.json",
            "GOOGLE_SHEETS_REVENUE_SPREADSHEET_ID must be set",
        ],
    },
    {
        "id": "cash_flow_forecast",
        "name": "Cash Flow Forecast (30/60/90 Day)",
        "frequency": "Weekly",
        "tools": ["QuickBooks", "Google Sheets"],
        "estimated_time": "30 min manual → automated once QB connected",
        "owner": "Kato + Vlad",
        "steps": [
            "1. Pull QuickBooks Accounts Receivable aging — all outstanding invoices with due dates",
            "2. Pull QuickBooks Accounts Payable — all upcoming bills with due dates (next 90 days)",
            "3. Calculate expected Medicaid ACH payments (claims submitted 30 days ago typically pay in 30-45 days)",
            "4. Add payroll obligations: bi-weekly ACH debit (15 employees)",
            "5. Add known recurring expenses: rent, utilities, food, insurance",
            "6. Net cash = starting balance + expected inflows - expected outflows (30/60/90 day buckets)",
            "7. Flag any projected week with net cash < $50K threshold",
            "8. Post forecast to Google Sheets cash flow tab",
            "9. Send summary to Kato + Vlad via Hermes",
        ],
        "current_status": "Manual",
        "automation_potential": "High once QuickBooks connected",
        "automation_blockers": ["QuickBooks OAuth must be connected"],
    },
    {
        "id": "bbg_revenue_pipeline",
        "name": "BBG Revenue Pipeline Tracking",
        "frequency": "Weekly",
        "tools": ["Clover POS (BBG)", "Lead Connector Clone CRM", "QuickBooks"],
        "estimated_time": "30 min manual → automated once CRM built",
        "owner": "Kato",
        "steps": [
            "1. Pull Clover weekly totals for BBG merchant account — compare to prior week",
            "2. Pull Lead Connector pipeline — open deals with expected close dates and values",
            "3. Calculate weighted pipeline value (deal value × close probability)",
            "4. Compare actual Clover revenue to weighted pipeline forecast",
            "5. Update QuickBooks BBG revenue for the week",
            "6. Calculate BBG contribution to GHS consolidated P&L",
            "7. Flag deals stale > 14 days (no activity) for follow-up",
        ],
        "current_status": "Manual — Lead Connector CRM not yet built",
        "automation_potential": "High once Lead Connector built",
        "automation_blockers": ["Lead Connector CRM under construction"],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# MODULE C — CLOVER INTEGRATION
# ─────────────────────────────────────────────────────────────────────────────

CLOVER_BASE_URL = "https://api.clover.com/v3"


def _get_clover_config() -> tuple:
    """Load Clover credentials from env vars or ~/.rex/config.json."""
    api_key = os.getenv("CLOVER_API_KEY", "")
    mid_goj = os.getenv("CLOVER_MERCHANT_ID_GOJ", os.getenv("CLOVER_MERCHANT_ID", ""))
    mid_bbg = os.getenv("CLOVER_MERCHANT_ID_BBG", "")

    if not api_key:
        config_path = os.path.expanduser("~/.rex/config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path) as f:
                    cfg = json.load(f)
                api_key = api_key or cfg.get("clover_api_key", "")
                mid_goj = mid_goj or cfg.get("clover_merchant_id_goj", cfg.get("clover_merchant_id", ""))
                mid_bbg = mid_bbg or cfg.get("clover_merchant_id_bbg", "")
            except Exception:
                pass

    return api_key, mid_goj, mid_bbg


async def _clover_get(endpoint: str, merchant_id: str, api_key: str, params: dict = None) -> dict:
    """Make a GET request to the Clover API."""
    if not api_key or not merchant_id:
        return {
            "error": "Clover credentials not configured",
            "configured": False,
            "fix": "Set CLOVER_API_KEY and CLOVER_MERCHANT_ID_GOJ/BBG in env or ~/.rex/config.json",
        }
    url = f"{CLOVER_BASE_URL}/merchants/{merchant_id}{endpoint}"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params or {})
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 401:
            return {"error": "Clover API key invalid or expired", "status_code": 401}
        return {"error": f"Clover API error {resp.status_code}", "detail": resp.text[:500]}
    except httpx.TimeoutException:
        return {"error": "Clover API request timed out"}
    except Exception as e:
        return {"error": f"Clover request failed: {str(e)}"}


def _sum_clover_payments(elements: list) -> dict:
    """Summarize a list of Clover payment elements."""
    successful = [p for p in elements if p.get("result") == "SUCCESS"]
    by_tender: dict = {}
    for p in successful:
        tender = (p.get("tender") or {}).get("label", "Unknown")
        by_tender[tender] = by_tender.get(tender, 0) + p.get("amount", 0)
    return {
        "total_cents": sum(p.get("amount", 0) for p in successful),
        "total": sum(p.get("amount", 0) for p in successful) / 100,
        "count": len(successful),
        "by_tender": {k: round(v / 100, 2) for k, v in by_tender.items()},
        "void_count": sum(1 for p in elements if p.get("result") == "VOID"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# PYDANTIC MODELS
# ─────────────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    context: Optional[str] = None   # tool key e.g. "quickbooks", "clover"
    session_id: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/tools")
async def list_tools():
    """List all GHS financial tools with name, purpose, and connection status."""
    summary = {}
    connected = 0
    not_connected = 0

    for tid, tool in FINANCIAL_TOOLS.items():
        status = tool["integration_status"]
        is_connected = "CONNECTED" in status and "NOT" not in status
        if is_connected:
            connected += 1
        else:
            not_connected += 1
        summary[tid] = {
            "name": tool["name"],
            "purpose": tool["purpose"],
            "integration_status": status,
            "setup_priority": tool.get("setup_priority", 99),
            "estimated_setup_time": tool.get("estimated_setup_time", "Unknown"),
        }

    return {
        "tools": summary,
        "total": len(summary),
        "connected": connected,
        "not_connected": not_connected,
        "next_action": "Connect QuickBooks — POST /rex-bill/quickbooks/connect",
    }


@router.get("/tools/{tool_name}")
async def get_tool(tool_name: str):
    """Full details for a specific financial tool."""
    tool = FINANCIAL_TOOLS.get(tool_name.lower())
    if not tool:
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{tool_name}' not found. Available: {list(FINANCIAL_TOOLS.keys())}",
        )
    return tool


@router.get("/tools/{tool_name}/explain")
async def explain_tool(tool_name: str):
    """Plain-English explanation of a tool and how GHS uses it."""
    tool = FINANCIAL_TOOLS.get(tool_name.lower())
    if not tool:
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{tool_name}' not found. Available: {list(FINANCIAL_TOOLS.keys())}",
        )
    return {
        "tool": tool["name"],
        "status": tool["integration_status"],
        "what_it_does": tool["purpose"],
        "how_ghs_uses_it": tool["ghs_workflows"],
        "how_to_connect": {
            "auth_type": tool["auth_type"],
            "credentials_needed": tool.get("env_vars", []),
            "where_stored": tool["credentials_location"],
            "estimated_setup_time": tool.get("estimated_setup_time", "Unknown"),
            "setup_guide": tool.get("setup_guide", "See CC_REX_BILL_GUIDE.md"),
        },
        "key_endpoints": tool.get("key_endpoints", []),
        "api_docs": tool["api_docs"],
        "notes": tool.get("notes", ""),
    }


@router.get("/workflows")
async def list_workflows():
    """List all financial workflow templates."""
    return {
        "workflows": [
            {
                "id": w["id"],
                "name": w["name"],
                "frequency": w["frequency"],
                "tools": w["tools"],
                "current_status": w["current_status"],
                "automation_potential": w["automation_potential"],
                "estimated_time": w["estimated_time"],
            }
            for w in WORKFLOWS
        ],
        "total": len(WORKFLOWS),
    }


@router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str):
    """Full step-by-step detail for a workflow."""
    for w in WORKFLOWS:
        if w["id"] == workflow_id:
            return w
    raise HTTPException(
        status_code=404,
        detail=f"Workflow '{workflow_id}' not found. Available: {[w['id'] for w in WORKFLOWS]}",
    )


@router.get("/dashboard")
async def financial_dashboard():
    """
    Financial snapshot:
    - Clover today (GOJ + BBG)
    - Tool connection status
    - QuickBooks status
    - Priority actions
    """
    api_key, mid_goj, mid_bbg = _get_clover_config()
    now = datetime.now()
    start_of_day_ms = int(datetime(now.year, now.month, now.day).timestamp() * 1000)

    # Clover GOJ
    clover_goj: dict = {}
    if api_key and mid_goj:
        raw = await _clover_get(
            "/payments",
            mid_goj,
            api_key,
            {"filter": f"createdTime>={start_of_day_ms}", "expand": "tender", "limit": 1000},
        )
        if "error" not in raw:
            summary = _sum_clover_payments(raw.get("elements", []))
            clover_goj = {"merchant": "GOJ", "configured": True, **summary}
        else:
            clover_goj = {"merchant": "GOJ", "configured": True, **raw}
    else:
        clover_goj = {
            "merchant": "GOJ",
            "configured": False,
            "message": "CLOVER_MERCHANT_ID_GOJ not set",
        }

    # Clover BBG
    clover_bbg: dict = {}
    if api_key and mid_bbg:
        raw = await _clover_get(
            "/payments",
            mid_bbg,
            api_key,
            {"filter": f"createdTime>={start_of_day_ms}", "expand": "tender", "limit": 1000},
        )
        if "error" not in raw:
            summary = _sum_clover_payments(raw.get("elements", []))
            clover_bbg = {"merchant": "BBG", "configured": True, **summary}
        else:
            clover_bbg = {"merchant": "BBG", "configured": True, **raw}
    else:
        clover_bbg = {
            "merchant": "BBG",
            "configured": False,
            "message": "CLOVER_MERCHANT_ID_BBG not set",
        }

    combined = (clover_goj.get("total") or 0) + (clover_bbg.get("total") or 0)

    tool_status = {
        tid: {"name": t["name"], "status": t["integration_status"], "priority": t.get("setup_priority", 99)}
        for tid, t in FINANCIAL_TOOLS.items()
    }

    return {
        "as_of": now.isoformat(),
        "clover": {
            "goj": clover_goj,
            "bbg": clover_bbg,
            "combined_today": round(combined, 2),
        },
        "quickbooks": {
            "status": "NOT_CONNECTED",
            "message": "POST /rex-bill/quickbooks/connect to authorize",
        },
        "medicaid": {
            "status": "MANUAL",
            "message": "Carecenta handles EDI. Gate 1 required for automation.",
        },
        "tool_status": tool_status,
        "priority_actions": [
            "1. POST /rex-bill/quickbooks/connect — connect QuickBooks (Priority 1)",
            "2. Set CLOVER_MERCHANT_ID_GOJ + CLOVER_MERCHANT_ID_BBG in ~/.rex/config.json",
            "3. Set GOOGLE_SHEETS_REVENUE_SPREADSHEET_ID for automated revenue logging",
            "4. Build akc_tokenizer.py (Gate 1) to unlock Medicaid API integration",
        ],
    }


@router.post("/quickbooks/connect")
async def quickbooks_connect():
    """
    Initiate QuickBooks OAuth2 flow.
    Returns the authorization URL — open it in a browser to grant access.
    After authorization, QBO redirects to /rex-bill/quickbooks/callback.
    """
    client_id = os.getenv("QBO_CLIENT_ID", "")

    if not client_id:
        config_path = os.path.expanduser("~/.rex/config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path) as f:
                    cfg = json.load(f)
                client_id = cfg.get("qbo_client_id", "")
            except Exception:
                pass

    if not client_id:
        return {
            "status": "NOT_CONFIGURED",
            "error": "QBO_CLIENT_ID not found in environment or ~/.rex/config.json",
            "setup_steps": [
                "1. Go to https://developer.intuit.com and sign in with your Intuit account",
                "2. Click 'Create an app' → select 'QuickBooks Online and Payments'",
                "3. Note your Client ID and Client Secret from the Keys & credentials tab",
                "4. Under 'Redirect URIs', add: http://localhost:8000/rex-bill/quickbooks/callback",
                "5. Add to ~/.rex/config.json: {'qbo_client_id': '...', 'qbo_client_secret': '...'}",
                "6. Call POST /rex-bill/quickbooks/connect again",
            ],
            "docs": "https://developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization/oauth-2.0",
        }

    redirect_uri = "http://localhost:8000/rex-bill/quickbooks/callback"
    auth_url = (
        "https://appcenter.intuit.com/connect/oauth2"
        f"?client_id={client_id}"
        "&response_type=code"
        "&scope=com.intuit.quickbooks.accounting"
        f"&redirect_uri={redirect_uri}"
        "&state=rex_bill_qbo_auth"
    )

    return {
        "status": "READY",
        "action": "Open this URL in your browser to authorize QuickBooks access",
        "auth_url": auth_url,
        "redirect_uri": redirect_uri,
        "next": "After authorizing, QBO redirects to the callback — REX captures the token automatically.",
    }


@router.get("/quickbooks/callback")
async def quickbooks_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    realmId: Optional[str] = None,
    error: Optional[str] = None,
):
    """
    QuickBooks OAuth2 callback.
    Exchanges the authorization code for access + refresh tokens and saves to ~/.rex/config.json.
    """
    if error:
        return {"status": "ERROR", "error": error}
    if not code or not realmId:
        return {"status": "ERROR", "error": "Missing 'code' or 'realmId' in callback parameters"}

    client_id = os.getenv("QBO_CLIENT_ID", "")
    client_secret = os.getenv("QBO_CLIENT_SECRET", "")

    config_path = os.path.expanduser("~/.rex/config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                cfg = json.load(f)
            client_id = client_id or cfg.get("qbo_client_id", "")
            client_secret = client_secret or cfg.get("qbo_client_secret", "")
        except Exception:
            pass

    if not client_id or not client_secret:
        return {"status": "ERROR", "error": "QBO_CLIENT_ID or QBO_CLIENT_SECRET not configured"}

    redirect_uri = "http://localhost:8000/rex-bill/quickbooks/callback"

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
            auth=(client_id, client_secret),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )

    if resp.status_code != 200:
        return {
            "status": "ERROR",
            "error": f"Token exchange failed ({resp.status_code})",
            "detail": resp.text[:500],
        }

    tokens = resp.json()

    # Load existing config and merge tokens
    config: dict = {}
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                config = json.load(f)
        except Exception:
            config = {}

    config.update(
        {
            "qbo_realm_id": realmId,
            "qbo_access_token": tokens.get("access_token"),
            "qbo_refresh_token": tokens.get("refresh_token"),
            "qbo_expires_in": tokens.get("expires_in"),
            "qbo_refresh_expires_in": tokens.get("x_refresh_token_expires_in"),
            "qbo_token_saved_at": datetime.now().isoformat(),
        }
    )

    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    return {
        "status": "SUCCESS",
        "message": "QuickBooks connected! Tokens saved to ~/.rex/config.json",
        "realm_id": realmId,
        "expires_in_seconds": tokens.get("expires_in"),
        "refresh_expires_in_days": round((tokens.get("x_refresh_token_expires_in", 0)) / 86400),
        "next_steps": [
            "GET /rex-bill/quickbooks/pl — pull current P&L",
            "GET /rex-bill/dashboard — see full financial snapshot",
            "Token auto-refresh: REX should refresh ~55 min after save (expires_in ~3600s)",
        ],
    }


@router.post("/quickbooks/refresh")
async def quickbooks_refresh():
    """Refresh the QuickBooks access token using the stored refresh token."""
    config_path = os.path.expanduser("~/.rex/config.json")
    config: dict = {}
    if os.path.exists(config_path):
        with open(config_path) as f:
            config = json.load(f)

    client_id = config.get("qbo_client_id") or os.getenv("QBO_CLIENT_ID", "")
    client_secret = config.get("qbo_client_secret") or os.getenv("QBO_CLIENT_SECRET", "")
    refresh_token = config.get("qbo_refresh_token") or os.getenv("QBO_REFRESH_TOKEN", "")

    if not all([client_id, client_secret, refresh_token]):
        return {"status": "ERROR", "error": "Missing credentials — run POST /rex-bill/quickbooks/connect first"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
            auth=(client_id, client_secret),
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        )

    if resp.status_code != 200:
        return {"status": "ERROR", "error": f"Refresh failed ({resp.status_code})", "detail": resp.text[:300]}

    tokens = resp.json()
    config.update(
        {
            "qbo_access_token": tokens.get("access_token"),
            "qbo_refresh_token": tokens.get("refresh_token", refresh_token),
            "qbo_token_saved_at": datetime.now().isoformat(),
        }
    )
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    return {"status": "SUCCESS", "message": "QuickBooks token refreshed", "expires_in": tokens.get("expires_in")}


@router.get("/quickbooks/pl")
async def quickbooks_pl(start_date: Optional[str] = None, end_date: Optional[str] = None):
    """
    Pull QuickBooks P&L report.
    Defaults to month-to-date. Requires OAuth to be connected.
    """
    config_path = os.path.expanduser("~/.rex/config.json")
    config: dict = {}
    if os.path.exists(config_path):
        with open(config_path) as f:
            config = json.load(f)

    access_token = config.get("qbo_access_token") or os.getenv("QBO_ACCESS_TOKEN", "")
    realm_id = config.get("qbo_realm_id") or os.getenv("QBO_REALM_ID", "")

    if not access_token or not realm_id:
        return {
            "status": "NOT_CONNECTED",
            "message": "QuickBooks not connected. Run POST /rex-bill/quickbooks/connect first.",
        }

    if not start_date:
        start_date = datetime.now().replace(day=1).strftime("%Y-%m-%d")
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    url = f"https://quickbooks.api.intuit.com/v3/company/{realm_id}/reports/ProfitAndLoss"
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    params = {"start_date": start_date, "end_date": end_date, "accounting_method": "Accrual"}

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, headers=headers, params=params)

    if resp.status_code == 401:
        return {
            "status": "TOKEN_EXPIRED",
            "message": "Access token expired. Run POST /rex-bill/quickbooks/refresh or re-authorize.",
        }
    if resp.status_code != 200:
        return {"status": "ERROR", "code": resp.status_code, "detail": resp.text[:500]}

    return {
        "status": "SUCCESS",
        "period": {"start": start_date, "end": end_date},
        "report": resp.json(),
    }


@router.get("/clover/today")
async def clover_today():
    """Today's Clover transactions — GOJ and BBG totals with tender breakdown."""
    api_key, mid_goj, mid_bbg = _get_clover_config()
    now = datetime.now()
    start_ms = int(datetime(now.year, now.month, now.day).timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)
    params = {
        "filter": f"createdTime>={start_ms}&createdTime<={end_ms}",
        "expand": "tender",
        "limit": 1000,
    }

    results: dict = {}
    for label, mid in [("goj", mid_goj), ("bbg", mid_bbg)]:
        if not api_key or not mid:
            results[label] = {
                "configured": False,
                "message": f"CLOVER_MERCHANT_ID_{label.upper()} not set in env or ~/.rex/config.json",
            }
            continue
        raw = await _clover_get("/payments", mid, api_key, params)
        if "error" in raw:
            results[label] = {"configured": True, "merchant": label.upper(), **raw}
        else:
            summary = _sum_clover_payments(raw.get("elements", []))
            results[label] = {
                "configured": True,
                "merchant": label.upper(),
                "date": now.strftime("%Y-%m-%d"),
                **summary,
            }

    combined = (results.get("goj", {}).get("total") or 0) + (results.get("bbg", {}).get("total") or 0)
    return {
        "as_of": now.isoformat(),
        "goj": results.get("goj"),
        "bbg": results.get("bbg"),
        "combined_total": round(combined, 2),
    }


@router.get("/clover/trend")
async def clover_trend(days: int = 7):
    """Revenue trend over the last N days (max 30). Returns daily GOJ + BBG totals."""
    days = min(days, 30)
    api_key, mid_goj, mid_bbg = _get_clover_config()

    if not api_key:
        return {"error": "CLOVER_API_KEY not configured"}

    trend = []
    for i in range(days - 1, -1, -1):
        day = datetime.now() - timedelta(days=i)
        start_ms = int(datetime(day.year, day.month, day.day).timestamp() * 1000)
        end_ms = int((datetime(day.year, day.month, day.day) + timedelta(days=1)).timestamp() * 1000)
        day_params = {"filter": f"createdTime>={start_ms}&createdTime<{end_ms}", "limit": 1000}

        goj_total = 0.0
        bbg_total = 0.0

        if mid_goj:
            raw = await _clover_get("/payments", mid_goj, api_key, day_params)
            if "error" not in raw:
                goj_total = sum(
                    p.get("amount", 0) for p in raw.get("elements", []) if p.get("result") == "SUCCESS"
                ) / 100

        if mid_bbg:
            raw = await _clover_get("/payments", mid_bbg, api_key, day_params)
            if "error" not in raw:
                bbg_total = sum(
                    p.get("amount", 0) for p in raw.get("elements", []) if p.get("result") == "SUCCESS"
                ) / 100

        trend.append(
            {
                "date": day.strftime("%Y-%m-%d"),
                "day_of_week": day.strftime("%A"),
                "goj": round(goj_total, 2),
                "bbg": round(bbg_total, 2),
                "total": round(goj_total + bbg_total, 2),
            }
        )

    avg = sum(d["total"] for d in trend) / len(trend) if trend else 0
    return {
        "days": days,
        "trend": trend,
        "average_daily": round(avg, 2),
        "period_total": round(sum(d["total"] for d in trend), 2),
    }


@router.get("/medicaid/pending")
async def medicaid_pending():
    """
    Medicaid claim tracking — placeholder until clearinghouse API connected.
    Returns current state and future endpoint plan.
    """
    return {
        "status": "PLACEHOLDER",
        "message": "Medicaid claim tracking via clearinghouse API not yet connected.",
        "current_state": {
            "billing_system": "Carecenta (manual EDI submission)",
            "clearinghouses": ["Availity", "Change Healthcare"],
            "medicaid_clients": 425,
            "automation_blocker": "Gate 1 (akc_tokenizer.py) must be built first",
        },
        "future_endpoints": {
            "GET /rex-bill/medicaid/claims": "All submitted claims with status",
            "GET /rex-bill/medicaid/claims/{id}": "Single claim detail + line items",
            "GET /rex-bill/medicaid/remittances": "835 remittance files",
            "POST /rex-bill/medicaid/submit": "Submit 837P claim batch",
            "GET /rex-bill/medicaid/denials": "Denied claims with denial codes",
            "GET /rex-bill/medicaid/aging": "Claims aging — days since submission",
        },
        "roadmap": [
            "Step 1: Complete akc_tokenizer.py (Gate 1) — blocks all Medicaid API work",
            "Step 2: Obtain Availity API credentials (availity_client_id, availity_client_secret)",
            "Step 3: Build EDI 837P claim generator from auth_tracker.db attendance data",
            "Step 4: Build 835 remittance parser (CLP, SVC, CAS segments)",
            "Step 5: Connect QuickBooks — auto-post payments from parsed 835s",
            "Step 6: Build denial management queue with follow-up tracking",
        ],
    }


@router.post("/chat")
async def rex_bill_chat(request: ChatRequest):
    """
    Conversational Rex Bill interface.
    Routes message to Hermes gateway with full financial context injected.
    Falls back to local knowledge base if Hermes is unreachable.
    """
    tool_summary = {
        tid: {
            "name": t["name"],
            "purpose": t["purpose"],
            "status": t["integration_status"],
            "workflows": t["ghs_workflows"][:4],
        }
        for tid, t in FINANCIAL_TOOLS.items()
    }

    workflow_summary = [
        {
            "name": w["name"],
            "frequency": w["frequency"],
            "tools": w["tools"],
            "steps": w["steps"],
            "status": w["current_status"],
        }
        for w in WORKFLOWS
    ]

    system_prompt = f"""You are Rex Bill, the financial intelligence layer for Gold Health Systems (GHS).
GHS operates Garden of Joy (GOJ) adult day care in Brooklyn NY (~425 Medicaid clients) and BBG (a retail/service business).

Your role:
1. Explain how each financial tool works and how GHS uses it
2. Walk Kato through financial workflows step by step
3. Identify automation opportunities across the financial stack
4. Answer financial questions about the business

FINANCIAL TOOLS:
{json.dumps(tool_summary, indent=2)}

WORKFLOW TEMPLATES:
{json.dumps(workflow_summary, indent=2)}

RULES — never break these:
- Rexxie handles Kato's PERSONAL finances ONLY — never mix personal and GOJ/BBG
- Gate 1 (akc_tokenizer.py) must be complete before ANY PHI reaches cloud or clearinghouse API
- QuickBooks connection is Priority 1 for financial automation
- Vlad gets financial view only — no operational or PHI detail
- Larry never appears on any transport or driver list under any circumstance
- PAE rule: Propose → Approve → Execute for all real-world financial actions

When answering, be specific: name the exact tool, endpoint, or workflow step. Reference CC_REX_BILL_GUIDE.md for setup instructions."""

    user_message = request.message
    if request.context:
        tool = FINANCIAL_TOOLS.get(request.context.lower())
        if tool:
            user_message = f"[Context: {tool['name']}]\n\n{request.message}"

    hermes_url = os.getenv("HERMES_URL", "http://localhost:3002")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{hermes_url}/v1/chat/completions",
                json={
                    "model": "claude-sonnet-4-6",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2000,
                },
                headers={"Content-Type": "application/json"},
            )
        if resp.status_code == 200:
            data = resp.json()
            reply = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
            return {
                "reply": reply,
                "routed_to": "hermes_gateway",
                "model": "claude-sonnet-4-6",
                "context_used": request.context,
            }
        logger.warning("Hermes returned %s — falling back to local", resp.status_code)
    except Exception as e:
        logger.warning("Hermes unreachable (%s) — using local knowledge base", str(e))

    return _local_fallback(request.message)


def _local_fallback(message: str) -> dict:
    """Local fallback: match message to knowledge base when Hermes is unreachable."""
    msg = message.lower()

    matched_tools = [
        (tid, t) for tid, t in FINANCIAL_TOOLS.items()
        if tid in msg or t["name"].lower() in msg
    ]
    matched_workflows = [
        w for w in WORKFLOWS
        if w["id"] in msg or any(word in msg for word in w["name"].lower().split() if len(word) > 4)
    ]

    parts = ["**Rex Bill** (local knowledge base — Hermes gateway unreachable)\n"]

    for tid, tool in matched_tools[:2]:
        parts.append(f"\n**{tool['name']}** — {tool['integration_status']}")
        parts.append(f"Purpose: {tool['purpose']}")
        parts.append("GHS workflows:")
        for wf in tool["ghs_workflows"][:3]:
            parts.append(f"  • {wf}")

    for w in matched_workflows[:1]:
        parts.append(f"\n**Workflow: {w['name']}** ({w['frequency']})")
        parts.append(f"Status: {w['current_status']}")
        for step in w["steps"]:
            parts.append(f"  {step}")

    if not matched_tools and not matched_workflows:
        parts.append(
            "No direct match found. Try asking about: "
            + ", ".join(FINANCIAL_TOOLS.keys())
            + ". Or ask about a specific workflow."
        )

    return {
        "reply": "\n".join(parts),
        "routed_to": "local_knowledge_base",
        "hermes_status": "unreachable",
    }


# ─────────────────────────────────────────────────────────────────────────────
# MODULE D — AUTH_TRACKER.DB LIVE DATA ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

AUTH_TRACKER_DB = os.path.expanduser("~/Documents/goj files/dashboard/auth_tracker.db")


def _db_query(query: str, params: tuple = ()) -> list:
    """Execute a read-only query against auth_tracker.db and return rows as dicts."""
    if not os.path.exists(AUTH_TRACKER_DB):
        return []
    conn = sqlite3.connect(AUTH_TRACKER_DB)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(query, params)
        rows = [dict(r) for r in cur.fetchall()]
        return rows
    finally:
        conn.close()


@router.get("/db/medicaid-pipeline")
async def medicaid_pipeline():
    """Live Medicaid pipeline from claims_837 and payments_835 tables."""
    if not os.path.exists(AUTH_TRACKER_DB):
        return {"error": f"Database not found: {AUTH_TRACKER_DB}", "db_connected": False}

    claims_rows = _db_query("""
        SELECT status, COUNT(*) as cnt, COALESCE(SUM(billed_amount), 0) as total_billed
        FROM claims_837
        GROUP BY status
    """)

    payments_rows = _db_query("""
        SELECT
            CASE WHEN is_denial THEN 'denied' WHEN is_partial THEN 'partial' ELSE 'paid' END as ptype,
            COUNT(*) as cnt,
            COALESCE(SUM(paid_amount), 0) as total_paid
        FROM payments_835
        GROUP BY ptype
    """)

    claims_by_status = {}
    claims_total_count = 0
    claims_total_billed = 0.0
    for r in claims_rows:
        claims_by_status[r["status"]] = {"count": r["cnt"], "billed": round(r["total_billed"], 2)}
        claims_total_count += r["cnt"]
        claims_total_billed += r["total_billed"]

    payments_by_type = {}
    payments_total = 0.0
    for p in payments_rows:
        payments_by_type[p["ptype"]] = {"count": p["cnt"], "amount": round(p["total_paid"], 2)}
        payments_total += p["total_paid"]

    return {
        "db_connected": True,
        "claims": {
            "total": claims_total_count,
            "total_billed": round(claims_total_billed, 2),
            "by_status": claims_by_status,
            "statuses_available": ["PENDING", "PAID", "DENIED", "PARTIAL", "VOID"],
        },
        "payments": {
            "total_paid": round(payments_total, 2),
            "by_type": payments_by_type,
        },
        "reconciliation_hint": "claims_837 rows represent submitted 837P claims; payments_835 rows are received 835 remittances",
    }


@router.get("/db/authorization-summary")
async def authorization_summary():
    """Authorization status breakdown from the authorization table."""
    if not os.path.exists(AUTH_TRACKER_DB):
        return {"error": f"Database not found: {AUTH_TRACKER_DB}", "db_connected": False}

    by_status = _db_query("""
        SELECT status, COUNT(*) as cnt
        FROM authorization
        GROUP BY status
        ORDER BY cnt DESC
    """)

    expiring_soon = _db_query("""
        SELECT COUNT(*) as cnt
        FROM authorization
        WHERE status = 'ACTIVE'
          AND service_end_date BETWEEN date('now') AND date('now', '+30 days')
    """)

    payer_breakdown = _db_query("""
        SELECT COALESCE(payer_canonical, payer_raw, 'Unknown') as payer,
               COUNT(*) as cnt
        FROM authorization
        WHERE status = 'ACTIVE'
        GROUP BY payer
        ORDER BY cnt DESC
        LIMIT 10
    """)

    return {
        "db_connected": True,
        "total_authorizations": sum(r["cnt"] for r in by_status),
        "by_status": {r["status"]: r["cnt"] for r in by_status},
        "expiring_within_30_days": expiring_soon[0]["cnt"] if expiring_soon else 0,
        "active_by_payer": {r["payer"]: r["cnt"] for r in payer_breakdown},
    }


@router.get("/db/attendance-summary")
async def attendance_summary(days: int = Query(default=30, ge=1, le=365)):
    """Attendance summary for billing — last N days."""
    if not os.path.exists(AUTH_TRACKER_DB):
        return {"error": f"Database not found: {AUTH_TRACKER_DB}", "db_connected": False}

    by_status = _db_query("""
        SELECT status, COUNT(*) as cnt
        FROM attendance_log
        WHERE log_date >= date('now', ?)
        GROUP BY status
        ORDER BY cnt DESC
    """, (f"-{days} days",))

    daily_counts = _db_query("""
        SELECT log_date, status, COUNT(*) as cnt
        FROM attendance_log
        WHERE log_date >= date('now', ?)
        GROUP BY log_date, status
        ORDER BY log_date DESC
        LIMIT 60
    """, (f"-{days} days",))

    total_attended = sum(r["cnt"] for r in by_status if r["status"] == "attended")

    return {
        "db_connected": True,
        "period_days": days,
        "total_records": sum(r["cnt"] for r in by_status),
        "total_attended": total_attended,
        "by_status": {r["status"]: r["cnt"] for r in by_status},
        "daily_breakdown": daily_counts,
        "billing_hint": "Multiply attended count × daily Medicaid rate (~$80-120/client) for estimated revenue",
    }


@router.get("/db/payment-summary")
async def payment_summary():
    """Payment summary from payments_835 table."""
    if not os.path.exists(AUTH_TRACKER_DB):
        return {"error": f"Database not found: {AUTH_TRACKER_DB}", "db_connected": False}

    total_stats = _db_query("""
        SELECT
            COUNT(*) as total_payments,
            COALESCE(SUM(paid_amount), 0) as total_paid,
            COALESCE(SUM(CASE WHEN is_denial THEN 1 ELSE 0 END), 0) as denials,
            COALESCE(SUM(CASE WHEN is_partial THEN 1 ELSE 0 END), 0) as partials
        FROM payments_835
    """)

    by_payer = _db_query("""
        SELECT payer_canonical, COUNT(*) as cnt, COALESCE(SUM(paid_amount), 0) as total
        FROM payments_835
        GROUP BY payer_canonical
        ORDER BY total DESC
    """)

    denial_reasons = _db_query("""
        SELECT denial_code, denial_reason, COUNT(*) as cnt
        FROM payments_835
        WHERE is_denial = 1 AND denial_code IS NOT NULL
        GROUP BY denial_code
        ORDER BY cnt DESC
        LIMIT 10
    """)

    ts = total_stats[0] if total_stats else {}

    return {
        "db_connected": True,
        "total_payments": ts.get("total_payments", 0),
        "total_paid_amount": round(ts.get("total_paid", 0), 2),
        "denials": ts.get("denials", 0),
        "partials": ts.get("partials", 0),
        "by_payer": [{"payer": r["payer_canonical"], "count": r["cnt"], "total": round(r["total"], 2)} for r in by_payer],
        "top_denial_reasons": [{"code": r["denial_code"], "reason": r["denial_reason"], "count": r["cnt"]} for r in denial_reasons],
    }


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD UI
# ─────────────────────────────────────────────────────────────────────────────

DASHBOARD_HTML = Path(os.path.expanduser("~/Desktop/REX/CC_rex_bill_dashboard.html"))


@router.get("/ui", response_class=HTMLResponse)
async def bill_dashboard_ui():
    """Serve the Rex Bill dashboard HTML."""
    if DASHBOARD_HTML.exists():
        return HTMLResponse(DASHBOARD_HTML.read_text())
    raise HTTPException(status_code=404, detail=f"Dashboard HTML not found at {DASHBOARD_HTML}")
