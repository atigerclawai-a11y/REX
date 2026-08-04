#!/usr/bin/env python3
"""CC_carecenta_auth_sync.py — load Carecenta authorizations INTO ghs_schedule.db.

🚫 HARD RULE (Kato 2026-08-01): THIS NIGHTLY SYNC MUST NEVER TOUCH OCR.
No OCR engines (surya/focr/tesseract/mineru), no vision models, no menu/scan
processing, no cloud AI calls. It ONLY parses the Carecenta text export and
writes sqlite. If you need OCR, do it in a SEPARATE job — never here.

Kato HARD RULE (2026-08-01): HHAeXchange authorizations are NULL AND VOID.
Carecenta is the ONLY source of truth. This syncs the Carecenta export into
ghs_schedule.db's authorizations table so daily sheets + dashboards read
Carecenta data, never auth_tracker.db (HHA).

Matches Carecenta rows to ghs_schedule.db clients by Carecenta Client ID.
Run after every fresh Carecenta export. Cron-scheduled or manual.
"""
import json, re, sqlite3, sys
from datetime import date, datetime
from pathlib import Path

HOME = Path.home()
GHS_DB = HOME / "Desktop/REX/signin_lists/ghs_schedule.db"
CARECENTA_DIR = HOME / "goj/data/carecenta"
CARECENTA_JSON_DIR = HOME / "goj/data"


def find_export():
    if CARECENTA_DIR.exists():
        xls = sorted(CARECENTA_DIR.glob("carecenta_authorizations_*.xls"),
                     key=lambda p: p.stat().st_mtime, reverse=True)
        if xls:
            return xls[0], "xls"
    js = sorted(CARECENTA_JSON_DIR.glob("carecenta_authorizations_*.json"),
                key=lambda p: p.stat().st_mtime, reverse=True)
    if js:
        return js[0], "json"
    return None, None


def parse_d(ms):
    ms = (ms or "").strip()
    if not ms:
        return None
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(ms, fmt).date()
        except ValueError:
            continue
    return None


def load_rows(path, kind):
    rows = []
    if kind == "xls":
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 12:
                    continue
                name = parts[0].strip()
                cid = parts[2].strip()
                if not name or not re.match(r"^\d+$", cid):
                    continue
                rows.append(dict(
                    cid=cid, name=name, payer=parts[6].strip(), svc=parts[7].strip(),
                    dfrom=parse_d(parts[8]), dto=parse_d(parts[9]), auth=parts[10].strip(),
                ))
    else:
        with open(path) as f:
            data = json.load(f)
        for r in data.get("rows", []):
            if len(r) < 12:
                continue
            name = str(r[1]).strip()
            cid = str(r[3]).strip()
            if not name or not re.match(r"^\d+$", cid):
                continue
            rows.append(dict(
                cid=cid, name=name, payer=str(r[7]).strip(), svc=str(r[8]).strip(),
                dfrom=parse_d(str(r[9])), dto=parse_d(str(r[10])), auth=str(r[11]).strip(),
            ))
    return rows


def main():
    path, kind = find_export()
    if not path:
        print("🔴 No Carecenta authorization export found")
        sys.exit(1)
    rows = load_rows(path, kind)
    print(f"Loaded {len(rows)} Carecenta auth rows from {path.name}")

    if not GHS_DB.exists():
        print(f"🔴 ghs_schedule.db not found at {GHS_DB}")
        sys.exit(1)

    conn = sqlite3.connect(str(GHS_DB))
    cur = conn.cursor()

    # clients table: how is Carecenta ID stored? probe
    cols = [r[1] for r in cur.execute("PRAGMA table_info(clients)")]
    print(f"clients cols: {cols}")
    id_col = "carecenta_id" if "carecenta_id" in cols else None
    if id_col is None:
        # try common alternatives
        for cand in ("client_id", "id"):
            if cand in cols:
                id_col = cand
                break
    if id_col is None:
        print("🔴 cannot find client ID column")
        sys.exit(1)

    # build client_id → Carecenta ID map
    id_map = {}
    for r in cur.execute(f"SELECT id, {id_col} FROM clients"):
        cid = str(r[1]).strip() if r[1] is not None else ""
        if cid:
            id_map[cid] = r[0]

    print(f"clients in db: {len(id_map)}")

    # sync: delete old Carecenta-sourced auths, insert fresh
    cur.execute("DELETE FROM authorizations")
    today = date.today().isoformat()
    inserted = 0
    unmatched = 0
    for r in rows:
        client_db_id = id_map.get(r["cid"])
        if client_db_id is None:
            unmatched += 1
            continue
        status = "ACTIVE" if (r["dto"] and r["dto"] >= date.today()) else "EXPIRED"
        cur.execute(
            """INSERT INTO authorizations
               (client_id, payer, auth_number, service_start, service_end, status, synced_at)
               VALUES (?,?,?,?,?,?,datetime('now'))""",
            (client_db_id, r["payer"], r["auth"], r["dfrom"].isoformat() if r["dfrom"] else None,
             r["dto"].isoformat() if r["dto"] else None, status))
        inserted += 1

    conn.commit()
    conn.close()
    print(f"✅ Synced {inserted} Carecenta auths into ghs_schedule.db (unmatched clients: {unmatched})")
    print(f"   Source: {path.name} | {kind}")


if __name__ == "__main__":
    main()
