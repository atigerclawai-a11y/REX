#!/usr/bin/env python3
'''focr recovery for quarantined menu docs (doc006808, doc006809).
Renders page pairs at 200dpi, runs focr_reader per pair, writes extraction.json
in the standard schema [dish, abbr, 100, 1.0]. Multi-mark days → first dish
(choice A) + printed for the alternating pass (Kato double-mark rule).

REBUILT 2026-08-03 from Blue #191 decompile + goj-ocr-canonical-build skill
(original deleted in the 05:01 scripts/ wipe).
'''
import json
import subprocess
import sys
import time
from pathlib import Path

REX = Path.home() / 'Desktop/REX'
sys.path.insert(0, str(REX / 'scripts'))
from focr_reader import read_form_pages

CAT_RU = {
    'salad': 'САЛАТЫ',
    'soup': 'СУПЫ',
    'main': 'ГЛАВНОЕ',
    'side': 'ГАРНИР',
}
PAUSE_SECS = 3
PAUSE_SECS_HEAVY = 8


def render_pair(pdf, p1, p2, work):
    """Render page pair at 200dpi to PNGs; return (a_path, b_path)."""
    a = work / f'p{p1}.png'
    b = work / f'p{p2}.png'
    for page, dst in ((p1, a), (p2, b)):
        if not dst.exists():
            subprocess.run(
                ['pdftoppm', '-png', '-r', '200', '-f', str(page), '-l', str(page),
                 str(pdf), str(dst.with_suffix(''))],
                check=True, capture_output=True, timeout=120,
            )
    return a, b


def process(doc, pdf, n_pages):
    work = REX / 'blank_parse' / doc
    work.mkdir(parents=True, exist_ok=True)
    out = {}
    doubles = []
    pause = PAUSE_SECS_HEAVY if n_pages > 40 else PAUSE_SECS
    first = True
    for p1 in range(1, n_pages + 1, 2):
        if not first:
            time.sleep(pause)
        first = False
        p2 = p1 + 1
        if p2 > n_pages:
            continue
        try:
            a, b = render_pair(pdf, p1, p2, work)
            res = read_form_pages(str(a), str(b))
        except Exception as e:
            print(f'  pair {p1}-{p2}: ERROR {e}')
            continue
        name = res.get('name')
        marks = res.get('marks') or {}
        if not name or not marks:
            print(f'  pair {p1}-{p2}: no name/marks (skip)')
            continue
        selections = {}
        for day, cats in marks.items():
            selections[day] = {}
            for cat, dishes in cats.items():
                if not dishes:
                    continue
                if len(dishes) > 1:
                    doubles.append((name, day, CAT_RU[cat], dishes))
                pick = dishes[0]
                selections[day][CAT_RU[cat]] = [pick, pick, 100, 1]
        out[name] = {
            'raw_name': name,
            'name_conf': 1,
            'pages': [p1],
            'selections': selections,
        }
        ndays = len(selections)
        print(f'  pair {p1}-{p2}: {name} — {ndays} days marked')
        dst = work / 'extraction.json'
        dst.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f'{doc}: {len(out)} forms -> extraction.json')
    if doubles:
        print(f'  DOUBLE-MARK flag ({len(doubles)}):')
        for d in doubles:
            print('   ', d)


def _find_pdf(doc):
    for loc in (REX / 'menu_intake_stable', REX / 'menu_ocr_quarantine',
                REX / 'menu_ocr_full' / doc, REX / 'menu_ocr_inbox',
                Path.home() / 'Documents/goj files/scans'):
        cands = list(loc.glob(f'{doc}*.pdf')) if loc.is_dir() else []
        if cands:
            return cands[0]
    return None


if __name__ == '__main__':
    manifest = REX / '.page_guard_recover.json'
    if manifest.exists():
        try:
            spec = json.loads(manifest.read_text())
            targets = spec.get('docs', [])
            if not targets:
                print('manifest empty — nothing to recover')
                sys.exit(0)
            print(f'PAGE GUARD manifest: recovering {len(targets)} docs')
            for doc, pages in targets:
                pdf = _find_pdf(doc)
                if pdf is None:
                    print(f'MISSING {doc}')
                    continue
                print(f'=== {doc} ({pages}pp) ===')
                process(doc, pdf, pages)
            # one-shot: clear manifest after processing (next census regenerates)
            manifest.unlink(missing_ok=True)
            sys.exit(0)
        except Exception as e:
            print(f'manifest error: {e}')
    # fallback: hardcoded known-recovery docs (same as original)
    for doc, pages in (('doc00680820260727160512', 44),
                       ('doc00680920260727160541', 42),
                       ('doc00681120260727160643', 38),
                       ('doc00688020260729073901', 62)):
        pdf = _find_pdf(doc)
        if pdf is None:
            print(f'MISSING {doc}')
            continue
        print(f'=== {doc} ({pages}pp) ===')
        process(doc, pdf, pages)
