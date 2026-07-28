# BBG / Victoria Number Untangle — Runbook (v2)
**2026-06-25 · Wire the number Kato ALREADY bought; separate Masha from Victoria's line.**

## Root cause (verified via Retell call logs + Twilio config)
- The GOJ number **646-760-3781** is the Victoria/Retell line.
- Masha's dedicated number — **+1-877-768-2887** — is a **Twilio toll-free Kato bought** (`TWILIO_PHONE_NUMBER=+18777682887`). It was **never imported into Retell**, so Masha's agent had no usable number.
- Result: every Masha→Lana call **fell back to the GOJ number** (first call June 22 1:07 PM was from `+16467603781` via `agent_26e3`). That fallback is the tangle.

Goal end-state:
- **646-760-3781** → Victoria (`agent_26e3`) ONLY.
- **+1-877-768-2887** (imported to Retell) → Masha (`agent_305ba9`).  *(or the published 929 line — see Step 4 note)*
- No agent borrows the other's number.

---

## ⚠️ Check first — the 877 number is shared
`+1-877-768-2887` is the GHS Twilio number used by the **Lead Connector** (`CC_lead_connector_api.py` default `from`). Importing it to Retell takes over its **VOICE** handling. Before repurposing it as Masha's voice line:
- [ ] Confirm nothing else makes **outbound voice** calls from it (Lead Connector voice would break). SMS is separate and unaffected.
- [ ] It's **toll-free** — fine for inbound voice, but a local (929/718) number is more natural for a Brighton Beach bar. If you'd rather, skip to Step 4-ALT (use the published 929 line).

## STEP 1 — Verify on dashboards (5 min)
- Retell (app.retellai.com → Phone Numbers): confirm 646-760-3781 → Victoria, and whether any **custom SIP** entry duplicates it → Masha (delete that duplicate here).
- Twilio (console.twilio.com → Phone Numbers): confirm `+1-877-768-2887` is owned, and note its current Voice/SMS webhooks.

## STEP 2 — Fix the GOJ number → canonical Victoria
```
~/Desktop/REX/CC_fix_victoria_routing.command
```
(points 646-760-3781 inbound+outbound at `agent_26e3`)

## STEP 3 — Remove the duplicate Masha-on-GOJ SIP binding (Retell dashboard)
Delete the custom SIP entry for 646-760-3781 bound to Masha. (Dashboard, not API — the API masks the number; a wrong delete is hard to undo.)

## STEP 4 — Import +1-877-768-2887 into Retell, bind to Masha  ← the number you bought
**Easiest (Retell dashboard):**
1. app.retellai.com → Phone Numbers → **Import / Connect Number**.
2. Enter your **Twilio Account SID + Auth Token** + the number **+18777682887**. Retell auto-configures the Twilio voice webhook.
3. Set **inbound agent = outbound agent = Masha** (`agent_305ba9fdc34276c523766cd096`).
4. Then run the bind/verify helper to confirm + lock it:
```
~/Desktop/REX/CC_bind_masha_number.command
```
**API alternative (advanced — needs a Twilio Elastic SIP Trunk):** create a Twilio SIP trunk, point origination to Retell, get the **termination URI**, then call Retell `import-phone-number` with it (the helper has a slot for this).

**STEP 4-ALT — use the published BBG line instead (929) 205-6408:**
That's the number customers actually call (currently GoHighLevel/Lana). Port it to Retell (carrier LOA, ~1–10 days) or forward it to the Retell-imported 877 number. Best long-term for the restaurant; slower.

## STEP 5 — Verify + record
- [ ] 646-760-3781 → `agent_26e3` (Victoria), no Masha binding.
- [ ] +1-877-768-2887 → `agent_305ba9` (Masha), imported to Retell.
- [ ] Update Perpetual Memory "Masha & Victoria": Masha's real number is +1-877-768-2887 (Twilio, now imported), NOT "deregistered." The 646-760-3781 fallback is fixed.
- [ ] Test: call +1-877-768-2887 → Masha (upgraded BBG receptionist) should answer.

---

## Quick reference
- Victoria (GOJ): `agent_26e3746829ae6e174f4a012bbd`  → 646-760-3781
- Masha (BBG):    `agent_305ba9fdc34276c523766cd096` → +1-877-768-2887 (import) or 929-205-6408 (port/forward)
- Victoria v2 (deprecated): `agent_8a326510567e7dc3e2dc5221df`
- Twilio toll-free 877-768-2887 is ALSO the Lead Connector number — check for voice conflicts before repurposing.
