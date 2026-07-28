#!/usr/bin/env python3
"""
CC_blank_form_extract.py — GoJ BLANK-form (checkbox grid) menu extractor.
Input: doc dir with origin.pdf + MinerU MD. Renders pages, tesseract-rus TSV per page,
locates day columns + dish labels + category sections, detects circled checkboxes
by dark-pixel count in a box window, maps dishes to the Drive 'Menu' catalog
abbreviations, matches names to roster. Emits JSON + human report.
"""
import csv, json, re, subprocess, sys, difflib, shutil
from pathlib import Path
import numpy as np
from PIL import Image

DOC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('/Users/mainsobhelper/Desktop/REX/menu_ocr_full/doc00673920260727042014')
DOC = DOC.resolve()
md_files = list(DOC.glob('ocr/*.md'))
_origin = (list(DOC.glob('ocr/*_origin.pdf')) or list(DOC.glob('*/auto/*_origin.pdf'))
           or list(Path('/Users/mainsobhelper/Desktop/REX/menu_intake_stable').glob(DOC.name + '.pdf')))
ORIGIN = _origin[0] if _origin else None
assert ORIGIN, f'no origin PDF found for {DOC.name}'
# week number -> menu dates (2026). w29 = 7/20-24, w30 = 7/27-31, w31 = 8/3-7
WEEK_DATES = {
    29: {'M': '2026-07-20', 'T': '2026-07-21', 'W': '2026-07-22', 'TH': '2026-07-23', 'F': '2026-07-24'},
    30: {'M': '2026-07-27', 'T': '2026-07-28', 'W': '2026-07-29', 'TH': '2026-07-30', 'F': '2026-07-31'},
    31: {'M': '2026-08-03', 'T': '2026-08-04', 'W': '2026-08-05', 'TH': '2026-08-06', 'F': '2026-08-07'},
}
_md_txt = md_files[0].read_text(errors='ignore') if md_files else ''
_wk = re.findall(r'Week\s*(\d+)', _md_txt)
WEEK_NUM = int(sys.argv[2]) if len(sys.argv) > 2 else (int(_wk[0]) if _wk else 30)
DAY_DATE = WEEK_DATES[WEEK_NUM]
WORK = Path('/Users/mainsobhelper/Desktop/REX/blank_parse') / DOC.name
PAGES = WORK / 'pages'
PAGES.mkdir(parents=True, exist_ok=True)

DAY_TOKENS = {'nH': 'M', 'NH': 'M', 'nH'.upper(): 'M', 'BT': 'T', 'cP': 'W', 'CP': 'W',
              'чт': 'TH', '4T': 'TH', 'YT': 'TH', 'NT': 'F', 'HT': 'F', 'nt': 'F',
              'ht': 'F', 'um': 'F', 'nm': 'F', 'ПН': 'M',
              'ВТ': 'T', 'СР': 'W', 'ЧТ': 'TH', 'ПТ': 'F'}
DAY_ORDER = ['M', 'T', 'W', 'TH', 'F']
DAY_CODE = {'M': 'M', 'T': 'T', 'W': 'W', 'TH': 'TH', 'F': 'F'}

CATEGORIES = ['САЛАТЫ', 'СУПЫ', 'ГЛАВНОЕ', 'ГАРНИР']
CAT_KEY = {'САЛАТЫ': 'salad', 'СУПЫ': 'soup', 'ГЛАВНОЕ': 'main', 'ГАРНИР': 'side'}

# ---------- catalog (dish name -> abbreviation) ----------
import openpyxl
CATALOG = {}   # normalized dish name -> (abbrev, category)
for fn, shift in (('/Users/mainsobhelper/Desktop/REX/menu_template/first_shift_menu.xlsx', '1'),
                  ):
    wb = openpyxl.load_workbook(fn, read_only=True, data_only=True)
    ws = wb['Menu']
    for row in ws.iter_rows(values_only=True):
        if len(row) < 2:
            continue
        name = str(row[0]).strip() if row[0] else ''
        abbr = str(row[1]).strip() if row[1] else ''
        if name and abbr and len(abbr) <= 12:
            CATALOG[name.lower()] = abbr
    wb.close()
CAT_NAMES = list(CATALOG.keys())

def norm(s):
    return re.sub(r'\s+', ' ', s.lower().replace('ё', 'е')).strip()

CATALOG_NORM = {norm(k): v for k, v in CATALOG.items()}
CAT_NAMES_NORM = list(CATALOG_NORM.keys())

def to_abbr(dish_text):
    n = norm(dish_text)
    if n in CATALOG_NORM: return CATALOG_NORM[n], 1.0
    m = difflib.get_close_matches(n, CAT_NAMES_NORM, n=1, cutoff=0.55)
    if m: return CATALOG_NORM[m[0]], difflib.SequenceMatcher(None, n, m[0]).ratio()
    return dish_text, 0.0

# ---------- render pages ----------
if not (PAGES / 'pg-01.png').exists():
    subprocess.run(['pdftoppm', '-png', '-r', '150', str(ORIGIN), str(PAGES / 'pg')], check=True)
pages = sorted(PAGES.glob('pg-*.png'))
print(f'{len(pages)} pages')

# ---------- tesseract per page ----------
def tsv_for(png):
    out = WORK / (png.stem + '_full')
    if not (WORK / (png.stem + '_full.tsv')).exists():
        subprocess.run(['tesseract', str(png), str(out), '-l', 'rus+eng', 'tsv'],
                       check=True, capture_output=True)
    words = []
    with open(str(out) + '.tsv') as f:
        for r in csv.DictReader(f, delimiter='\t'):
            if r['text'] and r['text'].strip() and float(r['conf']) > 25:
                words.append({'t': r['text'], 'x': int(r['left']), 'y': int(r['top']),
                              'w': int(r['width']), 'h': int(r['height']), 'c': float(r['conf'])})
    return words

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
    m = difflib.get_close_matches(k, list(ROSTER_C.keys()), n=1, cutoff=0.72)
    if m: return ROSTER_C[m[0]], difflib.SequenceMatcher(None, k, m[0]).ratio()
    return None, 0.0

# ---------- per-page structure ----------
def page_structure(words):
    """Return (client_name, day_cols {D:x}, sections {cat: y}, dishes [(cat, text, y_center)])."""
    # client name: words right of 'Uma:'/'Имя' near top (y<230), latin capitalized pairs
    name = None
    head_words = [w for w in words if w['y'] < 240]
    for i, w in enumerate(head_words):
        if re.match(r'^(Uma|Имя|Uma:|Имя:)$', w['t']) or w['t'].rstrip(':') in ('Uma', 'Имя'):
            cand = []
            for w2 in head_words:
                if w2['x'] > w['x'] and abs(w2['y'] - w['y']) < 30 and re.match(r'^[A-ZА-Я][A-Za-zа-я\-]+$', w2['t']):
                    cand.append((w2['x'], w2['t']))
            cand.sort()
            if len(cand) >= 2:
                name = f'{cand[0][1]} {cand[1][1]}'
            break
    if not name:
        # fallback: two adjacent latin words left of day headers near top
        lat = [w for w in head_words if re.match(r'^[A-Z][a-z\-]{2,}$', w['t']) and w['x'] < 600]
        lat.sort(key=lambda w: (w['y'], w['x']))
        if len(lat) >= 2:
            name = f'{lat[0]["t"]} {lat[1]["t"]}'

    # day columns: header tokens in top area
    day_cols = {}
    for w in words:
        if w['y'] < 240:
            d = DAY_TOKENS.get(w['t'].strip())
            if d and d not in day_cols:
                day_cols[d] = w['x'] + w['w'] // 2
    # fill missing columns by 115px spacing
    if day_cols:
        xs = sorted(day_cols.values())
        step = int(np.median(np.diff(xs))) if len(xs) > 1 else 115
        base = day_cols.get('M') or (min(xs) if xs else None)
        known = {d: x for d, x in day_cols.items()}
        for i, d in enumerate(DAY_ORDER):
            if d not in day_cols:
                # infer from nearest known
                if 'M' in known: day_cols[d] = known['M'] + i * step
                elif known:
                    k0 = list(known.items())[0]
                    day_cols[d] = k0[1] + (i - DAY_ORDER.index(k0[0])) * step

    # sections: category header words (tolerate latinized Cyrillic: CAJIATbI, CYIIbI...)
    LAT2CYR = str.maketrans({'A': 'А', 'B': 'В', 'C': 'С', 'E': 'Е', 'H': 'Н', 'K': 'К',
                             'M': 'М', 'O': 'О', 'P': 'Р', 'T': 'Т', 'X': 'Х', 'Y': 'У',
                             'a': 'а', 'b': 'ь', 'c': 'с', 'e': 'е', 'h': 'н', 'k': 'к',
                             'm': 'м', 'o': 'о', 'p': 'р', 't': 'т', 'x': 'х', 'y': 'у',
                             'I': 'І', 'i': 'і', 'J': 'Ј', 'j': 'ј', 'b': 'ь'})
    # sections: category headers are flanked by '+' decorators on the form
    # ("+ САЛАТЫ +"). Robust to latinized Cyrillic (CAJIATbI) via fuzzy translit.
    sections = []
    plus_words = [w for w in words if w['t'].strip() == '+']
    def is_flanked(w):
        near = [p for p in plus_words if abs(p['y'] - w['y']) < 25]
        return (any(p['x'] < w['x'] and w['x'] - p['x'] < 140 for p in near) and
                any(p['x'] > w['x'] and p['x'] - w['x'] < 140 for p in near))
    for w in words:
        if w['x'] > 620 or w['y'] < 150:
            continue
        t = w['t'].upper()
        t2 = w['t'].translate(LAT2CYR).upper()
        if not (is_flanked(w) or t.startswith('САЛАТ') or t2.startswith('САЛАТ')
                or t.startswith('ГЛАВН') or t2.startswith('ГЛАВН')
                or t.startswith('ГАРН') or t2.startswith('ГАРН')):
            continue
        for cat in CATEGORIES:
            m = difflib.get_close_matches(t2, [cat], n=1, cutoff=0.5) or difflib.get_close_matches(t, [cat], n=1, cutoff=0.5)
            if m:
                sections.append((w['y'], cat))
                break
    # dedupe: keep first occurrence per category per 100px
    sections.sort()
    dedup = []
    for sy, sc in sections:
        if not any(sc == c and abs(sy - y) < 100 for y, c in dedup):
            dedup.append((sy, sc))
    sections = dedup
    # dishes: label words x<520, below first section; group words per line.
    # Bucket at y//24 merges split labels ("Борщ"+"зеленый"); dishes are ~53px apart.
    SKIP_PAT = re.compile(r'BLANK|GOJ|GARDEN|DAYCARE|ПРОДОЛЖЕНИЕ|^\W*$', re.I)
    label_words_raw = [w for w in words if w['x'] < 520 and w['y'] > 200]
    label_words = [w for w in label_words_raw
                   if not any(abs(w['y'] - sy) < 18 for sy, _ in sections)]
    lines = {}
    for w in label_words:
        key = w['y'] // 24
        lines.setdefault(key, []).append(w)
    dishes = []
    for key in sorted(lines):
        ws_ = sorted(lines[key], key=lambda w: w['x'])
        text = ' '.join(w['t'] for w in ws_)
        text = re.sub(r'[|+©®]', '', text).strip()
        if len(text) < 3 or SKIP_PAT.search(text):
            continue
        if text.upper() in ('БЛЮДО', 'БЛЮ,', 'СУП'):
            continue
        yc = int(np.mean([w['y'] + w['h'] // 2 for w in ws_]))
        # category = last section above
        cat = None
        for sy, sc in sections:
            if sy < yc: cat = sc
        if cat:
            dishes.append((cat, text, yc))
    return name, day_cols, dishes

# ---------- checkbox detection ----------
def cell_dark(img_arr, cx, yc):
    """Dark px STRICTLY INSIDE the checkbox (Kato legend 2026-07-27: a selection is
    ANY ink inside the box — check, X, fill). Box is ~26px wide centered ~cx+5,
    vertically ~yc-12..yc+16; this window sits inside the border strokes so an
    empty box scores ~0-12 and any mark scores 25+."""
    x0, x1 = max(0, cx - 3), min(img_arr.shape[1], cx + 14)
    y0, y1 = max(0, yc - 7), min(img_arr.shape[0], yc + 12)
    crop = img_arr[y0:y1, x0:x1]
    return int((crop < 140).sum())

# ---------- OMRChecker hybrid reader (2026-07-27, validated on Gumarova ground truth) ----------
# Architecture: tesseract registers the page (day-col centers + first-row anchor),
# shift the reference template origins by (measured - reference), let OMRChecker's
# battle-tested thresholding read the grid. Beats fixed-threshold pixel counting.
OMR_DIR = Path('/Users/mainsobhelper/Desktop/REX/vendor/OMRChecker')
OMR_PY = Path('/Users/mainsobhelper/Desktop/REX/omr-venv/bin/python')
OMR_REF = {  # reference geometry @150dpi (Kulchinskaya pg-01): day centers + first-row centers
    'day_x': {'M': 650, 'T': 766, 'W': 880, 'TH': 996, 'F': 1110},
    'anchors': {'САЛАТЫ': 286, 'СУПЫ': 816, 'ГЛАВНОЕ': 1238, 'ГАРНИР': None},  # first-row center y per section
}
OMR_BLOCKS = {  # (n_rows, ref_origin_y) per section on page 1; page 2 handled via its own offsets
    'САЛАТЫ': (9, 273), 'СУПЫ': (7, 803), 'ГЛАВНОЕ': (6, 1225),
}

def omr_read_page(png_path, day_cols, first_row_y, sections_present, out_dir):
    """Run OMRChecker on one page with a per-page-shifted template.
    Returns {(section, row_idx, day): 'F'-style value or None}."""
    import json as _json, subprocess as _sp, tempfile as _tf
    blocks = {}
    for cat, (n_rows, ref_y) in OMR_BLOCKS.items():
        if cat not in sections_present:
            continue
        dy = first_row_y.get(cat, OMR_REF['anchors'][cat]) - OMR_REF['anchors'][cat]
        labels = [f'{cat[:2]}{i+1}' for i in range(n_rows)]
        blocks[cat] = {
            'bubblesGap': 116, 'bubbleValues': DAY_ORDER, 'direction': 'horizontal',
            'fieldLabels': labels, 'labelsGap': 53,
            'origin': [OMR_REF['day_x']['M'] - 13 + (day_cols.get('M', OMR_REF['day_x']['M']) - OMR_REF['day_x']['M']), ref_y + dy],
        }
    tmpl = {'pageDimensions': [1275, 1650], 'bubbleDimensions': [26, 26],
            'customLabels': {}, 'fieldBlocks': blocks, 'preProcessors': []}
    cfg = {'dimensions': {'display_height': 1650, 'display_width': 1275,
                          'processing_height': 1650, 'processing_width': 1275},
           'outputs': {'show_image_level': 0, 'save_image_level': 0},
           'threshold_params': {'GAMMA_LOW': 0.7, 'MIN_GAP': 30, 'MIN_JUMP': 25, 'CONFIDENT_SURPLUS': 5}}
    with _tf.TemporaryDirectory() as td:
        inp = Path(td) / 'in'
        inp.mkdir()
        (inp / 'template.json').write_text(_json.dumps(tmpl))
        (inp / 'config.json').write_text(_json.dumps(cfg))
        shutil.copy(png_path, inp / Path(png_path).name)
        _sp.run([str(OMR_PY), str(OMR_DIR / 'main.py'), '--inputDir', str(inp), '--outputDir', str(Path(td) / 'out')],
                capture_output=True, timeout=600, cwd=str(OMR_DIR))
        csvs = list((Path(td) / 'out').rglob('*.csv'))
        if not csvs:
            return {}
        rows = list(csv.reader(open(csvs[0])))
        hdr, vals = rows[0], rows[1]
        out = {}
        for h, v in zip(hdr, vals):
            if v and h not in ('file_id', 'input_path', 'output_path', 'score'):
                # find block/row: label like 'СА1'..'ГЛ6'
                for cat in blocks:
                    prefix = cat[:2]
                    if h.startswith(prefix):
                        row_idx = int(h[len(prefix):]) - 1
                        out[(cat, row_idx)] = v
        return out

results = {}
page_list = [tsv_for(p) for p in pages]

# segment pages into forms: a page starts a form if it has a name header matching roster
forms = []  # list of (roster_name, raw_name, [page_idxs])
for pi, (png, words) in enumerate(zip(pages, page_list)):
    name, day_cols, dishes = page_structure(words)
    rname, conf = match_roster(name) if name else (None, 0)
    if rname and (not forms or forms[-1][0] != rname):
        forms.append([rname, name, conf, [pi]])
    elif forms:
        forms[-1][3].append(pi)
    else:
        forms.append([rname or f'UNMATCHED_pg{pi+1}', name, conf, [pi]])

print(f'{len(forms)} forms segmented')
report = []
for rname, raw, nconf, pidxs in forms:
    sel = {d: {} for d in DAY_ORDER}  # day -> {cat: (dish, abbr, dark, abbr_conf)}
    cand = {d: {} for d in DAY_ORDER}  # day -> {cat: [(dark, text, abbr, ac)]} all rows
    anomalies = []
    for pi in pidxs:
        words = page_list[pi]
        name, day_cols, dishes = page_structure(words)
        img = np.array(Image.open(pages[pi]).convert('L'))
        for cat, text, yc in dishes:
            abbr, ac = to_abbr(text)
            for d in DAY_ORDER:
                if d in day_cols:
                    dark = cell_dark(img, day_cols[d], yc)
                    cand[d].setdefault(cat, []).append((dark, text, abbr, ac))
    # relative pick per day+category: argmax with margin rule (interior-ink scale,
    # calibrated 2026-07-27 on Gumarova ground truth from Kato: border noise ≤44,
    # real marks ≥96 → threshold 60; two cells ≥60 within 25 = genuine double-mark)
    for d in DAY_ORDER:
        for cat, rows_ in cand[d].items():
            rows_.sort(reverse=True)
            top = rows_[0]
            second = rows_[1] if len(rows_) > 1 else (0, None, None, 0)
            if top[0] < 60:
                continue  # no mark in this category for this day
            if second[0] >= 60 and (top[0] - second[0]) < 25:
                anomalies.append(f'AMBIGUOUS {cat} {d}: {top[1]}({top[0]}) vs {second[1]}({second[0]}) — needs eye review')
            sel[d][cat] = (top[1], top[2], top[0], top[3])
    results[rname] = {'raw_name': raw, 'name_conf': nconf, 'pages': [p+1 for p in pidxs],
                      'selections': sel, 'anomalies': anomalies}
    days_with = sum(1 for d in DAY_ORDER if sel[d])
    print(f'  {rname:28s} pages {[p+1 for p in pidxs]} days_ordered={days_with} anomalies={len(anomalies)}')

out = WORK / 'extraction.json'
out.write_text(json.dumps(results, ensure_ascii=False, indent=1))
print(f'\nwrote {out}')
