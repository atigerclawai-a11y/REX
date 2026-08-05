#!/usr/bin/env python3
"""Re-apply Kravets Sima removal (sick today per WhatsApp) AFTER the restore."""
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
a = sqlite3.connect(AUTH)
c = a.execute("UPDATE clients SET day_T_actual=0 WHERE name='Kravets Sima'")
print(f'Kravets Sima: {c.rowcount} row — Tue=0 (sick)')
a.commit()
s1 = a.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_T_actual=1").fetchone()[0]
s2 = a.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_T_actual=2").fetchone()[0]
print(f'Tue now: {s1}/{s2} (expect 80/55 — Kravets out, Sepashvili in)')
a.close()

# remove her Tue plate from both DBs
for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    c = con.execute("DELETE FROM client_menus WHERE client_name='Kravets Sima' AND menu_date='2026-08-04'")
    print(f'{db.split("/")[-1]}: {c.rowcount} Tue plate removed')
    con.commit()
    con.close()
