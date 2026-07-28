# PACKET B — LOCKED PHASED BUILD PLAN
## Gold Health Systems / REX Second Brain
**Planning Date:** 2026-04-16 | **Foundation:** Phase 13 complete and locked
**Authority:** Chairman Kato — final approval on all phases before build begins
**Status:** AWAITING CHAIRMAN APPROVAL — DO NOT BUILD

---

## Phase Sequence Summary (AMENDED 2026-04-16)

| Phase | Name | Key Deliverables |
|---|---|---|
| 14 | Multi-Business Context + Profiles + Venture Registry | business_registry.json, venture_registry.json, profiles.json, context isolation, Setup Wizard (questionnaire), Ventures tab in Command Center, Ideas Parking Lot, anti-bleed venture profiles |
| 15 | Agent Forge + Lineage | agent_forge_registry.json, forge engine, clone/template/create, lineage tracking, existing 13 agents migrated |
| 16 | Clause + Hiring/Firing | clause engine, hiring workflow (Clause→Kato→Chairman), firing levels, daily reports, training director formalization |
| 17 | WebRex Web/IT + Topology | web operations engine, topology/lineage visualization, draft/stage/approve publish flow, Clause oversight integration |
| 18 | Setup Studio + CC Master Synthesizer | Setup Studio (9 sections), Command Center expanded to 17 tabs, Module Activation Wizards per-module per-venture (Social Media, Delivery, CIME, Voice, WebRex etc.), modules listed in priority order with configured/unconfigured status |
| 19A | Signals + CIME + Social Media Expert | Customer Intelligence + Marketing Engine (ops logger, email blasts, promotions, smart coupons, marketing events, unified message hub), Social Media Expert (cross-agent coordination), Signals workspace |
| 19B | Voice Secretary + Delivery Optimizer + Clover POS | GOJ voice agent (RU), Uber Eats/GrubHub/Seamless obs, Clover POS sync and reconciliation |
| 20 | Rex/Rexxie Interface Identities + Final Polish | Green T-Rex Rex identity, turtle/shell Rexxie identity, orb/egg access point, topology final render |

## Deferred Beyond Packet B
- Rex Shield (full spec in plan document)
- Multi-tenant deployment
- Agent Forge v2, Lead Connector v2, Voice Secretary v2
- WebRex publish pipeline v2
- Financial execution (Signals read-only only)
- Telegram training approval commands
- Protected edit countdown visibility

## Phase 19A/19B — LOCKED ANSWERS (2026-04-16)

SOCIAL MEDIA:
  — Instagram + Facebook (Meta API), Yelp (Yelp Business API), Google Business Profile API: ALL businesses
  — TikTok (TikTok for Business API): sports bar + web design business ONLY
  — GOJ: website + Google Business Profile ONLY (no social accounts — HIPAA-adjacent risk)
  — Both GOJ and sports bar websites need full upgrade (flagged for Phase 17 WebRex)

DELIVERY PLATFORMS:
  — Uber Eats (Eats Manager API)
  — GrubHub + Seamless (one Merchant API — Seamless runs on GrubHub platform)
  — DoorDash RECOMMENDED (67% US market share) — Chairman to confirm before Phase 19B build
  — Open to additions that make sense

VOICE SECRETARY:
  — Real Twilio telephony integration (IVR, SMS, voicemail)
  — Natural TTS voice (ElevenLabs or OpenAI TTS — not robotic)
  — IVR: EN press 1 / RU press 2 / UK press 3 / Other press 4 → SMS + auto-translate
  — Missed call → auto-SMS + operations log + alert to Kato/Chairman
  — Voicemail → auto-transcription → message hub
  — All calls logged to operations log and message hub

CLOVER POS:
  — Credentials already in hand — ready for direct integration in Phase 19B
  — Sales sync, menu source of truth, payout reconciliation vs delivery platforms
  — Clover data scoped to sports_bar context only

## Files to Reference
- Full plan: PACKET_B_BUILD_PLAN.md (this file — summary only)
- Full detailed plan: see conversation record or REX_PacketB_BuildPlan.docx (if generated)
- Deferred items tracker: PHASE_DOCS_DEFERRED.md
- Current snapshot: REX_Backups/PHASE13_SNAPSHOT_2026-04-16_053722/

