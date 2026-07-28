"""
CC_ocr_confusion_map.py — Cyrillic OCR confusion patterns for menu items.
Loaded by CC_ocr_oversight_agent to auto-accept common OCR variants
instead of triggering PAUSE review.

Usage:
    from CC_ocr_confusion_map import resolve
    canonical = resolve("Винигрет")  # → "Винегрет"
    canonical = resolve("Туш. кап.") # → "Тушеная капуста"
"""

# Canonical item → list of common OCR/spelling variants
CANONICAL_MAP = {
    # Salads (Салаты)
    "Винегрет": ["Винигрет", "Винеrpет", "Bинeгpeт", "Вин", "Винег."],
    "Свекла": ["Свёкла", "Cвекла", "Свкл", "Свек.", "Св."],
    "Оливье": ["Оливье", "Олив'є", "Ол", "Олив."],
    "Селедка": ["Селёдка", "Селед.", "Сел", "Сел."],
    "Сало": ["Сало", "Салo"],
    "Квашеная капуста": ["капуста", "Капуста", "Кваш. кап.", "кап."],
    "Салат из баклажан": ["баклаж", "Баклаж", "Бакл.", "баклажаны"],
    "Весна": ["Весна", "Весенний", "Весен."],
    "Днестр": ["Днестр", "Днест.", "Дн."],
    "Олимп": ["Олимп", "Оlimp", "Олм."],
    
    # Soups (Супы)
    "Борщ красный": ["Борщ", "Б", "Бор."],
    "Борщ зеленый": ["Борщ зел.", "Б. зел.", "Зел. борщ"],
    "Харчо": ["Харчо", "Xарчо", "Хар."],
    "Гороховый суп": ["Горох", "Гороховый", "Гор."],
    "Грибной суп": ["Гриб", "Гриб.", "Грибной"],
    "Куриный суп": ["Кур", "Куриный", "Кур."],
    "Овощной суп": ["Овощ", "Овощ.", "Овощной"],
    "3.Б": ["3.Б", "3 Б", "З.Б", "Зел. борщ"],
    
    # Main dishes (Главное)
    "Салмон": ["Салмон", "S", "Сал.", "Салм."],
    "Цыпленок табака": ["табака", "Табака", "Таб.", "Цып. таб."],
    "Чалахач": ["Чалахач", "Чалах.", "Чал."],
    "Баса с помидорами под сыром": ["Баса", "Баса", "Баса с пом."],
    "Котлеты куриные": ["Котл. кур", "Котл.кур.", "Котлеты кур.", "Кур. котл."],
    "Куриные крылышки": ["крылья", "Крылья", "Крыл.", "Кур. крылья"],
    "Шницель куриный": ["Шницель", "Шницель", "Шниц.", "Шн."],
    "Свиная отбивная": ["Св. отбив", "Св.отбив.", "Отбивная", "Свин. отб."],
    "Блины с мясом": ["Бл. мясо", "Бл.мясо", "Блины мясо", "Бл. мяс."],
    "Блины с творогом": ["Бл. твор", "Бл.твор.", "Блины твор.", "Бл. тв."],
    "Вареники с картошкой": ["Вар.Кар", "Вар. Кар.", "Вареники", "Вар."],
    "Дорадо запеченая": ["Дорадо", "Дорадо", "Дор."],
    "Жульен": ["Жульен", "Жул.", "Жюльен"],
    "Голубцы": ["Голубцы", "Гол.", "Голуб."],
    "Гуляш": ["Гуляш", "Гул.", "Гуля."],
    "Курица в терияки соусе": ["Терияки", "Терияки", "Тер.", "Терiякi"],
    "Чебуреки": ["Чебуреки", "Чебур.", "Чеб."],
    "Пельмени": ["Пельмени", "Пел.", "Пельм."],
    "Поперечка": ["Поперечка", "Поп.", "Попер."],
    
    # Sides (Гарнир)
    "Гречка": ["Гр", "Гр.", "Греч.", "Гречка"],
    "Пюре": ["MP", "МР", "Пюре", "Пюр."],
    "Жареная картошка": ["FF", "Жар. карт.", "Картошка FF", "Карт. FF"],
    "Картошка по деревенски": ["Картошка", "Карт.", "Карт. по дер."],
    "Тушеная капуста": ["Туш. кап.", "Туш.кап.", "Тушеная кап.", "Туш. кап"],
    "Паста": ["Паста", "Паст.", "Макароны"],
    "Фасоль": ["Фасоль", "Фас.", "Струч. фасоль", "Стручковая фасоль"],
    "Рис": ["Рис", "Рис."],
}

# Reverse index: variant → canonical
VARIANT_TO_CANONICAL = {}
for canonical, variants in CANONICAL_MAP.items():
    VARIANT_TO_CANONICAL[canonical.lower()] = canonical  # exact match
    for v in variants:
        v_lower = v.lower().strip()
        if v_lower not in VARIANT_TO_CANONICAL:
            VARIANT_TO_CANONICAL[v_lower] = canonical

def resolve(text: str) -> str | None:
    """
    Resolve a possibly-misspelled menu item to its canonical form.
    Returns the canonical string or None if no match found.
    """
    if not text:
        return None
    
    clean = text.strip().lower()
    
    # Direct lookup
    if clean in VARIANT_TO_CANONICAL:
        return VARIANT_TO_CANONICAL[clean]
    
    # Fuzzy: check if any known variant is a substring
    for variant, canonical in VARIANT_TO_CANONICAL.items():
        if len(variant) >= 3 and variant in clean:
            return canonical
        if len(clean) >= 3 and clean in variant:
            return canonical
    
    return None

def resolve_with_confidence(text: str) -> tuple[str | None, float]:
    """
    Like resolve() but returns (canonical, confidence).
    Confidence is 0.95 for exact match, 0.85 for variant match, 0.70 for substring match.
    """
    if not text:
        return (None, 0.0)
    
    clean = text.strip().lower()
    
    if clean in VARIANT_TO_CANONICAL:
        return (VARIANT_TO_CANONICAL[clean], 0.95)
    
    for variant, canonical in VARIANT_TO_CANONICAL.items():
        if len(variant) >= 4 and variant == clean[:len(variant)]:
            return (canonical, 0.85)
        if len(variant) >= 4 and variant in clean:
            return (canonical, 0.70)
    
    return (None, 0.0)
