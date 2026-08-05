#!/usr/bin/env python3
"""For each Thu house_standard client: check if they have ANY prior Thursday order
in history to use (their own most recent Thursday)."""
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
HOUSE = ['Aronchik Bronya', 'Buziashvili Galina', 'Chupikova Elvira', 'Dodik Sima',
         'Drabkin Marat', 'Elbert Milla', 'Epshtein Isaak', 'Feldman Klavdya',
         'Furman Vladimir', 'Hurlenia Leanid', 'Krivchenok Mina', 'Mazo Nina',
         'Safonov Anatoliy', 'Sekh Stefaniia', 'Shadkhan Bella', 'Shteyman Faina',
         'Zubkova Valya']

for name in HOUSE:
    # their most recent COMPLETE order on any Thursday (day_code TH)
    r = p.execute("""SELECT menu_date, salad, soup, main, side, source_sheet
        FROM client_menus WHERE client_name=? AND day_code='TH'
        AND main != '' AND main NOT LIKE '%заказ не размещен%'
        AND source_sheet NOT IN ('house_standard','no_order_flag')
        ORDER BY menu_date DESC LIMIT 1""", (name,)).fetchone()
    if r:
        print(f'{name}: TH {r[0]}: {r[1]}|{r[2]}|{r[3]}|{r[4]} [{r[5]}]')
    else:
        # any recent complete order
        r2 = p.execute("""SELECT menu_date, day_code, salad, soup, main, side, source_sheet
            FROM client_menus WHERE client_name=? AND main != ''
            AND main NOT LIKE '%заказ не размещен%'
            AND source_sheet NOT IN ('house_standard','no_order_flag')
            ORDER BY menu_date DESC LIMIT 1""", (name,)).fetchone()
        if r2:
            print(f'{name}: NO TH history, last order {r2[0]} {r2[1]}: {r2[2]}|{r2[3]}|{r2[4]}|{r2[5]} [{r2[6]}]')
        else:
            print(f'{name}: NO HISTORY AT ALL')
p.close()
