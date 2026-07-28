# Red Team Findings — 2026-07-08 20:15 EDT (00:15 UTC July 9)

## Critical (needs immediate attention)

- [ ] **ChatGPT Bridge DOWN — MCP transport broken** — Both `hermes_status` and `hermes_list_projects` return `ClosedResourceError`. The HTTP bridge on :7000 is ALIVE (serves Hermes Build Status slideshow) but the MCP subprocess (`chatgpt_bridge_mcp.py`) has broken transport. Two instances spawned (PID 13456, 13786) plus a separate HTTP server (PID 6731). The bridge was RECOVERED ~08:00, then DOWN again by 16:03 — this is a persistent flip-flop (3 state changes in 24h).
- [ ] **Local Gateway :65001 DOWN** (5+ days, unchanged). No process listening. Blocks all local-profile agent sessions including REXXIE's primary gateway.
- [ ] **Open WebUI :8081 DOWN** (unchanged). No process listening. Root cause of n8n ShellCore Health Watchdog cascading failure — watchdog calls `GET http://127.0.0.1:8081/console/agents` every 5 min and always fails.
- [ ] **n8n ShellCore Health Watchdog errors every 5 min** — workflow `2rAqHTiiwTXQJyY5`. Calls dead :8081 endpoint continuously. Burns n8n execution quota.

## High (should fix within 24h)

- [ ] **9/25 cron delivery errors (36%)** — Unchanged from prior audit. Breakdown: 6x "unknown platform 'webui'" (Daily Graphify, Hermes Watchdog, Red Team, Blue Team, n8n Daily Backup, n8n Hourly Snapshot), 2x "no delivery target resolved for deliver=telegram" (Wiki Health Report, Wiki Daily Digest), 1x "no delivery target resolved for deliver=all" (Session Learning Loop). The WebUI delivery path is structurally broken — these jobs need either `telegram` with a valid chat_id or `local`.
- [ ] **Hermes System Integrity Watchdog error every 60 min** (job `86b7a055e06f`) — CONFIG DRIFT: work fallback chain has trailing comma (malformed second entry). Also webhook 404: watchdog POSTs to n8n "watchdog-alert" webhook which is not registered.
- [ ] **Email Intake cron error every 3 min** (job `5035221135ce`, no_agent) — `himalaya envelope list` times out after 15 seconds. Blocks GOJ document intake via email. Root cause: IMAP connection slow or himalaya config issue.
- [ ] **NotebookLM handoff 38.9h stale** — latest handoff `handoff_2026-07-07.md` (July 7 05:16 UTC). No July 8 handoff generated. Worsening from 34.8h in prior audit.
- [ ] **Session Brief 7.6h stale** (last modified 12:31 EDT). Was 3.5h at prior audit — getting worse. Header claims "ChatGPT Bridge RECOVERED" — it's now DOWN again.
- [ ] **MASTERLIST 2 days stale** (last modified Jul 6, 1714 lines). The ecosystem's comprehensive reference is aging.

## Medium (notable but not urgent)

- [ ] **Perpetual Memory footer timestamp 6.7h behind mtime** — Memory Injector overwrites the file but doesn't update the footer.
- [ ] **Business memory 7 days stale** — `higgsfield_business_memory.json` v3.1.0, last updated July 1.
- [ ] **cron jobs all show runs=0** — jobs.json records run_count=0 for all 25 jobs despite some clearly executing. Hermes cron engine reporting bug.
- [ ] **n8n execution logs show anonymous workflow names ("?")** — ShellCore Health Watchdog error logs show `workflowName: "?"`. n8n version/data integrity bug.

## MCP Bridge Status — MAJOR IMPROVEMENT Since Last Audit

11 of 11 previously-down MCP bridges RECOVERED. Only ChatGPT Bridge remains broken.
The MCP cascade that dominated the 16:03 audit has fully resolved. Bridges self-healed without intervention.

Full MCP status: openai ✅, claude_api ✅, grok ✅, perplexity ✅, tavily ✅, groq ✅, elevenlabs ✅, builds ✅, sites ✅, mistral ✅, notebooklm ✅, ghs_knowledge ✅, openrouter ✅, antigravity ✅. gmail ⚠️ (unconfigured by design). codex ⚠️ (CLI not installed). chatgpt_bridge ❌.

## Cross-Reference Drift

| System A | Claims | System B | Actual | Delta |
|----------|--------|----------|--------|-------|
| Session Brief header | "ChatGPT Bridge RECOVERED" | Chat Bridge MCP | ClosedResourceError — DOWN | REGRESSION |
| Session Brief header | "4 CRITICAL" | This audit | 4 CRITICAL | 0 ✅ |
| Perpetual Memory footer | "12:30 EDT" | File mtime | 19:10 EDT | +6.7h |
| NotebookLM | Handoff July 7 | Latest | 38.9h old | Missing July 8 |
| Session Brief | "41 sources" | NotebookLM API | 41 | 0 ✅ |

## System Health Summary

| System | Status | Issues |
|--------|--------|--------|
| Hermes cron | 🔴 16/25 healthy (9 delivery errors) | 6 "unknown webui", 2 "no telegram target", 1 "no all target", 2 job errors, 1 paused |
| n8n | 🔴 10/13 active, 1 erroring continuously | ShellCore Watchdog errors every 5 min |
| Obsidian | 🟢 Perpetual Memory fresh (1h), Session Brief stale (7.6h) | Session Brief ChatGPT status wrong |
| NotebookLM | 🟢 configured, 41 sources | Handoff 38.9h stale |
| Ports | 🔴 25/27 UP | :65001 DOWN 5d+, :8081 DOWN |
| MCP Bridges | 🟢 14/15 responding | Only ChatGPT Bridge DOWN |
| Netlify | 🟢 6 sites deployed | All resolving |
