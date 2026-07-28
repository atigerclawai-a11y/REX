# GOJ WhatsApp → Pipeline Integration Handoff
> For Kimi K3 — How the 3 group chats feed the OCR/document ecosystem

---

## 1. Architecture Overview

```
WhatsApp (phone)
    │
    ▼
CC_whatsapp_goj.js  ← whatsapp-web.js (15k⭐), LocalAuth session
    │  WebSocket, no browser window (headless:true)
    │  Launchd: com.goj.whatsapp-bridge (auto-start on boot)
    │  Session: ~/.whatsapp_bridge/wwjs_session/
    │
    ▼  live messages
DataRex :8080/api/imessage/intel  (POST JSON)
    │
    ├── CC_whatsapp_workflow.py  (822 lines, classification engine)
    │     Classifies each message by intent, cross-references DB,
    │     queues actions, sends Telegram alerts to Kato
    │
    └── Pipeline actions:
          • kitchen_adjustments.json  → kitchen count sheets
          • auth_tracker.db           → schedule/attendance cascade
          • pending_schedule_changes  → sign-in/driver/kitchen sheets
          • driver_routes            → transport manifests
```

## 2. The 3 Groups & Their Message Types

### Group: "plus and minus" — `update_kitchen_counts`

| Staff posts | What it means | Pipeline action |
|---|---|---|
| `+` / `-` (bare signals) | Attending / Not attending | Update `kitchen_adjustments.json` → next kitchen sheet |
| Photo of handwritten +/- list | OCR-extracted names with +/- | Parse via Tesseract (rus+eng), apply to kitchen counts |
| Text: "+ Ivanov... - Petrov..." | Explicit plus/minus per name | Match against `auth_tracker.db clients` table, flag kitchen |

**Cascade:** Kitchen adjustments → affects `generate_tomorrow.py --mode kitchen` counts → changes food prep quantities. Does NOT affect sign-in sheets (those show all scheduled clients regardless).

### Group: "attendance" — auth & schedule signals

| Staff posts | Classification | Pipeline action |
|---|---|---|
| "authorization Иванов ends 7/30" | `auth_expiring` | Cross-reference `authorization` table, alert if <30 days |
| "signature for Petrov at printer" | `signature_request` | Check `output_docs/` for today's sign-in sheets |
| "why is Sidorov not on today?" | `schedule_anomaly` | Check `day_*_actual` flags, alert Kato |
| "not in carecenta but yes at report" | `cross_system_gap` | Flag data sync issue between Carecenta ↔ auth_tracker.db |
| "wrong number for ... daughter's phone" | `wrong_contact_data` | Queue phone correction in auth_tracker.db |
| "can't log in, password changed" | `system_access_issue` | Log for Kato |
| "нет дня рождения у ..." | `missing_client_data` | Flag missing demographics |
| "counts for today?" | `count_request` | Log delivery confirmation |

### Group: "main" — operational changes

| Staff posts | Classification | Pipeline action |
|---|---|---|
| "всегда now Wednesday" / "permanent change" | `permanent_schedule_change` | Queue `day_*_actual` update in DB → all 7 sheets cascade |
| "not coming, surgery" / "больница" | `medical_absence` | Track duration, remove from sheets temporarily |
| "сами приедут" / "own car" | `self_transport` | Mark no-pickup in driver routes |
| "Ravil pick up Ivanov instead of Petrov" | `transport_change` | Update `driver_routes` table |
| "7/23 instead of 7/22" | `future_date_swap` | Queue future-dated schedule change |
| "all drivers come at 8" | `driver_announcement` | Log announcement |

## 3. Data Flow: WhatsApp → Daily Sheets

```
                    WhatsApp message
                          │
                          ▼
              CC_whatsapp_goj.js (bridge)
              ┌─────────────────────────┐
              │  Detects: group name    │
              │  Extracts: sender, text │
              │  Sends to: DataRex POST │
              └──────────┬──────────────┘
                         │
                         ▼
           ┌─────────────────────────┐
           │  CC_whatsapp_workflow   │ ← NOT YET WIRED
           │  .classify_message()    │    to current bridge
           │  .execute_action()      │
           └──────────┬──────────────┘
                      │
         ┌────────────┼────────────┬──────────────┐
         ▼            ▼            ▼              ▼
  kitchen_adj   auth_tracker   driver_routes   pending_changes
  .json         .db update     .db update      queue
         │            │            │              │
         ▼            ▼            ▼              ▼
  kitchen sheet   sign-in +     driver route    future sheet
  (food counts)   distribution   manifests      generations
                  sheets
```

## 4. Current State (2026-07-27 — ORCHESTRATED BY HERMES)

| Component | Status | Notes |
|---|---|---|
| WhatsApp bridge (`CC_whatsapp_goj.js`) | ✅ LIVE | **Baileys WebSocket** (replaced Playwright & whatsapp-web.js), launchd `com.goj.whatsapp-bridge`, KeepAlive, logs in `~/Library/Logs/whatsapp_bridge_*.log` |
| Session | ✅ PAIRED | `~/.whatsapp_bridge/baileys_auth/` — paired 2026-07-27 via QR PNG delivered in chat. No browser, no QR needed again |
| DataRex endpoint `/api/imessage/intel` | ✅ LIVE + WIRED | Logs to `~/.whatsapp_bridge/intel_log.jsonl` AND calls `CC_whatsapp_workflow.process_messages()` per message (app.py patched) |
| Message → DataRex flow | ✅ WORKING | Verified end-to-end 2026-07-27 |
| `CC_whatsapp_workflow.py` classify/act | ✅ WIRED | Real-time via DataRex hook; audit → `whatsapp_workflow_audit.jsonl` |
| Kitchen adjustments → sheets | ✅ WIRED | `kitchen_adjustments.json` created; consumed by cron d5a36bd909c4 Step 0 |
| Telegram alerts | ✅ WIRED | REXXIE_TOKEN added to `com.goj.datarex` plist env (correct 46-char extraction: `cut -d' ' -f1` to strip the .env comment). Verified delivered |
| Schedule change cascade | ✅ QUEUED | `whatsapp_approval_queue.json` — cron reports pending nightly, Kato approves |
| Daily consumption | ✅ CRON | `d5a36bd909c4` (8pm Sun–Fri) sweeps intel_log.jsonl + workflow outputs into the daily package |

**⚠️ Ops notes:** `imessage_intel.db` in dashboard/data is LEGACY (last row Jul 15) — live intel is the JSONL. Only ONE bridge instance may run (duplicate Baileys sessions `conflict/replaced`-loop each other). QR re-pairing: kill service, `rm -rf baileys_auth/*`, restart, grab `QR_RAW:` line from log, render PNG via python qrcode, send to Kato — valid ~60s.

## 5. What Needs Building

**Priority 1 — Wire the workflow engine:**
The current bridge calls `send()` which posts to DataRex. Instead (or in addition), it should:
1. Call `CC_whatsapp_workflow.process_messages(intel)` 
2. That function classifies each message, cross-references DB, takes action
3. Actions include: updating kitchen_adjustments.json, queueing DB changes, sending Telegram alerts

**Priority 2 — Kitchen adjustment auto-apply:**
When `plus_minus_update` fires:
1. OCR the image (if present) to extract names
2. Match names against `auth_tracker.db clients` table (fuzzy, handles Cyrillic/Latin)
3. Update `kitchen_adjustments.json` with +/- per client
4. On next `generate_tomorrow.py --mode kitchen` run, adjustments are incorporated into counts

**Priority 3 — Schedule change queue:**
When `permanent_schedule_change` or `future_date_swap` fires:
1. Extract client name and target day
2. Match against DB
3. Queue in `pending_schedule_changes` table
4. Kato approves via Telegram → cascade executes:
   - Update `day_*_actual` in `clients` table
   - Next sheet generation picks up new schedule

**Priority 4 — Transport change → driver routes:**
When `transport_change` fires:
1. Detect driver name (Ravil, Alisher, Vadik, Oleg, Andrey, Valera, Gena)
2. Detect day of week
3. Detect client name
4. Update `driver_routes` table → next route sheet reflects change

## 6. Key Files Reference

| File | Path | Purpose |
|---|---|---|
| Bridge script | `~/Desktop/REX/CC_whatsapp_goj.js` | whatsapp-web.js client, live monitoring |
| Workflow engine | `~/Desktop/REX/CC_whatsapp_workflow.py` | 822 lines: classify, cross-ref DB, execute actions |
| Auth DB | `~/Documents/goj files/dashboard/auth_tracker.db` | clients, authorization, attendance_log, driver_routes |
| Proprietary DB | `~/Documents/goj files/proprietary/goj_proprietary.db` | client_menus, kitchen data |
| Kitchen adjustments | `~/Desktop/REX/kitchen_adjustments.json` | +/- deltas for kitchen counts |
| Audit log | `~/Desktop/REX/whatsapp_workflow_audit.jsonl` | Every action logged |
| Daily sheet gen | `~/Documents/goj files/dashboard/generate_tomorrow.py` | Generates sign-in, kitchen, distribution PDFs |
| Launchd plist | `~/Library/LaunchAgents/com.goj.whatsapp-bridge.plist` | Auto-start on boot |
| Session data | `~/.whatsapp_bridge/wwjs_session/` | Chrome profile with WhatsApp Web auth |

## 7. Bridge Lifecycle

```
Boot → launchctl starts CC_whatsapp_goj.js
     → Puppeteer launches headless Chrome
     → LocalAuth restores saved session from wwjs_session/
     → WhatsApp Web loads (no QR if session valid)
     → "✓ Connected - monitoring"
     → Live message events fire for new messages
     → Messages POST to DataRex :8080/api/imessage/intel
     
If crash → launchd KeepAlive restarts in <10s
If log out → QR printed to bridge.log, Kato alerted via Telegram
Session backup → nightly cron backs up wwjs_session/
```

## 8. Phone Integration Pattern

When a staff WhatsApp message triggers a schedule change:
1. Bridge receives the message
2. Workflow engine classifies as `permanent_schedule_change`
3. System extracts: client name (`fuzzy match DB`), new day, effective date
4. Queues in `pending_schedule_changes` table
5. Telegram alert sent to Kato: `"⚠️ Dad: Иванов теперь среда"` 
6. Kato replies "approve" → cascade executes
7. Next sheet generation picks up the change automatically
8. Victoria voice calls reflect new schedule
