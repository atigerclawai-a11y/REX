#!/usr/bin/env python3
"""
CC_surya_menu_extract.py <doc_dir> [week_number] — surya-native BLANK-form extractor.

Reads a scanned GoJ BLANK-form batch (PDF) with surya-ocr (llama.cpp VLM):
- per-page layout blocks incl. tables whose cells contain
  <input type="checkbox"/> (empty) vs <input checked="" type="checkbox"/> (marked)
- parses per-client day x dish selections directly from table HTML
- emits the SAME extraction.json schema as CC_blank_form_extract.py so the
  writer / fill chain / review reports work unchanged.

Kato RAM rule: one batch at a time, --keep_server within the batch, force-kill after.
"""
import json, re, subprocess, sys, difflib, os
from pathlib import Path

DOC = Path(sys.argv[1]).resolve()
md_files = list(DOC.glob('ocr/*.md'))
_origin = (list(DOC.glob('ocr/*_origin.pdf')) or list(DOC.glob('*/auto/*_origin.pdf'))
           or list(Path('/Users/mainsobhelper/Desktop/REX/menu_intake_stable').glob(DOC.name + '.pdf')))
ORIGIN = _origin[0] if _origin else None
assert ORIGIN, f'no origin PDF for {DOC.name}'
_txt = md_files[0].read_text(errors='ignore') if md_files else ''
_wk = re.findall(r'Week\s*(\d+)', _txt)
WEEK_NUM = int(sys.argv[2]) if len(sys.argv) > 2 else (int(_wk[0]) if _wk else 30)

SURYA = '/Users/mainsobhelper/Desktop/REX/surya-venv/bin/surya_ocr'
WORK = Path('/Users/mainsobhelper/Desktop/REX/surya_parse') / DOC.name
WORK.mkdir(parents=True, exist_ok=True)
_rj = list(WORK.glob('out/*/results.json'))
RESULTS = WORK / 'out' / DOC.name / 'results.json'

# surya env — prevent memory thrashing (Kato 2026-07-28)
SURYA_ENV = dict(os.environ, SURYA_INFERENCE_PARALLEL='1', SURYA_INFERENCE_CTX_SIZE='16384')

DAYS = ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ']
DAY_KEY = {'ПН': 'M', 'ВТ': 'T', 'СР': 'W', 'ЧТ': 'TH', 'ПТ': 'F'}
CATS = {'САЛАТЫ': 'САЛАТЫ', 'СУПЫ': 'СУПЫ', 'ГЛАВНОЕ': 'ГЛАВНОЕ', 'ГАРНИР': 'ГАРНИР'}

# ---------- run surya ----------
if not RESULTS.exists() and _rj:
    RESULTS = _rj[0]
if not RESULTS.exists():
    r = subprocess.run([SURYA, str(ORIGIN), '--output_dir', str(WORK / 'out'), '--keep_server'],
                       capture_output=True, text=True, timeout=14400, env=SURYA_ENV)
    _rj = list(WORK.glob('out/*/results.json'))
    if _rj:
        RESULTS = _rj[0]
    if not RESULTS.exists():
        print(f'SURYA FAILED: {r.stderr[-400:]}')
        sys.exit(1)
    subprocess.run(['pkill', '-f', 'llama-server'], capture_output=True)  # RAM: release model

results = json.loads(RESULTS.read_text())

# ---------- PAGE-COMPLETENESS GATE (Kato 2026-08-02: "every page counts") ----------
# Surya can crash mid-doc (llama-server RAM cascade) leaving a PARTIAL results.json
# (e.g. 6/38 pages). The old code accepted it as complete and silently dropped
# 32+ pages of real forms (doc006811, doc006880 lost 56/62pp this way).
# Gate: if processed pages < pdfinfo page count → treat as incomplete → PNG fallback.
def _pdf_page_count(path):
    r = subprocess.run(['pdfinfo', str(path)], capture_output=True, text=True, timeout=30)
    for line in r.stdout.split('\n'):
        if line.startswith('Pages'):
            return int(line.split(':')[1].strip())
    return None

def _processed_page_count(res):
    """Count pages that actually produced blocks. A page with 0 blocks is either
    a genuinely blank scanner page (rare, isolated) or a page surya silently
    failed on mid-crash (contiguous tail). Partial runs leave a tail of empties."""
    n = 0
    for pages in res.values():
        for p in pages:
            if p.get('blocks'):
                n += 1
    return n

EXPECTED = _pdf_page_count(ORIGIN)
GOT = _processed_page_count(results)
if EXPECTED and GOT and GOT < EXPECTED:
    print(f'⚠️ PARTIAL SURYA RUN: {GOT}/{EXPECTED} pages produced blocks — treating as incomplete, PNG fallback')
    results = {}  # force the fallback path below

# ---------- PNG fallback: some PDFs render blank inside surya's own pipeline ----------
# (doc006525: pdftoppm renders fine, surya-PDF yields 0 blocks/page — Kato's tilt/
# encoding suspicion class). Detect all-empty output, re-render via pdftoppm, re-OCR.
def _all_empty(res):
    for pages in res.values():
        for p in pages:
            if p.get('blocks'):
                return False
    return True

if _all_empty(results):
    print('surya PDF render was empty — PNG fallback (pdftoppm render + re-OCR)')
    PNG_DIR = WORK / 'pages_png'
    PNG_DIR.mkdir(exist_ok=True)
    if not list(PNG_DIR.glob('*.png')):
        subprocess.run(['pdftoppm', '-png', '-r', '150', str(ORIGIN), str(PNG_DIR / 'pg')], check=True)
    for png in sorted(PNG_DIR.glob('*.png')):
        sub = WORK / 'out_png' / png.stem
        if not list(sub.glob('*/results.json')):
            subprocess.run([SURYA, str(png), '--output_dir', str(sub), '--keep_server'],
                           capture_output=True, text=True, timeout=1800, env=SURYA_ENV)
    subprocess.run(['pkill', '-f', 'llama-server'], capture_output=True)
    # merge per-page results
    merged = {}
    all_pages = []
    for png in sorted(PNG_DIR.glob('*.png')):
        rj = list((WORK / 'out_png' / png.stem).glob('*/results.json'))
        if not rj:
            continue
        r = json.loads(rj[0].read_text())
        for pages in r.values():
            for p in pages:
                m = re.search(r'(\d+)', png.stem)
                p['page'] = int(m.group(1)) if m else len(all_pages) + 1
                all_pages.append(p)
    merged[ORIGIN.stem] = sorted(all_pages, key=lambda p: p['page'])
    RESULTS = WORK / 'results_merged.json'
    RESULTS.write_text(json.dumps(merged))
    results = merged

# ---------- catalog (dish -> abbr) ----------
import openpyxl
CATALOG = {}
wb = openpyxl.load_workbook('/Users/mainsobhelper/Desktop/REX/menu_template/first_shift_menu.xlsx',
                            read_only=True, data_only=True)
for row in wb['Menu'].iter_rows(values_only=True):
    if len(row) >= 2 and row[0] and row[1]:
        CATALOG[str(row[0]).strip().lower()] = str(row[1]).strip()
wb.close()

def norm(s):
    return re.sub(r'\s+', ' ', s.lower().replace('ё', 'е')).strip()
CATALOG_NORM = {norm(k): v for k, v in CATALOG.items()}
CAT_NAMES = list(CATALOG_NORM)

def to_abbr(dish_text):
    n = norm(re.sub(r'<[^>]+>', '', dish_text))
    if n in CATALOG_NORM: return CATALOG_NORM[n], 1.0
    m = difflib.get_close_matches(n, CAT_NAMES, n=1, cutoff=0.55)
    if m: return CATALOG_NORM[m[0]], difflib.SequenceMatcher(None, n, m[0]).ratio()
    return dish_text, 0.0

# ---------- roster ----------
import sqlite3
aconn = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
ROSTER = {r[0]: 1 for r in aconn.execute('SELECT name FROM clients WHERE active=1')}
aconn.close()
def canon(n): return ' '.join(sorted(norm(n).split()))
ROSTER_C = {canon(k): k for k in ROSTER}

def match_roster(name):
    k = canon(name)
    if k in ROSTER_C: return ROSTER_C[k], 1.0
    m = difflib.get_close_matches(k, list(ROSTER_C), n=1, cutoff=0.72)
    if m: return ROSTER_C[m[0]], difflib.SequenceMatcher(None, k, m[0]).ratio()
    return None, 0.0

# ---------- parse pages ----------
TAG = re.compile(r'<[^>]+>')
def cell_text(c):
    return TAG.sub('', c).strip()

pages = results.get(DOC.name.replace('.pdf', ''), None) or results.get(ORIGIN.stem, None)
if pages is None:
    # surya keys results by input filename stem
    for k in results:
        pages = results[k]
        break

forms = {}   # roster_name -> entry
current_client = None
current_raw = None
current_cat = None
client_pages = {}

def ensure_form(raw_name, page_num):
    global current_client, current_raw
    rname, conf = match_roster(raw_name)
    key = rname or f'UNMATCHED_{raw_name}'
    if key not in forms:
        forms[key] = {'raw_name': raw_name, 'name_conf': conf, 'pages': [],
                      'selections': {d: {} for d in ['M', 'T', 'W', 'TH', 'F']}, 'anomalies': []}
    if page_num not in forms[key]['pages']:
        forms[key]['pages'].append(page_num)
    return key

for page in pages:
    pnum = page.get('page', 0)
    for block in page.get('blocks', []):
        html = block.get('html', '')
        label = block.get('label', '')
        # client name: table header with Имя: or a Text block "Week 30. Name· Shift N"
        m = re.search(r'Имя:\s*<u>([^<]+)</u>', html) or re.search(r'Имя:\s*([A-ZА-Я][^<,]+)', html)
        if m:
            current_raw = TAG.sub('', m.group(1)).strip()
            current_client = ensure_form(current_raw, pnum)
            continue
        m2 = re.search(r'Week\s*\d+\s*[·.\-]?\s*([A-Z][A-Za-z\-]+ [A-Z][A-Za-z\-]+)', html)
        if m2:
            current_raw = m2.group(1).strip()
            current_client = ensure_form(current_raw, pnum)
            continue
        # category headers
        t_upper = TAG.sub('', html).upper()
        for cword, ckey in (('САЛАТЫ', 'САЛАТЫ'), ('СУПЫ', 'СУПЫ'), ('ГЛАВНОЕ', 'ГЛАВНОЕ'), ('ГАРНИР', 'ГАРНИР')):
            if cword in t_upper and len(t_upper) < 60:
                current_cat = ckey
        # checkbox tables
        if label == 'Table' and 'input' in html and current_client and current_cat:
            for row in re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S):
                cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
                if len(cells) < 2:
                    continue
                dish = cell_text(cells[0])
                if not dish or len(dish) < 2 or dish.upper() in CATS:
                    continue
                abbr, ac = to_abbr(dish)
                for i, cell in enumerate(cells[1:6]):
                    if 'checked' in cell:
                        day = DAY_KEY[DAYS[i]]
                        entry = forms[current_client]['selections'][day]
                        if current_cat in entry:
                            forms[current_client]['anomalies'].append(
                                f'DOUBLE {current_cat} {day}: {entry[current_cat][0]} + {dish}')
                        entry[current_cat] = (dish, abbr, 100, ac)

# finalize
out = {}
for key, data in forms.items():
    data['pages'] = sorted(data['pages'])
    out[key] = data
    days = sum(1 for d in ['M', 'T', 'W', 'TH', 'F'] if data['selections'][d])
    print(f'  {key:30} pages={data["pages"]} days_ordered={days} anomalies={len(data["anomalies"])}')

dst = Path('/Users/mainsobhelper/Desktop/REX/blank_parse') / DOC.name / 'extraction_surya.json'
dst.parent.mkdir(parents=True, exist_ok=True)
dst.write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(f'\nwrote {dst} ({len(out)} forms, week {WEEK_NUM})')
