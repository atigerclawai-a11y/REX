"""
CC_menu_constants.py — Single source of truth for GOJ menu item lists.
Both goj_menu_ocr (HYBRID) and goj_menu_consensus_ocr (LOCAL ONLY) import from here.
"""

SALADS = [
    "Салат из баклажан", "Салат весенний", "Винегрет", "Салат Днестр",
    "Квашеная капуста", "Оливье", "Свекла", "Селедка", "Сало"
]

SOUPS = [
    "Борщ зеленый", "Борщ красный", "Грибной суп", "Куриный суп",
    "Овощной суп", "Харчо", "Гороховый суп"
]

# Page 1 mains (top half of form)
MAINS_P1 = [
    "Баса с помидорами под сыром", "Блины с мясом", "Блины с творогом",
    "Вареники с картошкой", "Голубцы", "Гуляш",
]

# Page 2 mains (bottom half / continuation)
MAINS_P2 = [
    "Дорадо запеченая", "Жульен", "Котлеты куриные", "Курица в терияки соусе",
    "Куриные крылышки", "Пельмени", "Поперечка", "Салмон",
    "Свиная отбивная", "Цыпленок табака", "Чалахач", "Чебуреки",
    "Шницель куриный",
]

ALL_MAINS = MAINS_P1 + MAINS_P2

SIDES = [
    "Тушеная капуста", "Картошка по деревенски", "Пюре", "Гречка",
    "Паста", "Рис", "Жареная картошка", "Стручковая фасоль", "Без гарнира",
]

# Day column abbreviations (form uses Russian, we store as English codes)
DAYS = ["M", "T", "W", "TH", "F", "SA"]

DAY_MAP = {
    "ПН": "M",  "Пн": "M",  "Пон": "M",
    "ВТ": "T",  "Вт": "T",  "Втор": "T",
    "СР": "W",  "Ср": "W",
    "ЧТ": "TH", "Чт": "TH", "Четв": "TH",
    "ПТ": "F",  "Пт": "F",  "Пят": "F",
    "СБ": "SA", "Сб": "SA", "Суб": "SA",
}

# Checkmark characters recognized as "checked"
# Fix 3: added filled-square glyphs common in scanned checkbox forms (■ ▪ ● □ ▣ •)
CHECKMARKS = {'✓', 'x', 'X', 'v', 'V', '+', '√', '☑', 'L', 'л', '*', '■', '▪', '●', '□', '▣', '•'}
