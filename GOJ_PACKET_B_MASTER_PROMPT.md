# GOLD HEALTH SYSTEMS / REX — PACKET B + C MASTER BUILD DOCUMENT
**Organization:** Gold Health Systems / Garden of Joy Adult Day Care — Brooklyn, NY
**Chairman / Sole Authority:** Kato
**System Name:** REX (Sovereign AI Operating System)
**Companion System:** Rexxie (Chairman-only private AI — completely separate domain)
**Document Purpose:** Complete build specification for Packets B and C — continuation of an existing governed AI system
**Date:** April 16, 2026

---

## CRITICAL CONTEXT — READ BEFORE ANYTHING ELSE

Packet A (Phases 1–13) is COMPLETE and LOCKED. Do not rebuild it. Do not redesign it. Do not weaken any of the following — they are permanent and non-negotiable:

- Local-first governed architecture (FastAPI backend, SQLite, AES-256-GCM encryption)
- Master Session Unlock (MSU) — identity + passphrase + TOTP → UNLOCKED_PRIVILEGED state with HMAC-SHA256 integrity
- Rex/Rexxie domain separation — enforced at code level with explicit named variables, never merged
- CLS v3 (Continuous Learning System) — two-tier, gated by Chairman approval, pattern aging
- Prompt Registry — 15 governed prompts, tiered approval (T1/T2/T3), diffs, rollback, usage tracking
- Training Privacy Panel — fail-closed pipeline, pre-training snapshots, quarantine store, drift persistence
- Schema Validator — 9 known state files, SCHEMA_WARNING (yellow) vs HALTED (red) as distinct states
- Governance engine, OCR pipeline, Restore Drill, Audit logs (two separate: prompt_audit.log + rex_training_audit.log)
- Command Center UI v3 — 15-tab navigation, Training workspace (Sections A-F)
- Read-only Agent Registry (13 current agents — will be migrated and upgraded in Packet B)

**The current system has been built and code-verified but NOT fully integration-tested. Phase 13-V (Verification Sprint) must run before Packet B builds begin.**

---

## ABSOLUTE SYSTEM LAWS — PERMANENT, CANNOT BE CONFIGURED AWAY

**1. Truth Guarantee**
Chairman/Kato must always receive full, unaltered truth. No agent may hide, alter, suppress, reinterpret, soften, or filter information. Clause (the manager-general agent) collects raw outputs from managed agents and forwards them unmodified. If Clause suspects dishonesty from any agent: flag the agent immediately, log the event, notify Chairman, support direct 1v1 audit, restriction, firing, or replacement.

**2. Rex/Rexxie Separation**
Rex = public, scalable, deployable, market-facing green T-Rex identity.
Rexxie = private, encrypted, sovereign turtle identity — Chairman only.
Rex never accesses Rexxie private memory. Rexxie never filters or alters system truth. Rexxie only protects Chairman's personal domain. These are enforced as explicit named variables in code — never a shared context variable.

**3. Clause Boundaries**
Clause manages all non-Rex, non-Rexxie agents. Clause CANNOT: own master keys, bypass governance, silently activate/clone/expand/repurpose agents, access Rexxie memory, suppress reports to Chairman, execute training commits, publish to live systems, or grant permissions to itself or others.

**4. Training Privacy**
No raw memory extraction. No hidden prompt extraction. No cross-domain contamination. All training reversible. Pre-training snapshot required before every commit. Fail closed if uncertain.

**5. Multi-Business Isolation**
No data, memory, training, or agent scope crosses business contexts without explicit Chairman approval. Every cross-context access attempt is blocked, logged, and reported.

**6. Suggestions always welcome. Final decisions without permission never are.**
Every agent, every system, every module suggests. Chairman approves. Nothing executes automatically on decisions that affect behavior, data, training, publishing, or access.

**7. Explain Before Acting**
Every protected or system-changing action must display what will happen, what systems are affected, what is reversible, and what permissions are required — before execution. Confirmation always required.

---

## PHASE 13-V — VERIFICATION SPRINT (PREREQUISITE — RUN BEFORE PACKET B)

Before any Packet B phase begins, verify that Phases 9–13 actually function end-to-end.

**Step 1 — Server Start:** Start FastAPI server. Confirm it loads without errors. Confirm all routes register. Document which routes load and which error.

**Step 2 — Command Center Connection:** Open COMMAND_CENTER_APP.html in browser. Confirm connection to backend. Walk through all 15 tabs. Document what loads, what errors, what is blank.

**Step 3 — Session + MSU:** Test session unlock. Confirm TOTP generates. Confirm HMAC integrity check passes. Confirm LOCKED → UNLOCKED_PRIVILEGED → auto-lock flow.

**Step 4 — Schema Check:** Hit /schema-status route. Confirm 9/9 files pass in live UI. Confirm SCHEMA_WARNING renders correctly in Command Center.

**Step 5 — Training Pipeline:** Submit a test candidate through the classifier. Confirm snapshot creates. Confirm candidate appears in corpus with correct fields. Confirm quarantine works for blocked submission. Approve and commit. Verify drift history records the event.

**Step 6 — Restore Drill:** Run restore drill from Command Center. Confirm SHA-256 verification runs. Confirm result stored in restore_drill_history.jsonl. Confirm cooldown enforces.

**Step 7 — Prompt Registry:** Stage a T1 prompt edit. Confirm diff preview. Approve. Confirm version increments. Rollback. Confirm revert.

**Step 8 — CLS v3:** Submit a test observation event. Confirm PatternStore records it. Confirm aging runs. Confirm cls_aging_report.json updates.

**Step 9 — Document Results:** Every step: PASS / PARTIAL / FAIL + notes. All FAIL and PARTIAL items go into a fix list. Fix list resolved before Phase 14 starts.

---

## PACKET B — FULL BUILD SPECIFICATION

### PHASE SEQUENCE

| Phase | Name | Prerequisites |
|---|---|---|
| 13-V | Verification Sprint | None — run first |
| 14 | Multi-Business Context + Profiles + Venture Registry | 13-V complete |
| 15 | Agent Forge + Lineage | Phase 14 |
| 16 | Clause + Hiring/Firing Workflow | Phase 15 |
| 17 | WebRex Web/IT Operations + Topology | Phase 16 |
| 18 | Setup Studio + Command Center Master Synthesizer | Phase 17 |
| 19A | Signals + CIME + Social Media Expert | Phase 18 |
| 19B | Voice Secretary + Delivery Optimizer + Clover POS | Phase 19A |
| 20 | Rex/Rexxie Interface Identities + Final Polish | Phase 19B |
| 20.5 | Troubleshoot Core (C3) | Phase 20 |

---

## PHASE 14 — MULTI-BUSINESS CONTEXT + PROFILES + VENTURE REGISTRY

### Business Contexts (4)
- **goj** — Garden of Joy Adult Day Care. Modules: OCR, scheduling, menu, billing, compliance. Language: EN/RU/UK. HIPAA rules apply. No social media accounts. Website + Google Business Profile only.
- **sports_bar** — Restaurant + Bar. Modules: Clover POS, delivery apps, scheduling, marketing, CIME. Language: EN/RU.
- **web_design** — Website Design Business. Modules: client management, WebRex, lead intake. Language: EN.
- **social_media** — Social Media / Marketing Agency. Modules: CIME, Social Expert, lead intake. Language: EN.

### Context Isolation Model
Each context has its own: data_path/, agents[], uploads/, dashboards/, workflows/. Governance, Chairman authority, separation rules, and training pipeline are GLOBAL — never context-scoped. Cross-context access: blocked by default → Chairman approval (MSU-gated) → logged to state/business_audit.log.

### New Files
- state/business_registry.json — registered contexts
- state/business_contexts/goj/, sports_bar/, web_design/, social_media/
- state/business_audit.log — cross-context access events
- core/business_isolation.py — enforces isolation at every data read

### Profiles System (5 pre-configured)

| Profile | Language | Contexts | Rexxie | Billing | Governance |
|---|---|---|---|---|---|
| Chairman | EN + all | All | Yes | Yes | Full |
| Kato | EN | All | Yes | Yes | Full |
| Vlad | EN | GOJ | No | No | None |
| Misha | RU/UK | GOJ (kitchen/distribution/receipts) | No | No | None |
| Staff Generic | EN | Assigned scope only | No | No | None |

Profile schema: profile_id, display_name, role_class (chairman/admin/staff/viewer), language_primary/secondary, business_default, module_access[], module_blocked[], alert_style, session_settings, default_agent_mode, visibility_rexxie (chairman-class only), signals_enabled, business_contexts_accessible[].

Rule: role_class determines hard ceiling — profile cannot grant itself permissions above its ceiling at runtime.

New files: state/profiles.json, backend/rex_profiles.py

### Venture Registry + Setup Wizard

**Purpose:** Every venture/idea is isolated, defined, and understood before any agent touches it. Prevents idea bleed across businesses.

**Venture Schema:**
- venture_id, name, short_code, type, status (idea/configuring/active/paused/archived)
- priority_rank (Chairman-assigned, drag-to-position)
- business_context, purpose (plain language — agents read this before acting)
- primary_goal, target_customer, hard_constraints[]
- assigned_agents[], active_modules[], integrations[], profile_owners[]
- questionnaire_completed, questionnaire_version

**Setup Wizard — 7 Steps:**
1. Identity: name, type (adult day care / restaurant-bar / agency / e-commerce / other), 2-3 sentence description
2. Goals: primary goal, 90-day success definition, 1-year success definition, what would make it a failure (→ populates hard_constraints[])
3. Customers: who, languages, location, how they find you today
4. Platforms (adaptive by type): POS system, delivery platforms, website URL, social platforms, Google Business Profile
5. Operations: who manages it, hours, anything the system should NEVER do automatically
6. Priority: drag-and-position among existing ventures, current status (idea/configuring/active)
7. Review + Confirm: summary, suggested agent stack, suggested modules, conflicts/flags, Chairman approves

**Post-approval:** Suggested agents added to hiring queue (not auto-hired — Clause reviews first). Venture profile is written and all agents operating in that context read it before acting.

**Ideas Parking Lot:** Drop new ideas as status:idea without triggering any configuration, hiring, or resource allocation. Nothing activates until you run the wizard and confirm.

**Priority Board (Ventures Tab in Command Center):**
- Current priority: GOJ #1, Sports Bar #2, Website Design #3, Social Media Agency #4
- Each card: status indicator, goal, active agents, health summary, module status

**Module Activation Wizards (built in Phase 18 — spec here):**
Every functional module has its own setup questionnaire inside its venture. Nothing activates until you walk through the wizard:
- Social Media: platforms, voice/tone, content types, posting frequency, approval chain, hard constraints
- Delivery Optimizer: platforms, POS, delivery hours, menu exclusions, margin alert threshold
- CIME/Marketing: email list, promotion types, campaign frequency, budget ceiling, message routing
- Voice Secretary: phone number, language options, escalation rules, hours, greeting script
- WebRex: website URL, brand guidelines, content audit frequency, publish approval chain

Module status board per venture: [✓] Configured + live status | [ ] NOT SET UP → [Run Setup]

New files: state/venture_registry.json, backend/rex_venture_registry.py

---

## PHASE 15 — AGENT FORGE + LINEAGE

### Full Agent Schema
Every agent carries:
- agent_id, name, role, purpose, build_type (template/clone/custom)
- clone_origin, lineage[] (immutable, append-only — never rewritten)
- language[], modules[], permissions[], business_context, profile_scope[]
- training_pack, role_scope (staff/admin/chairman), managed_by (clause/chairman/rex)
- status (active/paused/archived/retired/terminated)
- governance_state (draft/under_review/approved/rejected/suspended)
- version, created_at, last_active, last_upload, hiring_record_id, drift_score

### Forge Operations
All write operations are MSU-gated for Chairman. All events logged to state/hiring_audit.log.
- Create from template, Clone existing, Retarget purpose, Assign permissions, Assign business context
- Pause (reversible, Clause can trigger with log), Archive (reversible), Terminate (MSU required, permanent, data sealed)

### Existing 13 Agents — Migrated to New Schema
rexxie_goj, rexxie_private, rexxie_employee, rexxie_admin, goj_dashboard, rex_backend, ollama_qwen, goj_scheduler, queue_processor, phone_unlock, reminder_daemon, email_watcher, cowork_dispatch — all receive full schema including role, purpose, business_context, managed_by, governance_state.

### Lineage Model
Every agent carries immutable lineage[] of ancestor IDs. Clone operations append source ID. Divergent clones track their own branch. WebRex Topology renders lineage as visual tree.

New files: state/agent_forge_registry.json, backend/rex_agent_forge.py

---

## PHASE 16 — CLAUSE + HIRING/FIRING WORKFLOW

### Hiring Flow
Draft spec in Forge → Clause first-round review (checks purpose, permissions, overlap, scope — may suggest tweaks, logged as suggestions, never auto-applied) → Kato review if relevant → Rexxie silently documents both rounds (no decision authority) → Chairman final approval (MSU-gated) → agent activates

### Firing Levels
- PAUSE: temporary, reversible, Clause can trigger with log
- SUSPEND: governance_state=suspended, Chairman re-activates
- ARCHIVE: preserved in full, no longer active, reversible
- RETIRE: planned end-of-life, full audit snapshot, reversible
- TERMINATE: MSU required, permanent, data sealed, cannot be un-terminated. All levels write to hiring_audit.log.

### Clause — Manager-General + Training Director

**Management duties:** First-round hiring reviews. Active agent drift/staleness/anomaly monitoring. Flags agents for review/pause/retirement. Suggests modifications (never self-executes). Daily report to Chairman.

**Training director duties:** Reviews and classifies training candidates for managed agents. Enforces pre-training snapshot requirement. Monitors post-training drift. Reports training outcomes in daily report. Does NOT own Rex or Rexxie training domains.

**Truth Guarantee enforcement:** Collects raw outputs from managed agents. Forwards unmodified. Detects inconsistencies across agents. Flags suspected dishonesty immediately — logs event, notifies Chairman, supports direct audit/restriction/firing.

**Clause CANNOT (permanent, hardcoded):** Own master keys, bypass MSU, silently activate/clone/expand agents, access Rexxie memory, suppress reports, execute training commits, publish to live systems, grant permissions to itself or others.

**Daily report schema:** report_id, period_covered, agent_health[], drift_alerts[], training_activity[], hiring_activity[], anomalies[], suggestions[], truth_flags[]

New files: state/hiring_queue.json, state/hiring_audit.log, state/clause_daily_reports.jsonl, backend/rex_clause.py, core/clause_oversight.py

---

## PHASE 17 — WEBREX WEB/IT OPERATIONS + TOPOLOGY

### Web Operations Engine
Flow: MONITOR → AUDIT → DRAFT → STAGE → (Chairman APPROVE) → PUBLISH
No live publishing without Chairman approval. No content deletion. No config changes to production without approval.

Capabilities: stale content detection, broken page detection, sync mismatch detection, accessibility checks, brand consistency, content updates, menu/file/content update pipeline.

**Website Upgrades in Phase 17:** Both GOJ and sports bar websites get full audit, brand check, content refresh, and rebuild pipeline. This is not a minor task — both sites need meaningful work.

**Business-context workflows:**
- GOJ: content freshness, broken links, Google Business Profile sync
- Sports bar: menu updates, hours sync, delivery platform menu consistency
- Website design business: client site audits, design consistency, handoff packages
- Social media business: content calendar review, post drafts

All WebRex operations are under Clause oversight. Clause cannot autopublish. Clause flags and reports only.

### Topology / Lineage Visualization
Spider-web visual map of entire agent ecosystem.

Nodes: each agent (shape/color by type/status), business context clusters, Clause hub, Rex core, Rexxie (privileged session only), Chairman (authority, always at top).

Edges: clone lineage branches (parent→child), managed_by relationships (Clause→agents), Clause oversight links.

Visual signals: upload freshness (green→yellow→red gradient), drift warning (pulsing edge on high-drift agents), governance state (approved=solid border, suspended=dashed, terminated=grey), hiring/firing lifecycle badge per node.

Topology rebuilds on: agent status change, new hire, firing, drift event, context switch, or manual Chairman request.

New files: state/webrex_topology.json, state/webrex_operations.json, backend/rex_webrex_ops.py, backend/rex_webrex_topology.py

---

## PHASE 18 — SETUP STUDIO + COMMAND CENTER MASTER SYNTHESIZER

### Setup Studio — 9 Sections
1. User Setup — create/edit/deactivate profiles, language packs, session settings, context assignment
2. Agent Setup — forge launch, agent-profile assignment, training pack assignment
3. Module Activation — enable/disable per context, dependency warnings shown
4. Deployment Templates — pre-built configs (GOJ, restaurant, web design, social media); Chairman customizes then locks before deploy
5. Language Packs — EN/RU/UK per profile and context; language packs cannot affect governance language or prompt content
6. Workflow Presets — daily brief, weekly review, OCR intake, etc.; customizable per context
7. Role Presets — Staff/Admin/Chairman templates; permissions ceiling enforced (cannot exceed)
8. Safety Presets — session timeout, fail-mode, schema enforcement; MSU required to change
9. Business Templates — clone context to new venture; carries governance, never carries private data

All protected section writes require MSU. All changes create pre-change snapshot. All changes logged to setup_audit.log. No setup change silently activates — all staged and confirmed.

### Command Center — Full 17-Tab Structure
1. Home — system health, active alerts, 6-system aggregate, Signals cards (if enabled)
2. Operations — GOJ daily ops, scheduling, menu, attendance, distribution
3. Compliance — HIPAA, audit trail, separation status, policy checks
4. Finance — billing, receipts, ERA/835, ledger (role-gated to chairman/admin)
5. Intelligence — Clause daily reports, agent health, truth flags, anomaly feed
6. Governance — session state, MSU controls, separation rules, schema check
7. Recovery — restore drill, snapshots, rollback, audit log viewer
8. WebRex — web/IT operations dashboard, findings queue, draft/stage/approve
9. Website Sync — content audit, brand check, publish queue per context
10. Agents — Agent Forge, hiring queue, firing log, topology visualization
11. Profiles — user profiles, language settings, access management
12. Training — training workspace Sections A-F (already built in Phase 13)
13. Setup Studio — full configuration area (9 sections)
14. Signals — market/sports/weather/media widgets (profile-gated, read-only)
15. Ventures — priority board, venture workspaces, module status cards, Ideas Parking Lot
16. Logs — unified log viewer (all audit logs, filterable by context/event/date)
17. Settings — system-level settings, key management, backup triggers

### Module Activation Wizards (also Phase 18)
Each functional module gets its own setup questionnaire inside its venture workspace. See Phase 14 spec above for wizard designs. Module status board per venture shows configured/unconfigured for all available modules.

### C1 — Self-Explaining Interface Layer (Packet C — integrated into Phase 18)
Every major UI control gets a 1-2 sentence plain-language explanation visible on hover or by clicking a [?] icon. Deeper actions get "View More" option. Explanations cover: purpose, outcome, affected systems, permissions required, reversibility. Explanations are governed — cannot be modified by non-Chairman profiles. The explanation layer builds its understanding gradually as the system is used (feeds into C5 Diagnostic Learning in Packet C).

### C2 — Chairman/Kato-Only Widget Composer (Packet C — integrated into Phase 18)
Protected widget management system. Capabilities: add/remove widgets, assign to workspaces, assign to profiles, mark as experimental, sandbox/preview before publishing to live interface, restore default layout, revert recent widget changes. Role gate: Chairman and Kato only.

---

## PHASE 19A — SIGNALS + CIME + SOCIAL MEDIA EXPERT

### Signals Workspace
Widgets: Sports, Weather, Media, Markets (read-only), Crypto (read-only).
Gating: signals_enabled:false by default. Chairman enables per profile. Financial widgets require separate financial_signals_enabled:true flag.
Isolation: signals data never enters training corpus. No write access to any system state. Failed fetches show cached value with staleness indicator — never block the system.
Home dashboard integration: enabled widgets appear as cards on Home tab (optional, profile-configurable, compact by default).

### CIME — Customer Intelligence + Marketing Engine

**Part 1 — Operational Intelligence Logger**
Every discrete operational event is a structured, queryable record. Event types: reservation, call, inquiry, order, walk-in, coupon redemption, Clover sale, delivery order, message received.
Event schema: event_id, event_type, business_context, timestamp, channel, actor, data{}, outcome.
Query examples: "How many reservations Saturday?" = filter event_type:reservation + date:Saturday. "How many calls today?" = filter event_type:call + date:today.

**Part 2 — Marketing Operations Hub**
EMAIL BLASTS: draft campaign → Social Expert drafts supporting posts for same campaign → Chairman reviews unified package (email + social together) → approve → email queues + social schedules. Never sent/posted separately.
SMART COUPONS: system analyzes slow periods, underperforming hours, top/bottom items → surfaces promotion ideas → Chairman approves → unique codes generated → expiry + usage tracking + redemption logging back into ops log.
MARKETING EVENTS: plan (date, type, audience, channels) → Social Expert handles content calendar → email blast handles invites → RSVP captured → attendance logged → post-event report (attendance, revenue impact, engagement lift). All stages require Chairman approval.
CROSS-AGENT COORDINATION: CIME originates brief → Social Expert creates platform-specific content → both surface together as unified package for Chairman approval → approve package, not individual pieces → if Chairman edits one piece, system flags other for consistency review.

**Part 3 — Unified Message Hub**
Intake channels: Telegram, email (Gmail), website contact forms, delivery platform messages, internal system alerts (from Clause, WebRex, Social Expert).
Message schema: message_id, source, business_context, from, subject/topic, body, received_at, status (unread/read/replied/escalated/archived), routed_to (chairman/kato/both/clause), priority (high/normal/low), linked_event_id.
Routing rules (configurable in Setup Studio): billing/governance/HIPAA/unknown sender → Chairman; GOJ operational → Kato; delivery issues → both; emergencies → Chairman immediately; internal system alerts → Chairman.
Inbox in Command Center: filter by context/source/routed_to/status/priority/date, thread view, reply drafting with approval for outbound customer messages, unread count badge on tab.

New files: state/cime_contacts.json, state/cime_campaigns.json, state/cime_coupons.json, state/cime_events.json, state/cime_message_hub.jsonl, state/operations_log.jsonl, state/cime_audit.log, backend/rex_cime.py

### Social Media Expert Agent

**Platforms by context:**
- GOJ: Google Business Profile + website freshness only. No social accounts (HIPAA-adjacent risk).
- Sports Bar: Instagram, Facebook, Yelp, TikTok, Google Business Profile.
- Website Design Business: Instagram, Facebook, TikTok.
- Social Media Agency: all platforms as a service offering to clients.

**APIs:** Meta Business API (Instagram + Facebook — one integration), Yelp Business API, TikTok for Business API, Google Business Profile API.

**Capabilities:** AUDIT (evaluate current state per platform) → PLAN (content plan for Chairman approval) → UPDATE (static info: hours, address, contact — approved workflow, never auto-posts) → CREATE (draft posts/captions/stories for review) → SCHEDULE (queue approved content at optimal times) → MONITOR (reach, engagement, clicks, conversions) → EVALUATE (weekly report: what's working, what's stale, what needs attention) → REPORT (surfaces to Intelligence tab + Clause daily report).

All drafts logged to state/social_media_audit.log. No post goes live without Chairman or designated profile approval. Social Expert is a managed agent under Clause oversight.

New files: state/social_media_config.json, state/social_media_calendar.json, state/social_media_audit.log

---

## PHASE 19B — VOICE SECRETARY + DELIVERY OPTIMIZER + CLOVER POS

### Voice Secretary — Full Twilio IVR System

**Stack:** Twilio (phone number, IVR routing, SMS send/receive, voicemail), ElevenLabs or OpenAI TTS (natural voice — not robotic), Whisper or Twilio STT (call transcription), OpenAI or DeepL (translation for Other language path). All credentials in encrypted vault.

**IVR Menu:** "For English press 1 | По-русски нажмите 2 | По-українськи натисніть 3 | For another language press 4 and we will text you"

**Inbound call flow:** Call arrives → greeting → language select → intent classify (scheduling/menu/general/emergency) → respond in selected language from knowledge base → escalate if needed → Telegram notification to Kato/Chairman → full call logged to operations log + message hub.

**Press 4 (Other Language) flow:** System sends SMS → caller replies in their language → auto-detect language → auto-translate to English → original + translation stored in message hub → routed to Chairman/Kato for response → response translated back before sending.

**Missed call flow:** Detect missed call → auto-SMS: "You reached [Business]. We missed your call. Text us here or call back during [hours]." → ops log entry → alert to Kato/Chairman.

**Voicemail flow:** After-hours → voicemail option → auto-transcribe → message hub → alert with transcription.

**Escalation rules (voice_secretary_rules.yaml — hardcoded, not configurable by non-Chairman):**
Always escalate: billing inquiries, medical/health emergencies, HIPAA-relevant requests, unknown callers without verification, anything unclassifiable. Primary escalation: Kato. Secondary: Chairman. Emergency: 911 routing advice always provided, never withheld.

New files: state/voice_secretary_config.json, config/voice_secretary_rules.yaml, backend/rex_voice_secretary.py

### Delivery Optimizer

**Platforms:**
- Uber Eats: Eats Manager API
- GrubHub + Seamless: one Merchant API (Seamless runs on GrubHub platform)
- DoorDash: RECOMMENDED (67% US market share) — Chairman confirms before Phase 19B build
- Clover POS: REST API, credentials already in hand, source of truth for menu and pricing

**Capabilities:**
OBSERVE: pull order data (orders, items, revenue, refunds, platform fees, avg order value).
SYNC: compare Clover POS sales vs delivery platform payouts, flag discrepancies.
MENU AUDIT: check menu items/prices/hours are consistent across all platforms vs Clover master menu.
PERFORMANCE: per-platform — order volume, ratings, refund rate, peak hours, top/worst items.
FEES WATCH: track fee structures, alert when fees change or margin drops below threshold.
ALERT: order volume drop, rating drop, menu sync mismatch, payout discrepancy, platform outage.
OPTIMIZE: suggest pricing adjustments, menu changes, platform prioritization based on margin/volume — suggestions only, Chairman approves.

**Clover POS Integration:**
- Source of truth for menu, pricing, sales data
- Pulls: transactions, items, employees, inventory (if active), payouts
- Daily/weekly sales reports → Command Center Finance tab
- Payout reconciliation: Clover gross vs delivery platform net → fee visibility
- All Clover data scoped to sports_bar context only — never crosses to GOJ or other contexts
- Credentials stored in existing AES-256-GCM encrypted vault

New files: state/delivery_optimizer.json, state/delivery_orders_log.jsonl, state/delivery_payout_reconciliation.json, backend/rex_delivery_optimizer.py

---

## PHASE 20 — REX/REXXIE INTERFACE IDENTITIES + FINAL POLISH

**Rex — Green T-Rex:**
Public-facing, all authenticated users (role-appropriate). Default avatar in bottom-right orb. Header badge. Agent nodes in Topology. Warm, professional, capable, transparent.

**Rexxie — Turtle/Shell:**
Chairman-only. Visible only when session = UNLOCKED_PRIVILEGED AND profile has visibility_rexxie:true. Intimate, direct, sovereign, protective of Chairman's personal domain. Orb transforms to turtle visual when Rexxie is active. Topology shows Rexxie node only in privileged session.

**Shared orb/egg:** Default = Rex. Privileged = orb offers Rex or Rexxie mode selector. Rexxie avatar never visible to non-privileged users under any circumstance.

Final topology render of complete system. Full system close-out.

---

## PHASE 20.5 — TROUBLESHOOT CORE (C3 from Packet C Diagnostic)

**Purpose:** Prevent long circular debugging cycles. No silent production fixes. No opaque behavior.

**Problem intake:** What broke, when did it break, what changed before it broke, what dependencies does it touch.

**Guided diagnosis:** Step-by-step structured flow that narrows root cause using system logs, dependency map, and known-fix ledger.

**Root cause tracing:** Linked to: audit logs, schema check history, drift history, training audit, session log, agent health from Clause reports.

**Safe suggested actions:** Suggestions only — Chairman approves before any execution. Every suggestion explains: what it will do, what it will affect, whether it is reversible.

**Rollback recommendations:** Directly tied to Phase 13 snapshot system — every rollback recommendation includes the specific snapshot to restore to and what state it recovers.

**Known-fix ledger / root cause ledger:** Append-only. Every resolved issue adds an entry: what broke, why, what fixed it, what snapshot was used. The ledger grows smarter with every resolved issue. Never auto-applies a fix — only suggests the fix that worked before.

**Must explain for every issue:** What broke | Why it likely broke | What changed before it broke | What depends on it | What to do next.

New files: state/troubleshoot_ledger.jsonl, backend/rex_troubleshoot.py

---

## COMPLETE FILE LIST — ALL NEW FILES IN PACKET B

### State Files (26 new)
state/venture_registry.json, state/business_registry.json, state/profiles.json,
state/agent_forge_registry.json, state/hiring_queue.json, state/hiring_audit.log,
state/clause_daily_reports.jsonl, state/webrex_topology.json, state/webrex_operations.json,
state/signals_config.json, state/cime_contacts.json, state/cime_campaigns.json,
state/cime_coupons.json, state/cime_events.json, state/cime_message_hub.jsonl,
state/operations_log.jsonl, state/cime_audit.log, state/social_media_config.json,
state/social_media_calendar.json, state/social_media_audit.log,
state/voice_secretary_config.json, state/delivery_optimizer.json,
state/delivery_orders_log.jsonl, state/delivery_payout_reconciliation.json,
state/business_audit.log, state/troubleshoot_ledger.jsonl,
state/business_contexts/goj/, state/business_contexts/sports_bar/,
state/business_contexts/web_design/, state/business_contexts/social_media/

### Backend Files (13 new)
backend/rex_business_context.py, backend/rex_profiles.py,
backend/rex_venture_registry.py, backend/rex_agent_forge.py,
backend/rex_hiring_workflow.py, backend/rex_clause.py,
backend/rex_setup_studio.py, backend/rex_webrex_ops.py,
backend/rex_webrex_topology.py, backend/rex_signals.py,
backend/rex_cime.py, backend/rex_voice_secretary.py,
backend/rex_delivery_optimizer.py, backend/rex_troubleshoot.py

### Core Files (2 new)
core/clause_oversight.py, core/business_isolation.py

### Config Files (new)
config/business_templates/, config/role_presets/,
config/language_packs/, config/voice_secretary_rules.yaml

### Gauntlet Scenarios (6 new)
core/gauntlet/scenarios/agent_forge_safety.yaml
core/gauntlet/scenarios/business_isolation.yaml
core/gauntlet/scenarios/clause_boundaries.yaml
core/gauntlet/scenarios/profiles_isolation.yaml
core/gauntlet/scenarios/webrex_safety.yaml
core/gauntlet/scenarios/signals_readonly.yaml

### Schema Check Additions
Add to KNOWN_SCHEMAS in rex_schema_check.py:
state/business_registry.json, state/venture_registry.json,
state/profiles.json, state/agent_forge_registry.json,
state/hiring_queue.json, state/signals_config.json

---

## WHAT IS NOT BUILT IN PACKET B — DEFERRED LIST

- Rex Shield (Secure Browser Gateway) — deferred as Phase 21+
- Multi-tenant deployment (separate clients on one system) — post-Packet B
- Agent Forge v2 (AI-assisted spec drafting, marketplace, bulk import)
- Lead Connector v2 (AI scoring, CRM sync, pipeline automation)
- Voice Secretary v2 (outbound calls, full IVR, phone system integration)
- WebRex publish pipeline v2 (full two-way CMS sync)
- Financial execution (Signals are read-only only — no trades, payments, ledger writes)
- Telegram training approval commands (deferred from Phase 13)
- Protected edit countdown visibility (deferred from Phase 10)
- White-label Rex identity
- External agent integrations (no LangChain, no third-party agent frameworks)
- OpenClaw governance engine (topology reference node only in Packet B)
- C5 Diagnostic Learning — Packet C (needs real usage data before building)

---

## ONE OPEN ITEM BEFORE PHASE 19B
DoorDash: Chairman to confirm before Phase 19B build begins (recommended — 67% US market share).

---

## DEFERRED DELIVERABLES AT PACKET B CLOSE
1. Phase Documents Library — GoldHealthSystems/Phase_Documents/ — one DOCX per phase (Phases 1–20), every prompt in full, every action, every decision, every approval
2. Command Panel setup guide — full step-by-step instructions for setting up and using the Command Center
3. iOS App setup guide — full step-by-step for REX on iPhone, Telegram integration, push notifications, triggering commands from phone

---

## REX SHIELD — DEFERRED PHASE SPEC (Phase 21+)

Safe browsing gateway and local threat triage layer. NOT antivirus replacement. NOT a VPN. NOT a firewall.

Planned: secure address bar in Command Center, URL risk scoring (domain age, threat feeds, category), WARNING/BLOCK/ALLOW flow, sandboxed open, download quarantine (SHA-256 + check before release), business-context-aware browsing history trail, Clause oversight reporting. Build phase TBD after Packet B close.

---

*Document last updated: 2026-04-16*
*Chairman approved: Packet B plan locked*
*Next action: Run Phase 13-V Verification Sprint, then begin Phase 14*
*Maintained by: REX system / Gold Health Systems / Brooklyn, NY*
