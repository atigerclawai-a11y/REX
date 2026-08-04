#!/usr/bin/env python3
"""Unit-test the generator's flattened alias lookup (the jumble fix)."""
import json
import re
from pathlib import Path

alias_p = Path('/Users/mainsobhelper/Desktop/REX/scripts/dish_aliases.json')
_ALIASES = json.loads(alias_p.read_text())
_FLAT = {}
for _cm in _ALIASES.values():
    if isinstance(_cm, dict):
        _FLAT.update(_cm)
_STRIP = (' ✓', ' →', ' +')

def canon(v):
    if not v:
        return v
    v = re.sub(r'\s+без\s+\S+.*$', '', str(v).strip())
    if v in _FLAT:
        return _FLAT[v]
    for suf in _STRIP:
        if v.endswith(suf) and v[: -len(suf)] in _FLAT:
            return _FLAT[v[: -len(suf)]]
    return v

tests = {
    'Вин': 'Винегрет',
    'Вингерет': 'Винегрет',
    'Ол': 'Оливье',
    'Весна': 'Салат весенний',
    'баклаж': 'Салат из баклажан',
    'Кур': 'Куриный суп',
    'Горох': 'Гороховый суп',
    'Гр': 'Гречка',
    'Туш. кап.': 'Тушеная капуста',
    'MP': 'Пюре',
    'Св. отбив': 'Свиная отбивная',
    'Котл. кур': 'Котлеты куриные',
    'Дорадо': 'Дорадо запеченая',
    'Вар.Кар': 'Вареники с картошкой',
    'Баса': 'Баса с помидорами',
    'Курица в теринки': 'Курица в терияки',
    'Пюре ✓': 'Пюре',
    'Сало →': 'Сало',
    'Салмон ✓': 'Салмон',
    'Квашеня капуста': 'Квашеная капуста',
    'Свкл': 'Свекла',
    'Бл. твор': 'Блины с творогом',
    'крылья': 'Куриные крылышки',
    'Овощ': 'Овощной суп',
    'Хар': 'Харчо',
    '3.Б': '3.Б',  # not in aliases — needs DB-side fix (done)
}
passed = failed = 0
for inp, want in tests.items():
    got = canon(inp)
    if got == want:
        passed += 1
    else:
        failed += 1
        print(f'  FAIL: {inp!r} → {got!r} (want {want!r})')
print(f'canonicalization: {passed} passed, {failed} failed')
