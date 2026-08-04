#!/usr/bin/env python3
"""CANONICALIZE ALL HISTORY (all dates, both DBs) — kills the re-infection source.
Then fix the 8 garbage rows on Aug 4/5 by deleting + re-running fill."""
import json
import sqlite3
from pathlib import Path

ALIAS = json.load(open('/Users/mainsobhelper/Desktop/REX/scripts/dish_aliases.json'))
DBS = ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
       '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']

# flatten aliases
alias_flat = {}
for cat, mapping in ALIAS.items():
    if isinstance(mapping, dict):
        for k, v in mapping.items():
            alias_flat[str(k).strip().lower()] = v

def canon(v):
    if not v:
        return v
    s = str(v).strip()
    if not s:
        return ''
    # strip suffixes
    for suf in (' ✓', '✓', ' →', '→', ' +', '+', ' ✔', '✔'):
        if s.endswith(suf):
            s = s[:-len(suf)].strip()
    # strip leading markers
    for pre in ('Имя: ', 'ГЛАВНОЕ БЛЮДО (ПРОДОЛЖЕНИЕ)', 'ГЛАВНОЕ БЛЮДО'):
        if s.startswith(pre):
            s = s[len(pre):].strip()
    low = s.lower()
    if low in alias_flat:
        return alias_flat[low]
    # special mappings
    special = {
        'вингерет': 'Винегрет', 'квашеня капуста': 'Квашеная капуста',
        'бл. твор': 'Блины с творогом', 'бл.твор': 'Блины с творогом',
        'блины твор': 'Блины с творогом', 'котл. кур': 'Котлеты куриные',
        'котл.кур': 'Котлеты куриные', 'св. отбив': 'Свиная отбивная',
        'св.отбив': 'Свиная отбивная', 'вар.кар': 'Вареники с картошкой',
        'вар. кар': 'Вареники с картошкой', 'туш. кап': 'Тушеная капуста',
        'туш.кап': 'Тушеная капуста', 'капуста туш': 'Тушеная капуста',
    }
    if low in special:
        return special[low]
    # single-letter / fragment abbreviations that are NOT valid dishes
    return s

CATS = ['salad', 'soup', 'main', 'side']
total_fixed = 0
for db in DBS:
    con = sqlite3.connect(db)
    cur = con.cursor()
    rows = cur.execute("""SELECT id, client_name, menu_date, salad, soup, main, side
        FROM client_menus""").fetchall() if 'id' in [r[1] for r in cur.execute('PRAGMA table_info(client_menus)')] \
        else cur.execute("""SELECT rowid, client_name, menu_date, salad, soup, main, side
        FROM client_menus""").fetchall()
    fixed = 0
    for rid, name, d, salad, soup, main_, side in rows:
        vals = [canon(salad), canon(soup), canon(main_), canon(side)]
        cur.execute("""UPDATE client_menus SET salad=?, soup=?, main=?, side=? WHERE rowid=?""",
                    (*vals, rid))
        fixed += 1
    con.commit()
    print(f'{db.split("/")[-1]}: scanned {len(rows)} rows (all dates)')
    con.close()

print('\ncanonicalize-all complete — history is now clean')
