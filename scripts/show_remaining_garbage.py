#!/usr/bin/env python3
"""Show remaining non-canonical cells after history canonicalization."""
import sqlite3

BAD = ('FF', 'MP', 'S', 'Б', 'Вин', 'Гр', 'Кур', 'Горох', 'Ол', 'Весна', '3.Б',
       'Вар.Кар', 'Борщ', 'Баса', 'Гриб', 'Свкл', 'Котл.кур', 'Бл.твор', 'Овощ',
       'крылья', 'капуста', 'Рыба', 'Олимп')
con = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
rows = con.execute("""SELECT client_name, menu_date, day_code, shift, salad, soup, main, side, source_sheet
    FROM client_menus WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07'
    AND (salad IN ('FF','MP','S','Б','Вин','Гр','Кур','Горох','Ол','Весна','3.Б','Вар.Кар','Борщ','Баса','Гриб','Свкл','Котл.кур','Бл.твор','Овощ','крылья','капуста','Рыба','Олимп')
      OR soup IN ('FF','MP','S','Б','Вин','Гр','Кур','Горох','Ол','Весна','3.Б','Вар.Кар','Борщ','Баса','Гриб','Свкл','Котл.кур','Бл.твор','Овощ','крылья','капуста','Рыба','Олимп')
      OR main IN ('FF','MP','S','Б','Вин','Гр','Кур','Горох','Ол','Весна','3.Б','Вар.Кар','Борщ','Баса','Гриб','Свкл','Котл.кур','Бл.твор','Овощ','крылья','капуста','Рыба','Олимп')
      OR side IN ('FF','MP','S','Б','Вин','Гр','Кур','Горох','Ол','Весна','3.Б','Вар.Кар','Борщ','Баса','Гриб','Свкл','Котл.кур','Бл.твор','Овощ','крылья','капуста','Рыба','Олимп'))
    ORDER BY menu_date, client_name""").fetchall()
for r in rows:
    print(f'{r[0]} {r[1]} {r[2]} S{r[3]}: {r[4]}|{r[5]}|{r[6]}|{r[7]} [{r[8]}]')
con.close()
