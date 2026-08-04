#!/usr/bin/env python3
"""Canonicalize remaining garbage dish names in BOTH DBs using dish_aliases.json.
Only touches cells NOT already overwritten by the vision apply."""
import json
import sqlite3

ALIASES = json.load(open('/Users/mainsobhelper/Desktop/REX/scripts/dish_aliases.json'))
FIX = {'Пюре ✓': 'Пюре', 'Салмон ✓': 'Салмон', 'Сало →': 'Сало', '3.Б': 'Борщ красный',
       'Б': 'Борщ красный', 'S': None, 'MP': 'Пюре', 'Олимп': 'Салмон', 'Рыба': 'Салмон',
       'заказ не размещен': None, 'Имя: Fishman Mara + ГЛАВНОЕ БЛЮДО (ПРОДОЛЖЕНИЕ) +': None,
       'Котл. кур': 'Котлеты куриные', 'Курица в теринки': 'Курица в терияки'}

def canon_cell(cell, category):
    """Return canonical name, None (to clear), or the original if unknown."""
    if not cell:
        return None
    c = cell.strip()
    if c in FIX:
        return FIX[c]
    # alias map per category
    amap = ALIASES.get(category, {})
    if c in amap:
        return amap[c]
    # strip suffix markers
    c2 = c.rstrip(' ✓→').strip()
    if c2 in amap:
        return amap[c2]
    if c2 != c:
        return canon_cell(c2, category)
    return c  # leave as-is if truly unknown

DBS = ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
       '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']

CANON = {
    'Винегрет','Оливье','Сало','Селедка','Квашеная капуста','Салат Днестр','Свекла',
    'Салат из баклажан','Салат весенний','Борщ зеленый','Борщ красный','Куриный суп',
    'Гороховый суп','Грибной суп','Овощной суп','Харчо','Баса с помидорами','Блины с мясом',
    'Блины с творогом','Вареники с картошкой','Голубцы','Гуляш','Дорадо запеченая','Жульен',
    'Котлеты куриные','Курица в терияки','Куриные крылышки','Пельмени','Поперечка','Салмон',
    'Свиная отбивная','Цыпленок табака','Чалахач','Чебуреки','Шницель куриный','Тушеная капуста',
    'Картошка','Картошка фри','Паста','Гречка','Пюре','Стручковая фасоль'}

for db in DBS:
    con = sqlite3.connect(db)
    cols = [r[1] for r in con.execute("PRAGMA table_info(client_menus)")]
    has_id = 'id' in cols
    sel = "SELECT id, client_name, menu_date, day_code, salad, soup, main, side" if has_id else \
          "SELECT rowid, client_name, menu_date, day_code, salad, soup, main, side"
    rows = con.execute(f"""{sel}
        FROM client_menus WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07'""").fetchall()
    changed = 0
    cleared = 0
    for rid, name, d, dc, salad, soup, main_, side in rows:
        news = {}
        for label, cell in [('salad', salad), ('soup', soup), ('main', main_), ('side', side)]:
            if cell and cell.strip() not in CANON:
                fixed = canon_cell(cell, label)
                if fixed != cell:
                    news[label] = fixed
                    if fixed is None:
                        cleared += 1
                    else:
                        changed += 1
        if news:
            sets = ', '.join(f"{k}=?" for k in news)
            vals = [news[k] for k in news] + [rid]
            con.execute(f"UPDATE client_menus SET {sets} WHERE rowid=?", vals)
    con.commit()
    print(f'{db.split("/")[-1]}: canonicalized {changed} cells, cleared {cleared} no-order cells')
    con.close()
