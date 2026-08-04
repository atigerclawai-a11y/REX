#!/usr/bin/env python3
"""Fix the 3 Tue rows in the REX copy to match Documents (Б→Борщ красный, 3.Б→Борщ красный)."""
import sqlite3

FIX = {
    'Neginis Rivekka': ('Селедка', 'Борщ красный', 'Баса с помидорами', 'Пюре'),
    'Shkolnik Betya': ('Сало', 'Борщ красный', 'Гуляш', 'Картошка'),
    'Zabizhin Grigoriy': ('Сало', 'Борщ красный', 'Дорадо запеченая', 'Пюре'),
}

con = sqlite3.connect('/Users/mainsobhelper/Desktop/REX/goj_proprietary.db')
for name, (sal, sup, main_, side) in FIX.items():
    c = con.execute("""UPDATE client_menus SET salad=?, soup=?, main=?, side=?
        WHERE client_name=? AND menu_date='2026-08-04'""", (sal, sup, main_, side, name))
    print(f'REX {name}: {c.rowcount} row fixed')
con.commit()
con.close()
