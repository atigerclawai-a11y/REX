# Rexxie Firewall Rules — Gold Health Systems
# v1.0 · June 4 2026

---

## The Wall

Rexxie's private lane is absolutely isolated from all other GHS systems.
No rule, no feature request, no convenience trade-off overrides this wall.
Kato alone may adjust it, via explicit PAE (Propose → Approve → Execute).

---

## What Rexxie IS

- Kato's personal executive AI confidant
- Private finances, income, expenses, personal deals
- Passwords and vault secrets (triple-encrypted, local-only)
- Private notes, thoughts, and decisions
- Build monitor and personal life ledger

## What Rexxie IS NOT

- A GOJ operations tool accessible to staff
- A system with cloud routing for personal data
- A shared context with any other agent
- A backup location for GOJ data

---

## Hard Rules (These Never Bend)

### Rule 1 — rexxie.db is Rexxie-only
`~/Desktop/REX/rexxie.db` is accessed by the authorized list of scripts only.
No script not in the authorized list may open, read, or write to it.
No GOJ table names, column names, or data may appear in it.

**Authorized table names (as of June 4 2026, 9 tables):**
- rexxie_vault_recovery
- rexxie_credentials
- rexxie_vault_meta
- rexxie_memory (564 rows, all content_enc BLOB — AES-256-GCM)
- rexxie_sessions
- rexxie_training_schedule
- rexxie_training_lessons
- rexxie_daily_log
- sqlite_sequence (SQLite internal)

### Rule 2 — The Zombie Stays Dead
`com.hermes.rexxie-bot.plist` is permanently disabled.
Current status (June 4 2026): **PLIST DOES NOT EXIST** — ideal state.
If it reappears and is loaded: kill immediately + alert Kato.
If it reappears but inactive: alert Kato + hash-track for modification.
Do not re-enable it for any reason. Do not test it. It crashes and steals the Rexxie token.

### Rule 3 — One Token, One Owner
The `@goldhealth_rexxie_bot` token (stored in `rex_rexxie_telegram_config.json`)
belongs to the authorized Rexxie service only.
No other process may use it. No other file may read it.
`owner_chat_id` must always equal 5587703834 (Kato's Telegram ID).

### Rule 4 — Rexxie is Local-Only
Rexxie never routes to cloud AI with Kato's personal data unless:
- Local processing first (sovereign.py rexxie_mode)
- Gate 1 (akc_tokenizer.py) is complete
- Kato has explicitly approved cloud routing for the session

### Rule 5 — Content Encryption is Mandatory
All sensitive data in rexxie.db is stored as encrypted BLOBs.
Column: `content_enc BLOB` or `backup_enc BLOB` — AES-256-GCM.
If any rexxie_* table is found with a plaintext TEXT column containing personal data,
that is a HIGH violation to investigate.

### Rule 6 — GOJ Crossover is Zero-Tolerance
GOJ data:
- Client names, medical data, auth status
- Employee information
- Schedule, menus, attendance records

...must NEVER enter rexxie.db in any form.

Note: Rexxie's system prompt intentionally includes GOJ operational intelligence
(so Kato can ask her about client schedules, kitchen sheets, etc.) — this is READ-ONLY
access to auth_tracker.db, authorized by Kato, and does NOT constitute crossover.
What is forbidden is GOJ data being WRITTEN into rexxie.db tables.

---

## Authorized Files (Complete List, June 2026)

These files may access rexxie.db. Any unlisted Python script with it open = violation.

| File | Purpose | Access Type |
|------|---------|-------------|
| rex_rexxie.py | Primary Rexxie handler | Read/Write |
| rex_2fa.py | TOTP stored in rexxie.db | Read/Write |
| rex_credential_vault.py | Emergency wipe | Overwrite/Delete |
| rex_command_center.py | Status monitoring | Path check only |
| rex_command_center_status.py | Health display | Path/size check |
| rex_rexxie_training.py | Training data | Read/Write |
| rex_rexxie_preload.py | Memory preload | Write (run once) |
| rex_rexxie_daily.py | Daily lessons | Write |
| rex_saturday_review.py | Weekly review | Read/Write |
| rex_seed_phrase.py | Seed phrase storage | Read/Write |
| rex_vault_recovery.py | Vault backup/restore | Read/Write |
| rex_vault_migrate.py | Migration utility | Read/Write |
| cleanup_rexxie_memory.py | Memory maintenance | Read/Delete |
| rex_interface_contract.py | Contract validation | Path check only |
| rex_memory_inspect.py | Inspection utility | Read only |
| CC_rexxie_firewall.py | This firewall | Read only |

---

## Monitoring — CC_rexxie_firewall.py

The daemon runs every 60 seconds and performs four checks:

**Check 1: Zombie Plist**
- If `com.hermes.rexxie-bot.plist` is loaded → kill + CRITICAL alert
- If plist file exists but not loaded → HIGH alert + hash tracking
- If plist doesn't exist → ✅ (current ideal state)

**Check 2: Unauthorized DB Access**
- Uses `lsof` to find all processes with rexxie.db open
- Any Python process not in the authorized list → CRITICAL alert
- REX backend server (uvicorn/main.py) is implicitly authorized as it loads authorized modules

**Check 3: Table-Level Crossover (Schema Check)**
- Opens rexxie.db and reads `sqlite_master`
- Any GOJ table name present → CRITICAL alert
- Any unexpected table not in the authorized list → HIGH alert
- Any GOJ DDL pattern (service_end_date, day_T_actual, etc.) in schema → HIGH alert
- Tracks table list hash to detect schema drift between checks

**Check 4: Token Conflict**
- `pgrep -fa rexxie-bot` — if zombie process running → CRITICAL alert
- Reads `rex_rexxie_telegram_config.json` — if owner_chat_id ≠ Kato's ID → CRITICAL alert

---

## Alert Routing

CRITICAL violations → immediate Telegram alert to Kato via **Hermes bot** (NOT Rexxie token).
HIGH violations → Telegram alert via Hermes bot.
All violations → logged to `~/Desktop/REX/logs/rexxie_firewall.log`.
State persisted at `~/Desktop/REX/.rexxie_firewall_state.json`.

Alert token priority: `~/.hermes/profiles/cloud/.env` → Hermes config.yaml.
If no Hermes token available: log-only mode (no Telegram alert).

---

## What Happens When a Violation is Found

| Violation Type | Automatic Action | Manual Action Required |
|---------------|-----------------|----------------------|
| ZOMBIE_ACTIVE | Kill plist immediately | Investigate how it got activated |
| ZOMBIE_MODIFIED | None | Review plist contents; delete if tampered |
| UNAUTHORIZED_DB_ACCESS | None | Review process, terminate if malicious |
| GOJ_TABLE_IN_REXXIE_DB | None | Investigate how GOJ data entered; audit + purge |
| UNEXPECTED_TABLE | None | Review; add to whitelist if legitimate |
| GOJ_DDL_PATTERN | None | Investigate schema change |
| REXXIE_BOT_ZOMBIE_PROCESS | None | Kill process, investigate source |
| TOKEN_CONFIG_TAMPERED | None | Restore config, rotate token |

The firewall does NOT auto-remediate data violations (only the zombie kill is automatic).
Data violations require Kato's review before action.

---

## Installing the Firewall

```bash
# Step 1: Copy LaunchAgent plist
cp ~/Desktop/REX/com.ghs.rexxie-firewall.plist ~/Library/LaunchAgents/

# Step 2: Load it
launchctl load ~/Library/LaunchAgents/com.ghs.rexxie-firewall.plist

# Step 3: Verify it's running
launchctl list | grep rexxie-firewall

# Step 4: Check logs
tail -f ~/Desktop/REX/logs/rexxie_firewall.log

# Step 5: Run a one-time check manually
source ~/.rex-venv/bin/activate
python ~/Desktop/REX/CC_rexxie_firewall.py --once
```

## Stopping the Firewall

```bash
launchctl unload ~/Library/LaunchAgents/com.ghs.rexxie-firewall.plist
```

## Checking Status Without the Daemon

```bash
source ~/.rex-venv/bin/activate
python ~/Desktop/REX/CC_rexxie_firewall.py --status
```

---

## Current Baseline (Audit — June 4 2026)

| Check | Status |
|-------|--------|
| Zombie plist exists | ❌ — ABSENT (ideal) |
| Zombie active in launchctl | ❌ — NOT RUNNING (safe) |
| rexxie.db exists | ✅ — 208KB, last modified May 28 |
| rexxie.db encryption | ✅ — App-level AES-256-GCM on all content columns |
| GOJ tables in rexxie.db | ✅ — NONE found |
| rexxie.db table count | 9 tables, all rexxie_* prefixed |
| rexxie_memory rows | 564 rows |
| Telegram config integrity | ✅ — owner_chat_id = 5587703834 (Kato) |
| Token conflicts | ✅ — None detected |

---

## Derivation

This document derives from:
- CLAUDE.md (BRAIN/MASTER.md) — the governing document
- Audit conducted 2026-06-04 by Hermes/Claude
- Source: ~/Desktop/REX/CC_rexxie_firewall.py (the enforcement engine)

Update this document when:
- New scripts are added that access rexxie.db (update authorized list)
- New tables are added to rexxie.db (update expected table list)
- Alert routing changes (update token priority)
- Kato changes any policy
