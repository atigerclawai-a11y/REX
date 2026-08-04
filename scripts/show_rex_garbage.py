#!/usr/bin/env python3
"""Show exactly what find_garbage_dishes flags in the REX copy."""
import sqlite3

REX = '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db'
con = sqlite3.connect(REX)
rows = con.execute("""SELECT client_name, menu_date, day_code, salad, soup, main, side, source_sheet
    FROM client_menus WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07'
    AND (salad LIKE '%' ESCAPE '\\' AND (
      salad IN ('FF','MP','S','Б','Вин','Гр','Кур','Горох','Ол','Весна','3.Б','Вар.Кар','Борщ','Баса','Гриб','Свкл','Котл.кур','Бл.твор','Овощ','крылья','капуста','Рыба','Олимп')
      OR soup IN ('FF','MP','S','Б','Вин','Гр','Кур','Горох','Ол','Весна','3.Б','Вар.Кар','Борщ','Баса','Гриб','Свкл','Котл.кур','Бл.твор','Овощ','крылья','капуста','Рыба','Олимп')
      OR main IN ('FF','MP','S','Б','Вин','Гр','Кур','Горох','Ол','Весна','3.Б','Вар.Кар','Борщ','Баса','Гриб','Свкл','Котл.кур','Бл.твор','Овощ','крылья','капуста','Рыба','Олимп')
      OR side IN ('FF','MP','S','Б','Вин','Гр','Кур','Горох','Ол','Весна','3.Б','Вар.Кар','Борщ','Баса','Гриб','Свкл','Котл.кур','Бл.твор','Овощ','крылья','капуста','Рыба','Олимп')
    ))""").fetchall()
print(f'REX copy flagged: {len(rows)}')
for r in rows:
    print(f'  {r[0]} {r[1]} {r[2]}: {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}]')
con.close()
