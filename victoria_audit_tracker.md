# Victoria Red Team — Comprehensive Audit Tracker

Started: July 11, 2026
Purpose: Track every pre-call check and post-call audit to spot patterns.

---

## Schedule

| What | When | Job ID |
|---|---|---|
| Pre-Call Red Team Check | 1:45 PM daily (Mon–Sun) | f675a1fb2da6 |
| Victoria Caller | 2:00 PM daily (Sun–Fri, Sat OFF) | com.goj.victoria-caller |
| Post-Call Red Team Audit | 3:15 PM daily | d6cd2cd80fe8 |

## Plist Status

> launchd Weekday numbering: **0/7=Sunday, 1=Monday … 6=Saturday** (corrected Aug 2, 2026 — old table assumed 1=Sun and the plists were Mon–Sat, the reverse of intent for the weekend).

| Day | Caller | Pre-Check | Token Refresh |
|---|---|---|---|
| Sunday (0) | ✅ 2PM → Mon clients | ✅ 1:45PM | ✅ 1PM |
| Monday (1) | ✅ 2PM → Tue | ✅ 1:45PM | ✅ 1PM |
| Tuesday (2) | ✅ 2PM → Wed | ✅ 1:45PM | ✅ 1PM |
| Wednesday (3) | ✅ 2PM → Thu | ✅ 1:45PM | ✅ 1PM |
| Thursday (4) | ✅ 2PM → Fri | ✅ 1:45PM | ✅ 1PM |
| Friday (5) | ✅ 2PM → Sun (skip Sat) | ✅ 1:45PM | ✅ 1PM |
| Saturday (6) | ❌ REMOVED (was double-run: Sat+Fri both → Sun) | ✅ 1:45PM | ❌ No refresh (no run) |

---

## Audit Log

### 2026-08-02 (Sun) — 13:48 — PRE-CALL GATE + SCHEDULE REPAIR
- Gate: **HOLD** (approval file stale since Jul 19; Kato must approve for any run).
- Pre-check: 4/4 ALL CLEAR (Agent, Caller plist, Drive, DB, Token fresh).
- 🔴 **launchd numbering off-by-one found & fixed**: plists had Weekdays 1–6 = **Mon–Sat** (launchd: 1=Mon), while intent is **Sun–Fri, Sat OFF**. Since Jul 11 fix, caller NEVER fired Sundays → Monday clients never confirmed; Sat run duplicated Fri's Sun target (double-run risk when both approved). Token refresh Mon–Sat only → "Token fresh" false-failed today (Sun).
- FIX: caller + token-refresh plists Weekday 6→0, reloaded (launchctl). Now Sun–Fri (0,1,2,3,4,5). Refresh ran manually 13:49 to freshen heartbeat.
- Historical note: caller crashed at Python startup Jul 19–26 ("Fatal Python error: error evaluating path") — all those runs HELD anyway, no calls lost; self-recovered Jul 27.
- Action needed: Kato approve (`CC_victoria_approval_gate.sh approve`) if Monday calls should proceed — with schedule fixed, Sunday 2PM run will fire.
