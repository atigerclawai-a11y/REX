#!/usr/bin/env python3
"""Check which garbage-cell clients are in the confirmed 227 (vision marks will fix them)."""
import json
import sqlite3

# confirmed names from all batches
confirmed = set()
for f in ['/tmp/w31_forms.json', '/tmp/w31_batch_4.json', '/tmp/w31_batch_5.json']:
    try:
        for x in json.load(open(f)):
            confirmed.add(x['name'])
    except Exception:
        pass
print(f'confirmed clients: {len(confirmed)}')

DBS = ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
       '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']
for db in DBS:
    con = sqlite3.connect(db)
    rows = con.execute("""SELECT DISTINCT client_name FROM client_menus
        WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07'""").fetchall()
    garbage_clients = set()
    for (name,) in rows:
        pass
    # garbage cells
    bad_rows = con.execute("""SELECT client_name, menu_date, day_code, salad, soup, main, side
        FROM client_menus WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07'""").fetchall()
    bad_names = set()
    for name, d, dc, salad, soup, main_, side in bad_rows:
        for cell in (salad, soup, main_, side):
            if cell and cell.strip() not in {
                'Винегрет','Оливье','Сало','Селедка','Квашеная капуста','Салат Днестр',
                'Свекла','Салат из баклажан','Салат весенний','Борщ зеленый','Борщ красный',
                'Куриный суп','Гороховый суп','Грибной суп','Овощной суп','Харчо',
                'Баса с помидорами','Блины с мясом','Блины с творогом','Вареники с картошкой',
                'Голубцы','Гуляш','Дорадо запеченая','Жульен','Котлеты куриные',
                'Курица в терияки','Куриные крылышки','Пельмени','Поперечка','Салмон',
                'Свиная отбивная','Цыпленок табака','Чалахач','Чебуреки','Шницель куриный',
                'Тушеная капуста','Картошка','Картошка фри','Паста','Гречка','Пюре',
                'Стручковая фасоль'}:
                bad_names.add(name)
    in_conf = bad_names & confirmed
    not_conf = bad_names - confirmed
    print(f'\n{db.split("/")[-1]}: {len(bad_names)} clients w/ garbage; '
          f'{len(in_conf)} covered by vision, {len(not_conf)} NOT covered')
    print(f'  NOT covered: {sorted(not_conf)}')
    con.close()
