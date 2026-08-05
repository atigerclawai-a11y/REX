#!/usr/bin/env python3
"""GOJ Wednesday blank menus SPLIT BY SHIFT (73 S1 / 96 S2).
Uses auth day_W_actual (same source as sheets). QR bottom-right, [ID] footer."""
import sys, sqlite3, json, difflib
sys.path.insert(0, '/Users/mainsobhelper/Documents/goj files/tmp')
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import build_personalized_menus as bpm

auth = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
# Roster = auth day_W_actual (matches sheets + Carecenta 73/96)
s1_roster = [r[0] for r in auth.execute("SELECT name FROM clients WHERE active=1 AND day_W_actual=1 ORDER BY name")]
s2_roster = [r[0] for r in auth.execute("SELECT name FROM clients WHERE active=1 AND day_W_actual=2 ORDER BY name")]
id_by_name = {}
for cid4, nm, aid in auth.execute("SELECT canonical_id, name, auth_id FROM canonical_ids"):
    id_by_name[nm.strip().lower()] = cid4
    if aid is not None:
        r = auth.execute("SELECT name FROM clients WHERE client_id=?", (aid,)).fetchone()
        if r and r[0].strip().lower() != nm.strip().lower():
            id_by_name[r[0].strip().lower()] = cid4
auth.close()

def _flip(name):
    parts = [p.strip() for p in name.split(',')]
    if len(parts) == 2:
        return f"{parts[0]} {parts[1]}".lower()
    return name.strip().lower()

def cid_for(name):
    for key in (name.strip().lower(), _flip(name)):
        if key in id_by_name:
            return id_by_name[key]
    best, br = None, 0.0
    for k, v in id_by_name.items():
        r = difflib.SequenceMatcher(None, name.strip().lower(), k).ratio()
        if r > br: best, br = v, r
    if br >= 0.9:
        return best
    last = name.strip().lower().split()[0] if name.strip() else ''
    best, br = None, 0.0
    for k, v in id_by_name.items():
        kl = k.split()[0] if k else ''
        r = difflib.SequenceMatcher(None, last, kl).ratio()
        if r > br: best, br = v, r
    return best if br >= 0.95 else None

WEEK = '2026-08-10'

def build(names, out, title):
    c = canvas.Canvas(out, pagesize=letter)
    c.setTitle(title)
    c.setAuthor("Garden of Joy")
    missing = []
    for nm in names:
        cid = cid_for(nm)
        if cid is None:
            missing.append(nm)
            continue
        bpm.render_one_client(c, nm, cid, WEEK)
    c.save()
    print(f"Wrote {out}: {len(names)} clients ({len(names)*2}pp), missing IDs: {len(missing)}")
    if missing:
        print(f"  ❌ NO ID: {missing}")

OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'
build(s1_roster, f"{OUT}/Menus_Wed_Aug05_S1_LIVE.pdf", "GoJ Wed Aug 5 SHIFT 1 menus (73)")
build(s2_roster, f"{OUT}/Menus_Wed_Aug05_S2_LIVE.pdf", "GoJ Wed Aug 5 SHIFT 2 menus (96)")
