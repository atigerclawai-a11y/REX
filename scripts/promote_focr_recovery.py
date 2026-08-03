#!/usr/bin/env python3
"""Promote focr-recovered extractions to client_menus (both DBs).

Watches blank_parse/*/extraction.json (where focr_recover_quarantine.py writes)
and applies new/changed picks as ocr_scan rows. Run by cron every 15 min.
Tracks progress by (doc, extraction-mtime) in a marker file so re-runs pick
up only NEW work. Handles day_code/shift NOT NULL columns (schema 2026-08-02).
"""
import json, re, sqlite3, sys
from pathlib import Path

REX = Path.home() / 'Desktop/REX'
BP = REX / 'blank_parse'
MARKER = REX / '.focr_promoted.json'
DBS = ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
       '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']
AUTH_DB = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
WEEK_DATES = {  # week number → Monday date (extend per food week)
    27: '2026-07-06', 28: '2026-07-13', 29: '2026-07-20', 30: '2026-07-27', 31: '2026-08-03',
}
DAYCODE = {'M': 'M', 'T': 'T', 'W': 'W', 'TH': 'TH', 'F': 'F'}
CAT = {'САЛАТЫ': 'salad', 'СУПЫ': 'soup', 'ГЛАВНОЕ': 'main', 'ГАРНИР': 'side'}

def week_for(docname):
    """Detect the food week from the doc's MinerU md footer ("Week #: N" / "Week N").
    Fallback: receive-date +7 rule (emailed forms) or week 31 default."""
    md = REX / 'menu_ocr_full' / docname / 'ocr' / f'{docname}.md'
    if md.exists():
        try:
            t = md.read_text()
            import re as _re
            m = _re.search(r'Week\s*#?\s*:\s*(\d+)', t)
            if m:
                return int(m.group(1))
            m = _re.search(r'Week\s+(\d+)', t)
            if m:
                return int(m.group(1))
        except Exception:
            pass
    # fallback: derive from receive date (filename ts) +7 for emailed forms
    m = re.search(r'doc\d{6}(\d{4})(\d{2})(\d{2})', docname)
    if m:
        from datetime import date, timedelta
        try:
            rcvd = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            food_monday = rcvd + timedelta(days=7 - rcvd.weekday())
            for wk, mon in WEEK_DATES.items():
                if food_monday.isoformat() == mon:
                    return wk
        except Exception:
            pass
    return 31  # safest default (current food week)

def week_map_for(docname):
    """Build {day: date} for the doc's detected week."""
    wk = week_for(docname)
    mon = WEEK_DATES.get(wk)
    if not mon:
        return None, wk
    from datetime import date, timedelta
    base = date.fromisoformat(mon)
    return {d: (base + timedelta(days=i)).isoformat()
            for i, d in enumerate(['M', 'T', 'W', 'TH', 'F'])}, wk

done = {}
if MARKER.exists():
    try:
        done = json.loads(MARKER.read_text()).get('promoted', {})
    except Exception:
        done = {}

def shift_for(c, cname, mdate):
    """Prefer the client's existing shift for that date; else look up from
    auth_tracker schedule; else '1' (never silently default to '2' — Blue Team
    2026-08-02). Returns ('1'|'2', source)."""
    r = c.execute("SELECT shift FROM client_menus WHERE client_name=? AND menu_date=? LIMIT 1",
                  (cname, mdate)).fetchone()
    if r:
        return r[0], 'existing'
    try:
        auth = sqlite3.connect(AUTH_DB)
        row = auth.execute("SELECT shift FROM clients WHERE name=? AND active=1", (cname,)).fetchone()
        auth.close()
        if row and row[0] in ('1', '2'):
            return row[0], 'auth'
    except Exception:
        pass
    return '1', 'default'

changed = []
for doc in sorted(BP.iterdir()):
    if not doc.is_dir():
        continue
    # primary extraction.json; cloud results ONLY if no primary exists
    # (Blue Team 2026-08-02: cloud hallucinates — never let it supersede by mtime)
    ex = doc / 'extraction.json'
    ex_cloud = doc / 'extraction_cloud.json'
    if not ex.exists() and not ex_cloud.exists():
        continue
    src = ex
    if ex_cloud.exists() and not ex.exists():
        src = ex_cloud
    mt = str(int(src.stat().st_mtime))
    if done.get(doc.name) == mt:
        continue  # already promoted this version
    try:
        d = json.loads(src.read_text())
    except Exception:
        continue
    if not isinstance(d, dict) or not d:
        done[doc.name] = mt
        continue
    applied = 0
    week, wknum = week_map_for(doc.name)
    if week is None:
        done[doc.name] = mt
        print(f'skip {doc.name}: unknown week {wknum}')
        continue
    for cname, entry in d.items():
        if 'UNMATCHED' in cname and not (entry or {}).get('cid'):
            continue
        # QR-FIRST identity (Kato subgoal 2026-08-02): if the form carried a
        # readable QR, the client identity is authoritative — no name matching.
        cid = (entry or {}).get('cid')
        resolved_name = cname
        if cid:
            auth = sqlite3.connect(AUTH_DB)
            row = auth.execute(
                "SELECT name FROM canonical_ids WHERE canonical_id=?",
                (f'{int(cid):04d}',)).fetchone()
            auth.close()
            if row:
                resolved_name = row[0]
        sel = entry.get('selections') or {}
        for day, cats in sel.items():
            mdate = week.get(day)
            if not mdate or not cats:
                continue
            vals = {CAT.get(k): (v[0] if isinstance(v, list) else v) for k, v in cats.items()}
            if not vals.get('main') and not vals.get('salad'):
                continue
            for db in DBS:
                c = sqlite3.connect(db)
                shift, shift_src = shift_for(c, resolved_name, mdate)
                try:
                    c.execute("""INSERT OR REPLACE INTO client_menus
                        (client_name, menu_date, day_code, shift, salad, soup, main, side, source_sheet)
                        VALUES (?,?,?,?,?,?,?,?,'ocr_scan')""",
                        (resolved_name, mdate, DAYCODE.get(day, day), shift,
                         vals.get('salad', ''), vals.get('soup', ''),
                         vals.get('main', ''), vals.get('side', '')))
                    c.commit()
                except sqlite3.IntegrityError as e:
                    pass
                c.close()
            applied += 1
    if applied:
        changed.append(f'{doc.name}: +{applied} rows')
    done[doc.name] = mt

if changed:
    MARKER.write_text(json.dumps({'promoted': done}, ensure_ascii=False))
    print('\n'.join(changed))
    print('focr promotions applied')
