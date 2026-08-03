#!/usr/bin/env python3
"""focr (Unlimited-OCR) — local second-opinion reader for the consensus layer.
Auditioned + approved by Kato 2026-07-29 (read Pako Mayya's form perfectly where
surya garbled it). Use for: unmatched names, low-confidence pages, zero-block pages.
Returns {name, marks: {day: {category: [dishes]}}} from a form page pair.

FIX 2026-08-02: category assignment now uses DISH membership (authoritative),
not section-header text — focr emits СУПЫ/ГЛАВНОЕ tables WITHOUT header rows,
which leaked cur_cat (soups/mains tagged 'salad'). Marks per day-category are
now a LIST (multiple marks survive for the double-mark alternating rule).

REBUILT 2026-08-03 from Blue #191 recovered strings + goj-ocr-canonical-build skill
(original deleted in the 05:01 scripts/ wipe).
"""
import json
import re
import subprocess

FOCR = '/Users/mainsobhelper/.local/bin/focr'
DAYS = ['M', 'T', 'W', 'TH', 'F']

CAT_MAP = {
    'САЛАТ': 'salad',
    'СУП': 'soup',
    'ГЛАВНОЕ': 'main',
    'ГАРНИР': 'side',
}

# Authoritative dish → category membership (FIX 2026-08-02: DISH membership wins)
DISH_CAT = {}
_SALADS = ['Оливье', 'Сало', 'Квашеная капуста', 'Квашеня капуста', 'Свекла',
           'Винегрет', 'Вингерет', 'Салат Днестр', 'Салат из баклажан',
           'Селедка', 'Салат весенний']
_SOUPS = ['Борщ зеленый', 'Борщ красный', 'Гороховый суп', 'Грибной суп',
          'Куриный суп', 'Овощной суп', 'Харчо']
_MAINS = ['Баса с помидорами', 'Блины с мясом', 'Блины с творогом',
          'Вареники с картошкой', 'Голубцы', 'Гуляш', 'Дорадо запеченая',
          'Жульен', 'Котлеты куриные', 'Курица в терияки', 'Куриные крылышки',
          'Пельмени', 'Поперечка', 'Салмон', 'Свиная отбивная',
          'Цыпленок табака', 'Чалахач', 'Чебуреки', 'Шницель куриный']
_SIDES = ['Тушеная капуста', 'Картошка', 'Картошка фри', 'Паста', 'Гречка',
          'Пюре', 'Стручковая фасоль']
for _d in _SALADS:
    DISH_CAT[_d] = 'salad'
for _d in _SOUPS:
    DISH_CAT[_d] = 'soup'
for _d in _MAINS:
    DISH_CAT[_d] = 'main'
for _d in _SIDES:
    DISH_CAT[_d] = 'side'

# OCR typo variants → canonical dish (unambiguous only)
LABEL_FIX = {
    'Квашеня капуста': 'Квашеная капуста',
    'Квашеняя капуста': 'Квашеная капуста',
    'Вингерет': 'Винегрет',
    'Винеррет': 'Винегрет',
    'Винергет': 'Винегрет',
}


def _canon(dish):
    """Map focr's typo'd label to the canonical dish when unambiguous."""
    return LABEL_FIX.get(dish, dish)


def read_form_pages(p1_path, p2_path):
    """Read both pages of a menu form; return {name, marks: {day: {cat: [dishes]}}}.

    Runs `focr ocr --json` on each page (JSON with markdown+HTML tables), extracts
    the client name and the 5-day (ПН ВТ СР ЧТ ПТ) mark grid, assigns categories
    by DISH membership.
    """
    result = {'name': None, 'marks': {}}
    for page in (p1_path, p2_path):
        try:
            proc = subprocess.run(
                [FOCR, 'ocr', '--json', str(page)],
                capture_output=True, text=True, timeout=900,
            )
            if proc.returncode != 0:
                continue
            data = json.loads(proc.stdout)
            html = data.get('markdown', '')
        except Exception:
            continue
        # client name (first Имя: …< in the table header row)
        m = re.search(r'Имя:\s*([^<]+?)\s*<', html)
        if m and not result['name']:
            result['name'] = m.group(1).strip()
        # table rows — one per dish, day columns after the label
        rows = re.findall(r'<tr>(.*?)</tr>', html, re.S)
        for row in rows:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            cells = [c for c in cells if c]
            if not cells:
                continue
            label = cells[0]
            label_clean = re.sub(r'\s+', ' ', label).strip()
            cat = DISH_CAT.get(_canon(label_clean))
            if cat is None:
                continue  # section header or non-dish row
            dish = _canon(label_clean)
            # day columns: ПН ВТ СР ЧТ ПТ — marks are checkbox glyphs
            for day_idx, day in enumerate(DAYS):
                if day_idx + 1 >= len(cells):
                    continue
                cell = cells[day_idx + 1]
                if re.search(r'√|☑|✔|X|x|img', cell):
                    result['marks'].setdefault(day, {}).setdefault(cat, []).append(dish)
    return result


if __name__ == '__main__':
    import sys
    if len(sys.argv) != 3:
        sys.exit('usage: focr_reader.py <p1> <p2>')
    print(read_form_pages(sys.argv[1], sys.argv[2]))
