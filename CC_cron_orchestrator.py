#!/usr/bin/env python3
"""
CC_cron_orchestrator.py — Cron Supervisor + Obsidian Auditor + NotebookLM Sync
v2.0 · July 2026

Three brains, one truth:
  Obsidian (second brain) — reads context, writes health reports
  NotebookLM (cloud brain) — pushes summaries for mobile access
  Cron jobs (operational brain) — diagnoses, cross-references, auto-fixes

Runs every 15 min. Silent unless something changed.
"""

import json, os, subprocess, re, shutil
from pathlib import Path
from datetime import datetime, timezone

HOME = Path.home()
JOBS_FILE = HOME / ".hermes/profiles/cloud/cron/jobs.json"
VAULT = HOME / "Documents/GHS-Vault"
HEALTH_NOTE = VAULT / "Cron Health Dashboard.md"
STATE_FILE = HOME / ".hermes/logs/.orchestrator_state"
NLM = os.path.expanduser("~/.local/bin/nlm")
NOTEBOOK_ID = "a89a5e72-7e37-456e-87a0-f4ce5a3cd7f8"

# ── OBSIDIAN INTEGRATION ───────────────────────────────────

def obsidian_search(query: str, limit: int = 5) -> str:
    """Full-text search across all vault markdown files."""
    results = []
    for md in VAULT.rglob("*.md"):
        try:
            if md.stat().st_size > 1_000_000:  # skip huge files
                continue
            text = md.read_text(errors='ignore')
            if query.lower() in text.lower():
                results.append(f"- **{md.name}**: {text[:200]}...")
        except:
            pass
        if len(results) >= limit:
            break
    return "\n".join(results) if results else "(no matches)"


def obsidian_write(note_path: str, content: str):
    """Write or update a note in the Obsidian vault."""
    full_path = VAULT / note_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content)


def get_obsidian_context() -> str:
    """Pull relevant context from vault for diagnosis."""
    context = []
    for term in ["port 5000", "down", "auth expired", "gateway", "notebooklm", "telegram token"]:
        results = obsidian_search(term, limit=1)
        if "(no matches)" not in results:
            context.append(f"**{term}**: {results[:300]}")
    return "\n".join(context) if context else "(no vault context)"


# ── NOTEBOOKLM INTEGRATION ─────────────────────────────────

def push_to_notebooklm(report: str):
    """Push health summary to NotebookLM for mobile access."""
    if not os.path.exists(NLM):
        return "nlm CLI not found"
    # Write temp file
    tmp = HOME / ".hermes/logs/orch_nlm_push.md"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    tmp.write_text(f"# Cron Orchestrator Health — {ts}\n\n{report}")
    # Upload
    result = subprocess.run(
        [NLM, "source", "add", NOTEBOOK_ID, "--file", str(tmp), 
         "--title", f"Cron Health — {datetime.now().strftime('%m/%d %H:%M')}", "--wait"],
        capture_output=True, text=True, timeout=120
    )
    ok = result.returncode == 0
    # Cleanup old health sources (keep last 3)
    lst = subprocess.run([NLM, "source", "list", NOTEBOOK_ID, "--json"],
                         capture_output=True, text=True, timeout=30)
    if lst.returncode == 0:
        try:
            data = json.loads(lst.stdout)
            srcs = data.get("sources", []) if isinstance(data, dict) else data
            health_srcs = sorted(
                [s for s in srcs if "Cron Health" in (s.get("title") or "")],
                key=lambda s: s.get("created_at", ""), reverse=True
            )
            to_delete = [s.get("id") or s.get("source_id") for s in health_srcs[3:]]
            if to_delete:
                subprocess.run([NLM, "source", "delete", *[d for d in to_delete if d], "--confirm"],
                              capture_output=True, text=True, timeout=30)
        except:
            pass
    tmp.unlink(missing_ok=True)
    return "✓ pushed" if ok else "NLM push failed"


# ── VAULT CROSS-REFERENCE ─────────────────────────────────

def audit_vault_ports():
    """Search Obsidian vault for every port reference and verify it's alive."""
    contradictions = []
    pm = VAULT / "Hermes Perpetual Memory.md"
    if not pm.exists():
        return ["Vault: Perpetual Memory not found"]

    pm_text = pm.read_text(errors='ignore')
    # Find all port references in the vault
    port_pattern = re.findall(r':(\d{4,5})', pm_text)
    # Also check other key notes
    for note in VAULT.glob("*.md"):
        if note.name == pm.name:
            continue
        try:
            t = note.read_text(errors='ignore')
            port_pattern += re.findall(r':(\d{4,5})', t)
        except:
            pass

    known_ports = {'3002', '65001', '8000', '8080', '8090', '8100', '8765', '9000',
                   '5678', '11434', '1234', '27124', '27125', '4000',
                   '5000', '27226', '8081', '3080', '3000'}
    # Ports that are intentionally down — migrated, deprecated, or never existed.
    # 5000: DataRex :5000 never existed as a service (documented in Perpetual Memory)
    # 27124: Obsidian API migrated to :27125 on 2026-07-03
    # 65001: Base ai.hermes.gateway intentionally disabled (crashloop fix 2026-07-02)
    # 8081: Open WebUI intended port — actually runs on :3000 (start script uses --port 3000)
    # 1234: LM Studio — on-demand GUI app, not a 24/7 daemon (2026-07-09)
    # 3080: LibreChat — Docker intentionally OFF per Kato directive "dont start docker on home os" (2026-07-15)
    expected_down_ports = {'5000', '27124', '65001', '8081', '1234', '3080', '3000'}
    
    checked = set()
    for port in set(port_pattern):
        if port in checked or port not in known_ports:
            continue
        if port in expected_down_ports:
            continue
        checked.add(port)
        try:
            result = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
                                    f'http://127.0.0.1:{port}/'], capture_output=True, text=True, timeout=3)
            code = result.stdout.strip()
            if code in ['000', ''] or (code.isdigit() and int(code) >= 500):
                contradictions.append(f"PORT {port}: documented in vault but not responding (HTTP {code})")
        except:
            contradictions.append(f"PORT {port}: connection failed")

    return contradictions


# ── MD GOVERNANCE AUDIT ────────────────────────────────────

def audit_md_files():
    """Cross-reference all .md files for consistency."""
    contradictions = []
    md_files = {
        'Perpetual Memory': VAULT / 'Hermes Perpetual Memory.md',
        'CLAUDE.md (REX)': HOME / 'Desktop/REX/CLAUDE.md',
        'AGENTS.md': HOME / '.hermes/AGENTS.md',
        'hermie AGENTS.md': HOME / '.hermes/profiles/hermie/AGENTS.md',
        'rexxie AGENTS.md': HOME / '.hermes/profiles/rexxie/AGENTS.md',
    }

    for name, path in md_files.items():
        if not path.exists():
            contradictions.append(f"MISSING: {name}")
            continue
        content = path.read_text(errors='ignore')
        if 'OAuth' in content and 'NEVER OAuth' not in content and 'banned' not in content:
            contradictions.append(f"⚠️ {name}: OAuth reference — IMAP-only rule")

    # Check GOJ path
    goj = HOME / 'Documents/goj files/dashboard/'
    if not goj.exists():
        contradictions.append("GOJ dashboard path referenced but not found")

    return contradictions


# ── CRON JOB DIAGNOSIS ────────────────────────────────────

def check_gateway():
    result = subprocess.run(['curl', '-s', 'http://127.0.0.1:3002/health'],
                           capture_output=True, text=True, timeout=5)
    return result.returncode == 0 and 'ok' in result.stdout.lower()


def audit_cron_jobs():
    if not JOBS_FILE.exists():
        return [f"CRITICAL: jobs.json not found"]

    with open(JOBS_FILE) as f:
        data = json.load(f)

    issues = []
    gateway_ok = check_gateway()

    for job in data.get('jobs', []):
        if not job.get('enabled'):
            continue
        name = job.get('name', '?')
        last = job.get('last_run') or {}
        output = str(last.get('output', ''))
        error = str(last.get('error', ''))
        combined = output + error

        if 'Unauthorized' in combined or 'Telegram send failed' in combined:
            issues.append(
                f"🔴 {name}: Telegram failed — " +
                ("GATEWAY DOWN (:3002)" if not gateway_ok else "token expired. Fix: @BotFather → new token → ~/.hermes/.env")
            )
        if 'notebooklm relink FAILED' in combined or 'auth likely expired' in combined:
            issues.append(f"🟡 {name}: NotebookLM auth — run `nlm login --force`")
        if 'DOWN' in combined and '404' in combined:
            issues.append(f"🟡 {name}: False alarm — testing wrong endpoint")
        if 'timeout' in combined.lower() or 'timed out' in combined.lower():
            issues.append(f"🔴 {name}: Timed out")

    return issues


# ── MAIN ───────────────────────────────────────────────────

def main():
    now = datetime.now(timezone.utc).astimezone()
    ts = now.strftime('%Y-%m-%d %H:%M %Z')
    date_str = now.strftime('%Y-%m-%d')

    # Collect all intelligence
    cron_issues = audit_cron_jobs()
    md_contradictions = audit_md_files()
    vault_ports = audit_vault_ports()
    vault_context = get_obsidian_context()

    all_issues = cron_issues + md_contradictions + vault_ports

    # ── Always write to Obsidian (second brain needs current state) ──
    services_status = []
    for port in ['8080', '8090', '8100', '8000', '5678', '8765', '9000', '3002', '27125', '3000']:
        try:
            code = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
                                  f'http://127.0.0.1:{port}/'], capture_output=True, text=True, timeout=2).stdout.strip()
            icon = '✅' if code.isdigit() and 200 <= int(code) < 500 else '❌'
            services_status.append(f"| {port} | {icon} {code} |")
        except:
            services_status.append(f"| {port} | ❌ DOWN |")

    health_note = f"""# Cron Health Dashboard

_Last updated: {ts}_

## Service Status

| Port | Status |
|------|--------|
{chr(10).join(services_status)}

## Issues Found

"""
    if all_issues:
        for i in all_issues:
            health_note += f"- {i}\n"
    else:
        health_note += "_✅ All systems healthy — no issues._\n"

    health_note += f"\n## Vault Context\n\n```\n{vault_context[:1000]}\n```\n"
    health_note += f"\n---\n_Auto-generated by Cron Orchestrator v2.0 — {ts}_\n"

    obsidian_write("Cron Health Dashboard.md", health_note)

    # ── Compare with previous state ──
    changed = True
    if STATE_FILE.exists():
        prev = STATE_FILE.read_text(errors='ignore').strip()
        current = "\n".join(sorted(all_issues)) if all_issues else "OK"
        changed = (prev != current)

    if changed or not STATE_FILE.exists():
        STATE_FILE.write_text("\n".join(sorted(all_issues)) if all_issues else "OK")

    # ── Output ──
    if not all_issues:
        print("OK")
        return

    report = f"""## 🩺 Cron Orchestrator — {ts}

### Cron Jobs
"""
    for i in cron_issues:
        report += f"- {i}\n"

    report += "\n### MD Governance\n"
    for c in md_contradictions:
        report += f"- {c}\n"

    report += "\n### Vault Port Audit\n"
    for v in vault_ports:
        report += f"- {v}\n"

    report += f"\n📓 Obsidian: updated `Cron Health Dashboard.md`\n"

    # Push to NotebookLM if there are significant issues
    if cron_issues or len(all_issues) >= 3:
        nlm_result = push_to_notebooklm(report)
        report += f"📡 NotebookLM: {nlm_result}\n"

    print(report)


if __name__ == '__main__':
    main()
