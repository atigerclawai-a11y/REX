#!/usr/bin/env python3
"""
GOJ Transition Agent — Production Pipeline Supervisor
Replaces departing employee's daily workflow.
Every run creates a dated folder in handoff_runs/ with generated files,
a customized RUN_REPORT.md, and a Telegram payload ready to send.
"""
import subprocess, sys, json, os, sqlite3, shutil, textwrap, glob
from datetime import datetime, timedelta, date
from pathlib import Path

# LibreOffice binary — try common macOS locations then fall back to PATH
_SOFFICE_CANDIDATES = [
    '/Applications/LibreOffice.app/Contents/MacOS/soffice',
    '/opt/homebrew/bin/soffice',
    '/usr/local/bin/libreoffice',
    'soffice',
    'libreoffice',
]
SOFFICE = next((c for c in _SOFFICE_CANDIDATES
                if c in ('libreoffice', 'soffice') or Path(c).exists()), 'libreoffice')

REX_DIR    = Path.home() / 'Desktop' / 'REX'
GOJ_DIR    = Path.home() / 'Documents' / 'goj files'
DB_PATH    = GOJ_DIR / 'dashboard' / 'auth_tracker.db'
DAILY_DIR  = GOJ_DIR / 'dashboard' / 'daily'
PRINT_DIR  = GOJ_DIR / 'documents' / 'print_sheets'
LOG_DIR    = REX_DIR / 'scheduled_task_logs'
RUNS_DIR   = REX_DIR / 'handoff_runs'
LOG_DIR.mkdir(exist_ok=True)
RUNS_DIR.mkdir(exist_ok=True)

NOW      = datetime.now()
TODAY    = NOW.strftime('%Y-%m-%d')
TOMORROW = (NOW + timedelta(days=1)).strftime('%Y-%m-%d')
D2       = (NOW + timedelta(days=2)).strftime('%Y-%m-%d')
WEEKDAY  = (NOW + timedelta(days=1)).strftime('%A')
RUN_TS   = NOW.strftime('%Y-%m-%d_%H%M')

def log(msg):
    ts = NOW.strftime('%H:%M:%S')
    print(f'[{ts}] {msg}')

def run_step(name, cmd, cwd=None):
    log(f'▶ {name}')
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                          timeout=300, cwd=cwd or str(REX_DIR))
        if r.returncode == 0:
            log(f'  ✅ {name}')
            return True, r.stdout.strip()[-300:]
        else:
            log(f'  ❌ {name} FAILED (exit {r.returncode}): {r.stderr.strip()[-200:]}')
            return False, r.stderr.strip()[-200:]
    except Exception as e:
        log(f'  ❌ {name} ERROR: {e}')
        return False, str(e)

# ── XLSX → PDF conversion ──────────────────────────────────────────────────────

def convert_xlsx_to_pdf(src_dir: Path, out_dir: Path) -> list:
    """
    Convert all *.xlsx files in src_dir to PDF using LibreOffice headless.
    PDFs land in out_dir. Returns list of PDF filenames created.
    """
    xlsx_files = list(src_dir.glob('*.xlsx'))
    if not xlsx_files:
        log('  ℹ No XLSX files to convert')
        return []

    # LibreOffice converts in-place into out_dir
    cmd = [
        SOFFICE, '--headless', '--convert-to', 'pdf',
        '--outdir', str(out_dir),
    ] + [str(f) for f in xlsx_files]

    log(f'▶ XLSX→PDF ({len(xlsx_files)} files)')
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            converted = [f.stem + '.pdf' for f in xlsx_files]
            log(f'  ✅ Converted: {", ".join(converted)}')
            return converted
        else:
            log(f'  ❌ LibreOffice convert failed: {r.stderr.strip()[-200:]}')
            return []
    except FileNotFoundError:
        log(f'  ❌ LibreOffice not found at: {SOFFICE}')
        return []
    except Exception as e:
        log(f'  ❌ Conversion error: {e}')
        return []

# ── DB metrics ─────────────────────────────────────────────────────────────────

def db_metrics():
    """Pull live GOJ metrics for the report."""
    m = {
        's1_count': 0, 's2_count': 0, 'total_scheduled': 0,
        'auth_expiring_30': 0, 'auth_expired': 0, 'auth_active': 0,
        'menu_coverage_pct': 0, 'week_start': '', 'no_menu_count': 0,
    }
    if not DB_PATH.exists():
        return m
    try:
        day_map = {0:'M', 1:'T', 2:'W', 3:'TH', 4:'F', 5:'SA'}
        tomorrow = date.fromisoformat(TOMORROW)
        day_key  = day_map.get(tomorrow.weekday(), 'M')
        week_start = (tomorrow - timedelta(days=tomorrow.weekday())).isoformat()
        m['week_start'] = week_start

        con = sqlite3.connect(str(DB_PATH))
        cur = con.cursor()

        # Scheduled clients per shift (using client_menus for the day)
        cur.execute(
            "SELECT COUNT(*) FROM client_menus WHERE day=? AND week_start=? AND shift=1",
            (day_key, week_start)
        )
        m['s1_count'] = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*) FROM client_menus WHERE day=? AND week_start=? AND shift=2",
            (day_key, week_start)
        )
        m['s2_count'] = cur.fetchone()[0]

        # Fall back to clients table if no menu data
        if m['s1_count'] + m['s2_count'] == 0:
            cur.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND shift=1")
            row = cur.fetchone()
            m['s1_count'] = row[0] if row else 0
            cur.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND shift=2")
            row = cur.fetchone()
            m['s2_count'] = row[0] if row else 0

        m['total_scheduled'] = m['s1_count'] + m['s2_count']

        # Auth alerts
        cur.execute(
            "SELECT COUNT(*) FROM authorization WHERE status='ACTIVE' "
            "AND service_end_date BETWEEN ? AND ?",
            (TODAY, (date.today() + timedelta(days=30)).isoformat())
        )
        m['auth_expiring_30'] = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM authorization WHERE status='EXPIRED'")
        m['auth_expired'] = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM authorization WHERE status='ACTIVE'")
        m['auth_active'] = cur.fetchone()[0]

        # Menu coverage for tomorrow
        cur.execute(
            "SELECT COUNT(*) FROM client_menus WHERE day=? AND week_start=? AND main IS NOT NULL",
            (day_key, week_start)
        )
        menu_filled = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*) FROM client_menus WHERE day=? AND week_start=?",
            (day_key, week_start)
        )
        menu_total = cur.fetchone()[0]

        if menu_total > 0:
            m['menu_coverage_pct'] = round(100 * menu_filled / menu_total)
        m['no_menu_count'] = menu_total - menu_filled

        con.close()
    except Exception as e:
        log(f'  ⚠ DB metrics error: {e}')
    return m

# ── Copy generated files to handoff run folder ─────────────────────────────────

def collect_files(run_dir: Path):
    """
    1. Convert XLSXs from goj_generate_daily → PDFs in run_dir.
    2. Copy PDFs from generate_distribution_sheet + generate_kitchen_sheet.
    Returns list of filenames in run_dir.
    """
    copied = []

    # Convert XLSXs from goj_generate_daily (daily/TOMORROW/) to PDFs
    src_daily = DAILY_DIR / TOMORROW
    if src_daily.exists() and any(src_daily.glob('*.xlsx')):
        pdfs = convert_xlsx_to_pdf(src_daily, run_dir)
        copied.extend(pdfs)
    elif src_daily.exists():
        log('  ℹ No XLSX files found in daily/TOMORROW/ — daily steps may have failed')

    # Copy PDFs from distribution + kitchen scripts (print_sheets/)
    if PRINT_DIR.exists():
        today_dt = date.today()
        for f in sorted(PRINT_DIR.glob('*.pdf')):
            if datetime.fromtimestamp(f.stat().st_mtime).date() >= today_dt:
                dest = run_dir / f.name
                shutil.copy2(str(f), str(dest))
                copied.append(f.name)
                log(f'  📄 Copied: {f.name}')

    return copied

# ── Build customized run report ────────────────────────────────────────────────

def write_run_report(run_dir: Path, results: dict, m: dict, copied: list):
    passed  = sum(1 for v in results.values() if v[0])
    failed  = len(results) - passed
    status  = '✅ ALL CLEAR' if failed == 0 else f'⚠️ {failed} STEP(S) FAILED'
    auth_ok = '✅' if m['auth_expiring_30'] == 0 else f'⚠️  {m["auth_expiring_30"]} expiring in 30 days'
    menu_ok = '✅' if m['no_menu_count'] == 0 else f'⚠️  {m["no_menu_count"]} clients missing menus'

    lines = [
        f'# GOJ Handoff Run — {WEEKDAY}, {TOMORROW}',
        f'**Generated:** {NOW.strftime("%Y-%m-%d %H:%M")}  |  **Status:** {status}',
        '',
        '## Operations Summary',
        f'| Metric | Value |',
        f'|--------|-------|',
        f'| Clients scheduled tomorrow | {m["total_scheduled"]} ({m["s1_count"]} S1 / {m["s2_count"]} S2) |',
        f'| Menu coverage | {m["menu_coverage_pct"]}% — {menu_ok} |',
        f'| Active authorizations | {m["auth_active"]} |',
        f'| Auth expiring ≤30 days | {auth_ok} |',
        f'| Expired authorizations | {m["auth_expired"]} |',
        '',
        '## Steps',
        '| Step | Result | Output |',
        '|------|--------|--------|',
    ]
    step_labels = {
        'daily_shift1':  'Daily Docs — Shift 1 (signin + driver)',
        'daily_shift2':  'Daily Docs — Shift 2 (signin + driver)',
        'distribution':  'Distribution Sheet',
        'kitchen':       'Kitchen Count',
        'auth_check':    'Authorization Check',
        'attendance':    'Attendance Reconciliation',
    }
    for k, (ok, out) in results.items():
        icon  = '✅' if ok else '❌'
        label = step_labels.get(k, k)
        snippet = out.replace('\n', ' ').strip()[:80]
        lines.append(f'| {label} | {icon} | {snippet} |')

    lines += [
        '',
        '## Files Generated',
    ]
    if copied:
        for f in copied:
            lines.append(f'- `{f}`')
    else:
        lines.append('- *(no files copied — check step failures above)*')

    if failed > 0:
        lines += ['', '## Failures', '```']
        for k, (ok, out) in results.items():
            if not ok:
                lines.append(f'{step_labels.get(k,k)}: {out}')
        lines.append('```')

    (run_dir / 'RUN_REPORT.md').write_text('\n'.join(lines))

def write_telegram_payload(run_dir: Path, results: dict, m: dict):
    passed = sum(1 for v in results.values() if v[0])
    failed = len(results) - passed

    alert_lines = []
    if m['auth_expiring_30'] > 0:
        alert_lines.append(f'⚠️ {m["auth_expiring_30"]} auth(s) expiring in ≤30 days')
    if m['no_menu_count'] > 0:
        alert_lines.append(f'⚠️ {m["no_menu_count"]} client(s) missing menus for tomorrow')
    if m['auth_expired'] > 0:
        alert_lines.append(f'🔴 {m["auth_expired"]} expired authorizations on file')
    alerts_text = '\n'.join(alert_lines) if alert_lines else '✅ No alerts'

    step_icon = '✅' if failed == 0 else f'❌ {failed} step(s) failed'

    msg = textwrap.dedent(f"""\
        📋 <b>GOJ Daily Handoff — {WEEKDAY} {TOMORROW}</b>

        👥 Clients: <b>{m['total_scheduled']}</b> ({m['s1_count']} S1 / {m['s2_count']} S2)
        🍽 Menu coverage: <b>{m['menu_coverage_pct']}%</b>
        🔑 Auth active: <b>{m['auth_active']}</b>

        {alerts_text}

        📦 Pipeline: {step_icon}
        🕐 Run: {NOW.strftime('%H:%M')}
    """)

    (run_dir / 'telegram_message.txt').write_text(msg)

    # One-shot send script
    script = textwrap.dedent(f"""\
        #!/bin/bash
        # Send GOJ handoff Telegram alert
        # Usage: bash send_telegram_alert.sh
        TOKEN=$(python3 -c "import json; print(json.load(open('{REX_DIR}/rex_rexxie_telegram_config.json'))['telegram_token'])" 2>/dev/null || echo "")
        CHAT_ID="5587703834"
        MSG=$(cat "$(dirname "$0")/telegram_message.txt")
        curl -s -X POST "https://api.telegram.org/bot${{TOKEN}}/sendMessage" \\
          -d chat_id="$CHAT_ID" \\
          -d parse_mode="HTML" \\
          --data-urlencode text="$MSG"
        echo ""
        echo "Sent."
    """)
    script_path = run_dir / 'send_telegram_alert.sh'
    script_path.write_text(script)
    script_path.chmod(0o755)

# ── Google Drive upload ────────────────────────────────────────────────────────

TOKEN_PATH = Path.home() / '.rex_google_token.json'
CREDS_PATH = REX_DIR / 'google_credentials.json'

SCOPES = [
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.readonly',
]

# Filename substring → GOJ Drive folder ID
DRIVE_FOLDER_MAP = [
    ('SIGNIN',        '1znUHkOMfuSQo9iK1Nnz-SSoWVZdnax6H'),  # Sign-In Sheets
    ('DRIVER',        '1JCh5oQt9yJODyLB5PGdTLCjxku3a17HG'),  # Driver Sheets
    ('FOOD_DIST',     '1m8GAglqzBKEdrDuU5Am08Hl9MHnOqhsG'),  # Distribution Sheets
    ('distribution_', '1m8GAglqzBKEdrDuU5Am08Hl9MHnOqhsG'),  # Distribution Sheets (print)
    ('KITCHEN',       '1o56SCqK7QZVcDorAo1oyOAwiEu4CyVu8'),  # Kitchen Counts
    ('kitchen_',      '1o56SCqK7QZVcDorAo1oyOAwiEu4CyVu8'),  # Kitchen Counts (print)
]
DRIVE_FALLBACK = '1ct8yaXdN29OUZ_FXFZCSSu0_VeKOOXgB'  # GOJ Operations root
SUMMARY_TO     = 'atigerclawai@gmail.com'


def _get_google_creds():
    """Return valid Google credentials, refreshing if expired. None if unavailable."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError:
        log('  ⚠ google-auth not installed — skipping Drive/Gmail steps')
        return None
    if not TOKEN_PATH.exists():
        log(f'  ⚠ Google token missing — run: python backend/rex_gmail.py --setup')
        return None
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json())
        except Exception as e:
            log(f'  ⚠ Token refresh failed: {e}')
            return None
    return creds


def _drive_folder_for(filename: str) -> str:
    for keyword, folder_id in DRIVE_FOLDER_MAP:
        if keyword.lower() in filename.lower():
            return folder_id
    return DRIVE_FALLBACK


def goj_drive_upload(run_dir: Path, copied: list) -> dict:
    """Upload all PDFs from the run folder to their correct GOJ Drive folders."""
    drive_results = {}
    if not copied:
        return drive_results

    creds = _get_google_creds()
    if not creds:
        return drive_results

    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        log('  ⚠ google-api-python-client not installed')
        return drive_results

    svc = build('drive', 'v3', credentials=creds)

    for fname in copied:
        fpath = run_dir / fname
        if not fpath.exists():
            drive_results[fname] = {'ok': False, 'error': 'file not found'}
            continue
        folder_id = _drive_folder_for(fname)
        mime = 'application/pdf' if fname.lower().endswith('.pdf') else 'application/octet-stream'
        try:
            meta  = {'name': fname, 'parents': [folder_id]}
            media = MediaFileUpload(str(fpath), mimetype=mime, resumable=False)
            f     = svc.files().create(body=meta, media_body=media,
                                       fields='id,name,webViewLink').execute()
            log(f'  ☁ {fname} → Drive')
            drive_results[fname] = {
                'ok': True, 'file_id': f['id'],
                'web_link': f.get('webViewLink', ''), 'folder_id': folder_id,
            }
        except Exception as e:
            log(f'  ❌ Drive upload failed: {fname}: {e}')
            drive_results[fname] = {'ok': False, 'error': str(e)[:200]}

    ok_count = sum(1 for v in drive_results.values() if v.get('ok'))
    log(f'  Drive: {ok_count}/{len(copied)} uploaded')
    return drive_results


# ── Gmail summary ──────────────────────────────────────────────────────────────

def gmail_send_summary(m: dict, results: dict, drive_results: dict):
    """Send an HTML daily ops summary email with Drive links to Kato."""
    import base64
    from email.mime.text import MIMEText

    creds = _get_google_creds()
    if not creds:
        return False
    try:
        from googleapiclient.discovery import build
    except ImportError:
        return False

    svc = build('gmail', 'v1', credentials=creds)

    passed = sum(1 for v in results.values() if v[0])
    failed = len(results) - passed
    status_line = '✅ All systems go' if failed == 0 else f'⚠️ {failed} step(s) failed'

    step_labels = {
        'daily_shift1': 'Daily Docs S1', 'daily_shift2': 'Daily Docs S2',
        'distribution': 'Distribution Sheet', 'kitchen': 'Kitchen Count',
        'auth_check': 'Auth Check', 'attendance': 'Attendance',
    }

    drive_rows = ''
    for fname, dr in drive_results.items():
        if dr.get('ok') and dr.get('web_link'):
            drive_rows += f'<tr><td><a href="{dr["web_link"]}">{fname}</a></td><td>✅</td></tr>'
        elif dr.get('ok'):
            drive_rows += f'<tr><td>{fname}</td><td>✅ (no link)</td></tr>'
        else:
            drive_rows += f'<tr><td>{fname}</td><td>❌ {dr.get("error","")[:60]}</td></tr>'
    if not drive_rows:
        drive_rows = '<tr><td colspan="2">No files uploaded</td></tr>'

    step_rows = ''.join(
        f'<tr><td>{"✅" if ok else "❌"} {step_labels.get(k,k)}</td>'
        f'<td style="font-size:11px;color:#555">{out.replace(chr(10)," ").strip()[:100]}</td></tr>'
        for k, (ok, out) in results.items()
    )

    body_html = f"""\
<html><body style="font-family:Arial,sans-serif;font-size:14px;color:#222;">
<h2 style="color:#1a5276;">GOJ Daily Handoff — {WEEKDAY}, {TOMORROW}</h2>
<p><b>Status:</b> {status_line} &nbsp;|&nbsp; <b>Run:</b> {NOW.strftime('%Y-%m-%d %H:%M')}</p>
<h3 style="color:#1a5276;">Operations</h3>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;border-color:#ccc;">
  <tr><td>Clients tomorrow</td><td><b>{m['total_scheduled']}</b> ({m['s1_count']} S1 / {m['s2_count']} S2)</td></tr>
  <tr><td>Menu coverage</td><td>{m['menu_coverage_pct']}%{"  ⚠️ "+str(m['no_menu_count'])+" missing" if m["no_menu_count"] else "  ✅"}</td></tr>
  <tr><td>Active auths</td><td>{m['auth_active']}</td></tr>
  <tr><td>Auth expiring ≤30d</td><td>{"⚠️ "+str(m["auth_expiring_30"]) if m["auth_expiring_30"] else "✅ 0"}</td></tr>
  <tr><td>Expired auths</td><td>{"🔴 "+str(m["auth_expired"]) if m["auth_expired"] else "✅ 0"}</td></tr>
</table>
<h3 style="color:#1a5276;">Files → Google Drive</h3>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;border-color:#ccc;">{drive_rows}</table>
<h3 style="color:#1a5276;">Pipeline</h3>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;border-color:#ccc;">{step_rows}</table>
<p style="color:#aaa;font-size:11px;margin-top:16px;">GOJ Transition Supervisor</p>
</body></html>"""

    msg = MIMEText(body_html, 'html')
    msg['to']      = SUMMARY_TO
    msg['subject'] = f'[GOJ] Daily Handoff — {WEEKDAY} {TOMORROW} | {status_line}'
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    try:
        svc.users().messages().send(userId='me', body={'raw': raw}).execute()
        log(f'  📧 Summary email → {SUMMARY_TO}')
        return True
    except Exception as e:
        log(f'  ❌ Email send failed: {e}')
        return False

# ── Main ────────────────────────────────────────────────────────────────────────

def main(mode='full'):
    log(f'GOJ Transition Supervisor — {TODAY} — mode={mode}')

    # Create dated run folder
    run_dir = RUNS_DIR / f'{TODAY}_{NOW.strftime("%I%p").lower()}'
    run_dir.mkdir(parents=True, exist_ok=True)
    log(f'Run folder: {run_dir}')

    results = {}

    # Step 1: Daily docs Shift 1 (signin + driver + food_dist + kitchen in one call)
    # goj_generate_daily.py: positional date, --shift {1,2}
    if mode in ('full', 'am'):
        results['daily_shift1'] = run_step('Daily Docs Shift 1',
            f'python3.11 goj_generate_daily.py --shift 1 {TOMORROW}')

    # Step 2: Daily docs Shift 2
    if mode in ('full', 'am'):
        results['daily_shift2'] = run_step('Daily Docs Shift 2',
            f'python3.11 goj_generate_daily.py --shift 2 {TOMORROW}')

    # Step 3: Distribution PDF (no --shift; default output = print_sheets/)
    if mode in ('full', 'am'):
        results['distribution'] = run_step('Distribution Sheet',
            f'python3.11 generate_distribution_sheet.py --date {TOMORROW}')

    # Step 4: Kitchen Count for D+2
    if mode in ('full', 'am'):
        results['kitchen'] = run_step('Kitchen Count',
            f'python3.11 generate_kitchen_sheet.py --date {D2}')

    # Step 5: Authorization Check
    if mode in ('full', 'am'):
        results['auth_check'] = run_step('Auth Check',
            f'python3.11 rex_daily_curriculum.py --check-auth --date {TOMORROW}')

    # Step 6: Attendance Reconciliation (PM) — uses --from/--to
    if mode in ('full', 'pm'):
        results['attendance'] = run_step('Attendance Reconciliation',
            f'python3.11 goj_attendance_report.py --from {TODAY} --to {TODAY}')

    # Summary
    passed = sum(1 for v in results.values() if v[0])
    failed = len(results) - passed
    log(f'DONE: {passed} passed, {failed} failed')

    # Pull live DB metrics
    m = db_metrics()

    # Collect generated files into run folder
    copied = collect_files(run_dir)
    log(f'Files collected: {len(copied)} → {run_dir.name}/')

    # Upload to Google Drive
    log('▶ Google Drive upload')
    drive_results = goj_drive_upload(run_dir, copied)

    # Write customized report and Telegram payload
    write_run_report(run_dir, results, m, copied)
    write_telegram_payload(run_dir, results, m)
    log(f'RUN_REPORT.md and telegram_message.txt written')

    # Send Gmail summary with Drive links
    log('▶ Gmail summary')
    gmail_send_summary(m, results, drive_results)

    # Save JSON for programmatic use
    drive_ok = sum(1 for v in drive_results.values() if v.get('ok'))
    report = {
        'date': TODAY,
        'tomorrow': TOMORROW,
        'mode': mode,
        'passed': passed,
        'failed': failed,
        'metrics': m,
        'files': copied,
        'drive_uploaded': drive_ok,
        'drive_results': {k: {'ok': v.get('ok'), 'web_link': v.get('web_link', '')}
                          for k, v in drive_results.items()},
        'results': {k: {'ok': v[0], 'output': v[1][:500]} for k, v in results.items()},
    }
    json_path = LOG_DIR / f'transition_{TODAY}_{mode}.json'
    with open(json_path, 'w') as f:
        json.dump(report, f, indent=2)

    return 0 if failed == 0 else 1

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'full'
    sys.exit(main(mode))
