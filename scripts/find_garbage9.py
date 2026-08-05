#!/usr/bin/env python3
"""Find the 9 garbage cells + the W_S2 salad-cell soup leak."""
import sqlite3

con = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
BAD = ('FF', 'MP', 'S', 'Б', 'Вин', 'Гр', 'Кур', 'Горох', 'Ол', 'Весна', '3.Б',
       'Вар.Кар', 'Борщ', 'Баса', 'Гриб', 'Свкл', 'Котл.кур', 'Бл.твор', 'Овощ', 'крылья')
rows = con.execute("""SELECT client_name, menu_date, day_code, shift, salad, soup, main, side, source_sheet
    FROM client_menus WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07'
    AND (salad IN ('FF','MP','S','Б','Вин','Гр','Кур','Горох','Ол','Весна','3.Б','Вар.Кар','Борщ','Баса','Гриб','Свкл','Котл.кур','Бл.твор','Овощ','крылья')
      OR soup IN ('FF','MP','S','Б','Вин','Гр','Кур','Горох','Ол','Весна','3.Б','Вар.Кар','Борщ','Баса','Гриб','Свкл','Котл.кур','Бл.твор','Овощ','крылья')
      OR main IN ('FF','MP','S','Б','Вин','Гр','Кур','Горох','Ол','Весна','3.Б','Вар.Кар','Борщ','Баса','Гриб','Свкл','Котл.кур','Бл.твор','Овощ','крылья')
      OR side IN ('FF','MP','S','Б','Вин','Гр','Кур','Горох','Ол','Весна','3.Б','Вар.Кар','Борщ','Баса','Гриб','Свкл','Котл.кур','Бл.твор','Овощ','крылья'))
    ORDER BY menu_date, client_name""").fetchall()
print(f'garbage rows: {len(rows)}')
for r in rows:
    print(f'  {r[0]} {r[1]} {r[2]} S{r[3]}: {r[4]}|{r[5]}|{r[6]}|{r[7]} [{r[8]}]')

# who has Борщ in salad cell (the W_S2 kitchen leak)?
print('\nБорщ-in-salad rows:')
for r in con.execute("""SELECT client_name, menu_date, day_code, shift, salad, soup, source_sheet
    FROM client_menus WHERE salad='Борщ' OR salad='Борщ зеленый' OR salad='Борщ красный'"""):
    print(f'  {r}')
con.close()
