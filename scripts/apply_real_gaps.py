#!/usr/bin/env python3
"""Apply the 3 real attendance fixes:
1. Kormova Lyubov: reactivate (active=0→1), set Wed S2 (Carecenta truth)
2. Kravets Sima: remove from Tue (WhatsApp: sick today 08:36)
3. (Sepashvili already done)"""
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
a = sqlite3.connect(AUTH)

# 1. Kormova reactivate + Wednesday S2
c = a.execute("""UPDATE clients SET active=1, day_W_actual=2
    WHERE name='Kormova Lyubov'""")
print(f'Kormova Lyubov: {c.rowcount} row — active=1, Wed S2')

# 2. Kravets Sima: remove from Tuesday (day_T_actual=0)
c = a.execute("""UPDATE clients SET day_T_actual=0
    WHERE name='Kravets Sima'""")
print(f'Kravets Sima: {c.rowcount} row — Tue removed (sick)')
a.commit()
a.close()

# also remove their plates from the proprietary DBs
PROP = ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
        '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']
for db in PROP:
    con = sqlite3.connect(db)
    # Kormova needs a Wed plate (add her real order)
    n = con.execute("SELECT COUNT(*) FROM client_menus WHERE client_name='Kormova Lyubov' AND menu_date='2026-08-05'").fetchone()[0]
    if not n:
        # her TH plate pattern: Винегрет|Куриный суп|Поперечка|Пюре
        con.execute("""INSERT INTO client_menus (client_name, menu_date, day_code, shift,
            salad, soup, main, side, source_sheet)
            VALUES ('Kormova Lyubov', '2026-08-05', 'W', '2',
            'Винегрет', 'Куриный суп', 'Поперечка', 'Пюре', 'last_order_fallback')""")
        print(f'{db.split("/")[-1]} Kormova Wed plate added')
    # Kravets Sima: remove Tue plate
    c = con.execute("""DELETE FROM client_menus WHERE client_name='Kravets Sima' AND menu_date='2026-08-04'""")
    print(f'{db.split("/")[-1]} Kravets Sima: {c.rowcount} Tue plate removed')
    con.commit()
    con.close()
