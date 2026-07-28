"""
CC_quickbooks_capture.py — QuickBooks Workflow Capture Tool for Gold Health Systems
FastAPI router — mounts to REX on port 8000 at /quickbooks-capture

Purpose: Capture the departing bookkeeper's complete QuickBooks workflow before they leave.
Covers: daily routines, weekly routines, monthly close, invoice processing, bill pay,
         payroll, Medicaid billing (Carecenta/837P/835), bank reconciliation, reports.

Modes:
  1. HTML frontend  → GET /quickbooks-capture          (bookkeeper fills out in browser)
  2. JSON API       → GET/POST /quickbooks-capture/api  (programmatic access)
  3. CLI interview  → --cli flag                        (terminal-based interview)
  4. Capture mode   → placeholder for step-by-step recording with screenshots

State saved to: ~/Desktop/REX/state/quickbooks_workflow.json

Mount in main.py:
    from CC_quickbooks_capture import router as qb_capture_router
    app.include_router(qb_capture_router)
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict
import os
import json
import sys
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/quickbooks-capture", tags=["QuickBooks Workflow Capture"])

# ── State path ─────────────────────────────────────────────────────────────────
_STATE_DIR = Path(__file__).resolve().parent / "state"
_STATE_FILE = _STATE_DIR / "quickbooks_workflow.json"

# ── HTML frontend path ─────────────────────────────────────────────────────────
_HTML_FILE = Path(__file__).resolve().parent / "CC_quickbooks_capture.html"


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  QUESTIONNAIRE TEMPLATE                                                     ║
# ║  Comprehensive coverage of every QuickBooks workflow at GHS                  ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

QUESTIONNAIRE: dict = {
    "_meta": {
        "tool": "CC_quickbooks_capture",
        "version": "1.0.0",
        "created": datetime.now().isoformat(),
        "purpose": "Capture complete QuickBooks workflow from departing bookkeeper",
        "instructions": (
            "Fill out every field you can. The more detail, the easier the handoff. "
            "For step-by-step processes, use the capture_mode flag to record each action. "
            "Leave blank anything you don't handle — we'll flag it for the replacement."
        ),
    },

    # ── SECTION 1: DAILY ROUTINES ────────────────────────────────────────────────
    "daily_routines": {
        "label": "📅 Daily Routines",
        "description": "What you do every single day in QuickBooks",
        "questions": {
            "morning_procedure": {
                "label": "Morning Login & Setup",
                "hint": "Walk us through your first 10 minutes in QuickBooks each morning",
                "fields": {
                    "login_steps": {"type": "textarea", "label": "Login steps (URL, credentials location, 2FA method)", "required": True},
                    "dashboard_review": {"type": "textarea", "label": "What do you check first on the dashboard?", "required": False},
                    "notifications": {"type": "textarea", "label": "How do you handle QBO notifications/alerts?", "required": False},
                    "morning_notes": {"type": "textarea", "label": "Any other morning routine steps?", "required": False},
                },
            },
            "invoice_creation": {
                "label": "Invoice Creation",
                "hint": "How you create and send invoices each day",
                "fields": {
                    "when_created": {"type": "text", "label": "When during the day do you create invoices?", "required": False},
                    "client_invoice_steps": {"type": "textarea", "label": "Step-by-step: creating a new client invoice (which menu, which fields, templates?)", "required": True},
                    "medicaid_billing_sync": {"type": "textarea", "label": "How do invoices connect to Medicaid billing? Do you bill per client per day? Per week?", "required": False},
                    "private_pay_invoicing": {"type": "textarea", "label": "How do you handle private-pay (non-Medicaid) client invoices?", "required": False},
                    "invoice_numbering": {"type": "text", "label": "Invoice numbering convention (prefix, format, starting number?)", "required": False},
                    "templates_used": {"type": "text", "label": "Which invoice templates do you use?", "required": False},
                    "attachments": {"type": "textarea", "label": "What do you attach to invoices (attendance sheets, service logs, auth letters)?", "required": False},
                },
            },
            "payment_recording": {
                "label": "Payment Recording",
                "hint": "How you record payments received",
                "fields": {
                    "payment_entry_steps": {"type": "textarea", "label": "Step-by-step: recording a payment against an invoice", "required": True},
                    "payment_methods": {"type": "textarea", "label": "Payment methods handled (ACH, check, credit card, cash) and how each is recorded", "required": False},
                    "clover_payments": {"type": "textarea", "label": "How do Clover POS payments flow into QuickBooks?", "required": False},
                    "undeposited_funds": {"type": "textarea", "label": "Do you use Undeposited Funds? Walk us through the flow.", "required": False},
                    "partial_payments": {"type": "textarea", "label": "How do you handle partial payments or overpayments?", "required": False},
                },
            },
            "deposit_reconciliation": {
                "label": "Deposit Reconciliation",
                "hint": "Daily bank deposit matching",
                "fields": {
                    "deposit_steps": {"type": "textarea", "label": "Step-by-step: matching daily deposits to bank", "required": True},
                    "batch_matching": {"type": "textarea", "label": "How do you match Clover settlement batches to bank deposits?", "required": False},
                    "discrepancy_handling": {"type": "textarea", "label": "What do you do when deposit amounts don't match?", "required": False},
                    "deposit_timing": {"type": "text", "label": "How many days lag between transaction and bank deposit?", "required": False},
                },
            },
            "end_of_day": {
                "label": "End-of-Day Wrap-Up",
                "hint": "What you do before closing QuickBooks for the day",
                "fields": {
                    "eod_checklist": {"type": "textarea", "label": "End-of-day checklist (what do you verify before logging off?)", "required": True},
                    "backup_procedure": {"type": "textarea", "label": "Any backup/export steps?", "required": False},
                    "handoff_notes": {"type": "textarea", "label": "Do you leave notes for the next day? Where?", "required": False},
                },
            },
        },
    },

    # ── SECTION 2: WEEKLY ROUTINES ───────────────────────────────────────────────
    "weekly_routines": {
        "label": "📆 Weekly Routines",
        "description": "Tasks you do on specific days of the week",
        "questions": {
            "monday": {
                "label": "Monday Routine",
                "hint": "First business day of the week",
                "fields": {
                    "monday_tasks": {"type": "textarea", "label": "What MUST be done every Monday?", "required": False},
                    "monday_steps": {"type": "textarea", "label": "Step-by-step for Monday-specific tasks", "required": False},
                },
            },
            "payroll_prep": {
                "label": "Payroll Preparation",
                "hint": "Getting ready for payroll run (bi-weekly on ___?)",
                "fields": {
                    "payroll_schedule": {"type": "text", "label": "Payroll frequency and which day of the week it runs", "required": True},
                    "hours_collection": {"type": "textarea", "label": "How do you collect/verify employee hours before payroll?", "required": True},
                    "adp_steps": {"type": "textarea", "label": "ADP portal steps (login URL, process name, fields)", "required": False},
                    "payroll_journal_entry": {"type": "textarea", "label": "How do you record the payroll journal entry in QuickBooks (debits/credits, accounts used)?", "required": False},
                    "payroll_accounts": {"type": "textarea", "label": "Which accounts are involved? (Payroll Expense, Payroll Liabilities, Cash?)", "required": False},
                    "tax_withholding": {"type": "textarea", "label": "How are payroll taxes handled and recorded?", "required": False},
                    "pto_tracking": {"type": "textarea", "label": "How do you track PTO, sick days, and overtime?", "required": False},
                },
            },
            "vendor_bills": {
                "label": "Vendor Bill Processing",
                "hint": "How you handle incoming bills from vendors",
                "fields": {
                    "receipt_method": {"type": "textarea", "label": "How do vendor bills arrive? (email, mail, portal, all of the above?)", "required": True},
                    "entry_steps": {"type": "textarea", "label": "Step-by-step: entering a new vendor bill in QuickBooks", "required": True},
                    "approval_flow": {"type": "textarea", "label": "Who approves bills before payment? What's the approval process?", "required": False},
                    "recurring_bills": {"type": "textarea", "label": "List recurring vendors and their typical amounts (rent, utilities, food, insurance, laundry, etc.)", "required": True},
                    "payment_scheduling": {"type": "textarea", "label": "How do you decide when to pay each bill? Due date tracking?", "required": False},
                    "payment_methods": {"type": "textarea", "label": "How are bills paid? (ACH, check, wire?) Steps for each.", "required": False},
                    "vendor_w9": {"type": "textarea", "label": "Where are vendor W-9s stored? How do you track 1099 requirements?", "required": False},
                },
            },
            "expense_categorization": {
                "label": "Expense Categorization",
                "hint": "How you categorize and review expenses",
                "fields": {
                    "category_list": {"type": "textarea", "label": "List all expense categories/accounts used for GOJ and BBG", "required": True},
                    "categorization_rules": {"type": "textarea", "label": "How do you decide which category an expense goes into? Any gray areas?", "required": False},
                    "class_tracking": {"type": "textarea", "label": "How do you use Class tracking (GOJ vs BBG)?", "required": False},
                    "split_transactions": {"type": "textarea", "label": "How do you handle split transactions (one payment covering multiple categories)?", "required": False},
                },
            },
            "friday": {
                "label": "Friday Routine",
                "hint": "End-of-week wrap-up",
                "fields": {
                    "friday_tasks": {"type": "textarea", "label": "What MUST be done every Friday?", "required": False},
                    "friday_steps": {"type": "textarea", "label": "Step-by-step for Friday-specific tasks", "required": False},
                    "weekly_reporting": {"type": "textarea", "label": "Any weekly reports generated on Fridays?", "required": False},
                },
            },
        },
    },

    # ── SECTION 3: MONTHLY CLOSE ─────────────────────────────────────────────────
    "monthly_close": {
        "label": "📊 Monthly Close",
        "description": "Month-end closing procedures",
        "questions": {
            "close_timeline": {
                "label": "Close Timeline",
                "hint": "When and how you close each month",
                "fields": {
                    "close_day": {"type": "text", "label": "Which day of the month do you typically close? How many days does it take?", "required": True},
                    "close_checklist": {"type": "textarea", "label": "Complete month-end close checklist (all steps in order)", "required": True},
                    "close_period": {"type": "textarea", "label": "How do you close the accounting period in QuickBooks? (Settings → Accounts and Settings → Close Books?)", "required": False},
                    "password_protected": {"type": "text", "label": "Is the closed period password-protected? Where is the password?", "required": False},
                },
            },
            "bank_reconciliation": {
                "label": "Bank Reconciliation",
                "hint": "Monthly bank rec process",
                "fields": {
                    "bank_accounts": {"type": "textarea", "label": "List ALL bank accounts/credit cards connected to QuickBooks (name, last 4, bank)", "required": True},
                    "rec_steps": {"type": "textarea", "label": "Step-by-step: reconciling a bank account (which menu, what you match, what you flag)", "required": True},
                    "statement_source": {"type": "textarea", "label": "Where do you get bank statements? (download, mail, bank portal URL?)", "required": False},
                    "bank_feed": {"type": "textarea", "label": "Do you use QBO bank feeds? How do you match/categorize transactions in the feed?", "required": False},
                    "unreconciled_handling": {"type": "textarea", "label": "How do you handle unreconciled items? Stale checks? Deposits in transit?", "required": False},
                    "rec_frequency": {"type": "text", "label": "Do you reconcile more than monthly? (weekly, daily?)", "required": False},
                },
            },
            "financial_statements": {
                "label": "Financial Statements",
                "hint": "Monthly report generation",
                "fields": {
                    "pl_report": {"type": "textarea", "label": "P&L steps: how do you generate the monthly Profit & Loss?", "required": True},
                    "balance_sheet": {"type": "textarea", "label": "Balance Sheet: when and how do you generate it?", "required": False},
                    "cash_flow": {"type": "textarea", "label": "Cash Flow Statement: when and how?", "required": False},
                    "ar_aging": {"type": "textarea", "label": "AR Aging report: how often and what do you do with it?", "required": False},
                    "ap_aging": {"type": "textarea", "label": "AP Aging report: how often and what do you do with it?", "required": False},
                    "class_separation": {"type": "textarea", "label": "How do you separate GOJ vs BBG in financial statements? (Class filtering?)", "required": False},
                    "report_distribution": {"type": "textarea", "label": "Who gets which reports? (Kato? Vlad? Accountant?) How are they delivered?", "required": True},
                },
            },
            "sales_tax": {
                "label": "Sales Tax Filing",
                "hint": "Sales tax calculation and filing",
                "fields": {
                    "tax_agency": {"type": "text", "label": "Which tax agency? Filing frequency (monthly/quarterly)?", "required": False},
                    "tax_calculation_steps": {"type": "textarea", "label": "How do you calculate sales tax owed? (Which report in QBO?)", "required": False},
                    "filing_steps": {"type": "textarea", "label": "Step-by-step: filing sales tax (portal URL, login, payment method)", "required": False},
                    "bbg_goj_separate": {"type": "textarea", "label": "Are GOJ and BBG sales tax separate? How do you split?", "required": False},
                },
            },
            "journal_entries": {
                "label": "Month-End Journal Entries",
                "hint": "Adjusting entries, accruals, depreciation",
                "fields": {
                    "standard_jes": {"type": "textarea", "label": "List ALL standard month-end journal entries (depreciation, prepaids, accruals, etc.)", "required": False},
                    "je_approval": {"type": "textarea", "label": "Who reviews/approves journal entries?", "required": False},
                    "je_memo_format": {"type": "text", "label": "Memo/description format for journal entries", "required": False},
                },
            },
        },
    },

    # ── SECTION 4: INVOICE PROCESSING (DEEP DIVE) ────────────────────────────────
    "invoice_processing_deep_dive": {
        "label": "🧾 Invoice Processing — Deep Dive",
        "description": "Detailed invoice workflow for ALL client types",
        "questions": {
            "medicaid_invoices": {
                "label": "Medicaid Client Invoices",
                "hint": "How you bill for the 425 GOJ Medicaid clients",
                "fields": {
                    "billing_frequency": {"type": "text", "label": "Billing frequency: daily? weekly? monthly? per-session?", "required": True},
                    "rate_per_client": {"type": "text", "label": "Rate per client per day (typical range: $80-120)", "required": False},
                    "invoice_creation": {"type": "textarea", "label": "Step-by-step: creating a Medicaid batch invoice (do you bill individually or in batches?)", "required": True},
                    "customer_setup": {"type": "textarea", "label": "How are Medicaid clients set up as Customers in QBO? (Individual? One 'Medicaid' customer?)", "required": False},
                    "service_items": {"type": "textarea", "label": "What Products/Services items are used for Medicaid billing?", "required": False},
                    "attendance_reconciliation": {"type": "textarea", "label": "How do you reconcile billed days against actual attendance?", "required": False},
                    "authorization_tracking": {"type": "textarea", "label": "How do you track that each client's authorization is active before billing?", "required": False},
                },
            },
            "private_pay_invoices": {
                "label": "Private Pay Client Invoices",
                "hint": "Non-Medicaid client billing",
                "fields": {
                    "private_pay_clients": {"type": "text", "label": "Approximate number of private pay clients", "required": False},
                    "private_pay_rates": {"type": "textarea", "label": "Rate structure for private pay (daily rate? sliding scale?)", "required": False},
                    "private_pay_steps": {"type": "textarea", "label": "Step-by-step: creating and sending a private pay invoice", "required": False},
                    "payment_terms": {"type": "text", "label": "Payment terms (Net 15? Net 30? Due on receipt?)", "required": False},
                    "collections": {"type": "textarea", "label": "How do you handle overdue private pay accounts? Collections process?", "required": False},
                },
            },
            "bbg_invoices": {
                "label": "BBG (Black Belt Gold) Invoices",
                "hint": "Revenue from the sports bar / event venue",
                "fields": {
                    "bbg_revenue_sources": {"type": "textarea", "label": "What are BBG's revenue sources? (events, food sales, merchandise, classes?)", "required": False},
                    "bbg_invoicing_steps": {"type": "textarea", "label": "Step-by-step: how do you handle BBG-specific invoicing?", "required": False},
                    "bbg_item_list": {"type": "textarea", "label": "What Products/Services items are used for BBG?", "required": False},
                },
            },
            "invoice_delivery": {
                "label": "Invoice Delivery & Follow-Up",
                "hint": "How invoices get to clients and what happens after",
                "fields": {
                    "delivery_method": {"type": "textarea", "label": "How are invoices sent? (QBO email, mail, portal, hand-delivered?)", "required": True},
                    "email_template": {"type": "textarea", "label": "Email template/message used when sending invoices", "required": False},
                    "follow_up_process": {"type": "textarea", "label": "Invoice follow-up process: when and how do you follow up on unpaid invoices?", "required": False},
                    "late_fees": {"type": "textarea", "label": "Do you charge late fees? How are they calculated and applied?", "required": False},
                },
            },
        },
    },

    # ── SECTION 5: BILL PAY (DEEP DIVE) ──────────────────────────────────────────
    "bill_pay_deep_dive": {
        "label": "💳 Bill Pay — Deep Dive",
        "description": "Complete vendor bill and payment workflow",
        "questions": {
            "bill_entry": {
                "label": "Bill Entry Process",
                "hint": "From receiving a bill to entering it in QBO",
                "fields": {
                    "entry_workflow": {"type": "textarea", "label": "Complete workflow from bill receipt to QBO entry (every click)", "required": True},
                    "document_storage": {"type": "textarea", "label": "Where are vendor invoices/pdfs stored? (Drive, local folder, email?)", "required": False},
                    "filing_system": {"type": "textarea", "label": "Filing/naming convention for vendor documents", "required": False},
                    "qbo_attachment": {"type": "textarea", "label": "Do you attach the scanned bill to the QBO transaction?", "required": False},
                },
            },
            "payment_approval": {
                "label": "Payment Approval & Scheduling",
                "hint": "Who approves and when payments go out",
                "fields": {
                    "approval_workflow": {"type": "textarea", "label": "Walk through the payment approval workflow (who, how, where)", "required": True},
                    "payment_schedule": {"type": "textarea", "label": "Which days do you process payments? Morning or afternoon?", "required": False},
                    "urgent_payments": {"type": "textarea", "label": "How are urgent/rush payments handled differently?", "required": False},
                },
            },
            "payment_execution": {
                "label": "Payment Execution",
                "hint": "How payments are actually made",
                "fields": {
                    "ach_payments": {"type": "textarea", "label": "ACH payment steps (how to initiate, authorize, confirm in QBO)", "required": False},
                    "check_payments": {"type": "textarea", "label": "Check payment steps (printing, signing, mailing, recording)", "required": False},
                    "wire_transfers": {"type": "textarea", "label": "Wire transfer steps (initiation, recording in QBO)", "required": False},
                    "bill_pay_service": {"type": "textarea", "label": "Do you use QBO Bill Pay or a separate bill pay service?", "required": False},
                },
            },
            "vendor_management": {
                "label": "Vendor Management",
                "hint": "How vendors are tracked and maintained",
                "fields": {
                    "vendor_setup": {"type": "textarea", "label": "How do you add a new vendor in QBO?", "required": False},
                    "vendor_list_location": {"type": "text", "label": "Where is the master vendor list? (QBO only, or separate spreadsheet?)", "required": False},
                    "vendor_contacts": {"type": "textarea", "label": "Key vendor contacts (names, phone, email for critical vendors)", "required": False},
                    "contract_tracking": {"type": "textarea", "label": "How are vendor contracts tracked? Renewal dates?", "required": False},
                },
            },
        },
    },

    # ── SECTION 6: PAYROLL (DEEP DIVE) ───────────────────────────────────────────
    "payroll_deep_dive": {
        "label": "👥 Payroll — Deep Dive",
        "description": "Complete payroll processing workflow",
        "questions": {
            "payroll_system": {
                "label": "Payroll System & Schedule",
                "hint": "Which system and when payroll runs",
                "fields": {
                    "system_used": {"type": "text", "label": "Which payroll system? (ADP? Gusto? QuickBooks Payroll?)", "required": True},
                    "portal_url": {"type": "text", "label": "Payroll portal URL and login method", "required": True},
                    "pay_schedule": {"type": "text", "label": "Pay frequency and day (e.g., bi-weekly on Friday, pay date is following Thursday)", "required": True},
                    "employee_count": {"type": "text", "label": "Total employee count processed", "required": False},
                },
            },
            "payroll_run": {
                "label": "Payroll Run Process",
                "hint": "Step-by-step of each payroll run",
                "fields": {
                    "pre_run_steps": {"type": "textarea", "label": "Steps BEFORE running payroll (hours verification, PTO approval, etc.)", "required": True},
                    "run_steps": {"type": "textarea", "label": "Step-by-step: running payroll (every screen, every click)", "required": True},
                    "post_run_steps": {"type": "textarea", "label": "Steps AFTER running payroll (journal entry, report filing, notifications)", "required": True},
                    "qb_journal_entry": {"type": "textarea", "label": "EXACT journal entry posted to QuickBooks (account numbers, debit/credit amounts, memo format)", "required": True},
                },
            },
            "payroll_accounts": {
                "label": "Payroll Chart of Accounts",
                "hint": "Every account involved in payroll",
                "fields": {
                    "gross_wages_account": {"type": "text", "label": "Account name/number for Gross Wages Expense", "required": False},
                    "payroll_tax_expense": {"type": "text", "label": "Account name/number for Payroll Tax Expense (employer portion)", "required": False},
                    "payroll_liabilities": {"type": "text", "label": "Account name/number for Payroll Liabilities (taxes withheld)", "required": False},
                    "cash_account": {"type": "text", "label": "Account name/number for the Cash account payroll hits", "required": False},
                    "benefits_account": {"type": "text", "label": "Any benefits accounts? (health insurance, retirement)", "required": False},
                },
            },
            "tax_compliance": {
                "label": "Tax Compliance",
                "hint": "Payroll tax filings and deadlines",
                "fields": {
                    "quarterly_filings": {"type": "textarea", "label": "Quarterly tax filings (941, state) — process and deadlines", "required": False},
                    "annual_filings": {"type": "textarea", "label": "Annual filings (W-2, W-3, 940) — process and deadlines", "required": False},
                    "tax_payment_schedule": {"type": "textarea", "label": "When and how are payroll tax deposits made?", "required": False},
                },
            },
        },
    },

    # ── SECTION 7: MEDICAID BILLING (DEEP DIVE) ──────────────────────────────────
    "medicaid_billing_deep_dive": {
        "label": "🏥 Medicaid Billing — Deep Dive",
        "description": "Carecenta, 837P claims, 835 remittances — the complete cycle",
        "questions": {
            "carecenta_workflow": {
                "label": "Carecenta System Workflow",
                "hint": "How you use Carecenta for Medicaid billing",
                "fields": {
                    "carecenta_login": {"type": "textarea", "label": "Carecenta login steps (URL, username format, any special auth?)", "required": True},
                    "carecenta_daily_use": {"type": "textarea", "label": "What do you do in Carecenta daily? Weekly? Monthly?", "required": True},
                    "client_setup": {"type": "textarea", "label": "How are new Medicaid clients set up in Carecenta?", "required": False},
                    "carecenta_export": {"type": "textarea", "label": "How do you export data from Carecenta? What format does it come in?", "required": False},
                },
            },
            "claim_creation_837P": {
                "label": "837P Claim Creation & Submission",
                "hint": "How claims are built and submitted",
                "fields": {
                    "claim_batch_schedule": {"type": "text", "label": "How often do you submit claim batches? (weekly? monthly?)", "required": True},
                    "claim_creation_steps": {"type": "textarea", "label": "Step-by-step: creating an 837P claim batch (every screen, every field)", "required": True},
                    "required_fields": {"type": "textarea", "label": "What fields/info are REQUIRED for each claim? (client name, Medicaid ID, service dates, procedure codes, diagnosis codes, NPI, taxonomy)", "required": True},
                    "procedure_codes": {"type": "textarea", "label": "List ALL procedure codes used (HCPCS/CPT) and when each is used", "required": False},
                    "diagnosis_codes": {"type": "textarea", "label": "Common diagnosis codes used", "required": False},
                    "submission_method": {"type": "textarea", "label": "How are claims submitted? (Carecenta direct, clearinghouse portal, upload?)", "required": False},
                    "clearinghouse": {"type": "text", "label": "Which clearinghouse? (Availity? Change Healthcare? Direct?)", "required": False},
                },
            },
            "remittance_835": {
                "label": "835 Remittance Processing",
                "hint": "How you handle payment remittances",
                "fields": {
                    "remittance_schedule": {"type": "text", "label": "When do 835 remittances typically arrive? (weekly? as payments come in?)", "required": False},
                    "download_steps": {"type": "textarea", "label": "Step-by-step: downloading 835 remittance files", "required": True},
                    "parsing_steps": {"type": "textarea", "label": "How do you parse/read the 835? (software? manual review? spreadsheet?)", "required": True},
                    "payment_posting": {"type": "textarea", "label": "Step-by-step: posting Medicaid payments in QuickBooks against invoices", "required": True},
                    "denial_handling": {"type": "textarea", "label": "How do you handle denials? (CO-97 not authorized, CO-4 wrong procedure, PR-96 patient balance)", "required": True},
                    "appeal_process": {"type": "textarea", "label": "What is the denial appeal process?", "required": False},
                    "underpayment_handling": {"type": "textarea", "label": "How do you handle underpayments (paid less than billed)?", "required": False},
                },
            },
            "authorization_management": {
                "label": "Authorization Management",
                "hint": "Tracking and renewing Medicaid authorizations",
                "fields": {
                    "auth_tracking": {"type": "textarea", "label": "How do you track which authorizations are expiring? (spreadsheet? QBO? auth_tracker.db?)", "required": True},
                    "renewal_process": {"type": "textarea", "label": "Step-by-step: what happens when a client's authorization expires?", "required": True},
                    "expired_billing": {"type": "textarea", "label": "How do you handle billing for clients whose auth has expired? (hold claims? bill and appeal?)", "required": False},
                },
            },
        },
    },

    # ── SECTION 8: BANK RECONCILIATION (DEEP DIVE) ───────────────────────────────
    "bank_reconciliation_deep_dive": {
        "label": "🏦 Bank Reconciliation — Deep Dive",
        "description": "Complete reconciliation process for every account",
        "questions": {
            "reconciliation_setup": {
                "label": "Reconciliation Setup & Preparation",
                "hint": "What you need before starting a reconciliation",
                "fields": {
                    "accounts_list": {"type": "textarea", "label": "Complete list of accounts requiring reconciliation (bank, credit card, loan, line of credit)", "required": True},
                    "statement_retrieval": {"type": "textarea", "label": "How do you get statements? (download from bank portal, email, mail?) URLs?", "required": True},
                    "pre_rec_checks": {"type": "textarea", "label": "What do you check/verify BEFORE starting reconciliation?", "required": False},
                },
            },
            "reconciliation_execution": {
                "label": "Reconciliation Execution",
                "hint": "The actual reconciliation process in QBO",
                "fields": {
                    "qbo_rec_steps": {"type": "textarea", "label": "Step-by-step: reconciling in QuickBooks (menu path, every click)", "required": True},
                    "matching_rules": {"type": "textarea", "label": "How do you match transactions? (auto-match rules? manual matching? what do you match on?)", "required": False},
                    "bank_feed_cleaning": {"type": "textarea", "label": "How do you handle bank feed transactions? (categorization rules, exclusion rules)", "required": False},
                    "unmatched_handling": {"type": "textarea", "label": "How do you handle unmatched transactions? (deposits in transit, outstanding checks)", "required": True},
                    "difference_tolerance": {"type": "text", "label": "What difference do you tolerate before investigating? ($1? $0.01? must match to the penny?)", "required": False},
                },
            },
            "reconciliation_wrapup": {
                "label": "Reconciliation Wrap-Up",
                "hint": "After reconciliation is done",
                "fields": {
                    "rec_report": {"type": "textarea", "label": "Do you print/save reconciliation reports? Where?", "required": False},
                    "rec_signing": {"type": "textarea", "label": "Who signs off on reconciliations?", "required": False},
                    "rec_filing": {"type": "textarea", "label": "Where are completed reconciliations filed for audit purposes?", "required": False},
                },
            },
        },
    },

    # ── SECTION 9: REPORT GENERATION ─────────────────────────────────────────────
    "report_generation": {
        "label": "📈 Report Generation",
        "description": "All reports, who gets them, and when",
        "questions": {
            "standard_reports": {
                "label": "Standard Monthly Reports",
                "hint": "Reports generated every month",
                "fields": {
                    "report_list": {"type": "textarea", "label": "Complete list of reports generated each month", "required": True},
                    "pl_steps": {"type": "textarea", "label": "P&L report: steps, date range, format (accrual vs cash), class filtering", "required": True},
                    "balance_sheet_steps": {"type": "textarea", "label": "Balance Sheet: steps, date, format, any customizations", "required": False},
                    "ar_aging_steps": {"type": "textarea", "label": "AR Aging report: steps, date, what you do with the results", "required": False},
                    "ap_aging_steps": {"type": "textarea", "label": "AP Aging report: steps, date, what you do with the results", "required": False},
                },
            },
            "custom_reports": {
                "label": "Custom & Ad-Hoc Reports",
                "hint": "Special reports for specific purposes",
                "fields": {
                    "custom_report_list": {"type": "textarea", "label": "Any custom reports you've created or run regularly?", "required": False},
                    "vlad_reports": {"type": "textarea", "label": "What reports does Vlad receive? Format? Frequency? Delivery method?", "required": True},
                    "kato_reports": {"type": "textarea", "label": "What reports does Kato receive beyond standard?", "required": False},
                    "accountant_reports": {"type": "textarea", "label": "What does the external accountant/tax preparer need? When?", "required": False},
                },
            },
            "report_delivery": {
                "label": "Report Delivery & Archiving",
                "hint": "How reports get where they need to go",
                "fields": {
                    "delivery_methods": {"type": "textarea", "label": "How are reports delivered? (email, printed, Google Drive, PDF export?)", "required": True},
                    "filing_location": {"type": "textarea", "label": "Where are reports saved/archived? (Drive folder path? Local folder?)", "required": False},
                    "file_naming": {"type": "text", "label": "File naming convention for reports", "required": False},
                },
            },
        },
    },

    # ── SECTION 10: SYSTEM & ACCESS ──────────────────────────────────────────────
    "system_access": {
        "label": "🔑 System Access & Credentials",
        "description": "Everything the replacement needs to access",
        "questions": {
            "quickbooks_access": {
                "label": "QuickBooks Online Access",
                "hint": "Login and account details",
                "fields": {
                    "qbo_url": {"type": "text", "label": "QuickBooks Online URL", "required": False},
                    "company_name": {"type": "text", "label": "Company name as it appears in QBO", "required": False},
                    "user_role": {"type": "text", "label": "Your user role (Admin? Standard user?)", "required": False},
                    "mfa_method": {"type": "text", "label": "Multi-factor authentication method (SMS? Authenticator app?)", "required": False},
                },
            },
            "connected_apps": {
                "label": "Connected Apps & Integrations",
                "hint": "All third-party apps connected to QBO",
                "fields": {
                    "app_list": {"type": "textarea", "label": "List ALL connected apps (Clover, ADP, Bill.com, Expensify, banks, etc.)", "required": True},
                    "app_credentials": {"type": "textarea", "label": "Where are credentials for connected apps stored?", "required": False},
                    "sync_schedule": {"type": "textarea", "label": "Sync schedule for each connected app (realtime? daily?)", "required": False},
                },
            },
            "other_systems": {
                "label": "Other Systems & Portals",
                "hint": "Anything else the bookkeeper logs into",
                "fields": {
                    "carecenta_access": {"type": "textarea", "label": "Carecenta login details (URL, username format, special access)", "required": False},
                    "bank_portals": {"type": "textarea", "label": "Bank portal URLs and what each is used for", "required": True},
                    "adp_access": {"type": "textarea", "label": "ADP/payroll system login details", "required": False},
                    "tax_portals": {"type": "textarea", "label": "Tax agency portals (IRS, state, sales tax) — URLs and purpose", "required": False},
                    "other_portals": {"type": "textarea", "label": "Any other portals, systems, or tools you use regularly", "required": False},
                },
            },
        },
    },

    # ── SECTION 11: TROUBLESHOOTING & EDGE CASES ─────────────────────────────────
    "troubleshooting": {
        "label": "🔧 Troubleshooting & Edge Cases",
        "description": "Common problems and how you solve them",
        "questions": {
            "common_issues": {
                "label": "Common Issues",
                "hint": "Problems that come up regularly",
                "fields": {
                    "issue_list": {"type": "textarea", "label": "List the 5-10 most common problems you encounter and how you fix each", "required": True},
                    "qbo_errors": {"type": "textarea", "label": "Any QBO error messages you see regularly and how to resolve them", "required": False},
                    "data_fixes": {"type": "textarea", "label": "How do you handle data entry mistakes? (void vs delete? audit trail?)", "required": False},
                },
            },
            "edge_cases": {
                "label": "Edge Cases & Special Situations",
                "hint": "Rare but important scenarios",
                "fields": {
                    "refund_process": {"type": "textarea", "label": "How do you process client refunds or credit memos?", "required": False},
                    "nsf_handling": {"type": "textarea", "label": "How are bounced checks / NSF payments handled?", "required": False},
                    "write_offs": {"type": "textarea", "label": "How do you handle bad debt write-offs?", "required": False},
                    "year_end": {"type": "textarea", "label": "Special year-end procedures? (1099s, W-2s, year-end close)", "required": True},
                    "audit_prep": {"type": "textarea", "label": "What do you prepare for audits? Has GHS been audited?", "required": False},
                },
            },
            "gotchas": {
                "label": "\"Gotchas\" — Things the New Person MUST Know",
                "hint": "Unwritten rules and traps",
                "fields": {
                    "unwritten_rules": {"type": "textarea", "label": "What unwritten rules or conventions does the new person need to know?", "required": True},
                    "common_mistakes": {"type": "textarea", "label": "Most common mistakes a new person would make — and how to avoid them", "required": True},
                    "kato_preferences": {"type": "textarea", "label": "Any specific preferences Kato (Alejandro) has about how things are done?", "required": False},
                    "vlad_preferences": {"type": "textarea", "label": "Any specific preferences Vlad has about financial reporting?", "required": False},
                },
            },
        },
    },

    # ── SECTION 12: CAPTURE MODE SESSIONS ────────────────────────────────────────
    "capture_sessions": {
        "label": "🎥 Step-by-Step Capture Sessions",
        "description": "Recorded walkthroughs with screenshots (placeholder for recording tool)",
        "sessions": [],  # Each session: {id, label, steps: [{action, screenshot_path, notes}]}
    },
}

# ── Pydantic models ──────────────────────────────────────────────────────────

class WorkflowResponse(BaseModel):
    """Individual field response from the bookkeeper."""
    category: str
    question: str
    field: str
    value: str

class WorkflowSubmit(BaseModel):
    """Full or partial submission of the questionnaire."""
    responses: Dict[str, Dict[str, Dict[str, str]]] = {}
    # Top-level: category → question → field → value

class CaptureStep(BaseModel):
    """A single step in a capture session."""
    step_number: int
    action: str
    screenshot_path: Optional[str] = None
    notes: Optional[str] = None
    timestamp: Optional[str] = None

class CaptureSession(BaseModel):
    """A full capture session."""
    session_label: str
    category: str
    steps: List[CaptureStep] = []


# ── State helpers ────────────────────────────────────────────────────────────

def _load_state() -> dict:
    """Load existing workflow state, or return empty template."""
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    if _STATE_FILE.exists():
        try:
            return json.loads(_STATE_FILE.read_text())
        except json.JSONDecodeError:
            logger.warning("Corrupted state file, starting fresh")
    return {}


def _save_state(data: dict):
    """Save workflow state to disk."""
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    data["_meta"] = data.get("_meta", {})
    data["_meta"]["last_updated"] = datetime.now().isoformat()
    data["_meta"]["tool"] = "CC_quickbooks_capture"
    _STATE_FILE.write_text(json.dumps(data, indent=2))


# ── API Endpoints ────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the HTML questionnaire frontend."""
    if not _HTML_FILE.exists():
        return HTMLResponse(
            content="<h1>Questionnaire HTML not found</h1><p>CC_quickbooks_capture.html is missing.</p>",
            status_code=404,
        )
    return HTMLResponse(content=_HTML_FILE.read_text())


@router.get("/api/questionnaire")
async def get_questionnaire():
    """Return the full questionnaire template with any saved responses merged in."""
    state = _load_state()
    # Deep-merge saved responses into the template
    template = json.loads(json.dumps(QUESTIONNAIRE))  # Deep copy
    for category_key, category_data in state.items():
        if category_key.startswith("_") or category_key == "capture_sessions":
            continue
        if category_key in template:
            for question_key, question_data in category_data.items():
                if question_key in template[category_key].get("questions", {}):
                    template[category_key]["questions"][question_key]["responses"] = question_data
    # Attach capture sessions
    if "capture_sessions" in state:
        template["capture_sessions"]["sessions"] = state["capture_sessions"].get("sessions", [])
    template["_meta"]["has_saved_data"] = bool(state and any(
        k for k in state if not k.startswith("_")
    ))
    return template


@router.get("/api/responses")
async def get_responses():
    """Return only the saved responses (no template)."""
    state = _load_state()
    return state


@router.post("/api/responses")
async def save_responses(submit: WorkflowSubmit):
    """Save questionnaire responses. Merges with existing state."""
    state = _load_state()
    for category, questions in submit.responses.items():
        if category not in state:
            state[category] = {}
        for question, fields in questions.items():
            state[category][question] = fields
    _save_state(state)
    return {"status": "saved", "categories_updated": list(submit.responses.keys())}


@router.post("/api/single-response")
async def save_single_response(response: WorkflowResponse):
    """Save a single field response. Good for auto-save on each field change."""
    state = _load_state()
    if response.category not in state:
        state[response.category] = {}
    if response.question not in state[response.category]:
        state[response.category][response.question] = {}
    state[response.category][response.question][response.field] = response.value
    _save_state(state)
    return {"status": "saved", "field": f"{response.category}.{response.question}.{response.field}"}


@router.get("/api/summary")
async def get_summary():
    """Return a progress summary — which categories have been filled out."""
    template = QUESTIONNAIRE
    state = _load_state()
    summary = {}
    total_fields = 0
    filled_fields = 0
    for cat_key, cat_data in template.items():
        if cat_key.startswith("_") or cat_key == "capture_sessions":
            continue
        cat_total = 0
        cat_filled = 0
        for q_key, q_data in cat_data.get("questions", {}).items():
            for f_key in q_data.get("fields", {}):
                cat_total += 1
                saved_val = state.get(cat_key, {}).get(q_key, {}).get(f_key, "")
                if saved_val and saved_val.strip():
                    cat_filled += 1
        summary[cat_key] = {
            "label": cat_data["label"],
            "total": cat_total,
            "filled": cat_filled,
            "percent": round(100 * cat_filled / cat_total) if cat_total > 0 else 0,
        }
        total_fields += cat_total
        filled_fields += cat_filled
    summary["_total"] = {
        "label": "Overall",
        "total": total_fields,
        "filled": filled_fields,
        "percent": round(100 * filled_fields / total_fields) if total_fields > 0 else 0,
    }
    return summary


# ── Capture Mode (placeholder) ───────────────────────────────────────────────

@router.get("/api/capture-sessions")
async def list_capture_sessions():
    """List all saved capture sessions."""
    state = _load_state()
    sessions = state.get("capture_sessions", {}).get("sessions", [])
    return {"sessions": sessions, "count": len(sessions)}


@router.post("/api/capture-sessions")
async def create_capture_session(session: CaptureSession):
    """Save a new capture session (step-by-step recording)."""
    state = _load_state()
    if "capture_sessions" not in state:
        state["capture_sessions"] = {"sessions": []}
    session_dict = session.model_dump()
    session_dict["id"] = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    session_dict["created"] = datetime.now().isoformat()
    state["capture_sessions"]["sessions"].append(session_dict)
    _save_state(state)
    return {"status": "captured", "session_id": session_dict["id"]}


@router.delete("/api/capture-sessions/{session_id}")
async def delete_capture_session(session_id: str):
    """Delete a capture session."""
    state = _load_state()
    sessions = state.get("capture_sessions", {}).get("sessions", [])
    state["capture_sessions"]["sessions"] = [s for s in sessions if s.get("id") != session_id]
    _save_state(state)
    return {"status": "deleted"}


@router.post("/api/export")
async def export_workflow():
    """Export the complete workflow as a formatted markdown document."""
    state = _load_state()
    template = QUESTIONNAIRE
    lines = [
        "# QuickBooks Workflow — Gold Health Systems",
        f"*Captured: {datetime.now().strftime('%B %d, %Y')}*",
        "",
        "---",
        "",
    ]

    for cat_key, cat_data in template.items():
        if cat_key.startswith("_") or cat_key == "capture_sessions":
            continue
        lines.append(f"## {cat_data['label']}")
        lines.append(f"*{cat_data['description']}*")
        lines.append("")
        for q_key, q_data in cat_data.get("questions", {}).items():
            lines.append(f"### {q_data['label']}")
            if q_data.get("hint"):
                lines.append(f"_{q_data['hint']}_")
            lines.append("")
            for f_key, f_data in q_data.get("fields", {}).items():
                value = state.get(cat_key, {}).get(q_key, {}).get(f_key, "")
                value = value or "*(not yet filled in)*"
                lines.append(f"**{f_data['label']}**")
                lines.append(f"")
                lines.append(f"{value}")
                lines.append("")
            lines.append("")
        lines.append("---")
        lines.append("")

    # Capture sessions
    sessions = state.get("capture_sessions", {}).get("sessions", [])
    if sessions:
        lines.append("## 🎥 Capture Sessions")
        lines.append("")
        for session in sessions:
            lines.append(f"### {session.get('session_label', 'Unnamed Session')}")
            lines.append(f"*Recorded: {session.get('created', 'unknown')}*")
            lines.append("")
            lines.append("| Step | Action | Notes |")
            lines.append("|------|--------|-------|")
            for step in session.get("steps", []):
                action = step.get("action", "")
                notes = step.get("notes", "")
                screenshot = step.get("screenshot_path", "")
                if screenshot:
                    notes = f"{notes} [Screenshot: {screenshot}]"
                lines.append(f"| {step.get('step_number', '')} | {action} | {notes} |")
            lines.append("")

    markdown = "\n".join(lines)
    return {"markdown": markdown, "format": "markdown"}


# ── CLI Interview Mode ───────────────────────────────────────────────────────

def run_cli_interview():
    """Run the questionnaire as an interactive CLI interview."""
    import readline  # Enable line editing in raw_input

    print("\n" + "=" * 70)
    print("  🦖 QUICKBOOKS WORKFLOW CAPTURE — CLI INTERVIEW MODE")
    print("  Gold Health Systems · Bookkeeper Knowledge Transfer")
    print("=" * 70)
    print()
    print("  This interview will walk you through every aspect of your")
    print("  QuickBooks workflow. Take your time — be as detailed as possible.")
    print("  The more you share, the smoother the handoff to your replacement.")
    print()
    print("  • Press Enter to skip any question")
    print("  • Type 'back' to redo the previous question")
    print("  • Type 'save' at any prompt to save and continue later")
    print("  • Type 'quit' to save and exit")
    print()

    state = _load_state()
    template = QUESTIONNAIRE
    total = 0
    answered = 0

    categories = [(k, v) for k, v in template.items()
                  if not k.startswith("_") and k != "capture_sessions"]

    print(f"  Loading existing responses... ({_STATE_FILE})")
    print(f"  Categories: {len(categories)}")
    print()

    # Count total questions
    total_questions = 0
    for _, cat_data in categories:
        for _, q_data in cat_data.get("questions", {}).items():
            total_questions += len(q_data.get("fields", {}))

    current_idx = 0
    prev_value = None  # For 'back' command

    for cat_idx, (cat_key, cat_data) in enumerate(categories):
        print(f"\n{'─' * 70}")
        print(f"  📋 CATEGORY {cat_idx + 1}/{len(categories)}: {cat_data['label']}")
        print(f"  {cat_data['description']}")
        print(f"{'─' * 70}")

        questions = list(cat_data.get("questions", {}).items())
        for q_idx, (q_key, q_data) in enumerate(questions):
            print(f"\n  [{cat_idx+1}.{q_idx+1}] {q_data['label']}")
            if q_data.get("hint"):
                print(f"  💡 {q_data['hint']}")

            fields = list(q_data.get("fields", {}).items())
            for f_idx, (f_key, f_data) in enumerate(fields):
                current_idx += 1
                label = f_data["label"]
                required = f_data.get("required", False)
                req_mark = " *REQUIRED*" if required else ""

                # Show existing value if any
                existing = state.get(cat_key, {}).get(q_key, {}).get(f_key, "")
                existing_display = f" [current: {existing[:60]}...]" if existing else ""

                prompt = f"  ▶ {label}{req_mark}{existing_display}"
                is_textarea = f_data.get("type") == "textarea"

                if is_textarea:
                    print(prompt)
                    print("    (Enter multiple lines. Type a single '.' on its own line to finish)")
                    lines_list = []
                    while True:
                        try:
                            line = input("    > ").rstrip()
                        except (EOFError, KeyboardInterrupt):
                            print("\n    Exiting. Progress saved.")
                            _save_state(state)
                            sys.exit(0)
                        if line == ".":
                            break
                        if line.lower() == "quit":
                            _save_state(state)
                            print(f"\n  ✅ Saved {answered} responses to {_STATE_FILE}")
                            sys.exit(0)
                        if line.lower() == "save":
                            _save_state(state)
                            print(f"  ✅ Progress saved. Continuing...")
                            continue
                        if line.lower() == "back":
                            # Can't really go back mid-textarea easily
                            print("    (Cannot go back while entering multi-line text)")
                            continue
                        lines_list.append(line)
                    value = "\n".join(lines_list)
                else:
                    try:
                        value = input(f"{prompt}\n    > ").strip()
                    except (EOFError, KeyboardInterrupt):
                        print("\n    Exiting. Progress saved.")
                        _save_state(state)
                        sys.exit(0)

                # Handle commands
                if value.lower() == "quit":
                    _save_state(state)
                    print(f"\n  ✅ Saved {answered} responses to {_STATE_FILE}")
                    sys.exit(0)
                if value.lower() == "save":
                    _save_state(state)
                    print(f"  ✅ Progress saved. Resume with 'python3 CC_quickbooks_capture.py --cli'")
                    print("    Continuing with next question...")
                    continue
                if value.lower() == "back":
                    if prev_value is not None:
                        # Undo the previous save
                        state[prev_value["cat"]][prev_value["q"]][prev_value["f"]] = prev_value["old"]
                        print(f"    ↩ Restored previous value. Re-enter:")
                        try:
                            value = input("    > ").strip()
                        except (EOFError, KeyboardInterrupt):
                            _save_state(state)
                            sys.exit(0)
                        if value.lower() in ("quit", "save"):
                            _save_state(state)
                            if value.lower() == "quit":
                                sys.exit(0)
                    else:
                        print("    (No previous question to go back to)")
                        continue

                # Save this field
                if cat_key not in state:
                    state[cat_key] = {}
                if q_key not in state[cat_key]:
                    state[cat_key][q_key] = {}
                prev_value = {
                    "cat": cat_key,
                    "q": q_key,
                    "f": f_key,
                    "old": state[cat_key][q_key].get(f_key, ""),
                }
                if value:  # Only save non-empty
                    state[cat_key][q_key][f_key] = value
                    answered += 1

                # Show progress
                pct = round(100 * current_idx / total_questions)
                print(f"    [{pct}% complete — {current_idx}/{total_questions}]")

    # Final save
    _save_state(state)
    print(f"\n{'=' * 70}")
    print(f"  🎉 INTERVIEW COMPLETE!")
    print(f"  {answered}/{total_questions} questions answered")
    print(f"  State saved to: {_STATE_FILE}")
    print(f"{'=' * 70}")
    print()
    print("  Next steps:")
    print("  1. Review the HTML form at /quickbooks-capture for any missed fields")
    print("  2. Export to markdown: POST /quickbooks-capture/api/export")
    print("  3. New bookkeeper can reference: ~/Desktop/REX/state/quickbooks_workflow.json")
    print()


# ── Main entrypoint for CLI mode ─────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        run_cli_interview()
    elif len(sys.argv) > 1 and sys.argv[1] == "--export":
        # Quick export from CLI
        state = _load_state()
        out_path = _STATE_DIR / "quickbooks_workflow_export.md"
        lines = []
        template = QUESTIONNAIRE
        lines.append("# QuickBooks Workflow — Gold Health Systems")
        lines.append(f"*Exported: {datetime.now().strftime('%B %d, %Y')}*")
        lines.append("")
        for cat_key, cat_data in template.items():
            if cat_key.startswith("_") or cat_key == "capture_sessions":
                continue
            lines.append(f"## {cat_data['label']}")
            lines.append(f"*{cat_data['description']}*")
            lines.append("")
            for q_key, q_data in cat_data.get("questions", {}).items():
                lines.append(f"### {q_data['label']}")
                lines.append("")
                for f_key, f_data in q_data.get("fields", {}).items():
                    value = state.get(cat_key, {}).get(q_key, {}).get(f_key, "") or "*(not filled)*"
                    lines.append(f"**{f_data['label']}**")
                    lines.append(f"")
                    lines.append(f"{value}")
                    lines.append("")
        out_path.write_text("\n".join(lines))
        print(f"✅ Exported to {out_path}")
    elif len(sys.argv) > 1 and sys.argv[1] == "--summary":
        # Quick progress summary from CLI
        import subprocess
        try:
            import httpx
            resp = httpx.get("http://localhost:8000/quickbooks-capture/api/summary")
            if resp.status_code == 200:
                data = resp.json()
                print("\n  QuickBooks Capture Progress:\n")
                for key, info in data.items():
                    if key == "_total":
                        print(f"  {'─' * 40}")
                        print(f"  {info['label']}: {info['filled']}/{info['total']} ({info['percent']}%)")
                    else:
                        bar = "█" * (info['percent'] // 5) + "░" * (20 - info['percent'] // 5)
                        print(f"  {info['label']:40s} {bar} {info['percent']}%")
            else:
                print("REX not running on :8000")
        except Exception:
            # Fallback: compute locally
            template = QUESTIONNAIRE
            state = _load_state()
            print("\n  QuickBooks Capture Progress (offline):\n")
            total_all, filled_all = 0, 0
            for cat_key, cat_data in template.items():
                if cat_key.startswith("_") or cat_key == "capture_sessions":
                    continue
                total_q, filled_q = 0, 0
                for q_key, q_data in cat_data.get("questions", {}).items():
                    for f_key in q_data.get("fields", {}):
                        total_q += 1
                        if state.get(cat_key, {}).get(q_key, {}).get(f_key, "").strip():
                            filled_q += 1
                total_all += total_q
                filled_all += filled_q
                pct = round(100 * filled_q / total_q) if total_q > 0 else 0
                bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
                print(f"  {cat_data['label']:40s} {bar} {pct}%")
            overall = round(100 * filled_all / total_all) if total_all > 0 else 0
            print(f"  {'─' * 40}")
            print(f"  Overall: {filled_all}/{total_all} ({overall}%)")
    else:
        print("CC_quickbooks_capture.py — QuickBooks Workflow Capture Tool")
        print()
        print("Usage:")
        print("  python3 CC_quickbooks_capture.py --cli       Interactive CLI interview")
        print("  python3 CC_quickbooks_capture.py --export    Export responses to markdown")
        print("  python3 CC_quickbooks_capture.py --summary   Show progress summary")
        print()
        print("API endpoints (when mounted in REX):")
        print("  GET  /quickbooks-capture             HTML questionnaire frontend")
        print("  GET  /quickbooks-capture/api/questionnaire   Full template + saved data")
        print("  GET  /quickbooks-capture/api/responses       Saved responses only")
        print("  POST /quickbooks-capture/api/responses       Save responses")
        print("  POST /quickbooks-capture/api/single-response  Save one field (auto-save)")
        print("  GET  /quickbooks-capture/api/summary          Progress summary")
        print("  GET  /quickbooks-capture/api/capture-sessions  List recordings")
        print("  POST /quickbooks-capture/api/capture-sessions  Save new recording")
        print("  POST /quickbooks-capture/api/export            Export as markdown")
