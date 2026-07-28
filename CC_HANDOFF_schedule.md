# GOJ Daily PDF Pipeline — Schedule Handoff

## What this system does

Three scripts work together to pull client + menu data from Google Drive and send kitchen/distribution/sign-in PDFs to Telegram every day.

---

## Files

| File | Location | Purpose |
|------|----------|---------|
| `CC_drive_sync_data.py` | `~/Desktop/REX/` | Reads Drive sign-in + menu sheets → writes `clients.json` + `GOJ_Menu_Orders.json` |
| `CC_daily_delivery.py` | `~/Desktop/REX/` | Orchestrator — runs sync + calls `generate_tomorrow.py` at each scheduled time |
| `generate_tomorrow.py` | `~/Documents/goj files/dashboard/` | PDF generator — reads the JSON files and sends via Telegram |
| `CC_install_menu_pipeline.command` | `~/Desktop/REX/` | One-click installer that writes launchd plists and loads them |

---

## How to change scheduled times

There are **two places** to update — both must match:

### 1. `CC_daily_delivery.py` — what runs at each slot

Four `--time` slots: `morning`, `sheets`, `signin`, `evening`

Each slot calls `run_generate(day=..., mode=...)` where:
- `day` = `"today"` | `"tomorrow"` | `"Monday"` … `"Friday"` | `"Sunday"`
- `mode` = `"signin"` | `"distribution"` | `"all"`

**Current schedule logic:**
```python
if args.time == "morning":      # 7:30 AM
    run_sync()
    run_generate(day="tomorrow", mode="signin")

elif args.time == "sheets":     # 10:30 AM
    run_sync()
    run_generate(day="tomorrow", mode="distribution")

elif args.time == "signin":     # 3:15 PM
    run_sync()
    run_generate(day="tomorrow", mode="distribution")

elif args.time == "evening":    # 9:00 PM
    send_evening_summary()      # text-only, no PDF
```

To change WHAT each slot does → edit the `run_generate(day=..., mode=...)` call in the relevant `elif` block.

### 2. `CC_install_menu_pipeline.command` — WHEN each slot fires

Four launchd plists control the clock times. Each plist has a `StartCalendarInterval` block:

```xml
<!-- Morning: 7:30 AM -->
<key>StartCalendarInterval</key>
<dict>
    <key>Hour</key><integer>7</integer>
    <key>Minute</key><integer>30</integer>
</dict>

<!-- Sheets: 10:30 AM -->
<key>Hour</key><integer>10</integer>
<key>Minute</key><integer>30</integer>

<!-- Signin: 3:15 PM -->
<key>Hour</key><integer>15</integer>
<key>Minute</key><integer>15</integer>
```

The drive sync plist uses `StartInterval` (seconds between runs, currently 1800 = 30 min):
```xml
<key>StartInterval</key><integer>1800</integer>
```

To change a time → update `Hour` and `Minute` in the correct plist block inside the installer, then re-run the installer (or manually `launchctl unload` → edit the plist in `~/Library/LaunchAgents/` → `launchctl load`).

---

## Plist names (in `~/Library/LaunchAgents/`)

| Plist | Slot | Current time |
|-------|------|-------------|
| `com.goj.drive.sync.plist` | Continuous sync | Every 30 min |
| `com.goj.morning.sheets.plist` | morning | 7:30 AM |
| `com.goj.kitchen.sheets.plist` | sheets | 10:30 AM |
| `com.goj.signin.sheets.plist` | signin | 3:15 PM |

Evening summary has no plist yet — add one if needed using the same pattern.

---

## To apply time changes after editing

```bash
# Reload all four plists:
for label in com.goj.drive.sync com.goj.morning.sheets com.goj.kitchen.sheets com.goj.signin.sheets; do
    launchctl unload ~/Library/LaunchAgents/$label.plist 2>/dev/null
    launchctl load ~/Library/LaunchAgents/$label.plist
done

# Verify:
launchctl list | grep goj
```

---

## To test a slot immediately (no waiting for the clock)

```bash
~/.rex-venv/bin/python3 ~/Desktop/REX/CC_daily_delivery.py --time morning
~/.rex-venv/bin/python3 ~/Desktop/REX/CC_daily_delivery.py --time sheets
~/.rex-venv/bin/python3 ~/Desktop/REX/CC_daily_delivery.py --time signin
~/.rex-venv/bin/python3 ~/Desktop/REX/CC_daily_delivery.py --time evening
```

---

## generate_tomorrow.py — accepted `--day` values

`today` | `tomorrow` | `Monday` | `Tuesday` | `Wednesday` | `Thursday` | `Friday` | `Saturday` | `Sunday`

To generate for a specific named day (e.g., two days out), compute the weekday name and pass it:
```python
from datetime import date, timedelta
target = date.today() + timedelta(days=2)
day_name = target.strftime("%A")   # e.g. "Saturday"
run_generate(day=day_name, mode="distribution")
```

Modes: `signin` | `distribution` | `drivers` | `all`
