# 14-Day Build Inventory — 2026-05-26 → 2026-06-09

> Generated 2026-06-09 by Claude Code. Read-only scan across the filesystem, Claude Code session transcripts (`~/.claude/projects/*/*.jsonl`), Cowork session data, and `~/.hermes/MASTERLIST.md`.
> Newest first. Each entry: **name** — path — one-line description — [source].

---

## Summary

- **Window:** 2026-05-26 through 2026-06-09 (14 days).
- **Primary build zone:** `~/Desktop/REX/` (the `CC_*` artifact namespace) — ~280 files touched in window.
- **Approximate genuine artifacts catalogued:** ~660 files (excludes backups, cloned framework trees, runtime session dumps, logs, and the auto-generated screensaver gallery).
- **Source counts (where evidence came from):**
  - **filesystem** — ~660 dated artifacts across REX, hermes-hub, workspace, .hermes, .rex_infra, Gold_Health_Systems/BRAIN, GHS-Vault.
  - **cc-session** — 33 Claude Code session transcripts in window; the busiest (`d1a19021`, 437 file ops; `b4d79449`, 361; `28caf1c3`, 343; `53906123`, 224) drove the REX / hermes-hub / Tiger Claw HUD builds.
  - **cowork** — **FOUND.** Cowork VM data lives at `~/Library/Application Support/Claude/local-agent-mode-sessions/eca54719…/dc2e0e34…/`, logs at `~/Library/Logs/Claude/cowork_vm_*.log` + `coworkd.log`, settings at `…/cowork_settings.json`. 39 in-window deliverables found under the per-session `outputs/` folders.
  - **masterlist** — `~/.hermes/MASTERLIST.md` (1,475 lines) dated running-log confirmed/enriched the REX + GOJ pipeline builds.
- **Big multi-file builds in window:** Tiger Claw Command Center HUD (`~/workspace/hud/`, ~31 files), the tigerclaw-screensaver gallery (354 generated HTML — counted as ONE build), GHS BRAIN knowledge base (~75 markdown), hermes-hub web app (`~/hermes-hub/www/`), GOJ Pipeline v2 automation, and the Rex+Rexxie board deck (Cowork + CC).

> **Note on noise excluded:** backup dirs (`CC_june4_backup_*`, `hermes_critical_backup`, `CC_backups`, `GOJ_Backups`, `_backups`, BRAIN/backups), cloned frameworks (`REX/ecc/`, `.hermes/hermes-agent/`, `graphify_obsidian`, `Documents/comfy/ComfyUI`), `.hermes/sessions/` request dumps, `.hermes/cron/output/`, and `REX/logs/` were scanned but are not listed as builds.

---

## 2026-06-09

- **CC_infra_sentinel.py** — `~/.rex_infra/CC_infra_sentinel.py` — Infra sentinel agent: monitors services, writes `last_report.json` / `build_registry.json` / `alert_state.json`; root-caused goldhealthsys.com duplicate-zone DNS issue. — [filesystem, cc-session, masterlist]
- **CC_safe_update.py** — `~/Desktop/REX/CC_safe_update.py` — Safe-update agent (loop ASK #1); guarded config/update path. — [filesystem, masterlist]
- **CC_latest_build_finder.py** — `~/Desktop/REX/CC_latest_build_finder.py` — Finds the most-recent build artifact; writes `~/.rex_infra/build_finder_last.json`. — [filesystem]
- **CC_victoria_goj_integration.py** — `~/Desktop/REX/CC_victoria_goj_integration.py` — Victoria voice-agent ↔ GOJ integration (6 edits this session). — [filesystem, cc-session]
- **CC_victoria_report.html** — `~/Desktop/REX/CC_victoria_report.html` — Victoria call/activity report UI. — [filesystem]
- **CC_goj_live.html / CC_goj_live.py** — `~/Desktop/REX/CC_goj_live.{html,py}` — GOJ Live attendance dashboard + backend feed (9 edits each). — [filesystem, cc-session]
- **CC_transition_drive_hook.py** — `~/Desktop/REX/CC_transition_drive_hook.py` — TransitionAgent Drive hook, 60s polling (launchd `com.goj.transition-drive-hook`); state in `.transition_drive_hook_state.json`. — [filesystem, masterlist]
- **CC_hub_user.py** — `~/Desktop/REX/CC_hub_user.py` — Hub user management for the demo/read-only account (5 edits). — [filesystem, cc-session]
- **CC_cf_add_rex_cname.sh** — `~/Desktop/REX/CC_cf_add_rex_cname.sh` — Cloudflare CNAME-add script for rex/jarvis subdomains. — [filesystem]
- **rex_rexxie_telegram_bot.py** — `~/Desktop/REX/rex_rexxie_telegram_bot.py` — Rexxie Telegram bot. — [filesystem]
- **CC_social_media_router.py** — `~/Desktop/REX/CC_social_media_router.py` — Social-media dispatch router (10 edits this session). — [filesystem, cc-session]
- **CC_goj_drive_ingest.py** — `~/Desktop/REX/CC_goj_drive_ingest.py` — GOJ Drive ingest (10 edits); state in `.goj_drive_ingest_state.json`. — [filesystem, cc-session]
- **Rex + Rexxie board deck** — CC session `b4d79449` — `generate_rex_rexxie_deck.py`, `build_board_deck{,_v2,_v3}.js`, `build_booklet_pdf.py`, `build_printfriendly_proposal.py`, `deck_server.py` — board-deck/PDF generators for the Rex+Rexxie proposal. — [cc-session]
- **hermes-hub web app (refresh)** — `~/hermes-hub/www/{index,jarvis,login,docs,notebook}.html` + `server.py` + `auth.json` — Hermes Hub site + server updated. — [filesystem, cc-session]
- **jarvis-deploy/index.html** — `~/workspace/jarvis-deploy/index.html` — Jarvis deploy page → serves the real Tiger Claw Command Center on hermestigerclaw.com. — [filesystem, masterlist]
- **MASTERLIST.md (running log)** — `~/.hermes/MASTERLIST.md` — 8 new dated log entries (Infra Sentinel, domain switch, Jarvis fix, demo account, read-only walls, System Health fix). — [filesystem, cc-session, masterlist]
- **GHS BRAIN / GHS Live (daily)** — `~/Desktop/Gold_Health_Systems/BRAIN/GHS Live/{TODAY_LOG,SYSTEM_STATUS,GOJ_TODAY,BUILD_STATUS,ALERTS}.md` — daily knowledge-base status pages. — [filesystem]
- **.hermes runtime state** — `~/.hermes/{processes,hub_sync,health-state,gateway_state,channel_directory,auth,cron/jobs}.json` + `logs/ecosystem_changelog.md` — orchestrator/runtime state refresh. — [filesystem]

## 2026-06-09 (PM session highlights — from MASTERLIST)

- **Domain switch to hermestigerclaw.com** — diagnosed goldhealthsys.com pending-duplicate-zone (inert CNAMEs); moved to the working domain. — [masterlist]
- **24h full-access DEMO account + maintenance banner**, then **locked to read-only + personal data walled off**, then **sample-data tiles** (not blank/real). — [masterlist]

---

## 2026-06-08

- **CC_goj_drive_ingest.py** — `~/Desktop/REX/CC_goj_drive_ingest.py` — Drive→Dashboard pipeline brought fully live (OAuth scope-gap fix; canonical token rewritten). — [filesystem, cc-session, masterlist]
- **CC_ocr_worker.py** — `~/Desktop/REX/CC_ocr_worker.py` — OCR worker for the menu/paperwork pipeline. — [filesystem, cc-session]
- **CC_ocr_telegram_fallback.py** — `~/Desktop/REX/CC_ocr_telegram_fallback.py` — OCR-fail Telegram fallback; tested live (5 PDFs → @RexOfGold_bot), fixed Markdown parse-mode bug. — [filesystem, masterlist]
- **CC_rex_bill.py / CC_rex_bill_dashboard.html** — `~/Desktop/REX/CC_rex_bill.{py,html}` — Rex Bill billing module + dashboard (`/ui` route shipped). — [filesystem, cc-session, masterlist]
- **CC_quickbooks_capture.py / .html** — `~/Desktop/REX/CC_quickbooks_capture.{py,html}` — QuickBooks capture router + UI. — [filesystem, masterlist]
- **CC_telegram_present_bot.py** — `~/Desktop/REX/CC_telegram_present_bot.py` — "present-mark" Telegram bot; state in `.telegram_present_bot_state.json`. — [filesystem]
- **CC_loop_examiner.py** — `~/Desktop/REX/CC_loop_examiner.py` — Loop examiner agent; output `CC_loop_report_latest.md`. — [filesystem]
- **CC_build_monitor.py** — `~/Desktop/REX/CC_build_monitor.py` — Build monitor. — [filesystem]
- **CC_hub_security_sweep.py** — `~/Desktop/REX/CC_hub_security_sweep.py` — Hub security sweep. — [filesystem]
- **rex_red_team.py** — `~/Desktop/REX/rex_red_team.py` — Red-team security probe. — [filesystem]
- **CC_kato_hub.html / CC_login.html / CC_settings.html** — `~/Desktop/REX/CC_{kato_hub,login,settings}.html` — Hub front-end pages (login + settings). — [filesystem]
- **BBG NBA Finals social pack** — `~/Desktop/REX/CC_bbg_knicks_finals_menu.png`, `CC_bbg_knicks_square.jpg`, `CC_bbg_instagram_caption.txt` — BBG Knicks-finals menu graphic + IG caption. — [filesystem]
- **Audit + handoff docs** — `~/Desktop/REX/CC_{website_audit_june8,attendance_audit_2026-06-08,PAE_assessment_2026-06-08,DRIVE_SOURCE_MAP_2026-06-08,OCR_HANDOFF_june8,CLAUDE_HANDOFF_june8,CLAUDECODE_HANDOFF_june8,hermes_sync_brief}.md` — audit reports + cross-agent handoffs. — [filesystem, masterlist]
- **CC_full_system_audit.command / CC_gmail_reauth.command** — `~/Desktop/REX/CC_*.command` — full-system audit runner + Gmail re-auth helper. — [filesystem]
- **hermes-hub server + pages** — `~/hermes-hub/{server.py,hermes_agent_server.py,obsidian_api_server.py,_audit.py,_audit.sh}` + `www/{command,settings,notebooklm}.html` — Hermes Hub backend + command/settings/NotebookLM pages (CC sessions `9dc573d0`, `3404f8d1`, `d1a51cd9`, `0b9e6ad5`). — [filesystem, cc-session]
- **hermes-toggle / daily-debugpy** — CC session `6f1b6d15` — `hermes-toggle`, `daily_debugpy.sh`, `com.kato.daily-debugpy.plist`, settings.json edits. — [cc-session]
- **GHS BRAIN MASTER.md** — `~/Desktop/Gold_Health_Systems/BRAIN/MASTER.md` — BRAIN reconciliation (entries tagged "reconciled 2026-06-08"). — [filesystem, masterlist]
- **NotebookLM_State_2026-06-08.md** — `~/Documents/GHS-Vault/NotebookLM_State_2026-06-08.md` — refreshed NotebookLM-ready inventory. — [filesystem, masterlist]
- **Graphify vault graph** — `~/Documents/GHS-Vault/graphify-out/{graph.html,GRAPH_REPORT.md,2026-06-08/manifest.json}` — Obsidian vault graph visualization output. — [filesystem]
- **MASTERLIST refresh** — `~/.hermes/MASTERLIST.md` (prior backed up to `MASTERLIST_outdated_2026-06-08.md`) — refreshed Section 1 + new subsections 9G–9J + running log. — [filesystem, masterlist]
- **Cowork: build_signin.py + command-center v2 assets** — `…/outputs/build_signin.py`, `CC_command_center_v2.html`, `CC_p1_*/CC_p2_*` (html/css/js fragments), `CC_hermes_goj_knowledge.md`, `CC_hermes_change_log_2026.md`, `obsidian_daemon.log`, `.obsidian_state.json` — Cowork-side command-center v2 page build + sign-in builder + Hermes knowledge docs. — [cowork]

## 2026-06-08 — Large CC build sessions (multi-file)

- **Tiger Claw / Hermes ecosystem session** — `d1a19021` (437 file ops): heavy `server.py` (87), `index.html` (50), `config.yaml` (49), `goj_runner_base.py` (36), `.env` (31), `run.py`, `viewer.py`, `routes.py`, `imessage_watcher.py` — Hermes/REX server + GOJ runner consolidation. — [cc-session]
- **HUD/Tiger Claw + Docker session** — `49e44664` (176 ops): `index.html` (35), `config.yaml` (20), `docker-guardian` (11), `hermestigerclaw.yml` (9), `server.py`, `serve.py`, `main.py`, `rex_passkey.py`, `homebrew.mxcl.ollama.plist` — HUD + Docker/Cloudflare + passkey. — [cc-session]
- **GOJ watchers + timeclock session** — `53906123` (224 ops): `index.html` (62), `app.py` (20), `goj_gmail_watcher.py`, `goj_drive_watcher.py`, `com.goj.drive-watcher.plist`, `authorize_drive.py` — GOJ Gmail/Drive watchers + Drive auth. — [cc-session]
- **OCR / menu-scan session** — `af3ce3ee` (70 ops): `main.cjs` (14), `rex_menu_scan_watcher.py`, `claudeseek_runner.py`, `goj_menu_consensus_ocr.py`, `goj_menu_ocr.py`, `kanban_db.py`, `com.cloudflare.*.plist` — menu OCR consensus + Cloudflare tunnels. — [cc-session]
- **Timeclock app session** — `8b1b4c35` (44 ops): `app.py`, `nightly_handoff.py`, `dashboard.html`, `db.py`, `router_poll.py`, `register{,_success}.html`, `com.goj.timeclock.plist`, `com.goj.router-poll.plist` — GOJ employee timeclock web app + poller. — [cc-session]
- **Cloud workspace/landing session** — `21230ad2` (28 ops): `config.yaml`, `docker-compose.yml`, `hermestigerclaw.yml`, `com.hermes.{landing,cloud-workspace,workspace}.plist`, `TEMPLATE_menu_personalized_sample.pdf` — Hermes cloud workspace + landing plists. — [cc-session]

---

## 2026-06-07

- **CC_command_center.html** — `~/Desktop/REX/CC_command_center.html` — Tiger Claw Command Center page (Phase 2 plan in `CC_command_center_PHASE2_PLAN.md`). — [filesystem, cc-session]
- **CC_employee_clock.html** — `~/Desktop/REX/CC_employee_clock.html` — Employee clock-in UI. — [filesystem]
- **CC_auth_db.py / CC_lead_connector.db** — `~/Desktop/REX/CC_auth_db.py`, `CC_lead_connector.db` — Auth DB layer + lead-connector SQLite. — [filesystem]
- **CC_google_reauth.py / .command + CC_google_token_refresh.py** — `~/Desktop/REX/CC_google_*` — Google OAuth re-auth + token refresh utilities. — [filesystem]
- **CC_encrypt_auth_tracker.sh / CC_daily_backup.sh** — `~/Desktop/REX/CC_*.sh` (also `~/.hermes/scripts/CC_daily_backup.sh`, `CC_health_loop.sh`) — auth-tracker encryption + daily backup + health loop. — [filesystem]
- **rex_proximity_daemon.py / rex_phone_unlock.py** — `~/Desktop/REX/rex_*.py` — proximity daemon + phone-unlock (state `.proximity_state.json`). — [filesystem, cc-session]
- **goj_victoria_caller.py / goj_victoria_webhook.py** — `~/Desktop/REX/goj_victoria_*.py` — Victoria outbound caller + Retell webhook. — [filesystem]
- **CC_transition_drive_watcher.py** — `~/Desktop/REX/CC_transition_drive_watcher.py` — 5-min Drive watcher feeding `transition_supervisor.py` (later superseded by the hook). — [filesystem, masterlist]
- **CC_ocr_live_watcher.py / CC_start_receipts_bot.command** — `~/Desktop/REX/CC_*` — live OCR watcher + receipts-bot launcher. — [filesystem]
- **Railway deploy package** — `~/Desktop/REX/CC_railway_deploy/` + `railway.toml`, `.railwayignore`, `index.html` (CC session `b8ace6a3`) — Railway deployment scaffold for the REX site. — [filesystem, cc-session]
- **Reference / planning docs** — `~/Desktop/REX/CC_{HUB_MASTER_REFERENCE,HERMES_KNOWLEDGE,NEXT_STEPS,alienware_integration_plan,CLAUDE_RAILWAY_BUILD,CLAUDE_RAILWAY_BUILD_OUTPUT,CLAUDE_GAP_ANALYSIS,CLAUDE_GAP_OUTPUT,CLAUDE_CODE_COMMAND_CENTER,CLAUDE_AUDIT,CLAUDE_AUDIT_OUTPUT}.md` — hub reference + gap analysis + Railway build docs. — [filesystem, cc-session]
- **Tiger Claw HUD jarvis.html (major)** — CC session `28caf1c3` (343 ops): `jarvis.html` (79), `server.py` (78), `goj_runner_base.py`, `goj_drive_watcher.py`, `palace_ingest.py`/`palace_drive.py`/`palace_common.py`/`palace_manifest.py` (MemPalace), `reauth_gmail.py` — Jarvis HUD + MemPalace ingest pipeline. — [cc-session]
- **hermes-hub terminal + security** — `~/hermes-hub/{secmod.py,scan_results.json,pin.json}` + `www/terminal.html` — hub security module + terminal page. — [filesystem]
- **GHS-Vault graphify-out (2026-06-07)** — `~/Documents/GHS-Vault/graphify-out/2026-06-07/` + `screensaver.html` — vault graph snapshot. — [filesystem]

---

## 2026-06-06

- **CC_kanban_center.html** — `~/Desktop/REX/CC_kanban_center.html` — Kanban center UI. — [filesystem]
- **CC_fix_hermes_cloud.command / CC_hermes_cloud_fix_handoff.md** — `~/Desktop/REX/CC_*` — Hermes cloud fix script + handoff. — [filesystem]
- **MASTER_GOVERNANCE corpus (CC session e32b3b10)** — `MASTER_GOVERNANCE.md` (6 edits), `CORPUS_MANIFEST.json`, `USAGE_GUIDE.md`, `DAY_0_LAUNCH_READINESS_REPORT.md`, `COMPLEXITY_BUDGET_RULE.md`, `CLINE_NEXT_SAFE_TASKS.md`, plus several `*_2026-05-16.md` review/audit reports — governance/corpus documentation set. — [cc-session]
- **Tiger_Claw_Blueprint_2026-06-06.md** — referenced in CC session `556c141b` — Tiger Claw blueprint doc. — [cc-session]
- **tigerclaw-screensaver gallery (partial)** — `~/workspace/tigerclaw-screensaver/` — 34 HTML files generated this day (part of the 354-file generated gallery; counted as one build). — [filesystem]

---

## 2026-06-05

- **transition_supervisor.py** — `~/Desktop/REX/transition_supervisor.py` — TransitionAgent supervisor (full-run orchestrator). — [filesystem]
- **CC_voice_integration.py** — `~/Desktop/REX/CC_voice_integration.py` — Voice-agent integration layer (guide in `CC_VOICE_INTEGRATION_GUIDE.md`, dated 06-04). — [filesystem]
- **CC_unified_gateway_auth.py / CC_gateway_auth_proxy.py** — `~/Desktop/REX/CC_*` — unified gateway auth + auth proxy. — [filesystem]
- **CC_stats_api.py** — `~/Desktop/REX/CC_stats_api.py` — Stats API (installed as launchd `com.ghs.cc-stats-api`; install/restart commands). — [filesystem, masterlist]
- **CC_rexxie_firewall.py** — `~/Desktop/REX/CC_rexxie_firewall.py` — Rexxie firewall (rules in `CC_REXXIE_FIREWALL_RULES.md`; launchd `com.ghs.rexxie-firewall`). — [filesystem]
- **CC_kanban_drive_monitor.py / CC_group_chat_scheduler.py** — `~/Desktop/REX/CC_*` — kanban Drive monitor + group-chat scheduler. — [filesystem]
- **SOUL / memory install set** — `~/Desktop/REX/CC_{install_real_soul,install_memories,restore_soul_from_backup,find_soul_backup,soul_restore_auto,soul_fix_now,hermes_rebuild_soul}.command` + `~/.hermes/SOUL.md`, `HERMES_FLOW_MAP.md` — Hermes "soul"/memory restore tooling. — [filesystem]
- **Hermes recovery command suite** — `~/Desktop/REX/CC_hermes_{full_recovery,fix_provider,fix_identity,fix_config_v2,dump_config,diag,check_and_fix,read_memories,read_env,restore_config,status_check}.command` — large batch of Hermes diagnostic/fix scripts. — [filesystem]
- **Tunnel/port fix suite** — `~/Desktop/REX/CC_{fix_tunnel,patch_tunnel,patch_tunnel_auto,tunnel_diag,fix_8080,diagnose_8080,fix_hermes_gateway,fix_hermes_webui,fix_domain_tonight,revive_all,revive_webui,docker_force_restart}.command` — Cloudflare tunnel + gateway recovery. — [filesystem]
- **CC_setup_screensaver.command** — `~/Desktop/REX/CC_setup_screensaver.command` — screensaver installer (CC sessions `19a4a866`, `f388669b`). — [filesystem, cc-session]
- **Build reports** — `~/Desktop/REX/CC_build_report_june5.py`, `CC_build_progress_report_june5.pdf`, `CC_GHS_BUILD_REPORT_June5_2026.pdf`, `CC_clover_research.md` — build-progress reporting + Clover POS research. — [filesystem]
- **GHS BRAIN knowledge base (~37 docs)** — `~/Desktop/Gold_Health_Systems/BRAIN/*.md` — full BRAIN module set authored/refreshed: `REX.md`, `Rexxie.md`, `Hermes`, `Security.md`, `Routes.md`, `Billing.md`, `LeadConnector.md`, `MenuPipeline.md`, `PaperworkAgent.md`, `PAEEngine.md`, `CronGuardian.md`, `HR.md`, `MemPalace.md`, `SOUL.md`, `MEMORY.md`, `Agent_Activity_Log.md`, plus `GHS Live/*`. — [filesystem]
- **GOJ_WORKING_DOC.md** — `~/Desktop/Gold_Health_Systems/GOJ_WORKING_DOC.md` — GOJ working document. — [filesystem]
- **.hermes/claus reports** — `~/.hermes/claus/report_latest.{md,json}`, `~/.hermes/tasks.json`, `portal-auth.json` — Claus watchman latest report + task state. — [filesystem]
- **Cowork: screenshot-1780687344952.jpg** — Cowork `outputs/` UI capture (verification screenshot). — [cowork]

---

## 2026-06-04

> Largest single-day artifact count (124 files). GOJ Pipeline v2 deployment + a broad agent/dashboard build-out.

- **GOJ Pipeline v2** — `~/Desktop/REX/goj_generate_daily.py` + 7 daily crons (Observer 5:30AM → Mirror 5:35AM → sign-in/drivers/distribution/kitchen/menus/absentee) — full GOJ automation from proprietary DB; 411 clients, 5K schedules, 1.8K menus; outputs to Telegram. — [filesystem, masterlist]
- **launchd plists (6)** — `~/Desktop/REX/com.ghs.{rexxie-firewall,obsidian-daemon,gateway-watchdog,gateway-auth,doc-overseer,cc-stats-api}.plist` — service definitions for the agent stack. — [filesystem]
- **CC_claus_orchestrator.py** — `~/Desktop/REX/CC_claus_orchestrator.py` — Claus orchestration agent (brief in `CC_CLAUS_ORCHESTRATION_BRIEF.md`). — [filesystem]
- **CC_doc_overseer.py** — `~/Desktop/REX/CC_doc_overseer.py` — Documentation overseer agent (rules in `CC_DOC_OVERSEER_RULES.md`, readme `CC_DOCUMENTATION_AGENT_README.md`; launchd `com.ghs.doc-overseer`). — [filesystem]
- **CC_paperwork_agent.py** — `~/Desktop/REX/CC_paperwork_agent.py` — Paperwork agent (+ `CC_start_paperwork_agent.command`). — [filesystem]
- **CC_ocr_oversight_agent.py** — `~/Desktop/REX/CC_ocr_oversight_agent.py` — OCR oversight agent. — [filesystem]
- **CC_gateway_watchdog.py** — `~/Desktop/REX/CC_gateway_watchdog.py` — Gateway watchdog (launchd `com.ghs.gateway-watchdog`; enhancement proposal `CC_gateway_enhancement_proposal.md`). — [filesystem]
- **CC_cron_guardian.py** — `~/Desktop/REX/CC_cron_guardian.py` — Cron guardian (+ `CC_install_cron_guardian.command`). — [filesystem]
- **CC_obsidian_live_daemon.py** — `~/Desktop/REX/CC_obsidian_live_daemon.py` — Obsidian live-sync daemon (launchd `com.ghs.obsidian-daemon`; CC sessions `19a4a866`). — [filesystem, cc-session]
- **CC_analytics_engine.py** — `~/Desktop/REX/CC_analytics_engine.py` — Analytics engine. — [filesystem]
- **CC_security_scanner.py** — `~/Desktop/REX/CC_security_scanner.py` — Security scanner (+ `CC_run_security_scan.command`). — [filesystem]
- **CC_carerex_module1.py** — `~/Desktop/REX/CC_carerex_module1.py` — CareRex module 1. — [filesystem]
- **CC_datarex_app_current.py** — `~/Desktop/REX/CC_datarex_app_current.py` — DataRex app (current snapshot). — [filesystem]
- **CC_akc_tokenizer_v2.py** — `~/Desktop/REX/CC_akc_tokenizer_v2.py` — AKC PHI tokenizer v2 (Fernet-encrypted token map). — [filesystem]
- **CC_firewall_endpoint_patch.py** — `~/Desktop/REX/CC_firewall_endpoint_patch.py` — Rexxie firewall endpoint patch. — [filesystem]
- **CC_drive_roster_sync.py** — `~/Desktop/REX/CC_drive_roster_sync.py` — Drive roster sync. — [filesystem]
- **CC_lead_connector_api.py / CC_lead_connector.html** — `~/Desktop/REX/CC_lead_connector*` — Lead Connector API + UI (build plan `CC_LEAD_CONNECTOR_BUILD_PLAN.md`). — [filesystem]
- **CC_social_media_router.py / CC_social_media_command_center.html** — `~/Desktop/REX/CC_social_media_*` — social-media router + command center (`CC_social_drafts.json`; guides `CC_SOCIAL_REBUILD_GUIDE.md`, `CC_SOCIAL_HERMES_SKILL.md`). — [filesystem]
- **CC_masha_bbg_integration.py** — `~/Desktop/REX/CC_masha_bbg_integration.py` — Masha (BBG) voice integration. — [filesystem]
- **CC_hermes_knowledge_injector.py** — `~/Desktop/REX/CC_hermes_knowledge_injector.py` — Injects GOJ knowledge into Hermes (`CC_hermes_goj_knowledge.md`, `CC_hermes_change_log_2026.md`). — [filesystem, cowork]
- **Dashboard/UI pages** — `~/Desktop/REX/CC_{mission_control,home_base,web_rack,live_progress,live_progress_v2,attendance_bot_command_center,social_media_command_center}.html` — multiple command/dashboard UIs. — [filesystem]
- **CC_TOOL_REGISTRY.{md,json}** — `~/Desktop/REX/CC_TOOL_REGISTRY.*` — agent tool registry. — [filesystem]
- **Master build docs** — `~/Desktop/REX/CC_{MASTER_BUILD_LOG,GHS_MASTER_BUILD_DOC,GHS_AUTONOMOUS_BUILD_PLAN,PHASE_STATUS,SESSION_LOG_20260604,RND_REPORT_june4,repo_analysis_june4,audit_report_june4,alienware_gameplan,DESIGN_UPGRADE_GUIDE,OBSIDIAN_DASHBOARD_GUIDE}.md` — build logs, phase status, R&D + repo audit reports. — [filesystem]
- **CC_signin_*.xlsx** — `~/Desktop/REX/CC_signin_thursday_1st.xlsx`, `CC_signin_automated_latest.xlsx` — automated GOJ sign-in workbooks. — [filesystem]
- **Config snapshots** — `~/Desktop/REX/CC_{profile_config_current,profile_config_before_gemma4,config_current,config_pre_incident}.yaml`, `CC_config_diff_june4.txt` — Hermes config snapshots + diff. — [filesystem]
- **Cowork: nba_finals_setup.py (06-03) + command-center v2 fragments** — see Cowork outputs; `build_signin.py` and CC_p1/p2 HTML/CSS/JS fragments landed in the Cowork `outputs/` folder this day. — [cowork]

---

## 2026-06-03

- **goj_menu_consensus_ocr.py** — `~/Desktop/REX/goj_menu_consensus_ocr.py` — multi-pass consensus OCR for GOJ menus. — [filesystem, cc-session]
- **CC_menu_constants.py / CC_menus_dir_setup.command** — `~/Desktop/REX/CC_menu*` — menu constants + menus-dir setup. — [filesystem]
- **CC_gdrive_mirror.py / .command** — `~/Desktop/REX/CC_gdrive_mirror*` — Google Drive mirror. — [filesystem]
- **Hermes venv-fix suite** — `~/Desktop/REX/CC_hermes_{fix_venv2..6,rebuild_venv,fix_restart,restart,telegram_fix}.command` — Hermes virtualenv rebuild/restart batch. — [filesystem]
- **Gateway diag suite** — `~/Desktop/REX/CC_{gateway_quickcheck,gateway_errlog,gateway_diag,fix_rex_ssl,fix_everything,fix_all,dock_watchdog,dock_diag}.command` — gateway diagnostics + SSL/dock fixes. — [filesystem]
- **Install commands** — `~/Desktop/REX/CC_{install_pdf_watcher_plist,install_hermes_desktop,install_ecc}.command` — installers (PDF-watcher plist, Hermes desktop, ECC). — [filesystem]
- **CC_restart_gateway.scpt / CC_test.scpt** — `~/Desktop/REX/CC_*.scpt` — AppleScript gateway restart helpers. — [filesystem]
- **knicks build set (workspace)** — `~/workspace/{knicks_menu.py,build_knicks_tv.py,build_knicks_menu.py,clover_push.py}` — Knicks-finals menu/TV builders + Clover push. — [filesystem]
- **HUD api-server + hermes bridge** — `~/workspace/hud/{api-server.py,hermes_to_ag.py,SYSTEM_CONTEXT.md}` — HUD API server + Hermes→AntiGravity bridge. — [filesystem]
- **.hermes/scripts/claus_watchman.sh + memories** — `~/.hermes/scripts/claus_watchman.sh`, `~/.hermes/memories/{USER,MEMORY}.md` — Claus watchman script + memory files. — [filesystem]
- **tigerclaw-screensaver gallery (bulk)** — `~/workspace/tigerclaw-screensaver/` — 110 generated HTML files this day (part of the one screensaver gallery build). — [filesystem]

---

## 2026-06-02

- **goj_daily_scheduler.py** — `~/Desktop/REX/goj_daily_scheduler.py` — GOJ daily scheduler. — [filesystem]
- **reauth_google_full.py** — `~/Desktop/REX/reauth_google_full.py` — full Google OAuth re-auth. — [filesystem]
- **rex_telegram_config.json / rex_rexxie_telegram_config.json / rex_notify_config.json** — `~/Desktop/REX/rex_*.json` — Telegram + notify configs. — [filesystem]
- **Skills catalog PDFs** — `~/Desktop/REX/CC_skills_{top_picks,top_picks_v2,most_active,full_list,full_list_v2,complete_catalog}.pdf` — generated ECC skills catalog/report PDFs. — [filesystem]
- **Setup/fix commands** — `~/Desktop/REX/CC_{setup_paperless,kill_zombie_start_claus,install_telegram_plist,health_check,fix_telegram_bot,fix_gmail_oauth,fix_all_launchd_venvs}.command` — paperless setup, Claus start, Telegram plist, OAuth + launchd venv fixes. — [filesystem]

---

## 2026-06-01

- **CLAUDE.md** — `~/Desktop/REX/CLAUDE.md` — REX project instructions for Claude Code. — [filesystem]
- **SOUL / memory drafts** — `~/Desktop/REX/CC_{SOUL_FINAL_SHORT,SOUL_DRAFT_v5.2,MEMORY_FINAL,HERMES_KNOWLEDGE,DIAGNOSTIC_REPORT_20260601}.md` — Hermes soul/memory final drafts + diagnostic. — [filesystem]
- **Gateway/port diagnosis suite (~35 commands)** — `~/Desktop/REX/CC_{fix_local_gateway,fix_local_gateway2,verify_local_gateway,verify_local_gateway2,diagnose_local_port,deep_diagnose_port,test_port_resolution,trace_gateway_config,fix_gateway_json,fix_gateway_and_restart,fix_env_port,fix_display_port,fix_display_port2,fix_api_server_port,find_real_api_server,find_api_server_config,fix_context_floor,fix_ollama_ctx,instrument_and_restart,instrument2,switch_to_mistral,…}.command` — deep gateway/port/context troubleshooting batch. — [filesystem]
- **Memory lock/install commands** — `~/Desktop/REX/CC_{lock_memories,unlock_memories,set_memory_pin,install_soul_memory,install_karpathy,install_hermes_dreaming}.command` — memory lock/PIN + soul/skill installers. — [filesystem]
- **CC_wire_ecc_hermes.command / CC_wire_ecc_claude.command** — `~/Desktop/REX/CC_wire_ecc_*` — wire ECC rules into Hermes + Claude. — [filesystem]
- **Memory feedback rules (CC session 968300ee)** — `~/.claude/.../feedback_prefer_uv_and_ollama.md`, `feedback_no_paid_apis.md`, `MEMORY.md` — auto-memory rules written. — [cc-session]
- **workspace discord fixes** — `~/workspace/{fix_discord.js,fix_discord_pw.js,package.json,package-lock.json}` — Discord fix scripts. — [filesystem]
- **hermes-hub/www/screensaver.html** — `~/hermes-hub/www/screensaver.html` — hub screensaver page. — [filesystem]
- **Cowork: screenshot-1780298276547.jpg** — Cowork `outputs/` UI capture. — [cowork]

---

## 2026-05-31

- **download_menu_pdfs_impl.py** — `~/Desktop/REX/download_menu_pdfs_impl.py` — menu-PDF downloader implementation. — [filesystem]
- **SOUL drafts v2–v5** — `~/Desktop/REX/CC_SOUL_DRAFT{,_v2,_v3,_v4,_v5}.md`, `CC_MEMORY_DRAFT.md`, `CC_HERMES_SELFTEST_PROMPT.md` — iterative Hermes soul/memory drafts + self-test prompt. — [filesystem]
- **Session docs** — `~/Desktop/REX/CC_{SESSION_LOG_2026-05-31,SESSION_HANDOFF_May31_2026,SESSION_MASTER_BACKUP_May31_2026,KNOWLEDGE_STATE_May31_2026}.md` — session log/handoff/knowledge-state. — [filesystem]
- **Hermes fix commands** — `~/Desktop/REX/CC_{install_soul_v52,hermes_upgrade,fix_yaml_and_restart,fix_kimi_placement,fix_google_token,ecc_install_claude,diagnose_local_gateway,diagnose_local_gateway2,restart_hermes_cloud,backup_to_drive}.command` — soul install, model placement, token + gateway fixes, Drive backup. — [filesystem]

---

## 2026-05-30

- **hermes_CLAUDE.md** — `~/Desktop/REX/hermes_CLAUDE.md` — Hermes Claude instructions. — [filesystem]
- **CC_rex_backend.sh** — `~/Desktop/REX/CC_rex_backend.sh` — REX backend launch script. — [filesystem]
- **Model upgrade commands** — `~/Desktop/REX/CC_{upgrade_models_opus_gemini35,upgrade_fallback_to_sonnet,fix_model_and_fallback,hermes_best_fit_fallback}.command` — model/fallback upgrades (Opus + Gemini 3.5 / Sonnet fallback). — [filesystem, masterlist]
- **Hermes diagnosis/fix batch** — `~/Desktop/REX/CC_{hermes_nuclear_fix,hermes_full_diagnosis,hermes_code_dump,update_hermes_memory,update_hermes_cloud_token,show_hermes_memory,read_hermes_memory,dump_hermes_brain,fix_hermes_cloud_yaml,fix_hermes_cloud_token,fix_hermes_allowlist,kill_token_conflict,identify_pid77588,check_provider_error,check_gateway_status,check_claude_code,restart_rexxie,bot_status_check,show_error_log,find_receipts_bot,yaml_direct_fix}.command` — large Hermes recovery/diagnostic batch. — [filesystem]

---

## 2026-05-29

> Part of the "8-Day Build Sprint — MCP Ecosystem + HUD Rebuild + REX Lock" (per MASTERLIST).

- **Tiger Claw Command Center HUD (workspace/hud)** — `~/workspace/hud/` — full HUD site: `dashboard.html`, `dashboard_GOLDEN.html`, `launcher.html`, `webrex.html`, `voice.html`, `settings.html`, `personal.html`, `orgagent.html`, `conductor.html`, `billrex.html`, `screensaver.html`, `api-server.py`, `api-server_GOLDEN.py`, `hud_site_server.py`, `set-site-password.py`, `hot-corner-watcher.js`, `screensaver-launcher.sh`, `com.tigerclaw.{hudsite,api}.plist`, `HERMES_REVIEW_*.md` — gated Tiger Claw Command Center (per MASTERLIST: permanent gated hud on :27223). — [filesystem, masterlist]
- **org-agent** — `~/workspace/org-agent/organize.py` + `reports/REPORT-20260529-*.md` — org agent (read+propose scanner) with run reports. — [filesystem]
- **REX daily-ops API endpoints (M01–M12)** — per MASTERLIST: 12 daily-ops module API endpoints built; `~/Desktop/REX/MODULE_STATUS.md`, `ACTIVE_SYSTEM_MANIFEST.json`. — [filesystem, masterlist]
- **Phases 14–19 locked (Packet B)** — per MASTERLIST running log. — [masterlist]
- **hermes-hub PWA shell** — `~/hermes-hub/www/{service-worker.js,manifest.json}`, `~/hermes-hub/api_keys.json` — hub PWA service worker + manifest. — [filesystem]
- **WebUI/gateway check commands** — `~/Desktop/REX/CC_{webui_port_probe,webui_check_fix,restart_hermes_workspace,restart_hermes_gateway,owui_cloud_connect,openwebui_connect_cloud,hermes_gateway_probe,hermes_gateway_check,hermes_fix_context_and_update,hermes_diagnose,hermes_deep_diag,hermes_cloud_webui_fix,full_recovery,bots_webui_check_and_start}.command` — WebUI/gateway connect + recovery batch. — [filesystem]
- **tigerclaw-screensaver gallery (start)** — `~/workspace/tigerclaw-screensaver/` — 20 HTML files generated this day. — [filesystem]
- **Cowork: screenshot-1780068869689.jpg** — Cowork `outputs/` UI capture. — [cowork]

---

## 2026-05-28

- **goj_menu_ocr.py** — `~/Desktop/REX/goj_menu_ocr.py` — GOJ menu OCR. — [filesystem]
- **goj_doc_patterns.json** — `~/Desktop/REX/goj_doc_patterns.json` — document-pattern definitions for OCR. — [filesystem]
- **run_gemini_thursday_2026-05-28.py / test_config.py** — `~/Desktop/REX/*.py` — Thursday Gemini run + config test. — [filesystem]
- **HUD vellum bridge + antigravity** — `~/workspace/hud/{vellum-bridge.sh,fix-vellum.sh,screensaver_GOLDEN.html,com.tigerclaw.screensaver.plist,ANTIGRAVITY_PROMPT.md,ANTIGRAVITY_PROMPT_V2.md,ANTIGRAVITY_AUDIT.md}` — Vellum bridge + AntiGravity prompts/audit + golden screensaver. — [filesystem]
- **hermes-hub jarvis-iphone + webauthn** — `~/hermes-hub/www/jarvis-iphone.html`, `~/hermes-hub/webauthn/credentials.json`, `~/hermes-hub/rexxie_fortress.py` — iPhone Jarvis page + WebAuthn creds + Rexxie fortress. — [filesystem]
- **.hermes/scripts/rex_backup_ssh.sh** — `~/.hermes/scripts/rex_backup_ssh.sh` — SSH backup script. — [filesystem]
- **GHS-Vault session docs (per MASTERLIST)** — `~/Documents/GHS-Vault/{Session_Debrief_2026-05-28.md,NotebookLM_State_2026-05-28.md,Trello_Cards_2026-05-28.json}` — sprint session debrief + NotebookLM state + Trello export. — [masterlist]

---

## 2026-05-27

- **goj_10am_telegram_message_2026-05-28.txt** — `~/Desktop/REX/goj_10am_telegram_message_2026-05-28.txt` — generated 10AM GOJ Telegram message. — [filesystem]
- **goj-ai-copies (workspace)** — `~/workspace/goj-ai-copies/{ocr_pin_matcher.py,pin_map.json}` — OCR pin-matcher + pin map. — [filesystem]
- **HUD deploy.sh** — `~/workspace/hud/deploy.sh` — HUD deploy script. — [filesystem]
- **Cowork: GOJ Thursday report set** — `…/outputs/{thursday_full.json,thursday_clients.json,anticipated_signin_2026-05-28.txt,rex_email_body.{txt,html},_email_payload.json,goj_dropoff_report.txt,_goj_report_data.json}` — Cowork-generated GOJ Thursday sign-in/drop-off report + email payload. — [cowork]

---

## 2026-05-26

> All from the Cowork environment (`…/local_*/outputs/`).

- **Naomi Pastel Rainbow Workbook** — `…/outputs/Naomi_Pastel_Rainbow_Workbook.pdf` + `build_workbook.py` + `workbook.html` + page renders `p-01.png … p-12.png` — Cowork-built 12-page illustrated workbook (build script + HTML + PDF + page images). — [cowork]

---

## Where Cowork data lives (for reference)

- **Session store:** `~/Library/Application Support/Claude/local-agent-mode-sessions/eca54719-0914-489c-8b03-f9e55b1ee7f4/dc2e0e34-92f9-4101-82c7-ff1c7be17685/` — per-session `local_<uuid>.json` + `local_<uuid>/outputs/` deliverables.
- **Settings/caches:** `…/cowork_settings.json`, `…/cowork-clientdata-cache.json`, `…/cowork-gb-cache.json`, `~/Library/Application Support/Claude/cowork-enabled-cli-ops.json`.
- **VM logs:** `~/Library/Logs/Claude/cowork_vm_node.log`, `cowork_vm_node1.log`, `cowork_vm_swift.log`, `coworkd.log` (Ubuntu 22.04 microVM; recovered 733 users on 2026-06-07 boot).
- **Older Cowork session log (out of window):** `~/Documents/goj files/dashboard/cowork_session_log.txt` (Mar 26 — merge_clients.py / akc_tokenizer.py task log).
