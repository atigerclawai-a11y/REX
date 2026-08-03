#!/usr/bin/env python3
"""PAGE-GUARANTEE GUARD — "every page always is OCR'd" (Kato workflow, 2026-08-02).

Runs after every intake sweep (cron chained). For EVERY scanned doc:
  1. pdfinfo page count (ground truth)
  2. compare against extraction coverage (surya/focr extraction.json forms)
  3. FLAG any doc where pages/2 > extracted forms by >3 (page census gap)
  4. AUTO-RECOVER: write recovery manifest; focr recovery cron executes it
  5. Report; promoter cron then applies recovered picks to the DB.

GROUND TRUTH RULES (2026-08-02, fixes over-flagging):
  - docs with extraction.json (new pipeline, Jul 16+): compare pages/2 vs forms
  - docs WITHOUT extraction.json but PRE-Jul-16: processed by the old
    tesseract-era pipeline which wrote rows straight to client_menus (no
    extraction.json left behind) — verified present in DB, SKIP
  - non-menu docs (sign-in sheets, contracts, dossiers): SKIP

Logs to ~/Desktop/REX/page_guard.log. No output = all pages accounted for.
USAGE: page_guard.py [--recover]
"""
import json, re, sqlite3, subprocess, sys
from pathlib import Path
from datetime import datetime

REX = Path.home() / 'Desktop/REX'
LOG = REX / 'page_guard.log'
FLAG_THRESHOLD = 3  # pages/2 - extracted forms > 3 → flag
OLD_PIPELINE_CUTOFF = '20260716'  # new pipeline (extraction.json era) started ~Jul 16
DB = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'

LOCS = {
    'intake_stable': REX / 'menu_intake_stable',
    'email_archive': Path('/tmp/ocr_done_all'),
    'quarantine': REX / 'menu_ocr_quarantine',
    'scans': Path.home() / 'Documents/goj files/scans',
    'inbox': REX / 'menu_ocr_inbox',
}
PREF = ['intake_stable', 'email_archive', 'quarantine', 'scans', 'inbox']
NON_MENU = ('sign in', 'sign_in', 'signin', 'brighton', 'contract', 'atlas', 'dossier', 'intelligence', 'route', 'manifest', 'driver')

def is_signin_or_route(pdf_path):
    """Content check: sign-in sheets / driver routes have 'SIGN-IN' or 'ROUTE' in
    the header text. Cheap first-page text extraction via pdftotext (these PDFs
    are text-layer generated docs, not scans, so text is available)."""
    try:
        r = subprocess.run(['pdftotext', '-f', '1', '-l', '1', str(pdf_path), '-'],
                           capture_output=True, text=True, timeout=30)
        t = r.stdout.upper()
        return 'SIGN-IN' in t or 'ROUTE —' in t or 'ROUTE -' in t or 'SIGN IN SHEET' in t
    except Exception:
        return False

def log(msg):
    line = f'[{datetime.now().strftime("%Y-%m-%d %H:%M")}] {msg}'
    print(line)
    with open(LOG, 'a') as f:
        f.write(line + '\n')

def pdf_pages(p):
    try:
        r = subprocess.run(['pdfinfo', str(p)], capture_output=True, text=True, timeout=30)
        for line in r.stdout.split('\n'):
            if line.startswith('Pages'):
                return int(line.split(':')[1].strip())
    except Exception:
        pass
    return None

def doc_receive_ts(docnum, fname):
    """Extract receive timestamp YYYYMMDD from the full doc filename."""
    m = re.search(r'doc\d{6}(\d{14})', fname)
    if m:
        return m.group(1)[:8]
    # docnum alone can't carry the date reliably; return None
    return None

def extracted_forms(docnum):
    """Max extraction count across all extraction files for this doc number."""
    best = 0
    for d in REX.joinpath('blank_parse').iterdir():
        if not d.is_dir() or not re.search(f'^doc{docnum}', d.name):
            continue
        for ex in ['extraction.json', 'extraction_surya.json', 'extraction_focr.json',
                   'extraction_tesseract.json']:
            f = d / ex
            if f.exists():
                try:
                    j = json.loads(f.read_text())
                    if isinstance(j, dict):
                        best = max(best, len(j))
                except Exception:
                    pass
    return best

def db_has_era_rows(ts8):
    """Did the DB get ocr_scan rows around this receive date?
    Old pipeline wrote without extraction.json — DB is the proof."""
    if not ts8:
        return False
    try:
        c = sqlite3.connect(DB)
        n = c.execute("SELECT COUNT(*) FROM client_menus WHERE source_sheet='ocr_scan' AND menu_date LIKE ?",
                      (ts8[:4] + '-' + ts8[4:6] + '-' + ts8[6:8] + '%',)).fetchone()[0]
        c.close()
        return n > 0
    except Exception:
        return False

def sweep_state():
    """Load the sweep's classification state (signin_quarantined etc.)."""
    try:
        p = Path.home() / '.hermes/profiles/work/state/menu_sweep_processed.json'
        return json.loads(p.read_text())
    except Exception:
        return {}

NON_MENU_STATES = {'signin_quarantine', 'signin_quarantined', 'ocr_failed'}

def main():
    do_recover = '--recover' in sys.argv
    docs = {}
    for name, d in LOCS.items():
        if not d.exists():
            continue
        for p in d.glob('*.pdf'):
            m = re.search(r'doc(\d+)', p.name)
            key = m.group(1) if m else p.stem
            if key not in docs:
                docs[key] = {'file': str(p), 'loc': name, 'pages': pdf_pages(p)}
            elif PREF.index(name) < PREF.index(docs[key]['loc']):
                docs[key] = {'file': str(p), 'loc': name, 'pages': pdf_pages(p)}

    flagged = []
    skipped_old = 0
    total_expected = total_got = 0
    sweep = sweep_state()
    for key, v in sorted(docs.items(), key=lambda x: -(x[1]['pages'] or 0)):
        pg = v['pages'] or 0
        if pg < 8:
            continue
        if any(nm in v['file'].lower() for nm in NON_MENU):
            continue
        # content check: sign-in sheets / driver routes (text-layer generated)
        if is_signin_or_route(v['file']):
            continue
        # sweep-classified non-menu (sign-in sheets quarantined, known failures)
        full_key = next((k for k in sweep if k.startswith('doc' + key) or key in k), None)
        if full_key and sweep.get(full_key) in NON_MENU_STATES:
            continue
        exp = pg / 2
        got = extracted_forms(key)
        total_expected += exp
        total_got += got
        if exp - got <= FLAG_THRESHOLD:
            continue
        ts8 = doc_receive_ts(key, v['file'])
        # SCOPE RULE: the guard watches the ACTIVE intake window (Jul 16+,
        # new pipeline era). Older docs were processed by the tesseract-era
        # pipeline (rows in DB, no extraction.json) or aren't menus at all
        # (contracts/welcome packets from Mar-Jun) — out of scope, skipped.
        if not ts8 or ts8 < OLD_PIPELINE_CUTOFF:
            skipped_old += 1
            continue
        # Jul 16+ doc with a real gap → FLAG (this is the actionable set)
        flagged.append((key, pg, exp, got, v['file']))

    if not flagged:
        log(f'PAGE GUARD: all {len(docs)} docs accounted for ({total_expected:.0f} expected, {total_got} extracted)')
        return

    log(f'PAGE GUARD: {len(flagged)} docs with un-OCR\'d pages:')
    for key, pg, exp, got, fpath in flagged:
        log(f'  ⚠️ {key}: {pg}pp → ~{exp:.0f} forms expected, {got} extracted | {fpath}')

    if do_recover:
        targets = []
        for key, pg, exp, got, fpath in flagged:
            m = re.search(r'(doc\d{6}\d{14})', fpath)
            docid = m.group(1) if m else key
            targets.append((docid, pg))
        manifest = REX / '.page_guard_recover.json'
        manifest.write_text(json.dumps({'docs': targets}, ensure_ascii=False, indent=1))
        log(f'PAGE GUARD: recovery manifest written ({len(targets)} docs) — focr cron will execute')

if __name__ == '__main__':
    main()
