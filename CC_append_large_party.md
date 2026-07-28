

---

## Run: 2026-06-28 ~11:32 UTC — Scout-Large-Party (DIAL FAILED x2)

### Call #49 — Scout-Large-Party (Secondary — DIAL FAILED)
- Phone: (929) 205-6408 (secondary)
- Duration: 0 sec
- Call ID: call_f6140fc70ee33dbb56fb64dcad9
- Agent: Scout-Reservations (agent_01dd3c97a1d84bfc030007e641) with `override_agent_id`
- Scenario tag: lana_study_large_party
- **DIAL FAILED — call never connected.** Retell `create-phone-call` returned 200, call_status=`registered`, then the call died at the SIP/PSTN carrier layer (`disconnect=dial_failed`).
- Greeting: N/A — Lana never picked up.
- Accuracy: N/A
- Conversion: N/A
- call_cost: $0.00
- **No live Lana interaction. Per spec ("Don't spam — these are real phone calls to BBG"), a single retry was attempted after a 30s pause.**

### Call #50 — Scout-Large-Party (Secondary — DIAL FAILED, retry)
- Phone: (929) 205-6408 (secondary)
- Duration: 0 sec
- Call ID: call_bb499dd469d822b2d21f710b65b
- Agent: Scout-Reservations (agent_01dd3c97a1d84bfc030007e641) with `override_agent_id`
- Scenario tag: lana_study_large_party
- Time: 2026-06-28 11:36:17 UTC (4 minutes after Call #49)
- **DIAL FAILED — identical SIP auth failure.** Retell API healthy; carrier-layer flap continues.
- Greeting: N/A
- Accuracy: N/A
- Conversion: N/A
- **Stopped after 2nd failure** — per prior diagnosis (Call #46 / #48 notes), the +164****3781 trunk is in a flapping state and 2 attempts in 4 minutes add no new signal. No 3rd attempt made.

### Updated SIP-trunk instance count
- **Calls dial_failed due to SIP auth on +164****3781:** 9 instances
  - #39 (Jun 27 ~01:30 UTC) — Scout-New-Customer-Hours (secondary)
  - #40 (Jun 27 ~01:30 UTC) — Scout-New-Customer-Hours (primary)
  - #42-44 (Jun 27 ~08:00-14:30 UTC) — earlier dial_failed streak
  - #46 (Jun 27 ~17:09 UTC) — Scout-Complaint (secondary)
  - #48 (Jun 28 ~08:31 UTC) — Scout-Large-Party (secondary)
  - **#49 (Jun 28 ~11:32 UTC) — THIS RUN**
  - **#50 (Jun 28 ~11:36 UTC) — THIS RUN, retry**
- **Calls succeeded on +164****3781 (last 24h):** 2 (Call #45 at 14:10 UTC Jun 27, Call #47 at 02:20 UTC Jun 28)
- **Verdict:** Trunk has been mostly broken for ~24 hours. The flapping is trending more towards dial_failed than success. **The +164****3781 number is no longer reliable for live Lana scouting.**

### Scenario rotation
- Last completed run scenario: Make a Reservation (b) at 02:20 UTC → 174.6s live ✅
- This run scenario: Large Party (d) at 11:32/11:36 UTC → 2x dial_failed ❌
- **Next candidate (if SIP recovers):** Large Party (d) — STILL the only scenario not yet captured with a live Lana conversation in English. Or shift to Private Event (e) which has only ever been tested as a voicemail scenario on the primary line.

### New Patterns Observed (Run 2026-06-28 ~11:32 UTC)
- **⚠️ +164****3781 SIP trunk is now in extended dial_failed state.** The 2 successful calls in the last 24h (#45, #47) appear to have been lucky windows, not stable recovery. The flapping has shifted from "intermittent" to "mostly broken."
- **No Lana interaction data this run.** Large Party scenario remains unfulfilled after 4 attempts total (Call #26 = language mismatch, #34 = event space variant, #48 + #49 + #50 = dial_failed).
- **Recommendation for Masha production deployment:** Do NOT use +164****3781. Either provision a new Retell-native number (not BYOC SIP) or fix the trunk credentials persistently in the Retell dashboard. This number is unusable for any production voice-bot workload.
- **2-call retry cap policy confirmed.** This run placed 2 calls (#49 + #50) before stopping, consistent with prior run diagnosis that additional calls add no signal when the trunk is in a known-broken state. Per spec, "Don't spam — these are real phone calls to BBG."

### Masha Competitive Takeaway (this run)
- **Scenario tested:** Large Party (d) — booking inquiry for 10+ people
- **Key finding:** **No new Lana data this run** — 2x dial_failed due to Retell SIP trunk instability on outbound +164****3781. The Large Party scenario remains the least-tested English-language scenario; the SIP issue is the blocker, not Lana or BBG.
- **One thing Masha could do better than Lana (still stands from prior runs):** Collect the caller's name, phone, party size, and target date on the call (not just send a link), then offer a concrete follow-up time instead of the vague "team member will reach out." (Reinforced by Call #47 reservation transcript analysis.)

### Updated learning file: /Users/mainsobhelper/Desktop/REX/bbg_lana_analysis.md
