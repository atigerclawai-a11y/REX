#!/usr/bin/env python3
"""
CC_menu_sweep.py — close the menu intake loop (2026-07-27, Kato directive).
Watches ~/Desktop/REX/menu_intake_stable/ for scanned menu PDFs. For each new doc:
  1. MinerU OCR (ONE at a time — RAM discipline) -> menu_ocr_full/<doc>/ocr/*.md
  2. Classify: BLANK-grid (checkbox forms) vs old-style handwritten
  3. BLANK  -> CC_blank_form_extract.py -> write picks to client_menus (both DBs)
     old    -> leave MD in place; CC_menu_intake picks it up on its run
  4. Re-run CC_menu_fill.py for affected dates this week (travel rule + fallback chain)
Silent when nothing new. Prints one summary line per processed doc.
"""
import json, re, subprocess, sys, time
from pathlib import Path

HOME = Path.home()
STABLE = HOME / 'Desktop/REX/menu_intake_stable'
OCR_FULL = HOME / 'Desktop/REX/menu_ocr_full'
REX = HOME / 'Desktop/REX'
PY = HOME / '.rex-venv/bin/python3'
MINERU = HOME / 'Desktop/REX/mineru-venv/bin/mineru'
STATE = HOME / '.hermes/profiles/work/state/menu_sweep_processed.json'
QUARANTINE = HOME / 'Desktop/REX/menu_ocr_quarantine'
FAIL_LIMIT = 3  # OCR failures before a doc is quarantined (OBJ-024: stop retrying broken docs every cycle)

state = json.loads(STATE.read_text()) if STATE.exists() else {}
fails = state.get('_fails', {})  # doc -> consecutive OCR/extraction failure count
# Pre-mark docs already fully processed (OCR'd + parsed in earlier runs) so the
# first sweep after deploy doesn't redo 14 batches. A doc counts as done if its
# staged MD exists AND (BLANK -> extraction.json exists | old-style -> leave to intake).
for _d in OCR_FULL.glob('doc*'):
    _md = list((_d / 'ocr').glob('*.md'))
    if _md and _d.name not in state:
        _txt = _md[0].read_text(errors='ignore')
        _is_blank = 'BLANK' in _txt and _txt.count('□') > 20
        _ex = list(Path(HOME / 'Desktop/REX/blank_parse').glob(_d.name + '/extraction.json'))
        if (_is_blank and _ex) or not _is_blank:
            state[_d.name] = 'done'

WEEK_DATES = {
    29: ['2026-07-20', '2026-07-21', '2026-07-22', '2026-07-23', '2026-07-24'],
    30: ['2026-07-27', '2026-07-28', '2026-07-29', '2026-07-30', '2026-07-31'],
    31: ['2026-08-03', '2026-08-04', '2026-08-05', '2026-08-06', '2026-08-07'],
}

def is_signin(md_text):
    """Detect sign-in/attendance sheets — NOT menus. Quarantine, don't route to OCR pipeline."""
    return ('SIGN-IN SHEET' in md_text or 'SIGN IN SHEET' in md_text 
            or 'Attendance Report' in md_text or 'attendance report' in md_text.lower())

def classify(md_text):
    """Classify menu form type. Sign-in sheets are excluded by caller before this.
    
    BLANK-grid detection: checkbox forms have many □ characters + a name field.
    The word "BLANK" may be garbled by MinerU, so we also accept high □ density
    (>30 □ characters) with a name pattern present.
    """
    box_count = md_text.count('□')
    if box_count > 20:
        # Check for name pattern (FirstName LastName) in the MD
        has_name = bool(re.search(r'[A-Z][a-z]+\s+[A-Z][a-z]+', md_text))
        if 'BLANK' in md_text or (box_count > 30 and has_name):
            return 'BLANK'
    return 'old'

processed_any = False
need_write = False
weeks_touched = set()
for pdf in sorted(STABLE.glob('*.pdf')):
    doc = pdf.stem
    if state.get(doc) in ('done', 'quarantined', 'signin_quarantine'):
        continue
    ocr_dir = OCR_FULL / doc / 'ocr'
    md_path = ocr_dir / f'{doc}.md'
    if not md_path.exists():
        # 1. OCR (sequential, gentle)
        r = subprocess.run([str(MINERU), '-b', 'pipeline', '-p', str(pdf), '-o', str(OCR_FULL / doc)],
                           capture_output=True, text=True, timeout=1800)
        auto_md = OCR_FULL / doc / doc / 'auto' / f'{doc}.md'
        ocr_dir.mkdir(parents=True, exist_ok=True)
        if auto_md.exists():
            auto_md.replace(md_path)
        if not md_path.exists():
            print(f'[SWEEP] OCR FAILED {doc}: {r.stderr[-200:] if r.stderr else "no md"}')
            state[doc] = 'ocr_failed'
            fails[doc] = fails.get(doc, 0) + 1
            if fails[doc] >= FAIL_LIMIT:
                # Quarantine after FAIL_LIMIT consecutive failures (OBJ-024):
                # move the PDF out of intake so the sweep stops retrying it every 15min
                # and burning the cron's 3600s timeout budget on a broken doc.
                QUARANTINE.mkdir(parents=True, exist_ok=True)
                dst = QUARANTINE / pdf.name
                if not dst.exists():
                    pdf.replace(dst)
                state[doc] = 'quarantined'
                print(f'[SWEEP] {doc}: QUARANTINED after {FAIL_LIMIT} OCR failures -> {dst.name}')
            else:
                print(f'[SWEEP] {doc}: OCR fail {fails[doc]}/{FAIL_LIMIT} — will retry next cycle')
            processed_any = True
            continue
        time.sleep(3)  # RAM cooldown between docs
    text = md_path.read_text(errors='ignore')
    if is_signin(text):
        print(f'[SWEEP] {doc}: sign-in sheet — quarantined (not a menu)')
        state[doc] = 'signin_quarantine'
        processed_any = True
        continue
    kind = classify(text)
    wk_m = re.findall(r'Week\s*(\d+)', text)
    wk = int(wk_m[0]) if wk_m else 30

    if kind == 'BLANK':
        # surya-native extraction (2026-07-28: reads labels + checked-state natively);
        # fall back to tesseract extractor if surya fails
        r = subprocess.run([str(PY), str(REX / 'CC_surya_menu_extract.py'), str(OCR_FULL / doc), str(wk)],
                           capture_output=True, text=True, timeout=7200)
        sj = Path(HOME / 'Desktop/REX/blank_parse') / doc / 'extraction_surya.json'
        if sj.exists():
            # promote surya result; keep tesseract run as audit trail
            dst = sj.parent / 'extraction.json'
            if dst.exists():
                dst.rename(sj.parent / 'extraction_tesseract.json')
            sj.rename(dst)
            print(f'[SWEEP] {doc}: BLANK week={wk}, surya-extracted')
        else:
            r2 = subprocess.run([str(PY), str(REX / 'CC_blank_form_extract.py'), str(OCR_FULL / doc), str(wk)],
                                capture_output=True, text=True, timeout=1800)
            print(f'[SWEEP] {doc}: BLANK week={wk}, tesseract-extracted (surya fallback)')
        need_write = True
        weeks_touched.add(wk)
    else:
        r = subprocess.run([str(PY), str(REX / 'CC_menu_intake.py')], capture_output=True, text=True, timeout=900)
        tail = [l for l in r.stdout.splitlines() if 'rows' in l or 'Merged' in l]
        need_write = False  # intake writes directly
        print(f'[SWEEP] {doc}: old-style -> intake ({tail[-1] if tail else "ok"})')
        weeks_touched.add(30)

    state[doc] = 'done'
    processed_any = True

# Batch the DB write + fills ONCE after all docs (not per-doc)
if need_write:
    w = subprocess.run([str(PY), str(REX / 'scripts/write_blank_picks.py')],
                       capture_output=True, text=True, timeout=600)
    lines = [l for l in w.stdout.splitlines() if 'rows written' in l]
    print(f'[SWEEP] picks -> client_menus: {lines[0] if lines else "done"}')
for wk in sorted(weeks_touched):
    for d in WEEK_DATES.get(wk, []):
        subprocess.run([str(PY), str(REX / 'CC_menu_fill.py'), d], capture_output=True, text=True, timeout=300)
if weeks_touched:
    print(f'[SWEEP] fills refreshed for weeks {sorted(weeks_touched)}')

STATE.parent.mkdir(parents=True, exist_ok=True)
state['_fails'] = fails
STATE.write_text(json.dumps(state, indent=1))
if not processed_any:
    pass  # silent — watchdog pattern
