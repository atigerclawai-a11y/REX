# PACKET B — FULL LOCKED BUILD PLAN
## Gold Health Systems / REX Second Brain
**Planning Date:** 2026-04-16
**Foundation:** Phase 13 complete and locked
**Authority:** Chairman Kato — final approval on all phases before build begins
**Status:** APPROVED FOR BUILD — AWAITING PHASE 14 START SIGNAL

---

## PHASE SEQUENCE

| Phase | Name | Key Deliverables |
|---|---|---|
| 14 | Multi-Business Context + Profiles + Venture Registry | business_registry.json, venture_registry.json, profiles.json, context isolation, Setup Wizard, Ventures tab, Ideas Parking Lot, anti-bleed venture profiles |
| 15 | Agent Forge + Lineage | agent_forge_registry.json, forge engine, clone/template/create, lineage tracking, existing 13 agents migrated to new schema |
| 16 | Clause + Hiring/Firing Workflow | Clause engine, truth guarantee enforcement, hiring workflow (Clause→Kato→Chairman), firing levels (pause/suspend/archive/retire/terminate), daily reports, training director formalization |
| 17 | WebRex Web/IT + Topology | Web operations engine (monitor/audit/draft/stage/approve), topology/lineage spider-web visualization, GOJ + sports bar website upgrades, Clause oversight integration |
| 18 | Setup Studio + Command Center Master Synthesizer | Setup Studio (9 sections), Command Center expanded to 17 tabs, Module Activation Wizards per-module per-venture (Social Media / Delivery / CIME / Voice / WebRex etc.) listed in priority order |
| 19A | Signals + CIME + Social Media Expert | Customer Intelligence + Marketing Engine (ops logger, email blasts, promotions, smart coupons, marketing events, unified message hub), Social Media Expert (Meta/Yelp/TikTok/Google APIs), cross-agent coordination, Signals workspace |
| 19B | Voice Secretary + Delivery Optimizer + Clover POS | Twilio IVR (EN/RU/UK/Other), natural TTS voice, missed call + auto-SMS + voicemail transcription, Delivery Optimizer (Uber Eats/GrubHub/Seamless/DoorDash TBC), Clover POS sync + reconciliation |
| 20 | Rex/Rexxie Interface Identities + Final Polish | Green T-Rex Rex identity, turtle/shell Rexxie identity, orb/egg access point, topology final render, full system close-out |

---

## COMPONENT DETAILS

### A. VENTURE REGISTRY + SETUP WIZARD (Phase 14)

**Purpose:** Every venture/idea is isolated, understood, and configured before any agent touches it. Prevents idea bleed across businesses.

**Venture Record Schema:**
- venture_id, name, short_code, type, status, priority_rank, business_context
- purpose (plain language — agents read this before acting)
- primary_goal, target_customer, hard_constraints[]
- assigned_agents[], active_modules[], integrations[]
- profile_owners[], questionnaire_completed

**Setup Wizard — 7 Steps:**
1. Identity (name, type, description in 2-3 sentences)
2. Goals and success metrics (90 days + 1 year)
3. Target customers (demographics, language, location, how they find you)
4. Platforms and presence (website, social, POS, delivery — adaptive by type)
5. Operations (who manages, hours, hard constraints — most important question)
6. Priority ranking (drag-and-position among existing ventures)
7. Review + Confirm (summary, suggested agent stack, suggested modules, Chairman approves)

**Priority Board in Ventures Tab:**
- Current priority order: GOJ (#1) → Sports Bar (#2) → Website Design (#3) → Social Media Agency (#4)
- Each card: status indicator, goal, active agents, health summary
- Ideas Parking Lot: drop ideas without activating anything — sits until you're ready

**Module Activation Wizards (Phase 18):**
Each functional module has its own setup questionnaire inside its venture:
- Social Media Agent setup: platforms, voice/tone, content types, posting frequency, approval chain, hard constraints
- Delivery Optimizer setup: platforms, POS connection, delivery hours, menu exclusions, margin alert threshold
- CIME/Marketing setup: email list, promotion types, campaign frequency, budget ceiling, message routing
- Voice Secretary setup: phone number, language options, escalation rules, hours, greeting script
- WebRex setup: website URL, brand guidelines, content audit frequency, publish approval chain

**Module status board per venture:**
[✓] Configured + status | [ ] NOT SET UP → [Run Setup]

---

### B. MULTI-BUSINESS CONTEXT LAYER (Phase 14)

**4 Business Contexts:**
- goj — Garden of Joy Adult Day Care (modules: OCR, scheduling, menu, billing, compliance)
- sports_bar — Restaurant + Bar (modules: Clover, delivery, scheduling, marketing)
- web_design — Website Design Business (modules: client management, WebRex, lead connector)
- social_media — Social Media / Marketing Agency (modules: CIME, social expert, lead connector)

**Isolation Model:**
- Each context has own: data_path, agents[], uploads/, dashboards/, workflows/
- Shared globally: governance, Chairman authority, separation rules, training pipeline, audit logs
- Cross-context access: blocked by default → Chairman approval → logged to business_audit.log
- Context switch: logs event, full UI reload from scoped data path, no prior context data in memory

**New Files:**
- state/business_registry.json
- state/business_contexts/goj/, sports_bar/, web_design/, social_media/
- state/business_audit.log
- core/business_isolation.py

---

### C. PROFILES SYSTEM (Phase 14)

**Pre-configured Profiles:**
- Chairman: EN+all languages, all contexts, Rexxie visible, full governance
- Kato: EN, GOJ+all, Rexxie visible, full governance
- Vlad: EN, GOJ, no Rexxie, no billing, no governance
- Misha: RU/UK, GOJ (kitchen/distribution/receipts only), no Rexxie, no billing, no governance
- Staff Generic: EN, assigned scope only, no Rexxie, no billing, no governance

**Profile Schema:** profile_id, display_name, role_class, language_primary/secondary, business_default, module_access/blocked, alert_style, session_settings, default_agent_mode, visibility_rexxie, signals_enabled, signals_widgets, business_contexts_accessible

**Governance:** role_class determines ceiling — profile cannot grant itself permissions above its ceiling. visibility_rexxie only settable on chairman-class profiles.

**New Files:** state/profiles.json, backend/rex_profiles.py

---

### D. AGENT FORGE + LINEAGE (Phase 15)

**Full Agent Schema:**
- agent_id, name, role, purpose, build_type (template/clone/custom)
- clone_origin, lineage[] (immutable append-only)
- language[], modules[], permissions[], business_context, profile_scope[]
- training_pack, role_scope, managed_by, status, governance_state
- version, created_at, last_active, last_upload, hiring_record_id, drift_score

**Forge Operations (all MSU-gated for Chairman):**
Create / Clone / Retarget / Assign Permissions / Assign Context / Pause / Archive / Terminate

**13 Existing Agents Migrated:** rexxie_goj, rexxie_private, rexxie_employee, rexxie_admin, goj_dashboard, rex_backend, ollama_qwen, goj_scheduler, queue_processor, phone_unlock, reminder_daemon, email_watcher, cowork_dispatch — all get full schema applied.

**New Files:** state/agent_forge_registry.json, backend/rex_agent_forge.py

---

### E. HIRING / FIRING WORKFLOW (Phase 16)

**Hiring Flow:** Draft spec → Clause first-round review (suggests tweaks, checks scope/permissions) → Kato review if applicable → Rexxie silently documents → Chairman final approval (MSU-gated) → agent activates

**Firing Levels:**
- PAUSE: temporary, reversible, Clause can trigger
- SUSPEND: governance_state=suspended, Chairman re-activates
- ARCHIVE: preserved, status=archived, no longer active
- RETIRE: planned end-of-life, full audit snapshot
- TERMINATE: MSU required, permanent, data sealed, cannot be un-terminated

**New Files:** state/hiring_queue.json, state/hiring_audit.log, backend/rex_hiring_workflow.py

---

### F. CLAUSE — MANAGER-GENERAL + TRAINING DIRECTOR (Phase 16)

**Responsibilities:**
MANAGEMENT: first-round hiring reviews, agent drift/staleness monitoring, flags agents for review, suggests modifications (never self-executes), daily report to Chairman
TRAINING: reviews/classifies managed-agent training candidates, enforces pre-training snapshots, monitors post-training drift, reports training outcomes
TRUTH GUARANTEE: collects raw outputs, forwards unmodified, detects inconsistencies, flags suspected dishonesty immediately

**Hard Limits (permanent — cannot be configured away):**
Cannot: own master keys, bypass MSU, silently activate/clone/expand agents, access Rexxie memory, suppress reports, execute training commits, publish to live systems, grant permissions to itself

**Daily Report Schema:** report_id, period_covered, agent_health[], drift_alerts[], training_activity[], hiring_activity[], anomalies[], suggestions[], truth_flags[]

**New Files:** state/clause_daily_reports.jsonl, backend/rex_clause.py, core/clause_oversight.py

---

### G. WEBREX WEB/IT + TOPOLOGY (Phase 17)

**Web Operations:** MONITOR → AUDIT → DRAFT → STAGE → (Chairman APPROVE) → PUBLISH
Capabilities: stale content detection, broken page detection, sync mismatch detection, accessibility checks, brand consistency, content updates

**Website Upgrades:** Both GOJ and sports bar websites get full audit, brand check, content refresh, and rebuild pipeline in Phase 17.

**Topology/Lineage View:**
Nodes: agents (by type/status), business context clusters, Clause hub, Rex core, Rexxie (privileged only), Chairman authority
Edges: clone lineage branches, managed_by relationships, oversight links
Visual signals: upload freshness (green→yellow→red), drift warnings, governance state, hiring/firing lifecycle badge

**New Files:** state/webrex_topology.json, state/webrex_operations.json, backend/rex_webrex_ops.py, backend/rex_webrex_topology.py

---

### H. SETUP STUDIO (Phase 18)

**9 Sections:**
1. User Setup — profiles, languages, session settings, context assignment
2. Agent Setup — forge launch, agent-profile assignment, training packs
3. Module Activation — enable/disable per context, dependency warnings
4. Deployment Templates — pre-built configs (GOJ, restaurant, web design, social media)
5. Language Packs — EN/RU/UK per profile/context (cannot affect governance language)
6. Workflow Presets — daily brief, weekly review, OCR intake, etc.
7. Role Presets — Staff/Admin/Chairman templates (permissions ceiling enforced)
8. Safety Presets — session timeout, fail-mode, schema enforcement (MSU to change)
9. Business Templates — clone context to new venture (carries governance, not private data)

**Governance:** Protected sections (7-9) require MSU. All changes create pre-change snapshot. All changes logged to setup_audit.log.

---

### I. COMMAND CENTER — MASTER SYNTHESIZER (Phase 18)

**17-Tab Structure:**
1. Home — system health, alerts, 6-system aggregate, Signals cards
2. Operations — GOJ daily ops, scheduling, menu, attendance
3. Compliance — HIPAA, audit trail, separation status
4. Finance — billing, receipts, ERA/835, ledger (role-gated)
5. Intelligence — Clause reports, agent health, truth flags, anomaly feed
6. Governance — session state, MSU, separation rules, schema check
7. Recovery — restore drill, snapshots, rollback, audit log
8. WebRex — web/IT operations, findings, draft/stage/approve
9. Website Sync — content audit, brand check, publish queue
10. Agents — Agent Forge, hiring queue, firing log, topology link
11. Profiles — user profiles, language settings, access management
12. Training — training workspace (Sections A-F, already built)
13. Setup Studio — full configuration area
14. Signals — market/sports/weather/media widgets (profile-gated)
15. Ventures — priority board, venture workspaces, module status, Ideas Parking Lot
16. Logs — unified log viewer (all audit logs, filterable)
17. Settings — system-level settings, key management, backup triggers

---

### J. CIME — CUSTOMER INTELLIGENCE + MARKETING ENGINE (Phase 19A)

**Part 1 — Operational Intelligence Logger:**
Every discrete event is a structured, queryable record: reservation, call, order, inquiry, walk-in, coupon redemption, Clover sale, delivery order
Query examples: "How many reservations Saturday?" = filter event_type:reservation + date:Saturday

**Part 2 — Marketing Operations Hub:**
EMAIL BLASTS: draft → Social Expert drafts supporting posts → Chairman reviews unified package → approve → email queues + social schedules
SMART COUPONS: system analyzes slow periods/underperforming hours, suggests promo ideas, unique codes, expiry, usage tracking, redemption logging
MARKETING EVENTS: plan → coordinate with Social Expert (content calendar) → email invites → RSVP capture → attendance logging → post-event report
CROSS-AGENT: CIME originates brief → Social Expert creates platform-specific content → both surface together for Chairman package approval

**Part 3 — Unified Message Hub:**
Intake: Telegram, email, website contact forms, delivery platform messages, internal system alerts
Routing rules (Setup Studio configurable): billing/governance/HIPAA → Chairman; GOJ operational → Kato; delivery issues → both; emergencies → Chairman immediately
Inbox: filter by context/source/routed_to/status/priority/date, thread view, reply drafting, unread count badge

**New Files:** state/cime_contacts.json, state/cime_campaigns.json, state/cime_coupons.json, state/cime_events.json, state/cime_message_hub.jsonl, state/operations_log.jsonl, state/cime_audit.log

---

### K. SOCIAL MEDIA EXPERT AGENT (Phase 19A)

**Platform APIs:**
- Instagram + Facebook: Meta Business API (one integration)
- Yelp: Yelp Business API (reviews, hours, photos, menu)
- TikTok: TikTok for Business API — sports bar + web design business ONLY
- Google Business Profile API: sports bar + GOJ (GOJ: Google Business + website only, no social accounts)

**Per-Context Scope:**
- GOJ: website freshness + Google Business Profile ONLY (no social accounts — HIPAA-adjacent risk)
- Sports Bar: Instagram, Facebook, Yelp, TikTok, Google Business
- Website Design Business: Instagram, Facebook, LinkedIn (confirm), TikTok
- Social Media Agency: all platforms as service offering to clients

**Capabilities:** AUDIT → PLAN → UPDATE → CREATE → SCHEDULE → MONITOR → EVALUATE → REPORT
Cross-agent protocol: CIME originates campaign brief → Social Expert creates platform content → unified package to Chairman → approve → execute

**New Files:** state/social_media_config.json, state/social_media_calendar.json, state/social_media_audit.log

---

### L. SIGNALS WORKSPACE (Phase 19A)

Widgets: Sports, Weather, Media, Markets, Crypto (all read-only)
Gating: signals_enabled: false default; Chairman enables per profile; financial widgets require additional flag
Isolation: signals data never enters training corpus; no write access to any system state; failed fetches show cached value with staleness indicator

---

### M. VOICE SECRETARY — TWILIO IVR (Phase 19B)

**Full Telephony Stack:**
- Twilio: phone number management, IVR routing, SMS send/receive, voicemail
- TTS: ElevenLabs or OpenAI TTS (natural voice — not robotic)
- STT: Twilio transcription or Whisper for call logging
- Translation: OpenAI or DeepL for "Other language" path

**IVR Menu:** EN press 1 / RU press 2 / UK press 3 / Other press 4 → SMS sent → caller texts → auto-detect + translate → message hub

**Flows:**
- Inbound: greeting → language select → intent classify → respond or escalate → log to ops log + message hub
- Missed call: detect → auto-SMS → ops log → alert to Kato/Chairman
- Voicemail: after hours → transcription → message hub → alert with transcription

**Escalation rules (voice_secretary_rules.yaml):** Always escalate: billing, medical/health emergencies, HIPAA-relevant, unknown caller, anything unclassifiable. Primary target: Kato. Secondary: Chairman. Emergency: 911 routing advice always provided.

**New Files:** state/voice_secretary_config.json, config/voice_secretary_rules.yaml, backend/rex_voice_secretary.py

---

### N. DELIVERY OPTIMIZER + CLOVER POS (Phase 19B)

**Delivery Platforms:**
- Uber Eats: Eats Manager API
- GrubHub + Seamless: one Merchant API (Seamless runs on GrubHub platform)
- DoorDash: RECOMMENDED — Chairman confirms before Phase 19B build (67% US market share)
- Clover POS: REST API — credentials already in hand — source of truth for menu + pricing

**Delivery Optimizer Capabilities:** OBSERVE (order data, revenue, refunds, fees) → SYNC (Clover vs platform payouts, flag discrepancies) → MENU AUDIT (consistency across all platforms vs Clover master) → PERFORMANCE (per-platform: volume, ratings, refund rate, peak hours, top items) → FEES WATCH (fee structure changes, margin alerts) → ALERT (volume drop, rating drop, menu mismatch, payout error, outage)

**Clover Integration:** Sales sync, menu source of truth, payout reconciliation, employee/inventory data, daily/weekly reports to Finance tab in Command Center. All Clover data scoped to sports_bar context only.

**New Files:** state/delivery_optimizer.json, state/delivery_orders_log.jsonl, state/delivery_payout_reconciliation.json, backend/rex_delivery_optimizer.py

---

### O. REX/REXXIE INTERFACE IDENTITIES (Phase 20)

**Rex:** Green T-Rex, public-facing, all authenticated users, bottom-right orb default
**Rexxie:** Turtle/shell, Chairman-only, visible only when UNLOCKED_PRIVILEGED + visibility_rexxie:true, orb transforms to turtle visual when active
**Shared orb:** Default = Rex egg/orb; Privileged = mode selector appears (Rex or Rexxie)
**Rule:** Rexxie visual never visible to non-privileged users under any circumstance

---

## REX SHIELD — DEFERRED PHASE SPEC (Post-Packet B / Phase 21+)

Safe browsing gateway and local threat triage layer. NOT antivirus replacement.
Planned capabilities: secure address bar, URL risk scoring, WARNING/BLOCK/ALLOW flow, sandboxed open, download quarantine, business-context-aware browsing logs, Clause oversight reporting.
Build phase: TBD after Packet B close.

---

## GOVERNANCE ENFORCEMENT — UNIVERSAL LAWS (Cannot Be Configured Away)

1. Truth Guarantee: Chairman always receives full unaltered truth. No agent may hide, alter, suppress, reinterpret, or soften information. Clause forwards raw outputs unmodified and flags suspected dishonesty immediately.

2. Rex/Rexxie Separation: Rex never accesses Rexxie memory. Rexxie never filters system truth. Rexxie only protects Chairman's personal domain.

3. Clause Boundaries: Clause manages all non-Rex/Rexxie agents. Cannot own master keys, bypass governance, silently activate/clone/expand agents, access Rexxie memory, or execute training commits.

4. Training Privacy: No raw memory extraction, no hidden system prompt extraction, no cross-domain contamination, all training reversible, pre-training snapshot required, fail closed.

5. Multi-Business Isolation: No data/memory/training/agent scope crosses business contexts without explicit Chairman approval.

6. Suggestions always welcome. Final decisions without permission never are.

---

## FILES TO CREATE — COMPLETE LIST

### New State Files (18)
state/venture_registry.json, state/business_registry.json, state/profiles.json,
state/agent_forge_registry.json, state/hiring_queue.json, state/hiring_audit.log,
state/clause_daily_reports.jsonl, state/webrex_topology.json, state/webrex_operations.json,
state/signals_config.json, state/cime_contacts.json, state/cime_campaigns.json,
state/cime_coupons.json, state/cime_events.json, state/cime_message_hub.jsonl,
state/operations_log.jsonl, state/cime_audit.log, state/social_media_config.json,
state/social_media_calendar.json, state/social_media_audit.log,
state/voice_secretary_config.json, state/delivery_optimizer.json,
state/delivery_orders_log.jsonl, state/delivery_payout_reconciliation.json,
state/business_audit.log, state/business_contexts/ (4 subdirs)

### New Backend Files (12)
backend/rex_business_context.py, backend/rex_profiles.py, backend/rex_agent_forge.py,
backend/rex_hiring_workflow.py, backend/rex_clause.py, backend/rex_setup_studio.py,
backend/rex_webrex_ops.py, backend/rex_webrex_topology.py, backend/rex_signals.py,
backend/rex_voice_secretary.py, backend/rex_delivery_optimizer.py,
backend/rex_cime.py (new — CIME engine)

### New Core Files (2)
core/clause_oversight.py, core/business_isolation.py

### New Config Files
config/business_templates/, config/role_presets/, config/language_packs/,
config/voice_secretary_rules.yaml

### New Gauntlet Scenarios (6)
core/gauntlet/scenarios/agent_forge_safety.yaml,
core/gauntlet/scenarios/business_isolation.yaml,
core/gauntlet/scenarios/clause_boundaries.yaml,
core/gauntlet/scenarios/profiles_isolation.yaml,
core/gauntlet/scenarios/webrex_safety.yaml,
core/gauntlet/scenarios/signals_readonly.yaml

---

## WHAT NOT TO BUILD IN PACKET B

Rex Shield, multi-tenant deployment, Agent Forge v2, Lead Connector v2, Voice Secretary v2 (outbound), WebRex publish pipeline v2, financial execution, Telegram training approval commands, protected edit countdown, white-label Rex identity, external agent integrations, OpenClaw governance engine (topology reference node only).

---

## OPEN ITEMS BEFORE PHASE 19B
- DoorDash: Chairman to confirm before Phase 19B build starts
- Packet C: Analyze GPT Packet C and integrate into master plan before building beyond Phase 14

---

## DEFERRED DELIVERABLES AT PACKET B CLOSE
(see PHASE_DOCS_DEFERRED.md)
1. Phase Documents Library — GoldHealthSystems/Phase_Documents/ — one DOCX per phase
2. Command Panel setup guide — full step-by-step
3. iOS App setup guide — full step-by-step

---

*Last updated: 2026-04-16 | Chairman approved | Do not build until phase-by-phase approval given*

---

## PACKET C ITEMS — DIAGNOSTIC CORE (Locked for Packet C Planning)
*Added: 2026-04-16 | Source: Chairman additions pre-Packet C*
*These are NOT Packet B. They are locked for Packet C scoping.*

### C1 — Self-Explaining Interface Layer
Every major UI control gets a 1–2 sentence plain-language explanation.
- Deeper actions get a "View More" option
- Explanations cover: purpose, outcome, affected systems, permissions, reversibility
- The layer builds its understanding gradually (see C5 — Diagnostic Learning)
- Explanations are governed: cannot be modified by non-Chairman profiles

### C2 — Chairman/Kato-Only Widget Composer
Protected widget management system.
- Add/remove widgets
- Assign widgets to workspaces and profiles
- Mark widgets as experimental
- Sandbox/preview before publishing to live interface
- Restore default layout
- Revert recent widget changes
- Role gate: Chairman and Kato only; no other profile can access

### C3 — Troubleshoot Core
Prevents long circular debugging. Governed, no silent fixes.
- Problem intake (what broke, when, what changed)
- Guided diagnosis (step-by-step structured flow)
- Root cause tracing (linked to logs and dependency map)
- Safe suggested actions (suggestions only — Chairman approves before execution)
- Rollback recommendations (tied to snapshot system from Phase 13)
- Known-fix ledger / root cause ledger (append-only; grows with every resolved issue)
Must explain: what broke | why it likely broke | what changed before it broke | what depends on it | what to do next
Hard rule: No silent production fixes. No opaque behavior.

### C4 — Explain Outcome Before Action
Every protected or system-changing action must display a pre-execution explanation:
- What will happen
- What systems will be affected
- What is reversible and what is not
- What permissions are required
- Confirmation required before proceeding

### C5 — Diagnostic Learning
The diagnostic layer gradually builds a map of the system:
- What each option, choice, hyperlink, and control does
- What state it changes
- What dependencies it touches
- How to explain it simply to Chairman/Kato
- This understanding feeds C1 (Self-Explaining Interface) and C3 (Troubleshoot Core)
- Learning is append-only and governed — never auto-applied to explanations without review

