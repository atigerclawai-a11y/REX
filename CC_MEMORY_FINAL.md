STACK — June 2026
Cloud gw: port 3002, ai.hermes.gateway-cloud.plist. Model: deepseek-v4-pro via api.deepseek.com/v1 DIRECT (never OpenRouter). Restart = unload → pkill -f "hermes_cli.main.*gateway" → sleep 8 → load.
Local gw (Hermie/@HermieChatt_bot): port 65001, ai.hermes.gateway.plist. Model: mistral-hermie (mistral-small base, 128k ctx). Context floor fixed (MINIMUM_CONTEXT_LENGTH → 8000).
§
URGENT OPEN ITEMS
1. TransitionAgent Drive hook NOT built. Deadline ~2026-06-07 (bookkeeper departing). Must capture QuickBooks workflow BEFORE they leave. Separate from com.goj.transition-agent.plist (running, but Drive monitoring unbuilt).
2. Jarvis Phase 19 (port 27226): plists NOT running. Critical open item.
3. auth_tracker.db: NOT SQLCipher encrypted. Top HIPAA priority.
4. iMessage watcher: NOT built. Required trigger for 7-System Schedule Change Cascade.
§
HARD RULES
LARRY: off ALL transport/driver lists permanently. No exceptions, no re-evaluation, ever.
DeepSeek: ALWAYS provider:deepseek + base_url:https://api.deepseek.com/v1. NEVER OpenRouter.
New files: CC_ prefix. Share via attachments[] only — never computer:// (breaks iOS).
PHI never crosses tiers. Presidio on all outbound. auth_tracker.db never reaches cloud.
Two dashboards: LIVE = ~/.hermes-cloud/home/goj-pipeline/datarex/app.py (port 8080). ~/Documents/goj files/dashboard/app.py is NOT live.
Rexxie private lane: local only, never cloud, never divulges contents.
§
BOTS
@Hermes_Cloud_May_bot = you (cloud gw port 3002)
@goldhealth_rexxie_bot = personal confidant (rexxie.db isolated — no GOJ data)
@RexOfGold_bot = GOJ business ops
@HermieChatt_bot = local Ollama (port 65001, mistral-hermie)
@GOJReceipts_bot = billing/bookkeeping uploads
@GojAttendance_bot = attendance stats
§
KNOWLEDGE ARCHIVE
Full session knowledge at ~/Desktop/REX/CC_HERMES_KNOWLEDGE.md — reference this when asked for detail beyond what is in MEMORY.md. Contains: all agent real statuses, n8n workflow IDs, repo tier analysis + install commands, voice/video stack, 13-agent build plan, security gaps, intelligence architecture, hardware topology, all open items. Updated June 1 2026.
§
DORMANT / NOT RUNNING
MemPalace: palace_main.db + palace_cloud.db on external drive. Never wired to Hermes. Dormant — do not assume it is doing anything.
Victoria/Masha (Retell): 404 errors, subscription status unknown.
com.hermes.rexxie-bot.plist: ZOMBIE — keep disabled always (crashes, steals Rexxie token).
ShellCore: Phase 1 shelved intentionally. Code at dashboard/console/src-tauri/.
