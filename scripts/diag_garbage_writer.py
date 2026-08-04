#!/usr/bin/env python3
"""Trace who wrote garbage rows: check synced_at + find page_census."""
import sqlite3
import os

# find page_census / page_guard
for p in ['/Users/mainsobhelper/.hermes/profiles/work/scripts/page_census.py',
          '/Users/mainsobhelper/.hermes/profiles/work/scripts/page_guard.py',
          '/Users/mainsobhelper/Desktop/REX/scripts/page_guard.py',
          '/Users/mainsobhelper/Desktop/REX/page_guard.py']:
    print(f'{p}: {"EXISTS" if os.path.exists(p) else "missing"}')

# garbage rows with sync times
BAD = ('FF', 'MP', 'S', 'Б', 'Вин', 'Гр', 'Кур', 'Горох', 'Ол', 'Весна', '3.Б',
       'Вар.Кар', 'Борщ', 'Баса', 'Гриб', 'Свкл', 'Котл.кур', 'Бл.твор', 'Овощ', 'крылья')
con = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
print('\ngarbage rows (by synced_at):')
rows = con.execute("""SELECT client_name, menu_date, day_code, salad, soup, main, side,
    source_sheet, synced_at FROM client_menus
    WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07'
    AND (salad IN ('FF','MP','S','Б','Вин','Гр','Кур','Горох','Ол','Весна','3.Б','Вар.Кар','Борщ','Баса','Гриб','Свкл','Котл.кур','Бл.твор','Овощ','крылья')
      OR soup IN ('FF','MP','S','Б','Вин','Гр','Кур','Горох','Ол','Весна','3.Б','Вар.Кар','Борщ','Баса','Гриб','Свкл','Котл.кур','Бл.твор','Овощ','крылья')
      OR main IN ('FF','MP','S','Б','Вин','Гр','Кур','Горох','Ол','Весна','3.Б','Вар.Кар','Борщ','Баса','Гриб','Свкл','Котл.кур','Бл.твор','Овощ','крылья')
      OR side IN ('FF','MP','S','Б','Вин','Гр','Кур','Горох','Ол','Весна','3.Б','Вар.Кар','Борщ','Баса','Гриб','Свкл','Котл.кур','Бл.твор','Овощ','крылья'))
    ORDER BY synced_at DESC LIMIT 20""").fetchall()
for r in rows:
    print(f'  {r[0]} {r[1]} {r[2]}: {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}] synced={r[8]}')
con.close()
