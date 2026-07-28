# CC_LEAD_CONNECTOR_BUILD_PLAN.md
# GHS Lead Connector — Full Build Roadmap
# Gold Health Systems · v1.0 · June 4 2026

---

## What Is This

A fully local, privacy-first CRM + marketing automation platform built for Gold Health Systems. Replaces cloud CRMs (Salesforce, HighLevel, GoHighLevel) with a self-hosted stack that keeps all GOJ client data on-prem and HIPAA-compliant by design.

**Two primary use cases:**
- **GOJ (Garden of Joy):** Track 425+ adult day care clients through the Medicaid authorization lifecycle. Replace spreadsheet-based authorization tracking with a visual pipeline.
- **BBG (Boardwalk Beer Garden):** Track event inquiries, reservations, and repeat customers through a sales funnel.

---

## Phase 1 — Core CRM + Pipeline + Frontend (TODAY ✅)

**Files delivered:**
- `CC_lead_connector_api.py` — FastAPI backend, port 8002, SQLite at `~/Desktop/REX/CC_lead_connector.db`
- `CC_lead_connector.html` — Single-file dashboard (dark theme, 5 views)
- `CC_LEAD_CONNECTOR_BUILD_PLAN.md` — This document

**What was built:**

### Data Layer
5 SQLite tables: `contacts`, `pipelines`, `deals`, `activities`, `communications`.

Two pipelines seeded on first run:
1. **GOJ Authorization Pipeline:** New Lead → Auth Submitted → Auth Pending → Auth Active → Renewal Due → Expired
2. **BBG Events Pipeline:** Inquiry → Interested → Reservation → Confirmed → Attended → Repeat Customer

### API Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| GET/POST | `/contacts` | List (search/filter) + create |
| GET/PUT/DELETE | `/contacts/{id}` | Read, update, soft-delete |
| GET | `/contacts/{id}/timeline` | Merged activity + comms log |
| POST | `/contacts/{id}/note` | Add note |
| POST | `/contacts/import/goj` | One-way pull from auth_tracker.db |
| GET/POST | `/pipelines` | List + create |
| GET | `/pipelines/{id}/board` | Kanban columns with deal grouping |
| GET/POST | `/deals` | List + create |
| POST | `/deals/{id}/move` | Move deal to new stage (logs activity) |
| POST | `/communications/inbound` | Inbound webhook (Masha, SMS, IG DM) |
| GET | `/communications` | Inbox feed |
| GET | `/dashboard/stats` | Aggregate stats for dashboard |
| GET | `/health` | Health check |

### Frontend Views
- **Dashboard:** 4 stat cards (contacts, pipeline value, conversion rate, comms), GOJ stage breakdown bars, recent activity feed
- **Contacts:** Searchable/filterable table, color-coded GOJ/BBG badges, click to open detail panel
- **Pipeline:** Kanban board with drag-and-drop + click-to-move, deal value per column, pipeline switcher tabs
- **Inbox:** Unified communication feed (all channels), thread view, reply box placeholder
- **Calendar:** Monthly grid with sample events

Contact detail slide-over panel includes: info grid, stage pipeline progress bar, activity timeline, Add Note form, Log Call, Move Stage dropdown.

### To Start
```bash
source ~/debate-chamber/.venv/bin/activate
cd ~/Desktop/REX
uvicorn CC_lead_connector_api:app --host 0.0.0.0 --port 8002 --reload
# Then open CC_lead_connector.html in browser
```

---

## Phase 2 — SMS + Email Automation (Twilio Integration)

**Goal:** Real outbound/inbound messaging from the Inbox view. Trigger workflows on pipeline stage changes.

**SMS (Twilio):**
- Add `CC_twilio_handler.py` — webhook receiver for inbound SMS, outbound send via Twilio REST API
- Wire `POST /communications/send` endpoint → Twilio `messages.create()`
- Inbound: Twilio webhook → `POST /communications/inbound` (already built, just needs Twilio config)
- Store Twilio SID/token in macOS Keychain via `rex_vault.py`

**Email (SendGrid or Gmail API):**
- Reuse `rex_gmail.py` OAuth token for outbound from atigerclawai@gmail.com
- OR add SendGrid for transactional email (authorization renewal reminders, appointment confirmations)

**Automation Triggers:**
- Contact moves to `renewal_due` stage → auto-send SMS reminder (template configurable)
- Contact moves to `expired` stage → escalate to Kato via Telegram bot
- New inbound comm → create activity, flag in dashboard, send Telegram alert to `@RexOfGold_bot`
- New BBG inquiry → assign to BBG Events pipeline, send confirmation email

**Schema additions:**
```sql
CREATE TABLE automation_rules (
  id INTEGER PRIMARY KEY,
  name TEXT,
  trigger_type TEXT,  -- stage_change | new_contact | new_comm | deal_value
  trigger_value TEXT,
  action_type TEXT,   -- send_sms | send_email | notify_telegram | create_activity
  action_payload TEXT,  -- JSON template
  pipeline_id INTEGER,
  enabled INTEGER DEFAULT 1,
  created_at TEXT
);
```

---

## Phase 3 — Calendar + Appointment Booking + Masha Voice Confirmation

**Goal:** Bookable appointment slots with automated voice confirmation via Masha (Retell).

**Calendar backend:**
- Add `appointments` table: `id, contact_id, title, start_time, end_time, type (goj_auth/bbg_event/other), status (scheduled/confirmed/cancelled/no_show), notes, created_at`
- `GET /appointments?date=` — fetch day's appointments
- `POST /appointments` — create appointment
- `PUT /appointments/{id}/confirm` — confirm + trigger Masha call

**Masha integration (Retell voice agent):**
- Retell webhook fires on call completion → `POST /communications/inbound` with `channel=voice`
- Appointment confirmation flow: Masha calls contact → confirms date/time → webhook updates appointment status
- New call from unknown number → Masha creates contact automatically → routes to inbox

**Calendar frontend:**
- Replace sample events with real DB data
- Click day → show appointments list + "Add Appointment" button
- Appointment detail: contact link, status badge, Masha call button

---

## Phase 4 — Instagram DM Integration (Meta API)

**Goal:** Receive and reply to Instagram DMs directly from the Inbox view.

**Context:** Meta API is already partially configured for BBG. Phase 4 completes the webhook wiring.

**Architecture:**
- Meta Webhooks → `POST /communications/inbound` (channel=instagram_dm) — already built
- Outbound reply: `POST /communications/reply` → Meta Graph API `POST /{ig-user-id}/messages`
- Store Meta page token in Keychain
- Webhook verification: add `GET /communications/webhook/verify` endpoint for Meta handshake

**Contact matching:**
- Instagram sender PSID → look up in `contacts.custom_fields.instagram_psid`
- Auto-create contact on first message, add `instagram_dm` tag

**Phase 4 adds:**
- Outbound reply support in the Inbox view (currently SMS placeholder)
- Instagram conversation threading (group messages by sender)
- BBG lead auto-tagging from Instagram

---

## Phase 5 — Clover POS Sync (Payment Events → CRM)

**Goal:** BBG payment events (tabs, reservations, events) auto-log to CRM contact timeline.

**Clover webhook → Lead Connector:**
- Add `POST /contacts/{id}/payment` endpoint
- Clover fires webhook on payment completion → GHS middleware matches customer by phone/email → POST to Lead Connector
- Payment logged as activity type `payment` with amount, item list, timestamp

**BBG-specific pipeline automation:**
- Payment received → move deal from `reservation` to `confirmed`
- Repeat payment detected (same customer) → move to `repeat_customer` stage
- Revenue tracking per contact: `contacts.custom_fields.lifetime_value`

**Dashboard additions:**
- BBG revenue panel: total revenue this month, average event value, top customers by LTV
- GOJ billing view: authorization value tracking per client

**Schema additions:**
```sql
CREATE TABLE payments (
  id INTEGER PRIMARY KEY,
  contact_id INTEGER,
  amount REAL,
  clover_order_id TEXT,
  items TEXT,  -- JSON
  channel TEXT DEFAULT 'clover',
  created_at TEXT
);
```

---

## Phase 6 — Multi-Tenant SaaS (Sell to Other Adult Day Cares)

**Goal:** Package Lead Connector as a SaaS product for other adult day care facilities. Target: NYC/NJ adult day care market (estimated 200+ facilities).

**Multi-tenancy model:**
Add `tenant_id` column to all tables:
```sql
-- Every table gets:
ALTER TABLE contacts    ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'ghs';
ALTER TABLE pipelines   ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'ghs';
ALTER TABLE deals       ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'ghs';
ALTER TABLE activities  ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'ghs';
ALTER TABLE communications ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'ghs';

CREATE TABLE tenants (
  id TEXT PRIMARY KEY,  -- uuid
  name TEXT,
  plan TEXT DEFAULT 'starter',  -- starter | professional | enterprise
  created_at TEXT,
  settings TEXT  -- JSON: custom branding, pipeline defaults, etc.
);
```

**All API queries get `WHERE tenant_id = ?` guard — never cross-tenant data leakage.**

**Auth layer (Phase 6 only):**
- Currently: localhost always trusted (Desktop Mode)
- Phase 6: JWT-based auth, tenant isolation, per-user RBAC
- OAuth2 login for non-Kato users

**Infrastructure shift:**
- Phase 1–5: SQLite, local only
- Phase 6: Migrate to PostgreSQL, Docker Compose, reverse proxy (Caddy/nginx)
- Cloudflare tunnel already configured — extend for multi-tenant domains
- Consider Fly.io or Railway for managed hosting

**Pricing model concept:**
- Starter ($49/mo): 1 pipeline, 500 contacts, basic comms
- Professional ($149/mo): Unlimited pipelines, SMS/email automation, Masha voice
- Enterprise ($399/mo): White-label, Clover POS, custom integrations

---

## Integration Reference

### Masha (Retell Voice Agent) — Phase 3
```
Retell calls end → POST to /communications/inbound
{
  "channel": "voice",
  "from_number": "+17185551234",
  "content": "[Retell transcript summary]",
  "metadata": {
    "call_id": "...",
    "duration_seconds": 142,
    "sentiment": "positive",
    "appointment_confirmed": true,
    "retell_call_id": "..."
  }
}
```
Auto-creates contact if phone not found. Logs call summary as activity.

### Clover POS — Phase 5
```
Clover webhook → GHS middleware → POST /contacts/{id}/payment
{
  "amount": 245.00,
  "clover_order_id": "ABC123",
  "items": [{"name": "Event Deposit", "price": 245.00}]
}
```
Middleware does phone/email lookup to find contact_id before forwarding.

### Twilio Inbound SMS — Phase 2
```
Twilio webhook (POST) → GHS bridge → POST /communications/inbound
{
  "channel": "sms",
  "from_number": "+17185551234",
  "content": "Message body from Twilio"
}
```

---

## Open Items (Phase 1 Gaps)

1. **Deal creation UI** — currently deals created via API only; Phase 2 adds "+ Deal" button in kanban header
2. **Contact edit form** — panel shows contact but can only update stage/notes; Phase 2 adds full edit form
3. **Bulk import UI** — GOJ import via button works; Phase 2 adds CSV import for BBG
4. **Real calendar data** — Phase 1 calendar shows sample events; Phase 3 wires to appointments table
5. **Inbox reply** — SMS/email reply boxes are placeholders; Phase 2 connects Twilio + Gmail
6. **Authentication** — localhost is always trusted (Desktop Mode); Phase 6 adds JWT for multi-user

---

*Updated by Hermes · June 4, 2026 · Phase 1 complete*
