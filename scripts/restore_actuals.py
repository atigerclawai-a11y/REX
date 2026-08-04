#!/usr/bin/env python3
"""Restore day_T_actual (81/55) + day_W_actual (73/95) from bak_pre_apply_0804
(the last verified-correct state), preserving all other columns.
Also restore day_M_actual? — bak shows 106/58 which matches current, leave it."""
import sqlite3

BAK = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db.bak_pre_apply_0804'
CUR = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'

con_b = sqlite3.connect(BAK)
con_c = sqlite3.connect(CUR)

# copy day_T_actual + day_W_actual from backup
rows = con_b.execute("SELECT client_id, day_T_actual, day_W_actual FROM clients WHERE active=1").fetchall()
fixed_t = fixed_w = 0
for cid, t, w in rows:
    cur_t = con_c.execute("SELECT day_T_actual FROM clients WHERE client_id=?", (cid,)).fetchone()[0]
    cur_w = con_c.execute("SELECT day_W_actual FROM clients WHERE client_id=?", (cid,)).fetchone()[0]
    if cur_t != t:
        con_c.execute("UPDATE clients SET day_T_actual=? WHERE client_id=?", (t, cid))
        fixed_t += 1
    if cur_w != w:
        con_c.execute("UPDATE clients SET day_W_actual=? WHERE client_id=?", (w, cid))
        fixed_w += 1
con_c.commit()

s1t = con_c.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_T_actual=1").fetchone()[0]
s2t = con_c.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_T_actual=2").fetchone()[0]
s1w = con_c.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_W_actual=1").fetchone()[0]
s2w = con_c.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_W_actual=2").fetchone()[0]
print(f'fixed: day_T {fixed_t} clients, day_W {fixed_w} clients')
print(f'day_T_actual now: {s1t}/{s2t} (target 81/55)')
print(f'day_W_actual now: {s1w}/{s2w} (target 73/95)')
con_b.close()
con_c.close()
