#!/usr/bin/env python3
"""
CC_ghs_canonical_db.py — Build the canonical GHS database for the Sept 2026
Carecenta migration. Consolidates 4 source DBs into ONE ghs_canonical.db:
  - carecenta_history.db   (clients, attendance, billing, invoices, AR, auths)
  - auth_tracker.db        (plans, shifts, transport, member IDs, insurance)
  - goj_proprietary.db     (client menus, driver routes, schedules)
  - ghs_schedule.db        (weekly schedules)

Usage:
  python3 CC_ghs_canonical_db.py [--build] [--refresh] [--summary]

Design principles:
  - READ-ONLY on sources (mode=ro URIs); only ghs_canonical.db is written.
  - Idempotent: --build creates schema, --refresh reloads data (upsert).
  - Name matching across DBs uses the _cnorm alpha-token key (order-insensitive
    'last first' normalization) — the GHS standard (see ghs-platform-build pitfall 17).
  - PHI stays local: this DB is created under ~/Desktop/REX/carecenta_history/ and
    is excluded from cloud backups (same as carecenta_history).

Output:
  ~/Desktop/REX/carecenta_history/ghs_canonical.db
"""

import argparse
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

OUT_DIR = Path.home() / "Desktop" / "REX" / "carecenta_history"
CANON = OUT_DIR / "ghs_canonical.db"

SRC = {
    "history": Path.home() / "Desktop" / "REX" / "carecenta_history" / "carecenta_history.db",
    "auth": Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db",
    "prop": Path.home() / "Documents" / "goj files" / "proprietary" / "goj_proprietary.db",
    "sched": Path.home() / "Desktop" / "REX" / "signin_lists" / "ghs_schedule.db",
}
# TCC fallback for auth_tracker (Documents/ is TCC-blocked from some contexts)
AUTH_FALLBACK = Path.home() / "goj_corpus" / "goj files" / "dashboard" / "auth_tracker.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    canonical_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    carecenta_id        INTEGER UNIQUE,
    name                TEXT,
    name_key            TEXT,
    dob                 TEXT,
    phone               TEXT,
    address             TEXT,
    coordinator         TEXT,
    status              TEXT,
    member_id           TEXT,
    plan_canonical      TEXT,
    shift               INTEGER,
    transportation      TEXT,
    insurance           TEXT,
    scraped_at          TEXT
);
CREATE TABLE IF NOT EXISTS authorizations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    carecenta_id    INTEGER,
    client_name     TEXT,
    name_key        TEXT,
    from_date       TEXT,
    to_date         TEXT,
    payer           TEXT,
    service         TEXT,
    bill_code       TEXT,
    auth_number     TEXT,
    status          TEXT,
    days_per_week   INTEGER,
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS attendance (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    carecenta_id INTEGER,
    client_name TEXT,
    name_key    TEXT,
    payer       TEXT,
    route       TEXT,
    visit_date  TEXT,
    scheduled   TEXT,
    checkin     TEXT,
    pickup      TEXT,
    arrival     TEXT
);
CREATE TABLE IF NOT EXISTS billing (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    carecenta_id INTEGER,
    client_name TEXT,
    name_key    TEXT,
    provider    TEXT,
    insurance_id TEXT,
    inv_date    TEXT,
    invoice_id  TEXT,
    dos         TEXT,
    bill_code   TEXT,
    units       INTEGER,
    billed      REAL,
    allowed     REAL,
    paid        REAL,
    adjusted    REAL
);
CREATE TABLE IF NOT EXISTS open_invoices (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    carecenta_id INTEGER,
    invoice_id  TEXT,
    invoice_date TEXT,
    due_date    TEXT,
    status      TEXT,
    balance     REAL,
    scraped_at  TEXT,
    deleted     INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ar_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    carecenta_id INTEGER,
    svc_date    TEXT,
    payer_code  TEXT,
    bill_code   TEXT,
    rate        REAL,
    units       INTEGER,
    billed      REAL,
    paid        REAL,
    balance     REAL,
    scraped_at  TEXT,
    deleted     INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS schedules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    carecenta_id INTEGER,
    client_name TEXT,
    name_key    TEXT,
    plan        TEXT,
    day_code    TEXT,
    shift       INTEGER
);
CREATE TABLE IF NOT EXISTS menus (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    client_name TEXT,
    name_key    TEXT,
    menu_date   TEXT,
    day_code    TEXT,
    shift       INTEGER,
    salad       TEXT,
    soup        TEXT,
    main        TEXT,
    side        TEXT,
    source_sheet TEXT
);
CREATE INDEX IF NOT EXISTS idx_clients_key ON clients(name_key);
CREATE INDEX IF NOT EXISTS idx_attendance_key ON attendance(name_key);
CREATE INDEX IF NOT EXISTS idx_billing_key ON billing(name_key);
CREATE INDEX IF NOT EXISTS idx_ar_cid ON ar_items(carecenta_id);
"""


def _cnorm(name: str) -> str:
    """Order-insensitive alpha-token key: 'Ludmila 206578' → 'ludmila'."""
    if not name:
        return ""
    tokens = sorted(re.findall(r"[a-z]+", name.lower()))
    return " ".join(tokens)


def _num(v):
    """Parse money/units text → float ('' → 0.0)."""
    if v is None or v == "":
        return 0.0
    s = str(v).replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def _open_src(path, fallback=None):
    for p in (path, fallback):
        if p and p.exists():
            return sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    print(f"  ⚠ source missing: {path}")
    return None


def load_clients(con, src):
    hist = _open_src(SRC["history"])
    auth = _open_src(SRC["auth"], AUTH_FALLBACK)
    rows = 0
    if hist:
        for cid, name, dob, phone, addr, coord, scraped, status, _err in hist.execute(
            "SELECT carecenta_id,name,dob,phone,address,coordinator,scraped_at,status,error FROM clients"
        ):
            plan = shift = transp = member = ins = None
            if auth:
                try:
                    r = auth.execute(
                        "SELECT plan_canonical, shift, transportation, member_id, insurance FROM clients WHERE name=? COLLATE NOCASE",
                        (name,),
                    ).fetchone()
                    if r:
                        plan, shift, transp, member, ins = r
                except sqlite3.Error:
                    pass
            con.execute(
                "INSERT OR REPLACE INTO clients(carecenta_id,name,name_key,dob,phone,address,coordinator,status,member_id,plan_canonical,shift,transportation,insurance,scraped_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (cid, name, _cnorm(name), dob, phone, addr, coord, status, member, plan, shift, transp, ins, scraped),
            )
            rows += 1
    con.commit()
    return rows


def load_authorizations(con):
    hist = _open_src(SRC["history"])
    auth = _open_src(SRC["auth"], AUTH_FALLBACK)
    rows = 0
    if hist:
        for cid, frm, to, payer, svc, code, authnum, contract, raw in hist.execute(
            "SELECT carecenta_id,from_date,to_date,payer,service,bill_code,auth_number,contract_client_id,raw FROM authorizations"
        ):
            cname = None
            if auth:
                r = auth.execute("SELECT client_name FROM authorization WHERE member_id=? COLLATE NOCASE LIMIT 1", (contract,)).fetchone() if contract else None
                if r:
                    cname = r[0]
            con.execute(
                "INSERT INTO authorizations(carecenta_id,client_name,name_key,from_date,to_date,payer,service,bill_code,auth_number,status) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (cid, cname, _cnorm(cname or ""), frm, to, payer, svc, code, authnum, "ACTIVE" if to and to >= datetime.now().strftime("%Y-%m-%d") else "EXPIRED"),
            )
            rows += 1
    con.commit()
    return rows


def load_attendance(con):
    hist = _open_src(SRC["history"])
    rows = 0
    if hist:
        for cid, cname, payer, route, vdate, sched, checkin, pickup, arrival in hist.execute(
            "SELECT carecenta_id,client_name,payer,route,visit_date,scheduled,checkin,pickup,arrival FROM attendance"
        ):
            con.execute(
                "INSERT INTO attendance(carecenta_id,client_name,name_key,payer,route,visit_date,scheduled,checkin,pickup,arrival) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (cid, cname, _cnorm(cname), payer, route, vdate, sched, checkin, pickup, arrival),
            )
            rows += 1
    con.commit()
    return rows


def load_billing(con):
    hist = _open_src(SRC["history"])
    rows = 0
    if hist:
        for cid, cname, prov, insid, invdate, invid, dos, code, units, billed, allowed, paid, adj in hist.execute(
            "SELECT carecenta_id,client_name,provider,insurance_id,inv_date,invoice_id,dos,bill_code,units,billed,allowed,paid,adjusted FROM billing"
        ):
            con.execute(
                "INSERT INTO billing(carecenta_id,client_name,name_key,provider,insurance_id,inv_date,invoice_id,dos,bill_code,units,billed,allowed,paid,adjusted) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (cid, cname, _cnorm(cname), prov, insid, invdate, invid, dos, code, _num(units), _num(billed), _num(allowed), _num(paid), _num(adj)),
            )
            rows += 1
    con.commit()
    return rows


def load_open_invoices(con):
    hist = _open_src(SRC["history"])
    rows = 0
    if hist:
        for cid, invid, invdate, due, status, bal, scraped, deleted in hist.execute(
            "SELECT carecenta_id,invoice_id,invoice_date,due_date,status,balance,scraped_at,deleted FROM open_invoices"
        ):
            con.execute(
                "INSERT INTO open_invoices(carecenta_id,invoice_id,invoice_date,due_date,status,balance,scraped_at,deleted) VALUES(?,?,?,?,?,?,?,?)",
                (cid, invid, invdate, due, status, _num(bal), scraped, deleted or 0),
            )
            rows += 1
    con.commit()
    return rows


def load_ar(con):
    hist = _open_src(SRC["history"])
    rows = 0
    if hist:
        for cid, svcdate, payer, code, rate, units, billed, paid, bal, scraped, deleted in hist.execute(
            "SELECT carecenta_id,svc_date,payer_code,bill_code,rate,units,billed,paid,balance,scraped_at,deleted FROM open_ar_items"
        ):
            con.execute(
                "INSERT INTO ar_items(carecenta_id,svc_date,payer_code,bill_code,rate,units,billed,paid,balance,scraped_at,deleted) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (cid, svcdate, payer, code, _num(rate), _num(units), _num(billed), _num(paid), _num(bal), scraped, deleted or 0),
            )
            rows += 1
    con.commit()
    return rows


def load_schedules(con):
    for dbname in ("sched", "prop"):
        src = _open_src(SRC[dbname])
        if not src:
            continue
        try:
            cols = [r[1] for r in src.execute("PRAGMA table_info(client_schedule)")]
            if "day_code" not in cols:
                continue
            for row in src.execute("SELECT * FROM client_schedule"):
                d = dict(zip(cols, row))
                con.execute(
                    "INSERT INTO schedules(carecenta_id,client_name,name_key,plan,day_code,shift) VALUES(?,?,?,?,?,?)",
                    (d.get("client_id"), d.get("client_name"), _cnorm(d.get("client_name", "")), d.get("plan"), d.get("day_code"), d.get("shift")),
                )
        except sqlite3.Error:
            pass
    con.commit()


def load_menus(con):
    src = _open_src(SRC["prop"])
    rows = 0
    if src:
        try:
            cols = [r[1] for r in src.execute("PRAGMA table_info(client_menus)")]
            for row in src.execute("SELECT * FROM client_menus"):
                d = dict(zip(cols, row))
                con.execute(
                    "INSERT INTO menus(client_name,name_key,menu_date,day_code,shift,salad,soup,main,side,source_sheet) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (d.get("client_name"), _cnorm(d.get("client_name", "")), d.get("menu_date"), d.get("day_code"), d.get("shift"), d.get("salad"), d.get("soup"), d.get("main"), d.get("side"), d.get("source_sheet")),
                )
                rows += 1
        except sqlite3.Error as e:
            print(f"  ⚠ menus: {e}")
    con.commit()
    return rows


def summary(con):
    print("\n═══ ghs_canonical.db — SUMMARY ═══")
    for t in ("clients", "authorizations", "attendance", "billing", "open_invoices", "ar_items", "schedules", "menus"):
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:16} {n:>8,}")
    billed = con.execute("SELECT SUM(billed), SUM(paid), SUM(billed-paid) FROM billing").fetchone()
    print(f"\n  Billed: ${billed[0]:,.0f} | Paid: ${billed[1]:,.0f} | Open: ${billed[2]:,.0f}" if billed[0] else "  (no billing rows)")
    ar = con.execute("SELECT SUM(balance) FROM ar_items WHERE deleted=0").fetchone()
    print(f"  AR balance (open): ${ar[0]:,.0f}" if ar[0] else "  (no AR rows)")


def main():
    ap = argparse.ArgumentParser(description="Build canonical GHS DB for Sept 2026 migration")
    ap.add_argument("--build", action="store_true", help="create schema")
    ap.add_argument("--refresh", action="store_true", help="reload data from sources")
    ap.add_argument("--summary", action="store_true", help="print counts")
    args = ap.parse_args()

    CANON.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(CANON)

    if args.build or not CANON.exists():
        print("Building schema...")
        con.executescript(SCHEMA)
        con.commit()

    if args.refresh or args.build:
        for t in ("clients", "authorizations", "attendance", "billing", "open_invoices", "ar_items", "schedules", "menus"):
            con.execute(f"DELETE FROM {t}")
        con.commit()
        print("Loading clients..."); n = load_clients(con, SRC); print(f"  {n}")
        print("Loading authorizations..."); n = load_authorizations(con); print(f"  {n}")
        print("Loading attendance..."); n = load_attendance(con); print(f"  {n}")
        print("Loading billing..."); n = load_billing(con); print(f"  {n}")
        print("Loading open_invoices..."); n = load_open_invoices(con); print(f"  {n}")
        print("Loading AR..."); n = load_ar(con); print(f"  {n}")
        print("Loading schedules..."); load_schedules(con)
        print("Loading menus..."); n = load_menus(con); print(f"  {n}")

    summary(con)
    con.close()
    print(f"\n✅ Canonical DB: {CANON}")


if __name__ == "__main__":
    main()
